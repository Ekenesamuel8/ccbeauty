import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def reconcile_profiles_and_emails(apps, schema_editor):
    User = apps.get_model("auth", "User")
    UserProfile = apps.get_model("account", "UserProfile")
    database = schema_editor.connection.alias

    UserProfile.objects.using(database).filter(user_id=None).delete()
    duplicate_users = (
        UserProfile.objects.using(database)
        .values_list("user_id", flat=True)
        .order_by()
        .distinct()
    )
    for user_id in duplicate_users:
        profiles = list(
            UserProfile.objects.using(database).filter(user_id=user_id).order_by("id")
        )
        if len(profiles) <= 1:
            continue
        selected = next((row for row in profiles if row.profile_picture), profiles[0])
        UserProfile.objects.using(database).filter(user_id=user_id).exclude(
            pk=selected.pk
        ).delete()

    for user in User.objects.using(database).all().iterator():
        normalized = (user.email or "").strip().lower()
        if user.email != normalized:
            user.email = normalized
            user.save(update_fields=("email",), using=database)
        UserProfile.objects.using(database).get_or_create(user_id=user.id)

    duplicate_email = (
        User.objects.using(database)
        .exclude(email="")
        .values("email")
        .annotate(row_count=models.Count("id"))
        .filter(row_count__gt=1)
        .order_by("email")
        .first()
    )
    if duplicate_email:
        raise RuntimeError(
            "Case-insensitive duplicate user emails require manual reconciliation."
        )


def create_email_index(apps, schema_editor):
    schema_editor.execute(
        "CREATE UNIQUE INDEX auth_user_email_ci_unique "
        "ON auth_user (LOWER(email)) WHERE email <> ''"
    )


def drop_email_index(apps, schema_editor):
    schema_editor.execute("DROP INDEX IF EXISTS auth_user_email_ci_unique")


class Migration(migrations.Migration):
    dependencies = [
        ("account", "0003_userprofile_user"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(reconcile_profiles_and_emails, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="userprofile",
            name="user",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="profile",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(create_email_index, drop_email_index),
    ]
