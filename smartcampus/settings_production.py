"""
Production settings for smartcampus project.

This file contains production-specific settings that override the base settings.
Import this in your production environment by setting:
DJANGO_SETTINGS_MODULE=smartcampus.settings_production
"""

import os
from pathlib import Path

# Load environment variables from .env file
try:
    from decouple import config
except ImportError:
    # Fallback if python-decouple is not installed
    def config(key, default=None):
        return os.environ.get(key, default)

# Import base settings
from smartcampus.settings import (
    BASE_DIR, INSTALLED_APPS, MIDDLEWARE, ROOT_URLCONF, TEMPLATES,
    WSGI_APPLICATION, AUTH_PASSWORD_VALIDATORS, LANGUAGE_CODE, TIME_ZONE,
    USE_I18N, USE_TZ, DEFAULT_AUTO_FIELD, AUTH_USER_MODEL, LOGIN_URL,
    LOGIN_REDIRECT_URL, LOGOUT_REDIRECT_URL, handler403, handler404, handler500
)

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY')
if not SECRET_KEY:
    raise ValueError("SECRET_KEY must be set in .env file or environment variable")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=False, cast=bool)

# Allowed hosts - set via .env file (comma-separated)
ALLOWED_HOSTS_STR = config('ALLOWED_HOSTS', default='')
ALLOWED_HOSTS = [host.strip() for host in ALLOWED_HOSTS_STR.split(',') if host.strip()]
if not ALLOWED_HOSTS:
    raise ValueError("ALLOWED_HOSTS must be set in .env file (comma-separated list)")

# Database configuration from environment variables
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': config('DB_NAME', default='smartcampus'),
        'USER': config('DB_USER', default='root'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='3306'),
        'OPTIONS': {
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            'charset': 'utf8mb4',
        },
        'CONN_MAX_AGE': 600,  # Keep connections alive for 10 minutes
    }
}

# Static files (CSS, JavaScript, Images)
# In production, collectstatic will gather all static files here
STATIC_URL = '/static/'
STATIC_ROOT = config('STATIC_ROOT', default=str(BASE_DIR / 'staticfiles'))
STATICFILES_DIRS = [BASE_DIR / 'static'] if DEBUG else []

# Media files (User uploads)
MEDIA_URL = '/media/'
MEDIA_ROOT = config('MEDIA_ROOT', default=str(BASE_DIR / 'media'))

# Security Settings for Production
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=True, cast=bool)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'SAMEORIGIN'  # Keep this for PDF previews

# HSTS (HTTP Strict Transport Security)
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Base URL for callbacks (used by Daraja M-Pesa)
BASE_URL = config('BASE_URL', default='https://yourdomain.com')

# Caching Configuration - Use Redis in production
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': config('REDIS_URL', default='redis://127.0.0.1:6379/1'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        },
        'KEY_PREFIX': 'smartcampus',
        'TIMEOUT': 300,
    }
}

# Logging Configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': config('LOG_FILE', default=str(BASE_DIR / 'logs' / 'django.log')),
            'maxBytes': 1024 * 1024 * 15,  # 15MB
            'backupCount': 10,
            'formatter': 'verbose',
        },
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'root': {
        'handlers': ['file', 'console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.security': {
            'handlers': ['file', 'console'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}

# Email Configuration (if needed)
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@yourdomain.com')

