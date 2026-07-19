"""
Django settings for core_project project.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# ------------------------------------------------------------------
# SECURITY
# ------------------------------------------------------------------
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    raise RuntimeError("DJANGO_SECRET_KEY environment variable is not set")

DEBUG = os.environ.get('DEBUG', 'False') == 'True'

_allowed = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
_render_host = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
if _render_host:
    _allowed.append(_render_host)
ALLOWED_HOSTS = [h.strip() for h in _allowed if h.strip()]

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ------------------------------------------------------------------
# CORS  (allow the PWA/mobile client to call the API)
# ------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = os.environ.get(
    'CORS_ALLOWED_ORIGINS', 'http://localhost:3000,http://127.0.0.1:8000'
).split(',')
CORS_ALLOW_CREDENTIALS = True

# ------------------------------------------------------------------
# APPS & MIDDLEWARE
# ------------------------------------------------------------------
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'core',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'csp.middleware.CSPMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core_project.wsgi.application'

# ------------------------------------------------------------------
# DATABASE
# ------------------------------------------------------------------
_db_url = os.environ.get('DATABASE_URL', '')
if _db_url:
    import dj_database_url

    DATABASES = {'default': dj_database_url.config(default=_db_url)}
    DATABASES['default']['CONN_MAX_AGE'] = 600
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
            'CONN_MAX_AGE': 0,
        }
    }

# ------------------------------------------------------------------
# PASSWORD VALIDATION
# ------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ------------------------------------------------------------------
# INTERNATIONALISATION
# ------------------------------------------------------------------
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# ------------------------------------------------------------------
# STATIC FILES
# ------------------------------------------------------------------
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'core' / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# ------------------------------------------------------------------
# THIRD-PARTY API KEYS  (set these in your .env — never hardcode)
# ------------------------------------------------------------------
SUPABASE_URL            = os.environ.get('SUPABASE_URL', '')
SUPABASE_ANON_KEY       = os.environ.get('SUPABASE_ANON_KEY', '')
SUPABASE_SERVICE_KEY    = os.environ.get('SUPABASE_SERVICE_KEY', '')

STRIPE_PUBLISHABLE_KEY  = os.environ.get('STRIPE_PUBLISHABLE_KEY', '')
STRIPE_SECRET_KEY       = os.environ.get('STRIPE_SECRET_KEY', '')
STRIPE_WEBHOOK_SECRET   = os.environ.get('STRIPE_WEBHOOK_SECRET', '')

GIPHY_API_KEY                = os.environ.get('GIPHY_API_KEY', '')
RESEND_API_KEY               = os.environ.get('RESEND_API_KEY', '')
GOOGLE_CLOUD_VISION_API_KEY  = os.environ.get('GOOGLE_CLOUD_VISION_API_KEY', '')

# Eddie, the in-app assistant. The key is server-side only and must never be
# returned by /api/config/ — the browser talks to /api/eddie/*, never to
# api.anthropic.com directly.
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
EDDIE_MODEL       = os.environ.get('EDDIE_MODEL', 'claude-opus-4-8')

# Daily per-user caps, enforced server-side before any model call.
EDDIE_LIMIT_MESSAGES    = int(os.environ.get('EDDIE_LIMIT_MESSAGES', '40'))
EDDIE_LIMIT_ATTACHMENTS = int(os.environ.get('EDDIE_LIMIT_ATTACHMENTS', '10'))
EDDIE_LIMIT_IMAGES      = int(os.environ.get('EDDIE_LIMIT_IMAGES', '5'))

# Verification (Didit — replaces Stripe Identity), email (Brevo), voice (ElevenLabs)
DIDIT_API_KEY                = os.environ.get('DIDIT_API_KEY', '')
DIDIT_WORKFLOW_ID            = os.environ.get('DIDIT_WORKFLOW_ID', '')
BREVO_API_KEY                = os.environ.get('BREVO_API_KEY', '')
ELEVENLABS_API_KEY           = os.environ.get('ELEVENLABS_API_KEY', '')

# ------------------------------------------------------------------
# SECURITY HEADERS
# ------------------------------------------------------------------
SECURE_BROWSER_XSS_FILTER       = True
SECURE_CONTENT_TYPE_NOSNIFF     = True
X_FRAME_OPTIONS                 = 'DENY'
SESSION_COOKIE_HTTPONLY         = True
CSRF_COOKIE_HTTPONLY            = True
# Behind Render/any reverse proxy, trust the forwarded-proto header so HTTPS
# detection (secure cookies, SSL redirect, HSTS) works correctly.
SECURE_PROXY_SSL_HEADER         = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT             = os.environ.get('SECURE_SSL_REDIRECT', 'False') == 'True'
SESSION_COOKIE_SECURE           = not DEBUG
SESSION_COOKIE_SAMESITE         = 'Lax'
CSRF_COOKIE_SAMESITE            = 'Lax'
SECURE_HSTS_SECONDS             = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS  = True
SECURE_HSTS_PRELOAD             = True

# ------------------------------------------------------------------
# CACHE  (Redis in prod, local memory in dev)
# ------------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/1"),
    } if os.environ.get("REDIS_URL") else {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
    }
}

# Rate limiting is only meaningful in production where Redis is shared across workers.
# In local dev (no REDIS_URL), disable it so the dummy cache doesn't trigger errors.
RATELIMIT_ENABLE = bool(os.environ.get("REDIS_URL"))

# ------------------------------------------------------------------
# CONTENT SECURITY POLICY
# django-csp 4.x reads CONTENT_SECURITY_POLICY. The old CSP_* settings are
# ignored by 4.x, which is why no policy header was being sent at all.
#
# 'unsafe-inline' in script-src is unavoidable here: the UI is built on ~700
# inline on* handlers. Do NOT add a nonce to script-src -- a nonce makes
# browsers ignore 'unsafe-inline', which would break every onclick in the app.
# The policy still blocks foreign script sources, plugins, base-tag hijacking
# and framing, which is the bulk of the practical benefit.
# ------------------------------------------------------------------
CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": ["'self'"],
        "script-src": [
            "'self'", "'unsafe-inline'",
            # MediaPipe's segmentation model is WebAssembly, and a CSP without
            # this blocks WebAssembly.instantiate outright -- which silently
            # broke every cutout with "Segmentation failed". This is the narrow
            # directive: it permits wasm compilation WITHOUT allowing eval() of
            # arbitrary strings, so do NOT relax it to 'unsafe-eval'.
            "'wasm-unsafe-eval'",
            "https://cdn.jsdelivr.net",       # supabase-js, livekit-client
            "https://cdnjs.cloudflare.com",   # font-awesome, leaflet, qrcode
            "https://js.stripe.com",
            "https://js.paystack.co",
        ],
        "style-src": ["'self'", "'unsafe-inline'", "https://cdnjs.cloudflare.com"],
        "font-src": ["'self'", "data:", "https://cdnjs.cloudflare.com"],
        # Avatars, Giphy, OSM tiles and Supabase storage all serve images.
        "img-src": ["'self'", "data:", "blob:", "https:"],
        "media-src": ["'self'", "data:", "blob:", "https:"],
        "connect-src": [
            "'self'",
            "https://cdn.jsdelivr.net",               # MediaPipe wasm + model files
            "https://*.supabase.co", "wss://*.supabase.co",
            "https://*.livekit.cloud", "wss://*.livekit.cloud",
            "https://itunes.apple.com",               # music search
            "https://lrclib.net",                     # synced lyrics
            "https://overpass-api.de",                # nearby places
            "https://nominatim.openstreetmap.org",    # geocoding + place search
            "https://api.open-meteo.com",             # weather sticker
            "https://ipapi.co",
            "https://api.giphy.com",
            "https://api.stripe.com",
            "https://api.paystack.co",
        ],
        "frame-src": [
            "'self'",
            "https://www.openstreetmap.org",  # location map embed
            "https://js.stripe.com",
            "https://hooks.stripe.com",
        ],
        "worker-src": ["'self'", "blob:"],
        "object-src": ["'none'"],
        "base-uri": ["'self'"],
        "form-action": ["'self'"],
        "frame-ancestors": ["'self'"],
    }
}

# ------------------------------------------------------------------
# LOGGING
# ------------------------------------------------------------------
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{levelname}] {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': os.environ.get('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'core': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}

# ------------------------------------------------------------------
# STATICFILES  (whitenoise for production serving)
# ------------------------------------------------------------------
if not DEBUG:
    STATICFILES_STORAGE = 'whitenoise.storage.StaticFilesStorage'
    MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')
