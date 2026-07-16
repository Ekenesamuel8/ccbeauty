import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.utils import timezone


def reconcile_addresses(apps, schema_editor):
    Address = apps.get_model("payment", "RegisterAddress")
    database = schema_editor.connection.alias
    Address.objects.using(database).filter(user_id=None).delete()
    Address.objects.using(database).filter(created_at=None).update(
        created_at=timezone.now(),
        updated_at=timezone.now(),
    )
    user_ids = (
        Address.objects.using(database)
        .values_list("user_id", flat=True)
        .order_by()
        .distinct()
    )
    for user_id in user_ids:
        addresses = Address.objects.using(database).filter(user_id=user_id).order_by("id")
        default_id = addresses.values_list("id", flat=True).first()
        addresses.update(is_default=False)
        if default_id:
            Address.objects.using(database).filter(pk=default_id).update(is_default=True)


class Migration(migrations.Migration):
    dependencies = [
        ("payment", "0009_paystack_completion_metadata"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="registeraddress",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
        migrations.AddField(
            model_name="registeraddress",
            name="is_default",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="registeraddress",
            name="label",
            field=models.CharField(default="Home", max_length=50),
        ),
        migrations.AddField(
            model_name="registeraddress",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, null=True),
        ),
        migrations.RunPython(reconcile_addresses, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="registeraddress",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name="registeraddress",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AlterField(
            model_name="registeraddress",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="shipping_addresses",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterModelOptions(
            name="registeraddress",
            options={
                "ordering": ("-is_default", "id"),
                "verbose_name": "RegisterAddress",
                "verbose_name_plural": "RegisterAddress",
            },
        ),
        migrations.AddConstraint(
            model_name="registeraddress",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_default", True)),
                fields=("user",),
                name="one_default_address_per_user",
            ),
        ),
    ]
