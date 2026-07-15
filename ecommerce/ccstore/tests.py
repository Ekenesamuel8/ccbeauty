from importlib import import_module

from django.conf import settings
from django.db import connection
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import resolve, reverse

from ecommerce.settings import development


class DevelopmentSettingsTests(SimpleTestCase):
    def test_development_settings_are_isolated_from_external_services(self):
        # Django's test runner forces the active DEBUG setting to False while
        # tests run, so inspect the environment module's declared value.
        self.assertTrue(development.DEBUG)
        self.assertEqual(settings.DJANGO_ENVIRONMENT, "development")
        self.assertEqual(
            settings.DATABASES["default"]["ENGINE"],
            "django.db.backends.sqlite3",
        )
        self.assertEqual(
            settings.STORAGES["default"]["BACKEND"],
            "django.core.files.storage.FileSystemStorage",
        )
        self.assertNotIn("supabase", str(settings.DATABASES["default"]).lower())
        self.assertNotIn("s3boto3", str(settings.STORAGES["default"]).lower())

    def test_root_url_configuration_imports_and_resolves(self):
        urlconf = import_module(settings.ROOT_URLCONF)
        self.assertTrue(urlconf.urlpatterns)
        self.assertEqual(resolve(reverse("store")).url_name, "store")


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class StoreSmokeTests(TestCase):
    def test_store_renders_without_catalog_fixtures(self):
        response = self.client.get(reverse("store"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "ccstore/store.html")
        self.assertContains(response, "All products")
        self.assertEqual(connection.vendor, "sqlite")
        self.assertNotEqual(
            str(connection.settings_dict["NAME"]),
            str(settings.BASE_DIR / "db.sqlite3"),
        )
