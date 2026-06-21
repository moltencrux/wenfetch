import os
from .base import *

DEBUG = os.environ.get("DJANGO_DEBUG", "False") == "True"
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]   # fails loudly if not set
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "").split(",")

MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Reverse proxy / HTTPS
# Works with both Caddy and nginx as long as they set X-Forwarded-Proto
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
CSRF_TRUSTED_ORIGINS = [
    o for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if o
]
