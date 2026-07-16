import logging

from django.db import models
from django.urls import reverse
from django.utils.text import slugify

logger = logging.getLogger(__name__)

# Create your models here.
class Category(models.Model):
    name = models.CharField(max_length=250, db_index=True)

    slug = models.SlugField(max_length=250, unique=True)

    class Meta:
        verbose_name_plural = 'categories'

    def __str__(self):
        return self.name
    
    def get_absolute_url(self):
        return reverse('pdt_category', args=[self.slug])
    
    
    
class Product(models.Model):

    Category = models.ForeignKey(Category, related_name='product', on_delete=models.CASCADE, null=True)

    title = models.CharField(max_length=250)

    price = models.DecimalField(max_digits=10, decimal_places=2)

    description = models.TextField(blank=True)

    brand = models.CharField(max_length=250, default='unbranded')

    slug = models.SlugField(max_length=250, unique=True, blank=True)

    sku = models.CharField(max_length=64, unique=True, blank=True)

    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text='Deactivate products for normal catalog removal; deletion may be protected by order history.',
    )

    stock_quantity = models.PositiveIntegerField(default=0)

    low_stock_threshold = models.PositiveIntegerField(default=5)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    image = models.ImageField(upload_to='images/')

    class Meta:
        verbose_name_plural = 'products'
        ordering = ('title', 'id')
        constraints = [
            models.CheckConstraint(
                condition=models.Q(stock_quantity__gte=0),
                name='product_stock_gte_zero',
            ),
        ]

    def __str__(self):
        return self.title
    
    def get_absolute_url(self):
        return reverse('product_info', args=[self.slug])

    def save(self, *args, **kwargs):
        if self.sku:
            self.sku = self.sku.strip().upper()
        if not self.slug:
            base = slugify(self.title)[:220] or 'product'
            candidate = base
            suffix = 2
            while type(self).objects.exclude(pk=self.pk).filter(slug=candidate).exists():
                candidate = f'{base[:240-len(str(suffix))]}-{suffix}'
                suffix += 1
            self.slug = candidate
        elif type(self).objects.exclude(pk=self.pk).filter(slug=self.slug).exists():
            logger.warning('Product slug conflict product_id=%s slug=%s', self.pk, self.slug)
        needs_sku = not self.sku
        super().save(*args, **kwargs)
        if needs_sku:
            self.sku = f'CCB-{self.pk:06d}'
            type(self).objects.filter(pk=self.pk).update(sku=self.sku)

    @property
    def is_available(self):
        return self.is_active and self.stock_quantity > 0

    @property
    def is_low_stock(self):
        return 0 < self.stock_quantity <= self.low_stock_threshold

class ProductImage(models.Model):
    product = models.ForeignKey(Product, related_name='images', on_delete=models.CASCADE)
    image = models.ImageField(upload_to='images/', blank=True, null=True)

    def __str__(self):
        return f"{self.product.title} - Image {self.id}"
    
    class Meta:
        verbose_name_plural = 'product images'
