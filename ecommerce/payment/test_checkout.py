from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from ccstore.models import Category, Product
from payment.models import Order, OrderItem, Payment, RegisterAddress
from payment.services.checkout import (
    AddressOwnershipError,
    EmptyCartError,
    CheckoutResult,
    InvalidCartItemError,
    InvalidCheckoutTokenError,
    InvalidQuantityError,
    MissingAddressError,
    ProductUnavailableError,
    create_checkout_order,
)


class CheckoutFixtures(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user_a = User.objects.create_user(
            username="checkout-a",
            email="user-a@example.com",
            password="test-password-a",
        )
        cls.user_b = User.objects.create_user(
            username="checkout-b",
            email="user-b@example.com",
            password="test-password-b",
        )
        cls.address_a = RegisterAddress.objects.create(
            user=cls.user_a,
            fullname="Customer A",
            email="shipping-a@example.com",
            address1="1 Trusted Street",
            address2="Suite A",
            city="Lagos",
            state="Lagos",
            country="Nigeria",
            zipcode="100001",
            phone="08000000001",
        )
        cls.address_b = RegisterAddress.objects.create(
            user=cls.user_b,
            fullname="Customer B",
            email="shipping-b@example.com",
            address1="2 Trusted Street",
            address2="Suite B",
            city="Abuja",
            state="FCT",
            country="Nigeria",
            zipcode="900001",
            phone="08000000002",
        )
        cls.category = Category.objects.create(
            name="Checkout products",
            slug="checkout-products",
        )
        cls.product = Product.objects.create(
            Category=cls.category,
            title="Current price product",
            price=Decimal("125.50"),
            slug="current-price-product",
            image="images/current-price-product.jpg",
        )
        cls.second_product = Product.objects.create(
            Category=cls.category,
            title="Second product",
            price=Decimal("20.00"),
            slug="second-product",
            image="images/second-product.jpg",
        )

    def token(self, character="a"):
        return character * 43

    def cart(self, *, product=None, quantity=2, stored_price="0.01"):
        product = product or self.product
        return {
            str(product.id): {
                "price": stored_price,
                "product_qty": quantity,
            }
        }

    def create_checkout(self, **kwargs):
        defaults = {
            "user": self.user_a,
            "cart": self.cart(),
            "shipping_address": self.address_a,
            "idempotency_key": self.token(),
        }
        defaults.update(kwargs)
        return create_checkout_order(**defaults)


class CheckoutServiceTests(CheckoutFixtures):
    def test_empty_cart_is_rejected(self):
        with self.assertRaises(EmptyCartError):
            self.create_checkout(cart={})
        self.assertEqual(Order.objects.count(), 0)

    def test_invalid_product_id_is_rejected(self):
        with self.assertRaises(InvalidCartItemError):
            self.create_checkout(cart={"not-an-id": {"product_qty": 1}})

    def test_deleted_or_stale_product_is_rejected(self):
        stale_id = self.second_product.id
        self.second_product.delete()

        with self.assertRaises(ProductUnavailableError):
            self.create_checkout(
                cart={str(stale_id): {"price": "20.00", "product_qty": 1}}
            )

    def test_zero_quantity_is_rejected(self):
        with self.assertRaises(InvalidQuantityError):
            self.create_checkout(cart=self.cart(quantity=0))

    def test_negative_quantity_is_rejected(self):
        with self.assertRaises(InvalidQuantityError):
            self.create_checkout(cart=self.cart(quantity=-1))

    def test_non_integer_quantity_is_rejected(self):
        with self.assertRaises(InvalidQuantityError):
            self.create_checkout(cart=self.cart(quantity="1.5"))

    def test_excessive_quantity_is_rejected(self):
        with self.assertRaises(InvalidQuantityError):
            self.create_checkout(cart=self.cart(quantity=100))

    def test_current_database_price_overrides_stale_session_price(self):
        result = self.create_checkout(cart=self.cart(quantity=2, stored_price="1.00"))

        self.assertEqual(result.order.amount_paid, Decimal("251.00"))
        item = result.order.orderitem_set.get()
        self.assertEqual(item.price, Decimal("125.50"))

    def test_exact_snapshots_order_and_payment_are_created(self):
        cart = self.cart(quantity=2)
        cart[str(self.second_product.id)] = {
            "price": "9999.99",
            "product_qty": 3,
        }

        result = self.create_checkout(cart=cart)

        self.assertTrue(result.created)
        self.assertEqual(result.order.status, Order.Status.PENDING_PAYMENT)
        self.assertEqual(result.order.amount_paid, Decimal("311.00"))
        self.assertEqual(result.order.fullname, self.address_a.fullname)
        self.assertIn(self.address_a.address1, result.order.address1)
        self.assertEqual(result.payment.order, result.order)
        self.assertEqual(result.payment.amount_paid, result.order.amount_paid)
        self.assertEqual(result.payment.status, Payment.Status.INITIALIZED)
        snapshots = set(
            result.order.orderitem_set.values_list(
                "product_title", "price", "quantity"
            )
        )
        self.assertEqual(
            snapshots,
            {
                ("Current price product", Decimal("125.50"), 2),
                ("Second product", Decimal("20.00"), 3),
            },
        )

    def test_order_item_failure_rolls_back_everything(self):
        with patch(
            "payment.services.checkout.OrderItem.objects.bulk_create",
            side_effect=RuntimeError("simulated item failure"),
        ):
            with self.assertRaises(RuntimeError):
                self.create_checkout()

        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)
        self.assertEqual(Payment.objects.count(), 0)

    def test_payment_failure_rolls_back_order_and_items(self):
        with patch(
            "payment.services.checkout.Payment.objects.create",
            side_effect=RuntimeError("simulated payment failure"),
        ):
            with self.assertRaises(RuntimeError):
                self.create_checkout()

        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)
        self.assertEqual(Payment.objects.count(), 0)

    def test_missing_address_is_rejected(self):
        with self.assertRaises(MissingAddressError):
            self.create_checkout(shipping_address=None)

    def test_address_from_another_user_is_rejected(self):
        with self.assertRaises(AddressOwnershipError):
            self.create_checkout(shipping_address=self.address_b)


class CheckoutIdempotencyTests(CheckoutFixtures):
    def test_same_user_and_token_create_only_one_checkout(self):
        first = self.create_checkout()
        second = self.create_checkout(cart={})

        self.assertTrue(first.created)
        self.assertFalse(second.created)
        self.assertEqual(second.order, first.order)
        self.assertEqual(second.payment, first.payment)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Payment.objects.count(), 1)

    def test_different_tokens_create_separate_orders(self):
        first = self.create_checkout(idempotency_key=self.token("a"))
        second = self.create_checkout(idempotency_key=self.token("b"))

        self.assertNotEqual(first.order, second.order)
        self.assertEqual(Order.objects.count(), 2)

    def test_another_user_cannot_reuse_token(self):
        first = self.create_checkout()

        with self.assertRaises(InvalidCheckoutTokenError):
            self.create_checkout(
                user=self.user_b,
                shipping_address=self.address_b,
                idempotency_key=first.order.idempotency_key,
            )

        self.assertEqual(Order.objects.count(), 1)

    def test_database_unique_constraint_prevents_duplicate_token(self):
        first = self.create_checkout()

        with self.assertRaises(IntegrityError), transaction.atomic():
            Order.objects.create(
                user=self.user_a,
                fullname="Duplicate",
                email="duplicate@example.com",
                address1="Duplicate",
                amount_paid=Decimal("1.00"),
                idempotency_key=first.order.idempotency_key,
            )

    def test_service_recovers_the_winning_checkout_after_uniqueness_race(self):
        existing = self.create_checkout()
        duplicate_result = CheckoutResult(
            order=existing.order,
            payment=existing.payment,
            created=False,
        )

        with patch(
            "payment.services.checkout._existing_checkout",
            side_effect=(None, None, duplicate_result),
        ), patch(
            "payment.services.checkout.Order.objects.create",
            side_effect=IntegrityError("simulated uniqueness race"),
        ):
            recovered = self.create_checkout()

        self.assertEqual(recovered, duplicate_result)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Payment.objects.count(), 1)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class CheckoutViewTests(CheckoutFixtures):
    def setUp(self):
        self.client.force_login(self.user_a)

    def set_cart(self, cart=None):
        session = self.client.session
        session["sess_key"] = cart if cart is not None else self.cart()
        session.save()

    def set_token(self, token=None):
        token = token or self.token()
        session = self.client.session
        session["checkout_token"] = token
        session.save()
        return token

    def post_checkout(self, *, token=None, address=None, extra=None):
        data = {
            "checkout_token": token or self.token(),
            "address_id": (address or self.address_a).id,
        }
        data.update(extra or {})
        return self.client.post(reverse("orders"), data)

    def test_checkout_submission_rejects_get(self):
        response = self.client.get(reverse("orders"))
        self.assertEqual(response.status_code, 405)

    def test_checkout_submission_requires_authentication(self):
        self.client.logout()
        response = self.client.post(reverse("orders"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_checkout_page_generates_token_and_uses_current_total(self):
        self.set_cart(self.cart(stored_price="1.00"))
        response = self.client.get(reverse("checkout"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_cost"], Decimal("251.00"))
        self.assertTrue(response.context["checkout_token"])

    def test_checkout_page_redirects_when_saved_address_is_missing(self):
        RegisterAddress.objects.filter(user=self.user_a).delete()
        self.set_cart()

        response = self.client.get(reverse("checkout"))

        self.assertRedirects(
            response,
            reverse("manage_shipping_address"),
            fetch_redirect_response=False,
        )

    def test_empty_cart_gets_friendly_redirect(self):
        self.set_cart({})
        token = self.set_token()

        response = self.post_checkout(token=token)

        self.assertRedirects(response, reverse("cart_summary"), fetch_redirect_response=False)
        self.assertEqual(Order.objects.count(), 0)

    def test_valid_checkout_redirects_to_exact_payment(self):
        self.set_cart()
        token = self.set_token()

        response = self.post_checkout(token=token)

        payment = Payment.objects.get()
        self.assertRedirects(
            response,
            reverse("makepayment", args=(payment.ref,)),
            fetch_redirect_response=False,
        )
        self.assertEqual(payment.order.idempotency_key, token)

    def test_payment_page_refresh_creates_no_payment(self):
        self.set_cart()
        token = self.set_token()
        self.post_checkout(token=token)
        payment = Payment.objects.get()

        first = self.client.get(reverse("makepayment", args=(payment.ref,)))
        second = self.client.get(reverse("makepayment", args=(payment.ref,)))

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(Payment.objects.count(), 1)

    def test_reposting_same_token_returns_existing_checkout(self):
        self.set_cart()
        token = self.set_token()
        first = self.post_checkout(token=token)
        second = self.post_checkout(token=token)

        self.assertEqual(first.url, second.url)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Payment.objects.count(), 1)

    def test_reposting_created_token_does_not_depend_on_address_or_cart(self):
        self.set_cart()
        token = self.set_token()
        first = self.post_checkout(token=token)
        RegisterAddress.objects.filter(pk=self.address_a.pk).delete()
        self.set_cart({})

        second = self.post_checkout(token=token)

        self.assertEqual(first.url, second.url)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Payment.objects.count(), 1)

    def test_browser_total_and_address_text_are_ignored(self):
        self.set_cart(self.cart(stored_price="0.01"))
        token = self.set_token()

        self.post_checkout(
            token=token,
            extra={
                "total_cost": "0.01",
                "fullname": "Browser Attacker",
                "email": "attacker@example.com",
                "address1": "Untrusted browser address",
            },
        )

        order = Order.objects.get()
        self.assertEqual(order.amount_paid, Decimal("251.00"))
        self.assertEqual(order.fullname, self.address_a.fullname)
        self.assertNotIn("Untrusted", order.address1)

    def test_address_lookup_is_scoped_to_authenticated_user(self):
        self.set_cart()
        token = self.set_token()

        response = self.post_checkout(token=token, address=self.address_b)

        self.assertRedirects(
            response,
            reverse("manage_shipping_address"),
            fetch_redirect_response=False,
        )
        self.assertEqual(Order.objects.count(), 0)

    def test_user_can_open_only_their_own_payment_page(self):
        result_a = self.create_checkout()
        result_b = self.create_checkout(
            user=self.user_b,
            shipping_address=self.address_b,
            idempotency_key=self.token("b"),
        )

        own_response = self.client.get(
            reverse("makepayment", args=(result_a.payment.ref,))
        )
        other_response = self.client.get(
            reverse("makepayment", args=(result_b.payment.ref,))
        )

        self.assertEqual(own_response.status_code, 200)
        self.assertRedirects(
            other_response,
            reverse("checkout"),
            fetch_redirect_response=False,
        )

    def test_cart_is_not_cleared_before_verification(self):
        cart = self.cart()
        self.set_cart(cart)
        token = self.set_token()

        response = self.post_checkout(token=token)
        payment = Payment.objects.get()
        self.client.get(reverse("makepayment", args=(payment.ref,)))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session["sess_key"], cart)

    def test_checkout_sends_no_confirmation_email(self):
        self.set_cart()
        token = self.set_token()

        self.post_checkout(token=token)

        self.assertEqual(mail.outbox, [])

    def test_invalid_checkout_token_is_rejected(self):
        self.set_cart()
        self.set_token(self.token("a"))

        response = self.post_checkout(token=self.token("b"))

        self.assertRedirects(response, reverse("checkout"), fetch_redirect_response=False)
        self.assertEqual(Order.objects.count(), 0)

    def test_non_pending_order_is_not_payable(self):
        result = self.create_checkout()
        result.order.status = Order.Status.CANCELLED
        result.order.save(update_fields=("status",))

        response = self.client.get(
            reverse("makepayment", args=(result.payment.ref,))
        )

        self.assertRedirects(response, reverse("checkout"), fetch_redirect_response=False)

    def test_payment_amount_must_match_exact_order_total(self):
        result = self.create_checkout()
        result.payment.amount_paid = Decimal("1.00")
        result.payment.save(update_fields=("amount_paid",))

        response = self.client.get(
            reverse("makepayment", args=(result.payment.ref,))
        )

        self.assertRedirects(response, reverse("checkout"), fetch_redirect_response=False)
