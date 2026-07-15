"""Safe local-development settings with no required external services."""

from .base import *  # noqa: F403


DEBUG = True
SECRET_KEY = env_value(  # noqa: F405
    "SECRET_KEY",
    default="django-insecure-development-only-ccbeauty-do-not-use-in-production",
)
ALLOWED_HOSTS = env_list(  # noqa: F405
    "DJANGO_ALLOWED_HOSTS",
    default=("localhost", "127.0.0.1", "[::1]", "testserver"),
)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": env_value("SQLITE_PATH", default=BASE_DIR / "db.sqlite3"),  # noqa: F405
        "TEST": {"NAME": None},
    }
}

MEDIA_ROOT = BASE_DIR / "media"  # noqa: F405
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
    },
}

if env_bool("DEVELOPMENT_USE_SMTP", default=False):  # noqa: F405
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = env_value("SMTP_HOST", default="smtp.gmail.com")  # noqa: F405
    EMAIL_PORT = int(env_value("SMTP_PORT", default="465"))  # noqa: F405
    EMAIL_USE_TLS = env_bool("SMTP_USE_TLS", default=False)  # noqa: F405
    EMAIL_USE_SSL = env_bool("SMTP_USE_SSL", default=True)  # noqa: F405
    EMAIL_HOST_USER = env_value(  # noqa: F405
        "EMAIL_HOST_USER", "EMAIL_HOST_USERS", default=""
    )
    EMAIL_HOST_PASSWORD = env_value(  # noqa: F405
        "EMAIL_HOST_PASSWORD", "EMAIL_HOST", default=""
    )
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

