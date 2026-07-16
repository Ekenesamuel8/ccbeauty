"""Settings shared by every CCbeauty environment."""

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]


def env_value(name, *aliases, default=None):
    """Return the first configured environment variable without exposing it."""
    for candidate in (name, *aliases):
        value = os.environ.get(candidate)
        if value is not None and value != "":
            return value
    return default


def required_env(name, *aliases):
    value = env_value(name, *aliases)
    if value is None:
        accepted = ", ".join((name, *aliases))
        raise RuntimeError(f"A required environment variable is missing: {accepted}")
    return value


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{name} must be true or false")


def env_list(name, default=()):
    value = os.environ.get(name)
    if value is None:
        return list(default)
    return [item.strip() for item in value.split(",") if item.strip()]


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "ccstore",
    "cart",
    "mathfilters",
    "account",
    "payment",
    "crispy_forms",
    "corsheaders",
    "storages",
    "axes",
]

CRISPY_TEMPLATE_PACK = "bootstrap4"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "axes.middleware.AxesMiddleware",
]

ROOT_URLCONF = "ecommerce.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "ccstore.views.category",
                "cart.session_context.cart",
            ],
        },
    },
]

WSGI_APPLICATION = "ecommerce.wsgi.application"
ASGI_APPLICATION = "ecommerce.asgi.application"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "/media/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

DEFAULT_FROM_EMAIL = env_value(
    "DEFAULT_FROM_EMAIL",
    "EMAIL_HOST_USER",
    "EMAIL_HOST_USERS",
    default="webmaster@localhost",
)

# Optional during ordinary development; production validates both values.
PAYSTACK_PUBLIC_KEY = env_value("PAYSTACK_PUBLIC_KEY", default="")
PAYSTACK_SECRET_KEY = env_value("PAYSTACK_SECRET_KEY", default="")
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin-allow-popups"

# Preserved from the existing configuration. This controls requests to Django,
# not Django's outbound Paystack API calls.
CORS_ALLOWED_ORIGINS = [
    "https://paystack.com",
    "https://checkout.paystack.com",
]

SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE = 600
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesBackend",
    "account.auth_backend.EmailOrUsernameModelBackend",
    "django.contrib.auth.backends.ModelBackend",
]

CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}

AXES_HANDLER = "axes.handlers.database.AxesDatabaseHandler"
AXES_LOCKOUT_TEMPLATE = "account/lockout.html"
AXES_ENABLED = True
AXES_LOCK_OUT_BY_USER = True
AXES_LOCK_OUT_BY_IP = False
AXES_FAILURE_LIMIT = 5
AXES_RESET_ON_SUCCESS = True
