from pathlib import Path
import os
from dotenv import load_dotenv
from decouple import config

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables
load_dotenv()

SECRET_KEY = config('SECRET_KEY')

DEBUG = False

ALLOWED_HOSTS = [
    #'localhost',           # For local testing
    #'127.0.0.1',          # For local testing
    #'your-domain.com',    # Replace with your actual domain (if applicable)
    #'your-s3-bucket-url', # Replace with your AWS S3 custom domain (e.g., ccbeatystatic.s3.af-south-1.amazonaws.com)
    '*',                   # Allow all hosts (for development only, restrict in production)
]

# CSRF_TRUSTED_ORIGINS = [

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'ccstore',
    'cart',
    'mathfilters',
    'account',
    'payment',
    'crispy_forms',
    'corsheaders',
    'storages',
    #'django_recaptcha',
    'axes',  # Add Axes for rate limiting
]

CRISPY_TEMPLATE_PACK = 'bootstrap4'

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'axes.middleware.AxesMiddleware',  # Add Axes middleware for rate limiting
]

ROOT_URLCONF = 'ecommerce.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'ccstore.views.category',
                'cart.session_context.cart',
            ],
        },
    },
]

WSGI_APPLICATION = 'ecommerce.wsgi.application'

"""
# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}
# RDS Configuration FROM AWS
"""
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('NAME'),
        'USER': config('USER'),
        'PASSWORD': config('PASSWORD'),
        'HOST': config('HOST'),
        'PORT': config('PORT'),
    }
}

CORS_ALLOWED_ORIGINS = [
    'https://paystack.com',
    'https://checkout.paystack.com',
]

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

if DEBUG:
    STATIC_URL = '/static/'
    STATICFILES_DIRS = [
        BASE_DIR / "static",
    ]

    MEDIA_URL = '/media/'

    MEDIA_ROOT = BASE_DIR / 'static/media'
else:
    # AWS S3 settings
    AWS_STORAGE_BUCKET_NAME = os.getenv('AWS_STORAGE_BUCKET_NAME')
    AWS_S3_REGION_NAME = os.getenv('AWS_S3_REGION_NAME')
    AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
    AWS_S3_CUSTOM_DOMAIN = f'{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com'
    AWS_DEFAULT_ACL = None
    AWS_S3_FILE_OVERWRITE = False

    STATIC_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/static/'
    MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/images/'

    STORAGES = {
        'default': {
            'BACKEND': 'storages.backends.s3boto3.S3Boto3Storage',
            'OPTIONS': {
                'bucket_name': 'ccbeatystatic',
                'region_name': 'af-south-1',
            },
        },
        'staticfiles': {
            'BACKEND': 'storages.backends.s3boto3.S3Boto3Storage',
            'OPTIONS': {
                'bucket_name': 'ccbeatystatic',
                'region_name': 'af-south-1',
            },
        },
    }

# Email settings
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend' #'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 465  # Use 587 instead of 465 for TLS
EMAIL_USE_TLS = False #false
EMAIL_USE_SSL = True #true
EMAIL_HOST_USER = config('EMAIL_HOST_USERS')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST')

# Paystack settings
PAYSTACK_PUBLIC_KEY = config('PAYSTACK_PUBLIC_KEY')
PAYSTACK_SECRET_KEY = config('PAYSTACK_SECRET_KEY')

# Allow popups for Paystack
SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin-allow-popups'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Recaptcha settings
#RECAPTCHA_ENABLED = False
#RECAPTCHA_PUBLIC_KEY = config('RECAPTCHA_PUBLIC_KEY')
#RECAPTCHA_PRIVATE_KEY = config('RECAPTCHA_PRIVATE_KEY')

"""
# Session and cookie security settings
SESSION_COOKIE_SECURE = True  # Only send cookies over HTTPS
CSRF_COOKIE_SECURE = True  # Only send CSRF cookies over HTTPS
SESSION_COOKIE_HTTPONLY = True  # Prevent JavaScript access to session cookies
SESSION_COOKIE_SAMESITE = 'Lax'  # Protect against CSRF in cross-site requests
"""

SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE = 600 # Session expires after 10 minutes (600 seconds) of inactivity
SESSION_SAVE_EVERY_REQUEST = True

AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesBackend',
    'django.contrib.auth.backends.ModelBackend',
]

# Cache for django-ratelimit, this is for local development
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}

''' Redis cache configuration for django-ratelimit 
switch to this for django-ratelimit caching for production use
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}'''

AXES_HANDLER = 'axes.handlers.database.AxesDatabaseHandler'

AXES_LOCKOUT_TEMPLATE = 'account/lockout.html'

AXES_ENABLED = True #help me debug
AXES_LOCK_OUT_BY_USER = True
AXES_LOCK_OUT_BY_IP = False
AXES_ONLY_USER_FAILURES = True  # ✅ Only track failures by user, not IP or user agent and this help too
AXES_FAILURE_LIMIT = 5
AXES_RESET_ON_SUCCESS = True

