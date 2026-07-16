from django.test import TestCase
from django.urls import reverse

from ccstore.models import Category, Product


class CartInventoryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        category = Category.objects.create(name='Cart stock', slug='cart-stock')
        cls.product = Product.objects.create(Category=category, title='Stocked', slug='stocked', price='10.00', image='images/a.jpg', stock_quantity=3)

    def post(self, quantity, *, endpoint='add_cart'):
        key = 'product_quantity' if endpoint == 'add_cart' else 'product_qty'
        return self.client.post(reverse(endpoint), {'action': 'post', 'product_id': self.product.id, key: quantity})

    def test_valid_quantity_is_accepted(self):
        self.assertEqual(self.post(2).status_code, 200)

    def test_zero_negative_noninteger_and_above_stock_are_rejected(self):
        for quantity in (0, -1, 'one', 4):
            with self.subTest(quantity=quantity):
                self.assertEqual(self.post(quantity).status_code, 400)

    def test_inactive_and_out_of_stock_are_rejected(self):
        for updates in ({'is_active': False}, {'stock_quantity': 0}):
            values = {'is_active': True, 'stock_quantity': 3}
            values.update(updates)
            Product.objects.filter(pk=self.product.pk).update(**values)
            self.assertEqual(self.post(1).status_code, 400)

    def test_update_rechecks_current_database_stock(self):
        self.post(2)
        Product.objects.filter(pk=self.product.pk).update(stock_quantity=1)
        response = self.post(2, endpoint='update_cart')
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())
