"""Production settings for PostgreSQL, Cloudflare R2, and HTTPS."""

from .base import *  # noqa: F403


DEBUG = False
SECRET_KEY = required_env("SECRET_KEY")  # noqa: F405
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")  # noqa: F405
if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
    raise RuntimeError(
        "DJANGO_ALLOWED_HOSTS must contain explicit production hostnames"
    )

CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")  # noqa: F405

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": required_env("DB_NAME", "SUPABASE_DB_NAME", "NAME"),  # noqa: F405
        "USER": required_env("DB_USER", "SUPABASE_DB_USER", "USER"),  # noqa: F405
        "PASSWORD": required_env(  # noqa: F405
            "DB_PASSWORD", "SUPABASE_DB_PASSWORD", "PASSWORD"
        ),
        "HOST": required_env("DB_HOST", "SUPABASE_DB_HOST", "HOST"),  # noqa: F405
        "PORT": env_value(  # noqa: F405
            "DB_PORT", "SUPABASE_DB_PORT", "PORT", default="5432"
        ),
        "OPTIONS": {
            "sslmode": env_value("DB_SSLMODE", default="require"),  # noqa: F405
        },
    }
}

STATIC_ROOT = BASE_DIR / "staticfiles"  # noqa: F405

CLOUDFLARE_R2_BUCKET_NAME = required_env("CLOUDFLARE_R2_BUCKET_NAME")  # noqa: F405
CLOUDFLARE_R2_ACCOUNT_ID = required_env("CLOUDFLARE_R2_ACCOUNT_ID")  # noqa: F405
CLOUDFLARE_R2_ACCESS_KEY_ID = required_env(  # noqa: F405
    "CLOUDFLARE_R2_ACCESS_KEY_ID"
)
CLOUDFLARE_R2_SECRET_ACCESS_KEY = required_env(  # noqa: F405
    "CLOUDFLARE_R2_SECRET_ACCESS_KEY"
)
CLOUDFLARE_R2_CUSTOM_DOMAIN = required_env(  # noqa: F405
    "CLOUDFLARE_R2_CUSTOM_DOMAIN"
)
CLOUDFLARE_R2_ENDPOINT_URL = env_value(  # noqa: F405
    "CLOUDFLARE_R2_ENDPOINT_URL",
    default=f"https://{CLOUDFLARE_R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
)

MEDIA_URL = f"https://{CLOUDFLARE_R2_CUSTOM_DOMAIN.strip('/')}/"
STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        "OPTIONS": {
            "bucket_name": CLOUDFLARE_R2_BUCKET_NAME,
            "access_key": CLOUDFLARE_R2_ACCESS_KEY_ID,
            "secret_key": CLOUDFLARE_R2_SECRET_ACCESS_KEY,
            "endpoint_url": CLOUDFLARE_R2_ENDPOINT_URL,
            "region_name": "auto",
            "default_acl": None,
            "file_overwrite": False,
            "querystring_auth": False,
            "custom_domain": CLOUDFLARE_R2_CUSTOM_DOMAIN,
        },
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
    },
}

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env_value("SMTP_HOST", default="smtp.gmail.com")  # noqa: F405
EMAIL_PORT = int(env_value("SMTP_PORT", default="465"))  # noqa: F405
EMAIL_USE_TLS = env_bool("SMTP_USE_TLS", default=False)  # noqa: F405
EMAIL_USE_SSL = env_bool("SMTP_USE_SSL", default=True)  # noqa: F405
EMAIL_HOST_USER = required_env("EMAIL_HOST_USER", "EMAIL_HOST_USERS")  # noqa: F405
EMAIL_HOST_PASSWORD = required_env(  # noqa: F405
    "EMAIL_HOST_PASSWORD", "EMAIL_HOST"
)

PAYSTACK_PUBLIC_KEY = required_env("PAYSTACK_PUBLIC_KEY")  # noqa: F405
PAYSTACK_SECRET_KEY = required_env("PAYSTACK_SECRET_KEY")  # noqa: F405

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = env_bool("DJANGO_USE_X_FORWARDED_HOST", default=True)  # noqa: F405
SECURE_HSTS_SECONDS = int(env_value("DJANGO_HSTS_SECONDS", default="3600"))  # noqa: F405
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool(  # noqa: F405
    "DJANGO_HSTS_INCLUDE_SUBDOMAINS", default=False
)
SECURE_HSTS_PRELOAD = env_bool("DJANGO_HSTS_PRELOAD", default=False)  # noqa: F405

