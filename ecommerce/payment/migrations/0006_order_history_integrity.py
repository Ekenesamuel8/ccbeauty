import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


def populate_product_titles(apps, schema_editor):
    OrderItem = apps.get_model("payment", "OrderItem")
    Product = apps.get_model("ccstore", "Product")
    database = schema_editor.connection.alias

    product_ids = set(
        OrderItem.objects.using(database).exclude(product_id=None).values_list(
            "product_id", flat=True
        )
    )
    titles = dict(
        Product.objects.using(database)
        .filter(pk__in=product_ids)
        .values_list("pk", "title")
    )

    items = []
    for item in OrderItem.objects.using(database).all().iterator():
        item.product_title = titles.get(
            item.product_id,
            (
                f"Unavailable product #{item.product_id}"
                if item.product_id
                else "Unavailable product"
            ),
        )
        items.append(item)

    if items:
        OrderItem.objects.using(database).bulk_update(
            items,
            ("product_title",),
            batch_size=500,
        )


def clear_product_titles(apps, schema_editor):
    OrderItem = apps.get_model("payment", "OrderItem")
    database = schema_editor.connection.alias
    OrderItem.objects.using(database).update(product_title=None)


class Migration(migrations.Migration):
    dependencies = [
        ("payment", "0005_payment"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="order",
            options={"ordering": ("-date_ordered", "-id")},
        ),
        migrations.AddField(
            model_name="order",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending_payment", "Pending payment"),
                    ("paid", "Paid"),
                    ("processing", "Processing"),
                    ("shipped", "Shipped"),
                    ("delivered", "Delivered"),
                    ("cancelled", "Cancelled"),
                    ("refunded", "Refunded"),
                    ("payment_failed", "Payment failed"),
                ],
                db_index=True,
                default="pending_payment",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="updated_at",
            field=models.DateTimeField(
                auto_now=True,
                default=django.utils.timezone.now,
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="order",
            name="amount_paid",
            field=models.DecimalField(
                decimal_places=2,
                max_digits=8,
                verbose_name="order total",
            ),
        ),
        migrations.AlterField(
            model_name="order",
            name="user",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "The account may be deleted while the copied customer details "
                    "remain on this historical order."
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="orderitem",
            name="product_title",
            field=models.CharField(blank=True, max_length=250, null=True),
        ),
        migrations.RunPython(populate_product_titles, clear_product_titles),
        migrations.AlterField(
            model_name="orderitem",
            name="product_title",
            field=models.CharField(
                help_text=(
                    "Immutable product-name snapshot captured when the line is created."
                ),
                max_length=250,
            ),
        ),
        migrations.AlterField(
            model_name="orderitem",
            name="product",
            field=models.ForeignKey(
                help_text=(
                    "Protected so deleting a product cannot erase this order line."
                ),
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="ccstore.product",
            ),
        ),
        migrations.AlterField(
            model_name="orderitem",
            name="user",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddIndex(
            model_name="order",
            index=models.Index(
                fields=["user", "-date_ordered"],
                name="order_user_date_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="order",
            constraint=models.CheckConstraint(
                condition=models.Q(("amount_paid__gte", 0)),
                name="order_amount_gte_zero",
            ),
        ),
        migrations.AddConstraint(
            model_name="order",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    (
                        "status__in",
                        (
                            "pending_payment",
                            "paid",
                            "processing",
                            "shipped",
                            "delivered",
                            "cancelled",
                            "refunded",
                            "payment_failed",
                        ),
                    )
                ),
                name="order_status_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="orderitem",
            constraint=models.CheckConstraint(
                condition=models.Q(("quantity__gt", 0)),
                name="orderitem_qty_gt_zero",
            ),
        ),
        migrations.AddConstraint(
            model_name="orderitem",
            constraint=models.CheckConstraint(
                condition=models.Q(("price__gte", 0)),
                name="orderitem_price_gte_zero",
            ),
        ),
    ]
