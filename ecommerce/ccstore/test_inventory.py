from decimal import Decimal
from time import sleep

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.contrib import admin

from ccstore.models import Category, Product
from ccstore.admin import ProductAdmin


class ProductInventoryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(name='Inventory', slug='inventory')

    def product(self, **overrides):
        number = Product.objects.count() + 1
        values = dict(Category=self.category, title=f'Product {number}', price=Decimal('10.00'), image='images/product.jpg', stock_quantity=10)
        values.update(overrides)
        return Product.objects.create(**values)

    def test_slug_and_sku_are_generated_and_sku_is_normalized(self):
        product = self.product(title='New Brush', sku='  abc-1  ')
        self.assertEqual(product.slug, 'new-brush')
        self.assertEqual(product.sku, 'ABC-1')

    def test_generated_sku_uses_primary_key(self):
        product = self.product()
        self.assertEqual(product.sku, f'CCB-{product.id:06d}')

    def test_slug_and_sku_are_unique(self):
        self.product(slug='unique', sku='SKU-1')
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.product(title='Other', slug='unique', sku='SKU-2')
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.product(title='Other 2', slug='other-2', sku=' sku-1 ')

    def test_availability_and_low_stock_properties(self):
        product = self.product(stock_quantity=5, low_stock_threshold=5)
        self.assertTrue(product.is_available)
        self.assertTrue(product.is_low_stock)
        product.stock_quantity = 0
        self.assertFalse(product.is_available)
        self.assertFalse(product.is_low_stock)
        product.stock_quantity = 10
        product.is_active = False
        self.assertFalse(product.is_available)

    def test_negative_stock_is_rejected_by_database(self):
        product = self.product()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Product.objects.filter(pk=product.pk).update(stock_quantity=-1)

    def test_updated_timestamp_changes(self):
        product = self.product()
        original = product.updated_at
        sleep(0.01)
        product.title = 'Changed'
        product.save()
        self.assertGreater(product.updated_at, original)

    def test_product_admin_exposes_operational_fields(self):
        model_admin = ProductAdmin(Product, admin.site)
        self.assertIn('sku', model_admin.list_display)
        self.assertIn('stock_quantity', model_admin.list_display)


class CatalogAvailabilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        category = Category.objects.create(name='Catalog', slug='catalog')
        for number in range(14):
            Product.objects.create(Category=category, title=f'Active {number:02d}', slug=f'active-{number}', price='10.00', image='images/a.jpg', stock_quantity=0 if number == 0 else 3)
        cls.inactive = Product.objects.create(Category=category, title='Hidden', slug='hidden', price='10.00', image='images/a.jpg', stock_quantity=3, is_active=False)
        cls.category = category

    def test_store_hides_inactive_keeps_out_of_stock_and_paginates(self):
        response = self.client.get(reverse('store'))
        self.assertNotContains(response, 'Hidden')
        self.assertContains(response, 'Out of stock')
        self.assertEqual(len(response.context['my_products']), 12)

    def test_inactive_detail_is_404(self):
        self.assertEqual(self.client.get(self.inactive.get_absolute_url()).status_code, 404)

    def test_category_and_search_hide_inactive(self):
        category_response = self.client.get(self.category.get_absolute_url())
        search_response = self.client.get(reverse('search'), {'q': 'Hidden'})
        self.assertNotContains(category_response, 'Hidden')
        self.assertEqual(list(search_response.context['products']), [])

    def test_empty_search_is_safe(self):
        response = self.client.get(reverse('search'), {'q': '   '})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['products']), [])
