from io import BytesIO
from unittest.mock import patch

from PIL import Image
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from account.form import UserProfileForm
from account.models import UserProfile
from account.token import user_tokenizer_generate
from ccstore.models import Category, Product
from payment.models import Order, OrderItem, Payment, RegisterAddress


User = get_user_model()
PASSWORD = "StrongPass123!"


def image_upload(name="profile.png", content_type="image/png"):
    stream = BytesIO()
    Image.new("RGB", (10, 10), "blue").save(stream, format="PNG")
    return SimpleUploadedFile(name, stream.getvalue(), content_type=content_type)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AccountFixtureTests(TestCase):
    def create_user(self, username="customer", email="customer@example.com", active=True):
        return User.objects.create_user(
            username=username,
            email=email,
            password=PASSWORD,
            is_active=active,
        )

    def create_address(self, user, **kwargs):
        defaults = {
            "user": user,
            "label": "Home",
            "fullname": "  Customer Name  ",
            "email": user.email,
            "address1": "  1 Test Street  ",
            "address2": "",
            "city": "  Lagos  ",
            "state": " Lagos ",
            "country": "Nigeria",
            "zipcode": "100001",
            "phone": " +234 800 000 0000 ",
        }
        defaults.update(kwargs)
        return RegisterAddress.objects.create(**defaults)

    def create_order_records(self, user):
        category, _ = Category.objects.get_or_create(name="Account tests", slug="account-tests")
        product, _ = Product.objects.get_or_create(
            slug="retained-product",
            defaults={
                "Category": category,
                "title": "Retained product",
                "price": "50.00",
                "image": "images/retained.jpg",
            },
        )
        order = Order.objects.create(
            user=user,
            fullname="Historical Customer",
            email=user.email,
            address1="Historical address",
            amount_paid="50.00",
        )
        item = OrderItem.objects.create(
            order=order,
            product=product,
            product_title=product.title,
            user=user,
            quantity=1,
            price="50.00",
        )
        payment = Payment.objects.create(
            order=order,
            user=user,
            amount_paid="50.00",
            email=user.email,
        )
        return order, item, payment


class ProfileTests(AccountFixtureTests):
    def test_profile_is_created_exactly_once(self):
        user = self.create_user()
        user.save()
        self.assertEqual(UserProfile.objects.filter(user=user).count(), 1)

    def test_duplicate_profile_is_rejected(self):
        user = self.create_user()
        with self.assertRaises(IntegrityError), transaction.atomic():
            UserProfile.objects.create(user=user)

    def test_missing_profile_is_repaired_by_dashboard(self):
        user = self.create_user()
        UserProfile.objects.filter(user=user).delete()
        self.client.force_login(user)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(UserProfile.objects.filter(user=user).exists())

    def test_user_deletion_removes_profile(self):
        user = self.create_user()
        profile_id = user.profile.id
        user.delete()
        self.assertFalse(UserProfile.objects.filter(pk=profile_id).exists())

    def test_profile_fallback_uses_existing_static_asset(self):
        user = self.create_user()
        self.client.force_login(user)
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "media/images/ccbeauty_logo.jpg")


class AddressTests(AccountFixtureTests):
    def setUp(self):
        self.user_a = self.create_user("address-a", "address-a@example.com")
        self.user_b = self.create_user("address-b", "address-b@example.com")

    def test_address_is_normalized_and_first_is_default(self):
        address = self.create_address(self.user_a)
        self.assertEqual(address.fullname, "Customer Name")
        self.assertEqual(address.address1, "1 Test Street")
        self.assertEqual(address.city, "Lagos")
        self.assertTrue(address.is_default)
        self.assertEqual(address.user, self.user_a)

    def test_only_one_default_address_per_user(self):
        first = self.create_address(self.user_a)
        second = self.create_address(self.user_a, label="Office", is_default=True)
        first.refresh_from_db()
        self.assertFalse(first.is_default)
        self.assertTrue(second.is_default)

    def test_database_rejects_two_defaults(self):
        first = self.create_address(self.user_a)
        second = self.create_address(self.user_a, label="Other", is_default=True)
        with self.assertRaises(IntegrityError), transaction.atomic():
            RegisterAddress.objects.filter(pk=first.pk).update(is_default=True)
        self.assertTrue(RegisterAddress.objects.get(pk=second.pk).is_default)

    def test_deleting_address_does_not_change_order_snapshot(self):
        address = self.create_address(self.user_a)
        order, _, _ = self.create_order_records(self.user_a)
        snapshot = order.address1
        address.delete()
        order.refresh_from_db()
        self.assertEqual(order.address1, snapshot)

    def test_required_address_fields_are_validated(self):
        self.client.force_login(self.user_a)
        response = self.client.post(
            reverse("address_create"),
            {
                "label": "Home",
                "fullname": " ",
                "email": self.user_a.email,
                "phone": " ",
                "address1": " ",
                "city": " ",
                "state": " ",
                "zipcode": "100001",
                "country": "Nigeria",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(RegisterAddress.objects.count(), 0)

    def test_user_cannot_edit_delete_or_default_another_users_address(self):
        other = self.create_address(self.user_b)
        self.client.force_login(self.user_a)
        self.assertEqual(self.client.get(reverse("address_edit", args=(other.id,))).status_code, 404)
        self.assertEqual(self.client.post(reverse("address_delete", args=(other.id,))).status_code, 404)
        self.assertEqual(self.client.post(reverse("address_set_default", args=(other.id,))).status_code, 404)


class RegistrationAndLoginTests(AccountFixtureTests):
    def registration_data(self, **overrides):
        values = {
            "first_name": "  New ",
            "last_name": " User ",
            "username": "NewCustomer",
            "email": "  NEW@Example.COM ",
            "password1": PASSWORD,
            "password2": PASSWORD,
        }
        values.update(overrides)
        return values

    def test_registration_creates_inactive_user_profile_and_hashed_password(self):
        response = self.client.post(reverse("register"), self.registration_data())
        self.assertRedirects(response, reverse("email_verification_sent"), fetch_redirect_response=False)
        user = User.objects.get(username="NewCustomer")
        self.assertFalse(user.is_active)
        self.assertEqual(user.email, "new@example.com")
        self.assertEqual(user.first_name, "New")
        self.assertTrue(user.check_password(PASSWORD))
        self.assertTrue(hasattr(user, "profile"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("http://testserver", mail.outbox[0].body)

    def test_case_insensitive_duplicate_email_is_rejected(self):
        self.create_user(email="duplicate@example.com")
        response = self.client.post(
            reverse("register"),
            self.registration_data(username="another", email="DUPLICATE@EXAMPLE.COM"),
        )
        self.assertContains(response, "already exists")
        self.assertEqual(User.objects.filter(email__iexact="duplicate@example.com").count(), 1)

    def test_database_enforces_case_insensitive_email_uniqueness(self):
        self.create_user(username="first", email="database@example.com")
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_user(username="second", email="DATABASE@EXAMPLE.COM")

    def test_duplicate_username_and_invalid_password_are_rejected(self):
        self.create_user(username="TakenName")
        response = self.client.post(
            reverse("register"),
            self.registration_data(username="takenname", password1="weak", password2="weak"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "username")
        self.assertContains(response, "password")

    @patch("account.views._send_verification_email", side_effect=OSError("mail down"))
    def test_email_failure_keeps_consistent_inactive_user_and_profile(self, send_mock):
        response = self.client.post(reverse("register"), self.registration_data())
        self.assertRedirects(response, reverse("email_verification_sent"), fetch_redirect_response=False)
        user = User.objects.get(username="NewCustomer")
        self.assertFalse(user.is_active)
        self.assertTrue(UserProfile.objects.filter(user=user).exists())

    def test_authenticate_by_username_or_case_insensitive_email(self):
        user = self.create_user(username="LoginName", email="Login@Example.com")
        request = RequestFactory().post(reverse("login"))
        self.assertEqual(authenticate(request, username="LoginName", password=PASSWORD), user)
        self.assertEqual(authenticate(request, username="LOGIN@EXAMPLE.COM", password=PASSWORD), user)

    def test_login_error_is_generic_and_external_next_is_ignored(self):
        self.create_user()
        response = self.client.post(
            reverse("login") + "?next=https://evil.example/",
            {"username": "unknown@example.com", "password": "wrong"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid username/email or password")


class VerificationAndResetTests(AccountFixtureTests):
    def verification_url(self, user, token=None, uid=None):
        uid = uid or urlsafe_base64_encode(force_bytes(user.pk))
        token = token or user_tokenizer_generate.make_token(user)
        return reverse("email_verification", kwargs={"uidb64": uid, "token": token})

    def test_valid_token_activates_user_and_reused_token_is_safe(self):
        user = self.create_user(active=False)
        response = self.client.get(self.verification_url(user))
        self.assertRedirects(response, reverse("manage_shipping_address"), fetch_redirect_response=False)
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        repeated = self.client.get(self.verification_url(user, token="reused"))
        self.assertRedirects(repeated, reverse("login"), fetch_redirect_response=False)

    def test_malformed_missing_and_invalid_verification_links_fail_safely(self):
        user = self.create_user(active=False)
        self.assertRedirects(
            self.client.get(self.verification_url(user, uid="not-base64")),
            reverse("email_verification_failed"),
            fetch_redirect_response=False,
        )
        missing_uid = urlsafe_base64_encode(force_bytes(999999))
        self.assertRedirects(
            self.client.get(self.verification_url(user, uid=missing_uid)),
            reverse("email_verification_failed"),
            fetch_redirect_response=False,
        )
        self.assertRedirects(
            self.client.get(self.verification_url(user, token="invalid-token")),
            reverse("email_verification_failed"),
            fetch_redirect_response=False,
        )

    def test_resend_response_does_not_enumerate_accounts(self):
        inactive = self.create_user(active=False)
        known = self.client.post(reverse("resend_verification"), {"email": inactive.email})
        unknown = self.client.post(reverse("resend_verification"), {"email": "unknown@example.com"})
        self.assertEqual(known.status_code, unknown.status_code)
        self.assertEqual(known.url, unknown.url)

    def test_password_reset_has_same_visible_response_for_known_and_unknown_email(self):
        user = self.create_user()
        known = self.client.post(reverse("password_reset"), {"email": user.email})
        known_count = len(mail.outbox)
        unknown = self.client.post(reverse("password_reset"), {"email": "unknown@example.com"})
        self.assertEqual(known.url, unknown.url)
        self.assertEqual(known.status_code, unknown.status_code)
        self.assertEqual(known_count, 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_password_reset_token_changes_password_and_cannot_be_reused(self):
        user = self.create_user()
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        initial = self.client.get(reverse("password_reset_confirm", args=(uid, token)))
        self.assertEqual(initial.status_code, 302)
        set_url = initial.url
        response = self.client.post(
            set_url,
            {"new_password1": "ChangedPass123!", "new_password2": "ChangedPass123!"},
        )
        self.assertRedirects(response, reverse("password_reset_complete"), fetch_redirect_response=False)
        user.refresh_from_db()
        self.assertTrue(user.check_password("ChangedPass123!"))
        self.assertContains(self.client.get(reverse("password_reset_confirm", args=(uid, token))), "not valid")


class ProfileEditDeletionHistoryLogoutTests(AccountFixtureTests):
    def setUp(self):
        self.user = self.create_user()
        self.other = self.create_user("other", "other@example.com")

    def test_profile_update_normalizes_and_enforces_uniqueness(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("profile_account"),
            {"update_user": "1", "first_name": "  Trimmed ", "last_name": " Name ", "username": "customer", "email": " CUSTOMER@EXAMPLE.COM "},
        )
        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Trimmed")
        self.assertEqual(self.user.email, "customer@example.com")
        duplicate = self.client.post(
            reverse("profile_account"),
            {"update_user": "1", "first_name": "A", "last_name": "B", "username": "customer", "email": "OTHER@EXAMPLE.COM"},
        )
        self.assertContains(duplicate, "already exists")

    def test_valid_image_is_accepted_and_invalid_images_are_rejected(self):
        valid = UserProfileForm(files={"profile_picture": image_upload()}, instance=self.user.profile)
        self.assertTrue(valid.is_valid(), valid.errors)
        invalid = UserProfileForm(files={"profile_picture": SimpleUploadedFile("bad.jpg", b"not-image", content_type="image/jpeg")}, instance=self.user.profile)
        self.assertFalse(invalid.is_valid())
        oversized = UserProfileForm(files={"profile_picture": SimpleUploadedFile("huge.png", b"x" * (5 * 1024 * 1024 + 1), content_type="image/png")}, instance=self.user.profile)
        self.assertFalse(oversized.is_valid())

    def test_account_deletion_requires_post_and_correct_password(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("delete_profile")).status_code, 405)
        wrong = self.client.post(reverse("delete_profile"), {"password": "wrong"})
        self.assertEqual(wrong.status_code, 200)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_account_deletion_preserves_business_records(self):
        address = self.create_address(self.user)
        order, item, payment = self.create_order_records(self.user)
        profile_id = self.user.profile.id
        user_id = self.user.id
        self.client.force_login(self.user)
        response = self.client.post(reverse("delete_profile"), {"password": PASSWORD})
        self.assertRedirects(response, reverse("store"), fetch_redirect_response=False)
        self.assertFalse(User.objects.filter(pk=user_id).exists())
        self.assertFalse(UserProfile.objects.filter(pk=profile_id).exists())
        self.assertFalse(RegisterAddress.objects.filter(pk=address.pk).exists())
        order.refresh_from_db(); item.refresh_from_db(); payment.refresh_from_db()
        self.assertIsNone(order.user)
        self.assertIsNone(item.user)
        self.assertIsNone(payment.user)
        self.assertEqual(order.fullname, "Historical Customer")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_order_history_and_detail_are_owner_scoped(self):
        own_order, _, _ = self.create_order_records(self.user)
        other_order, _, _ = self.create_order_records(self.other)
        self.client.force_login(self.user)
        history = self.client.get(reverse("order_history"))
        self.assertContains(history, f"#{own_order.id}")
        self.assertNotContains(history, f"#{other_order.id}")
        detail = self.client.get(reverse("order_detail", args=(own_order.id,)))
        self.assertContains(detail, "Retained product")
        self.assertContains(detail, "50.00")
        self.assertEqual(self.client.get(reverse("order_detail", args=(other_order.id,))).status_code, 404)

    def test_empty_history_is_safe(self):
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse("order_history")), "no orders")

    def test_logout_requires_post_removes_auth_and_preserves_cart(self):
        self.client.force_login(self.user)
        session = self.client.session
        session["sess_key"] = {"1": {"price": "1.00", "product_qty": 1}}
        session.save()
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        response = self.client.post(reverse("logout"))
        self.assertRedirects(response, reverse("store"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertIn("sess_key", self.client.session)
        dashboard = self.client.force_login(self.user) or self.client.get(reverse("dashboard"))
        self.assertContains(dashboard, reverse("logout"))
