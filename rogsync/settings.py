"""
RogSync AI — Django Settings
"""
from pathlib import Path

from decouple import config, Csv

# ──────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent

# ──────────────────────────────────────────────
# Security
# ──────────────────────────────────────────────
SECRET_KEY = config("SECRET_KEY", default="insecure-dev-key-change-me")
DEBUG = config("DEBUG", default=True, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1,web", cast=Csv())
CSRF_TRUSTED_ORIGINS = config(
    "CSRF_TRUSTED_ORIGINS",
    default="http://localhost:8000,http://127.0.0.1:8000",
    cast=Csv(),
)

# ──────────────────────────────────────────────
# Application definition
# ──────────────────────────────────────────────
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Local
    "sync_app",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "rogsync.urls"

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
            ],
        },
    },
]

WSGI_APPLICATION = "rogsync.wsgi.application"

# ──────────────────────────────────────────────
# Database (Postgres in Docker; SQLite locally unless USE_POSTGRES=true)
# ──────────────────────────────────────────────
USE_POSTGRES = config("USE_POSTGRES", default=False, cast=bool)
if USE_POSTGRES:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": config("POSTGRES_DB", default="rogsync"),
            "USER": config("POSTGRES_USER", default="rogsync"),
            "PASSWORD": config("POSTGRES_PASSWORD", default="rogsync"),
            "HOST": config("POSTGRES_HOST", default="db"),
            "PORT": config("POSTGRES_PORT", default="5432"),
            "CONN_MAX_AGE": 60,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# ──────────────────────────────────────────────
# Internationalization
# ──────────────────────────────────────────────
LANGUAGE_CODE = "fa"
TIME_ZONE = "Asia/Tehran"
USE_I18N = True
USE_TZ = True

# ──────────────────────────────────────────────
# Static files
# ──────────────────────────────────────────────
STATIC_URL = "static/"
_static_dir = BASE_DIR / "static"
STATICFILES_DIRS = [_static_dir] if _static_dir.exists() else []
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ──────────────────────────────────────────────
# Default primary key
# ──────────────────────────────────────────────
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ──────────────────────────────────────────────
# Celery / Redis
# ──────────────────────────────────────────────
CELERY_BROKER_URL = config("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = config("CELERY_RESULT_BACKEND", default="redis://localhost:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE

# ──────────────────────────────────────────────
# WooCommerce — Source
# ──────────────────────────────────────────────
WC_SOURCE_URL = config("WC_SOURCE_URL", default="")
WC_SOURCE_KEY = config("WC_SOURCE_KEY", default="")
WC_SOURCE_SECRET = config("WC_SOURCE_SECRET", default="")

# ──────────────────────────────────────────────
# WooCommerce — Target
# ──────────────────────────────────────────────
WC_TARGET_URL = config("WC_TARGET_URL", default="")
WC_TARGET_KEY = config("WC_TARGET_KEY", default="")
WC_TARGET_SECRET = config("WC_TARGET_SECRET", default="")

# ──────────────────────────────────────────────
# OpenRouter API
# ──────────────────────────────────────────────
OPENROUTER_API_KEY = config("OPENROUTER_API_KEY", default="")
OPENROUTER_MODEL = config("OPENROUTER_MODEL", default="openai/gpt-4o")
