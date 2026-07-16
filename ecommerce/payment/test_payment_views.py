import hashlib
import hmac
import json
from datetime import datetime, timezone as datetime_timezone
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from ccstore.models import Category, Product
from payment.models import Order, OrderItem, Payment
from payment.services.paystack import (
    PaystackNetworkError,
    PaystackVerificationResult,
)
from payment.services.payment_processing import PaymentProcessingError


@override_settings(
    PAYSTACK_SECRET_KEY="webhook-test-secret",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="orders@example.com",
)
class PaymentCompletionViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user_a = User.objects.create_user(
            username="callback-a",
            email="callback-a@example.com",
            password="test-password-a",
        )
        cls.user_b = User.objects.create_user(
            username="callback-b",
            email="callback-b@example.com",
            password="test-password-b",
        )
        category = Category.objects.create(name="Callback", slug="callback")
        cls.product = Product.objects.create(
            Category=category,
            title="Callback product",
            price=Decimal("50.00"),
            slug="callback-product",
            image="images/callback-product.jpg",
            stock_quantity=100,
        )
        cls.extra_product = Product.objects.create(
            Category=category,
            title="Later cart product",
            price=Decimal("10.00"),
            slug="later-cart-product",
            image="images/later-cart-product.jpg",
            stock_quantity=100,
        )

    def setUp(self):
        self.order = Order.objects.create(
            user=self.user_a,
            fullname="Callback Customer",
            email="callback-a@example.com",
            address1="1 Callback Street",
            amount_paid=Decimal("100.00"),
        )
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            product_title=self.product.title,
            user=self.user_a,
            quantity=2,
            price=Decimal("50.00"),
        )
        self.payment = Payment.objects.create(
            order=self.order,
            user=self.user_a,
            amount_paid=Decimal("100.00"),
            email="callback-a@example.com",
        )

    def verification(self, **overrides):
        values = {
            "reference": self.payment.ref,
            "status": "success",
            "amount_kobo": 10000,
            "currency": "NGN",
            "customer_email": "callback-a@example.com",
            "transaction_id": "view-transaction-1",
            "paid_at": datetime(2026, 7, 16, 12, 0, tzinfo=datetime_timezone.utc),
            "channel": "card",
        }
        values.update(overrides)
        return PaystackVerificationResult(**values)

    def webhook_body(self, *, event="charge.success", reference=None):
        payload = {
            "event": event,
            "data": {
                "reference": reference or self.payment.ref,
                "amount": 1,
                "currency": "USD",
                "status": "success",
            },
        }
        return json.dumps(payload, separators=(",", ":")).encode("utf-8")

    def signature(self, body):
        return hmac.new(
            settings.PAYSTACK_SECRET_KEY.encode("utf-8"),
            body,
            hashlib.sha512,
        ).hexdigest()

    def post_webhook(self, body, signature=None, client=None):
        return (client or self.client).post(
            reverse("paystack_webhook"),
            data=body,
            content_type="application/json",
            HTTP_X_PAYSTACK_SIGNATURE=(
                self.signature(body) if signature is None else signature
            ),
        )

    def login_a(self):
        self.client.force_login(self.user_a)

    def set_cart(self, first_quantity=2):
        session = self.client.session
        session["sess_key"] = {
            str(self.product.id): {
                "price": "50.00",
                "product_qty": first_quantity,
            },
            str(self.extra_product.id): {
                "price": "10.00",
                "product_qty": 1,
            },
        }
        session.save()

    def test_webhook_allows_post_only(self):
        response = self.client.get(reverse("paystack_webhook"))
        self.assertEqual(response.status_code, 405)

    def test_webhook_is_csrf_exempt_but_requires_valid_signature(self):
        csrf_client = Client(enforce_csrf_checks=True)
        body = self.webhook_body()

        with patch("payment.views.verify_transaction", return_value=self.verification()):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.post_webhook(body, client=csrf_client)

        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PAID)

    def test_invalid_signature_is_rejected(self):
        response = self.post_webhook(self.webhook_body(), signature="invalid")
        self.assertEqual(response.status_code, 401)

    def test_missing_signature_is_rejected(self):
        body = self.webhook_body()
        response = self.client.post(
            reverse("paystack_webhook"),
            data=body,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)

    def test_malformed_signed_json_is_rejected(self):
        body = b"{not-json"
        response = self.post_webhook(body)
        self.assertEqual(response.status_code, 400)

    @patch("payment.views.verify_transaction")
    def test_unsupported_event_is_acknowledged_without_verification(self, verify_mock):
        response = self.post_webhook(self.webhook_body(event="transfer.success"))
        self.assertEqual(response.status_code, 200)
        verify_mock.assert_not_called()

    def test_webhook_payload_alone_cannot_mark_order_paid(self):
        body = self.webhook_body()
        with patch(
            "payment.views.verify_transaction",
            side_effect=PaystackNetworkError("temporary"),
        ):
            response = self.post_webhook(body)

        self.assertEqual(response.status_code, 503)
        self.order.refresh_from_db()
        self.payment.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PENDING_PAYMENT)
        self.assertEqual(self.payment.status, Payment.Status.INITIALIZED)

    def test_duplicate_webhook_is_idempotent_and_sends_one_email(self):
        body = self.webhook_body()
        with patch("payment.views.verify_transaction", return_value=self.verification()):
            with self.captureOnCommitCallbacks(execute=True):
                first = self.post_webhook(body)
            with self.captureOnCommitCallbacks(execute=True):
                second = self.post_webhook(body)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)

    def test_unknown_webhook_reference_is_acknowledged_safely(self):
        body = self.webhook_body(reference="unknown-reference")
        unknown_data = self.verification(reference="unknown-reference")
        with patch("payment.views.verify_transaction", return_value=unknown_data):
            response = self.post_webhook(body)

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("exception", response.content.decode().lower())

    def test_webhook_response_hides_internal_processing_details(self):
        body = self.webhook_body()
        with patch("payment.views.verify_transaction", return_value=self.verification()), patch(
            "payment.views.process_verified_payment",
            side_effect=PaymentProcessingError("internal-sensitive-detail"),
        ):
            response = self.post_webhook(body)

        self.assertEqual(response.status_code, 400)
        self.assertNotIn("internal-sensitive-detail", response.content.decode())

    def test_browser_return_requires_authentication(self):
        response = self.client.post(
            reverse("verify_payment", args=(self.payment.ref,))
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_browser_return_rejects_get(self):
        self.login_a()
        response = self.client.get(reverse("verify_payment", args=(self.payment.ref,)))
        self.assertEqual(response.status_code, 405)

    @patch("payment.views.verify_transaction")
    def test_user_cannot_complete_another_users_payment(self, verify_mock):
        self.client.force_login(self.user_b)
        response = self.client.post(
            reverse("verify_payment", args=(self.payment.ref,))
        )

        self.assertRedirects(response, reverse("checkout"), fetch_redirect_response=False)
        verify_mock.assert_not_called()

    def test_unknown_browser_reference_is_safe(self):
        self.login_a()
        response = self.client.post(
            reverse("verify_payment", args=("unknown-reference",))
        )
        self.assertRedirects(response, reverse("checkout"), fetch_redirect_response=False)

    def test_successful_browser_return_redirects_to_exact_success_page(self):
        self.login_a()
        self.set_cart()

        with patch("payment.views.verify_transaction", return_value=self.verification()):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    reverse("verify_payment", args=(self.payment.ref,))
                )

        self.assertRedirects(
            response,
            reverse("payment_success", args=(self.payment.ref,)),
            fetch_redirect_response=False,
        )
        self.payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.VERIFIED)
        self.assertEqual(self.order.status, Order.Status.PAID)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_temporary_browser_verification_error_stays_pending(self):
        self.login_a()
        self.set_cart()
        with patch(
            "payment.views.verify_transaction",
            side_effect=PaystackNetworkError("temporary"),
        ):
            response = self.client.post(
                reverse("verify_payment", args=(self.payment.ref,))
            )

        self.assertRedirects(
            response,
            reverse("payment_pending", args=(self.payment.ref,)),
            fetch_redirect_response=False,
        )
        self.assertIn("sess_key", self.client.session)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PENDING_PAYMENT)

    def test_failed_payment_leaves_cart_intact(self):
        self.login_a()
        self.set_cart()
        failed_data = self.verification(status="failed")

        with patch("payment.views.verify_transaction", return_value=failed_data):
            response = self.client.post(
                reverse("verify_payment", args=(self.payment.ref,))
            )

        self.assertRedirects(
            response,
            reverse("payment_failed", args=(self.payment.ref,)),
            fetch_redirect_response=False,
        )
        self.assertEqual(self.client.session["sess_key"][str(self.product.id)]["product_qty"], 2)

    def test_successful_return_reconciles_paid_items_and_preserves_new_items(self):
        self.login_a()
        self.set_cart(first_quantity=3)

        with patch("payment.views.verify_transaction", return_value=self.verification()):
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(reverse("verify_payment", args=(self.payment.ref,)))

        cart = self.client.session["sess_key"]
        self.assertEqual(cart[str(self.product.id)]["product_qty"], 1)
        self.assertEqual(cart[str(self.extra_product.id)]["product_qty"], 1)

    def test_webhook_marks_paid_without_touching_browser_cart(self):
        self.login_a()
        self.set_cart()
        original_cart = self.client.session["sess_key"]
        body = self.webhook_body()

        with patch("payment.views.verify_transaction", return_value=self.verification()):
            with self.captureOnCommitCallbacks(execute=True):
                self.post_webhook(body)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PAID)
        self.assertEqual(self.client.session["sess_key"], original_cart)

    def test_webhook_then_browser_callback_sends_confirmation_once(self):
        self.login_a()
        body = self.webhook_body()
        with patch("payment.views.verify_transaction", return_value=self.verification()):
            with self.captureOnCommitCallbacks(execute=True):
                self.post_webhook(body)
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    reverse("verify_payment", args=(self.payment.ref,))
                )

        self.assertRedirects(
            response,
            reverse("payment_success", args=(self.payment.ref,)),
            fetch_redirect_response=False,
        )
        self.assertEqual(len(mail.outbox), 1)

    def test_success_page_is_scoped_to_exact_owner(self):
        self.order.status = Order.Status.PAID
        self.order.save(update_fields=("status",))
        self.payment.status = Payment.Status.VERIFIED
        self.payment.save(update_fields=("status",))

        self.login_a()
        own = self.client.get(reverse("payment_success", args=(self.payment.ref,)))
        self.client.force_login(self.user_b)
        other = self.client.get(reverse("payment_success", args=(self.payment.ref,)))

        self.assertEqual(own.status_code, 200)
        self.assertContains(own, f"order #{self.order.id}")
        self.assertRedirects(other, reverse("checkout"), fetch_redirect_response=False)
