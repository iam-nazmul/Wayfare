from .base import *  # noqa: F403

DEBUG = True
ALLOWED_HOSTS = ["*"]

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

SPECTACULAR_SETTINGS["SERVE_INCLUDE_SCHEMA"] = True  # noqa: F405
