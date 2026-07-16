from datetime import datetime, timezone as datetime_timezone
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase, override_settings

from ccstore.models import Category, Product
from payment.models import Order, OrderItem, Payment
from payment.services.paystack import PaystackVerificationResult
from payment.services.payment_processing import (
    DuplicateProviderTransactionError,
    InvalidPaymentStateError,
    LegacyPaymentError,
    PaymentAmountMismatch,
    PaymentCurrencyMismatch,
    PaymentOwnershipError,
    PaymentReferenceMismatch,
    process_verified_payment,
)


class PaymentCompletionFixtures:
    def create_fixtures(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="payer",
            email="payer@example.com",
            password="test-password",
        )
        self.other_user = User.objects.create_user(
            username="other-payer",
            email="other@example.com",
            password="test-password",
        )
        category = Category.objects.create(name="Paid products", slug="paid-products")
        self.product = Product.objects.create(
            Category=category,
            title="Paid product",
            price=Decimal("125.50"),
            slug="paid-product",
            image="images/paid-product.jpg",
            stock_quantity=100,
        )
        self.order = Order.objects.create(
            user=self.user,
            fullname="Paying Customer",
            email="payer@example.com",
            address1="1 Paid Street\nLagos",
            amount_paid=Decimal("251.00"),
        )
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            product_title=self.product.title,
            user=self.user,
            quantity=2,
            price=Decimal("125.50"),
        )
        self.payment = Payment.objects.create(
            order=self.order,
            user=self.user,
            amount_paid=Decimal("251.00"),
            email="payer@example.com",
        )

    def verification(self, **overrides):
        values = {
            "reference": self.payment.ref,
            "status": "success",
            "amount_kobo": 25100,
            "currency": "NGN",
            "customer_email": "payer@example.com",
            "transaction_id": "provider-transaction-1",
            "paid_at": datetime(2026, 7, 16, 10, 30, tzinfo=datetime_timezone.utc),
            "channel": "card",
        }
        values.update(overrides)
        return PaystackVerificationResult(**values)


class PaymentProcessingTests(PaymentCompletionFixtures, TestCase):
    def setUp(self):
        self.create_fixtures()

    def process(self, **overrides):
        return process_verified_payment(
            reference=self.payment.ref,
            verification_data=self.verification(**overrides),
        )

    def test_exact_payment_and_order_are_updated_atomically(self):
        result = self.process()
        self.payment.refresh_from_db()
        self.order.refresh_from_db()

        self.assertTrue(result.newly_verified)
        self.assertEqual(self.payment.status, Payment.Status.VERIFIED)
        self.assertEqual(self.order.status, Order.Status.PAID)
        self.assertIsNotNone(self.payment.verified_at)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 98)
        self.assertIsNotNone(self.order.stock_deducted_at)
        self.assertEqual(self.payment.provider_transaction_id, "provider-transaction-1")
        self.assertEqual(self.payment.provider, "paystack")
        self.assertEqual(self.payment.currency, "NGN")
        self.assertEqual(self.payment.provider_channel, "card")

    def test_amount_mismatch_is_rejected(self):
        with self.assertRaises(PaymentAmountMismatch):
            self.process(amount_kobo=1)
        self.payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.INITIALIZED)
        self.assertEqual(self.order.status, Order.Status.PENDING_PAYMENT)

    def test_currency_mismatch_is_rejected(self):
        with self.assertRaises(PaymentCurrencyMismatch):
            self.process(currency="USD")

    def test_reference_mismatch_is_rejected(self):
        with self.assertRaises(PaymentReferenceMismatch):
            self.process(reference="another-reference")

    def test_legacy_payment_without_order_is_rejected(self):
        legacy = Payment.objects.create(
            user=self.user,
            amount_paid=Decimal("251.00"),
            email="payer@example.com",
        )
        data = self.verification(reference=legacy.ref)

        with self.assertRaises(LegacyPaymentError):
            process_verified_payment(reference=legacy.ref, verification_data=data)

    def test_payment_order_ownership_mismatch_is_rejected(self):
        self.payment.user = self.other_user
        self.payment.save(update_fields=("user",))

        with self.assertRaises(PaymentOwnershipError):
            self.process()

    def test_duplicate_provider_transaction_is_rejected(self):
        other_order = Order.objects.create(
            user=self.other_user,
            fullname="Other",
            email="other@example.com",
            address1="Other address",
            amount_paid=Decimal("251.00"),
        )
        Payment.objects.create(
            order=other_order,
            user=self.other_user,
            amount_paid=Decimal("251.00"),
            email="other@example.com",
            provider_transaction_id="provider-transaction-1",
        )

        with self.assertRaises(DuplicateProviderTransactionError):
            self.process()

    def test_repeated_processing_is_idempotent(self):
        first = self.process()
        second = self.process()

        self.assertTrue(first.newly_verified)
        self.assertFalse(second.newly_verified)
        self.payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.VERIFIED)
        self.assertEqual(self.order.status, Order.Status.PAID)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 98)

    def test_verified_payment_with_insufficient_stock_requires_staff_attention(self):
        self.product.stock_quantity = 1
        self.product.save(update_fields=('stock_quantity', 'updated_at'))
        result = self.process()
        self.order.refresh_from_db()
        self.payment.refresh_from_db()
        self.product.refresh_from_db()
        self.assertTrue(result.successful)
        self.assertEqual(self.payment.status, Payment.Status.VERIFIED)
        self.assertEqual(self.order.status, Order.Status.PAID_STOCK_ISSUE)
        self.assertIsNone(self.order.stock_deducted_at)
        self.assertEqual(self.product.stock_quantity, 1)
        self.assertFalse(result.confirmation_scheduled)

    def test_verified_payment_cannot_be_downgraded(self):
        self.process()
        result = self.process(status="failed")

        self.payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertTrue(result.successful)
        self.assertEqual(self.payment.status, Payment.Status.VERIFIED)
        self.assertEqual(self.order.status, Order.Status.PAID)

    def test_paid_order_cannot_become_payment_failed(self):
        self.order.status = Order.Status.PAID
        self.order.save(update_fields=("status",))

        with self.assertRaises(InvalidPaymentStateError):
            self.process(status="failed")

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PAID)

    def test_definitive_failure_sets_safe_failure_states(self):
        result = self.process(status="failed")
        self.payment.refresh_from_db()
        self.order.refresh_from_db()

        self.assertEqual(result.state, Payment.Status.FAILED)
        self.assertEqual(self.payment.status, Payment.Status.FAILED)
        self.assertEqual(self.order.status, Order.Status.PAYMENT_FAILED)
        self.assertIn("failed", self.payment.failure_reason)

    def test_temporary_status_remains_pending(self):
        result = self.process(status="ongoing")
        self.payment.refresh_from_db()
        self.order.refresh_from_db()

        self.assertEqual(result.state, Payment.Status.PENDING)
        self.assertEqual(self.payment.status, Payment.Status.PENDING)
        self.assertEqual(self.order.status, Order.Status.PENDING_PAYMENT)

    def test_database_failure_rolls_back_payment_and_order(self):
        original_save = Order.save

        def fail_paid_order(instance, *args, **kwargs):
            if instance.status == Order.Status.PAID:
                raise RuntimeError("simulated order write failure")
            return original_save(instance, *args, **kwargs)

        with patch.object(Order, "save", new=fail_paid_order):
            with self.assertRaises(RuntimeError):
                self.process()

        self.payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.INITIALIZED)
        self.assertIsNone(self.payment.provider_transaction_id)
        self.assertEqual(self.order.status, Order.Status.PENDING_PAYMENT)


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="orders@example.com",
)
class ConfirmationEmailTests(PaymentCompletionFixtures, TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.create_fixtures()

    def process(self):
        return process_verified_payment(
            reference=self.payment.ref,
            verification_data=self.verification(),
        )

    def test_no_email_exists_before_verification(self):
        from django.core import mail

        self.assertEqual(mail.outbox, [])

    def test_one_confirmation_is_sent_after_verified_commit(self):
        from django.core import mail

        self.process()
        self.order.refresh_from_db()

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(self.order.confirmation_status, Order.ConfirmationStatus.SENT)
        self.assertIsNotNone(self.order.confirmation_sent_at)
        self.assertIn(f"order #{self.order.id}", mail.outbox[0].body)
        self.assertIn(self.payment.ref, mail.outbox[0].body)
        self.assertIn("Paid product", mail.outbox[0].body)
        self.assertIn("1 Paid Street", mail.outbox[0].body)

    def test_duplicate_processing_sends_no_second_email(self):
        from django.core import mail

        self.process()
        self.process()

        self.assertEqual(len(mail.outbox), 1)

    @patch(
        "payment.services.payment_processing.send_mail",
        side_effect=RuntimeError("SMTP unavailable"),
    )
    def test_email_failure_does_not_roll_back_paid_state(self, send_mail_mock):
        self.process()
        self.order.refresh_from_db()
        self.payment.refresh_from_db()

        self.assertEqual(self.order.status, Order.Status.PAID)
        self.assertEqual(self.payment.status, Payment.Status.VERIFIED)
        self.assertEqual(self.order.confirmation_status, Order.ConfirmationStatus.FAILED)
        self.assertIsNone(self.order.confirmation_sent_at)
        send_mail_mock.assert_called_once()

    def test_failed_email_remains_retryable(self):
        from django.core import mail

        with patch(
            "payment.services.payment_processing.send_mail",
            side_effect=RuntimeError("SMTP unavailable"),
        ):
            self.process()
        self.order.refresh_from_db()
        self.assertEqual(self.order.confirmation_status, Order.ConfirmationStatus.FAILED)

        self.process()
        self.order.refresh_from_db()

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(self.order.confirmation_status, Order.ConfirmationStatus.SENT)
