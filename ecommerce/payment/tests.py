from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from ccstore.models import Category, Product
from payment.models import Order, OrderItem, Payment


class CommerceModelTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user_a = User.objects.create_user(
            username="customer-a",
            email="a@example.com",
            password="test-password-a",
        )
        cls.user_b = User.objects.create_user(
            username="customer-b",
            email="b@example.com",
            password="test-password-b",
        )
        cls.category = Category.objects.create(name="Brushes", slug="brushes")
        cls.product = Product.objects.create(
            Category=cls.category,
            title="Historical brush",
            price=Decimal("12.50"),
            slug="historical-brush",
            image="images/historical-brush.jpg",
            stock_quantity=100,
        )

    def create_order(self, user=None, amount=Decimal("25.00"), **kwargs):
        if user is None:
            user = self.user_a
        defaults = {
            "user": user,
            "fullname": "Test Customer",
            "email": "customer@example.com",
            "address1": "1 Test Street",
            "amount_paid": amount,
        }
        defaults.update(kwargs)
        return Order.objects.create(**defaults)

    def create_payment(self, order=None, user=None, **kwargs):
        if user is None:
            user = self.user_a
        defaults = {
            "order": order,
            "user": user,
            "amount_paid": Decimal("25.00"),
            "email": "customer@example.com",
        }
        defaults.update(kwargs)
        return Payment.objects.create(**defaults)


class OrderModelTests(CommerceModelTestCase):
    def test_default_status_is_pending_payment(self):
        order = self.create_order()
        self.assertEqual(order.status, Order.Status.PENDING_PAYMENT)

    def test_status_choices_are_the_expected_persisted_values(self):
        self.assertEqual(
            set(Order.Status.values),
            {
                "pending_payment",
                "paid",
                "processing",
                "shipped",
                "delivered",
                "cancelled",
                "refunded",
                "payment_failed",
                "paid_stock_issue",
            },
        )

    def test_negative_total_is_rejected_by_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_order(amount=Decimal("-0.01"))

    def test_invalid_status_is_rejected_by_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_order(status="not-a-real-status")

    def test_user_deletion_preserves_order_and_copied_customer_details(self):
        order = self.create_order(
            user=self.user_a,
            fullname="Retained Customer",
            email="retained@example.com",
        )

        self.user_a.delete()
        order.refresh_from_db()

        self.assertIsNone(order.user)
        self.assertEqual(order.fullname, "Retained Customer")
        self.assertEqual(order.email, "retained@example.com")

    def test_default_ordering_is_newest_first(self):
        older = self.create_order(fullname="Older")
        newer = self.create_order(fullname="Newer")

        order_ids = list(Order.objects.values_list("id", flat=True))

        self.assertLess(order_ids.index(newer.id), order_ids.index(older.id))


class OrderItemModelTests(CommerceModelTestCase):
    def create_item(self, **kwargs):
        defaults = {
            "order": self.create_order(),
            "product": self.product,
            "user": self.user_a,
            "quantity": 2,
            "price": Decimal("12.50"),
        }
        defaults.update(kwargs)
        return OrderItem.objects.create(**defaults)

    def test_product_title_snapshot_is_created_and_retained(self):
        item = self.create_item()
        self.product.title = "Renamed product"
        self.product.save(update_fields=("title",))
        item.refresh_from_db()

        self.assertEqual(item.product_title, "Historical brush")

    def test_product_deletion_is_protected_and_order_line_survives(self):
        item = self.create_item()

        with self.assertRaises(ProtectedError):
            self.product.delete()

        self.assertTrue(OrderItem.objects.filter(pk=item.pk).exists())
        self.assertEqual(item.product_title, "Historical brush")

    def test_quantity_must_be_positive(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_item(quantity=0)

    def test_price_cannot_be_negative(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_item(price=Decimal("-0.01"))

    def test_line_total_is_decimal_safe(self):
        item = self.create_item(quantity=3, price=Decimal("12.50"))
        self.assertEqual(item.line_total, Decimal("37.50"))


class PaymentModelTests(CommerceModelTestCase):
    def test_payment_links_to_one_exact_order(self):
        order = self.create_order()
        payment = self.create_payment(order=order)

        self.assertEqual(payment.order, order)
        self.assertEqual(list(order.payments.all()), [payment])

    def test_one_order_supports_multiple_payment_attempts(self):
        order = self.create_order()
        first = self.create_payment(order=order)
        second = self.create_payment(order=order)

        self.assertSetEqual(set(order.payments.all()), {first, second})

    def test_status_defaults_to_initialized(self):
        payment = self.create_payment(order=self.create_order())
        self.assertEqual(payment.status, Payment.Status.INITIALIZED)

    def test_legacy_payment_may_remain_unreconciled(self):
        payment = self.create_payment(order=None)

        self.assertIsNone(payment.order)
        self.assertTrue(payment.is_legacy_unreconciled)

    def test_generated_references_are_nonempty_and_unique(self):
        first = self.create_payment(order=self.create_order())
        second = self.create_payment(order=self.create_order())

        self.assertTrue(first.ref)
        self.assertNotEqual(first.ref, second.ref)

    def test_duplicate_reference_is_rejected_by_database(self):
        order = self.create_order()
        self.create_payment(order=order, ref="duplicate-reference")

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_payment(order=order, ref="duplicate-reference")

    def test_negative_payment_amount_is_rejected_by_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_payment(
                order=self.create_order(),
                amount_paid=Decimal("-0.01"),
            )

    def test_invalid_payment_status_is_rejected_by_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_payment(
                order=self.create_order(),
                status="not-a-real-status",
            )

    def test_verified_compatibility_property_uses_status_as_source_of_truth(self):
        payment = self.create_payment(order=self.create_order())
        self.assertFalse(payment.verified)

        payment.verified = True
        payment.save(update_fields=("status",))
        payment.refresh_from_db()

        self.assertTrue(payment.verified)
        self.assertEqual(payment.status, Payment.Status.VERIFIED)

    def test_amount_value_converts_decimal_naira_to_kobo(self):
        payment = self.create_payment(
            order=self.create_order(),
            amount_paid=Decimal("100.50"),
        )
        self.assertEqual(payment.amount_value(), 10050)

    def test_order_with_payment_is_protected_from_deletion(self):
        order = self.create_order()
        payment = self.create_payment(order=order)

        with self.assertRaises(ProtectedError):
            order.delete()

        self.assertTrue(Payment.objects.filter(pk=payment.pk).exists())

    def test_user_deletion_preserves_payment(self):
        order = self.create_order(user=self.user_a)
        payment = self.create_payment(order=order, user=self.user_a)

        self.user_a.delete()
        payment.refresh_from_db()

        self.assertIsNone(payment.user)
        self.assertTrue(Payment.objects.filter(pk=payment.pk).exists())

    def test_payment_never_drifts_to_another_users_later_order(self):
        order_a = self.create_order(user=self.user_a, fullname="Customer A")
        payment_a = self.create_payment(order=order_a, user=self.user_a)
        order_b = self.create_order(user=self.user_b, fullname="Customer B")
        payment_b = self.create_payment(order=order_b, user=self.user_b)

        payment_a.refresh_from_db()

        self.assertEqual(payment_a.order, order_a)
        self.assertNotEqual(payment_a.order, order_b)
        self.assertEqual(list(order_a.payments.all()), [payment_a])
        self.assertEqual(list(order_b.payments.all()), [payment_b])
