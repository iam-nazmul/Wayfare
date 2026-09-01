from .base import *  # noqa: F403

DEBUG = False
SECRET_KEY = "test-secret-key"

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Analytics is fire-and-forget in tests; never reach for a real ClickHouse.
ANALYTICS_ENABLED = False
