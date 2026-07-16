from django.db import migrations, models


def populate_sku_snapshots(apps, schema_editor):
    OrderItem = apps.get_model('payment', 'OrderItem')
    Product = apps.get_model('ccstore', 'Product')
    database = schema_editor.connection.alias
    skus = dict(Product.objects.using(database).values_list('id', 'sku'))
    batch = []
    for item in OrderItem.objects.using(database).order_by('id').iterator():
        item.product_sku = skus.get(item.product_id, '')
        batch.append(item)
        if len(batch) >= 500:
            OrderItem.objects.using(database).bulk_update(batch, ('product_sku',))
            batch = []
    if batch:
        OrderItem.objects.using(database).bulk_update(batch, ('product_sku',))


class Migration(migrations.Migration):
    dependencies = [('ccstore', '0005_catalog_inventory'), ('payment', '0010_shipping_address_lifecycle')]

    operations = [
        migrations.AddField(
            model_name='orderitem', name='product_sku',
            field=models.CharField(blank=True, help_text='Immutable SKU snapshot captured when the line is created.', max_length=64),
        ),
        migrations.AddField(
            model_name='order', name='stock_deducted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='order', name='stock_restored_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(populate_sku_snapshots, migrations.RunPython.noop),
        migrations.RemoveConstraint(model_name='order', name='order_status_valid'),
        migrations.AlterField(
            model_name='order', name='status',
            field=models.CharField(choices=[('pending_payment', 'Pending payment'), ('paid', 'Paid'), ('processing', 'Processing'), ('shipped', 'Shipped'), ('delivered', 'Delivered'), ('cancelled', 'Cancelled'), ('refunded', 'Refunded'), ('payment_failed', 'Payment failed'), ('paid_stock_issue', 'Paid - stock issue')], db_index=True, default='pending_payment', max_length=20),
        ),
        migrations.AddConstraint(
            model_name='order',
            constraint=models.CheckConstraint(condition=models.Q(('status__in', ['pending_payment', 'paid', 'processing', 'shipped', 'delivered', 'cancelled', 'refunded', 'payment_failed', 'paid_stock_issue'])), name='order_status_valid'),
        ),
    ]
