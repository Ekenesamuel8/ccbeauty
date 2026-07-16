from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.contrib import admin

from ccstore.models import Category, Product
from payment.models import Order, OrderItem, Payment
from payment.admin import OrderAdmin
from payment.services.inventory import (
    InvalidOrderTransition,
    deduct_stock_for_verified_order,
    restore_order_stock,
    resolve_paid_stock_issue,
    transition_order,
)


class InventoryLifecycleTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user('inventory-user', email='inventory@example.com')
        category = Category.objects.create(name='Lifecycle', slug='lifecycle')
        self.first = Product.objects.create(Category=category, title='First', slug='first', price='10.00', image='images/a.jpg', stock_quantity=10)
        self.second = Product.objects.create(Category=category, title='Second', slug='second', price='5.00', image='images/b.jpg', stock_quantity=8)
        self.order = Order.objects.create(user=user, fullname='Customer', email=user.email, address1='Saved snapshot', amount_paid=Decimal('25.00'))
        OrderItem.objects.create(order=self.order, product=self.first, product_title=self.first.title, quantity=2, price='10.00', user=user)
        OrderItem.objects.create(order=self.order, product=self.second, product_title=self.second.title, quantity=1, price='5.00', user=user)
        Payment.objects.create(order=self.order, user=user, amount_paid=self.order.amount_paid, email=user.email, status=Payment.Status.VERIFIED)

    def test_deduction_and_restoration_are_each_idempotent(self):
        self.assertTrue(deduct_stock_for_verified_order(self.order))
        self.order.refresh_from_db()
        self.assertTrue(deduct_stock_for_verified_order(self.order))
        self.first.refresh_from_db(); self.second.refresh_from_db()
        self.assertEqual((self.first.stock_quantity, self.second.stock_quantity), (8, 7))
        transition_order(self.order.id, Order.Status.CANCELLED)
        self.assertTrue(restore_order_stock(self.order.id))
        self.assertFalse(restore_order_stock(self.order.id))
        self.first.refresh_from_db(); self.second.refresh_from_db()
        self.assertEqual((self.first.stock_quantity, self.second.stock_quantity), (10, 8))

    def test_pending_order_cannot_restore_or_process(self):
        self.assertFalse(restore_order_stock(self.order.id))
        with self.assertRaises(InvalidOrderTransition):
            transition_order(self.order.id, Order.Status.PROCESSING)

    def test_practical_lifecycle_and_terminal_rules(self):
        deduct_stock_for_verified_order(self.order)
        transition_order(self.order.id, Order.Status.PROCESSING)
        transition_order(self.order.id, Order.Status.SHIPPED)
        delivered = transition_order(self.order.id, Order.Status.DELIVERED)
        self.assertEqual(delivered.status, Order.Status.DELIVERED)
        with self.assertRaises(InvalidOrderTransition):
            transition_order(self.order.id, Order.Status.PENDING_PAYMENT)

    def test_stock_issue_cannot_silently_become_delivered(self):
        self.first.stock_quantity = 0
        self.first.save(update_fields=('stock_quantity', 'updated_at'))
        self.assertFalse(deduct_stock_for_verified_order(self.order))
        with self.assertRaises(InvalidOrderTransition):
            transition_order(self.order.id, Order.Status.DELIVERED)

    def test_staff_can_restock_and_deliberately_resolve_stock_issue(self):
        self.first.stock_quantity = 0
        self.first.save(update_fields=('stock_quantity', 'updated_at'))
        self.assertFalse(deduct_stock_for_verified_order(self.order))
        self.first.stock_quantity = 10
        self.first.save(update_fields=('stock_quantity', 'updated_at'))
        resolved = resolve_paid_stock_issue(self.order.id)
        self.assertEqual(resolved.status, Order.Status.PAID)
        self.assertIsNotNone(resolved.stock_deducted_at)

    def test_order_admin_has_no_mark_paid_action(self):
        actions = OrderAdmin(Order, admin.site).actions
        self.assertNotIn('mark_paid', actions)
