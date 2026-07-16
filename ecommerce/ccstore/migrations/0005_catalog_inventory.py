import django.utils.timezone
from django.db import migrations, models
from django.utils.text import slugify


def normalize_catalog(apps, schema_editor):
    Product = apps.get_model('ccstore', 'Product')
    database = schema_editor.connection.alias
    used = set()
    for product in Product.objects.using(database).order_by('id').iterator():
        original = (product.slug or '').strip()
        base = slugify(original or product.title)[:220] or 'product'
        candidate = original if original and original not in used else base
        if candidate in used:
            candidate = f'{base[:230]}-{product.id}'
        suffix = 2
        while candidate in used:
            candidate = f'{base[:235]}-{product.id}-{suffix}'
            suffix += 1
        product.slug = candidate
        product.sku = f'CCB-{product.id:06d}'
        # Historical stock is unknowable. Zero is the only safe finite value.
        product.stock_quantity = 0
        product.save(update_fields=('slug', 'sku', 'stock_quantity'))
        used.add(candidate)


class Migration(migrations.Migration):
    dependencies = [('ccstore', '0004_productimage')]

    operations = [
        migrations.AddField(
            model_name='product', name='sku',
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.AddField(
            model_name='product', name='is_active',
            field=models.BooleanField(db_index=True, default=True, help_text='Deactivate products for normal catalog removal; deletion may be protected by order history.'),
        ),
        migrations.AddField(
            model_name='product', name='stock_quantity',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='product', name='low_stock_threshold',
            field=models.PositiveIntegerField(default=5),
        ),
        migrations.AddField(
            model_name='product', name='created_at',
            field=models.DateTimeField(default=django.utils.timezone.now, auto_now_add=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='product', name='updated_at',
            field=models.DateTimeField(default=django.utils.timezone.now, auto_now=True),
            preserve_default=False,
        ),
        migrations.RunPython(normalize_catalog, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='product', name='slug',
            field=models.SlugField(blank=True, max_length=250, unique=True),
        ),
        migrations.AlterField(
            model_name='product', name='sku',
            field=models.CharField(blank=True, max_length=64, unique=True),
        ),
        migrations.AlterModelOptions(
            name='product', options={'ordering': ('title', 'id'), 'verbose_name_plural': 'products'},
        ),
        migrations.AddConstraint(
            model_name='product',
            constraint=models.CheckConstraint(condition=models.Q(('stock_quantity__gte', 0)), name='product_stock_gte_zero'),
        ),
    ]
