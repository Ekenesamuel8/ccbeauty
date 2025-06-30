from pathlib import Path
import os
from dotenv import load_dotenv
from decouple import config

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables
load_dotenv()

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = [
    'localhost',           # For local testing
    '127.0.0.1',          # For local testing
    'your-domain.com',    # Replace with your actual domain (if applicable)
    'your-s3-bucket-url', # Replace with your AWS S3 custom domain (e.g., ccbeatystatic.s3.af-south-1.amazonaws.com)

]

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

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}
# RDS Configuration FROM AWS
""""
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST'),
        'PORT': config('DB_PORT'),
    }
}
"""
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
    AWS_STORAGE_BUCKET_NAME = 'ccbeatystatic'
    AWS_S3_REGION_NAME = 'af-south-1'
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
EMAIL_PORT = 587  # Use 587 instead of 465 for TLS
EMAIL_USE_TLS = True #false
EMAIL_USE_SSL = False #true
EMAIL_HOST_USER = config('EMAIL_HOST_USERS')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST')

# Paystack settings
PAYSTACK_PUBLIC_KEY = config('PAYSTACK_PUBLIC_KEY')
PAYSTACK_SECRET_KEY = config('PAYSTACK_SECRET_KEY')

# Allow popups for Paystack
SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin-allow-popups'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

