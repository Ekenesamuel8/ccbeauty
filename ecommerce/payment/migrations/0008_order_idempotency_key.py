from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("payment", "0007_payment_order_and_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="idempotency_key",
            field=models.CharField(
                blank=True,
                editable=False,
                help_text="Durable checkout token; legacy orders remain null.",
                max_length=64,
                null=True,
                unique=True,
            ),
        ),
    ]
