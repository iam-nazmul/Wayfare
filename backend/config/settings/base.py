from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
env.read_env(BASE_DIR.parent / ".env", overwrite=False)

SECRET_KEY = env("SECRET_KEY", default="insecure-dev-key")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "corsheaders",
    "drf_spectacular",
    "django_celery_beat",
    "apps.common",
    "apps.accounts",
    "apps.catalog",
    "apps.inventory",
    "apps.pricing",
    "apps.booking",
    "apps.payments",
    "apps.ticketing",
    "apps.ops",
    "apps.analytics",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.common.middleware.RequestIDMiddleware",
    "apps.analytics.middleware.RequestLogMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": env.db(
        "DATABASE_URL", default="postgres://wayfare:wayfare@postgres:5432/wayfare"
    )
}
DATABASES["default"]["ATOMIC_REQUESTS"] = False
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

# --- Redis -------------------------------------------------------------------
REDIS_URL = env("REDIS_URL", default="redis://redis:6379")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": f"{REDIS_URL}/2",
    }
}
REDIS_LOCK_URL = f"{REDIS_URL}/3"
REDIS_RATELIMIT_URL = f"{REDIS_URL}/4"
REDIS_OFFER_URL = f"{REDIS_URL}/5"
REDIS_EVENTS_URL = f"{REDIS_URL}/6"
EVENT_STREAM_KEY = "wayfare:events"
EVENT_STREAM_MAXLEN = 1_000_000

# --- DRF ---------------------------------------------------------------------
REST_FRAMEWORK = {
    # Bearer only. SessionAuthentication would authenticate any browser carrying a Django
    # session cookie from /admin, and then enforce CSRF on it — so a staff member with the
    # admin open got "CSRF Failed" on public endpoints like POST /bookings. The SPA cannot
    # answer that check either: CSRF_COOKIE_HTTPONLY hides the token from JS in production.
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.WayfareCursorPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.common.exceptions.problem_detail_handler",
    "DEFAULT_THROTTLE_CLASSES": ["apps.common.throttling.ScopedWindowRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {
        "search": "30/min",
        "search_authenticated": "120/min",
        "booking_create": "10/hour",
        # Higher than booking_create: a declined card is retried on the same booking.
        "payment": "30/hour",
        "login": "10/15min",
        "guest_retrieve": "5/15min",
        "collect": "600/min",
        "authenticated": "1000/hour",
    },
    "UNAUTHENTICATED_USER": "django.contrib.auth.models.AnonymousUser",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Wayfare API",
    "DESCRIPTION": "Flight inventory, booking and air-ticket management.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "OAS_VERSION": "3.1.0",
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": "/api/v1",
    # Several models expose a "status" choice set; name them explicitly or spectacular
    # invents StatusNNNEnum and the generated client names churn between builds.
    "ENUM_NAME_OVERRIDES": {
        "FlightStatusEnum": "apps.inventory.constants.FlightStatus.choices",
        "ScheduleStatusEnum": "apps.inventory.constants.ScheduleStatus.choices",
        "SeatStatusEnum": "apps.inventory.constants.SeatStatus.choices",
        "CabinEnum": "apps.inventory.constants.Cabin.choices",
        "AgencyStatusEnum": "apps.accounts.constants.AgencyStatus.choices",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=["http://localhost:5173"])
CORS_ALLOW_CREDENTIALS = True
# The SPA sends these on booking, payment and search calls; without them the browser blocks
# the request at preflight and the failure looks like a server error.
CORS_ALLOW_HEADERS = (
    "accept",
    "authorization",
    "content-type",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
    "idempotency-key",
    "if-match",
    "x-session-id",
    "x-request-id",
)
CORS_EXPOSE_HEADERS = ["ETag", "X-Request-ID"]

# --- Celery ------------------------------------------------------------------
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=f"{REDIS_URL}/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default=f"{REDIS_URL}/1")
CELERY_RESULT_EXPIRES = 3600
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_TIME_LIMIT = 300
CELERY_TASK_SOFT_TIME_LIMIT = 270
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TIMEZONE = "UTC"

# --- ClickHouse --------------------------------------------------------------
CLICKHOUSE = {
    "HOST": env("CLICKHOUSE_HOST", default="clickhouse"),
    "PORT": env.int("CLICKHOUSE_PORT", default=8123),
    "DATABASE": env("CLICKHOUSE_DB", default="wayfare"),
    "USER": env("CLICKHOUSE_USER", default="default"),
    "PASSWORD": env("CLICKHOUSE_PASSWORD", default=""),
    "ASYNC_INSERT": env.bool("CLICKHOUSE_ASYNC_INSERT", default=True),
}

ANALYTICS_ENABLED = env.bool("ANALYTICS_ENABLED", default=True)

# --- Domain rules ------------------------------------------------------------
HOLD_TTL_MINUTES = env.int("HOLD_TTL_MINUTES", default=20)
OFFER_TTL_MINUTES = env.int("OFFER_TTL_MINUTES", default=15)
CHECKIN_OPEN_HOURS = env.int("CHECKIN_OPEN_HOURS", default=48)
CHECKIN_CLOSE_MINUTES = env.int("CHECKIN_CLOSE_MINUTES", default=60)
REFUND_AUTO_APPROVE_LIMIT = env.int("REFUND_AUTO_APPROVE_LIMIT", default=500)
DEFAULT_CURRENCY = env("DEFAULT_CURRENCY", default="USD")
MCT_DOMESTIC_MINUTES = env.int("MCT_DOMESTIC_MINUTES", default=45)
MCT_INTERNATIONAL_MINUTES = env.int("MCT_INTERNATIONAL_MINUTES", default=90)

PAYMENT_PROVIDER = env("PAYMENT_PROVIDER", default="sandbox")
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY", default="")
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET", default="")

# --- Email -------------------------------------------------------------------
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", default="mailpit")
EMAIL_PORT = env.int("EMAIL_PORT", default=1025)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@wayfare.local")

# --- Logging -----------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"json": {"()": "apps.common.logging.JSONFormatter"}},
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "json"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.db.backends": {"level": "WARNING", "handlers": ["console"], "propagate": False},
        "wayfare": {"level": "INFO", "handlers": ["console"], "propagate": False},
    },
}
