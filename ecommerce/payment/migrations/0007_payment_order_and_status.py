import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import Count, Q


def validate_payment_references(apps, schema_editor):
    Payment = apps.get_model("payment", "Payment")
    database = schema_editor.connection.alias
    payments = Payment.objects.using(database)
    blank_count = payments.filter(Q(ref__isnull=True) | Q(ref="")).count()
    duplicate_groups = (
        payments.exclude(ref="")
        .values("ref")
        .annotate(row_count=Count("id"))
        .filter(row_count__gt=1)
        .count()
    )
    if blank_count or duplicate_groups:
        raise RuntimeError(
            "Cannot make payment references unique: "
            f"{blank_count} blank rows and {duplicate_groups} duplicate groups "
            "require manual reconciliation."
        )


def copy_verified_to_status(apps, schema_editor):
    Payment = apps.get_model("payment", "Payment")
    payments = Payment.objects.using(schema_editor.connection.alias)
    payments.filter(verified=True).update(status="verified")
    payments.filter(verified=False).update(status="initialized")


def copy_status_to_verified(apps, schema_editor):
    Payment = apps.get_model("payment", "Payment")
    payments = Payment.objects.using(schema_editor.connection.alias)
    payments.update(verified=False)
    payments.filter(status="verified").update(verified=True)


class Migration(migrations.Migration):
    dependencies = [
        ("payment", "0006_order_history_integrity"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="payment",
            options={"ordering": ("-date_paid", "-id")},
        ),
        migrations.AddField(
            model_name="payment",
            name="order",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Legacy payments created before the explicit relationship remain "
                    "unreconciled with order=NULL."
                ),
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="payments",
                to="payment.order",
            ),
        ),
        migrations.AddField(
            model_name="payment",
            name="status",
            field=models.CharField(
                choices=[
                    ("initialized", "Initialized"),
                    ("pending", "Pending"),
                    ("verified", "Verified"),
                    ("failed", "Failed"),
                    ("cancelled", "Cancelled"),
                    ("refunded", "Refunded"),
                ],
                db_index=True,
                default="initialized",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="payment",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(copy_verified_to_status, copy_status_to_verified),
        migrations.RemoveField(
            model_name="payment",
            name="verified",
        ),
        migrations.RunPython(validate_payment_references, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="payment",
            name="ref",
            field=models.CharField(max_length=200, unique=True),
        ),
        migrations.AddIndex(
            model_name="payment",
            index=models.Index(
                fields=["order", "-date_paid"],
                name="payment_order_date_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="payment",
            constraint=models.CheckConstraint(
                condition=models.Q(("amount_paid__gte", 0)),
                name="payment_amount_gte_zero",
            ),
        ),
        migrations.AddConstraint(
            model_name="payment",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    (
                        "status__in",
                        (
                            "initialized",
                            "pending",
                            "verified",
                            "failed",
                            "cancelled",
                            "refunded",
                        ),
                    )
                ),
                name="payment_status_valid",
            ),
        ),
    ]
