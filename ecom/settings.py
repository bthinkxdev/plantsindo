import os
from pathlib import Path
from decouple import config
BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = config('DJANGO_SECRET_KEY')
DEBUG = config('DJANGO_DEBUG', cast=bool)
DEBUG_TRACE = config('DEBUG_TRACE', default=False, cast=bool)
ALLOWED_HOSTS_STR = config('ALLOWED_HOSTS')
ALLOWED_HOSTS = [host.strip().strip('\'"') for host in ALLOWED_HOSTS_STR.split(',') if host.strip()]
if DEBUG:
    ALLOWED_HOSTS = ['*']
else:
    for h in ('localhost', '127.0.0.1', '*'):
        if h not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(h)
INSTALLED_APPS = ['storages', 'django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles', 'app']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware', 'whitenoise.middleware.WhiteNoiseMiddleware', 'app.middleware.DebugTraceMiddleware', 'django.contrib.sessions.middleware.SessionMiddleware', 'django.middleware.common.CommonMiddleware', 'django.middleware.csrf.CsrfViewMiddleware', 'django.contrib.auth.middleware.AuthenticationMiddleware', 'app.middleware.EnsureGuestSessionMiddleware', 'django.contrib.messages.middleware.MessageMiddleware', 'django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF = 'ecom.urls'
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [BASE_DIR / 'templates'], 'APP_DIRS': True, 'OPTIONS': {'context_processors': ['django.template.context_processors.request', 'django.contrib.auth.context_processors.auth', 'django.contrib.messages.context_processors.messages', 'app.context_processors.site_contact_context', 'app.context_processors.cart_context', 'app.context_processors.wishlist_context', 'app.context_processors.admin_message_badge', 'app.context_processors.delivery_settings', 'app.context_processors.home_section_flags', 'app.context_processors.admin_product_settings', 'app.context_processors.storefront_brand', 'app.context_processors.search_typed_suggestions']}}]
WSGI_APPLICATION = 'ecom.wsgi.application'

_postgres_db = config('POSTGRES_DB', default='').strip()
if _postgres_db:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': _postgres_db,
            'USER': config('POSTGRES_USER'),
            'PASSWORD': config('POSTGRES_PASSWORD', default=''),
            'HOST': config('POSTGRES_HOST', default='localhost'),
            'PORT': config('POSTGRES_PORT', default='5432'),
            'CONN_MAX_AGE': config('DB_CONN_MAX_AGE', default=60, cast=int),
            'OPTIONS': {
                'connect_timeout': config('DB_CONNECT_TIMEOUT', default=10, cast=int),
            },
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
AUTH_PASSWORD_VALIDATORS = [{'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'}, {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'}, {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'}, {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'}]
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
SESSION_COOKIE_AGE = 60 * 60 * 24 * 7
SESSION_SAVE_EVERY_REQUEST = False
SESSION_COOKIE_SECURE = False
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
DELIVERY_INTEGRATED = False
WISHLIST_ENABLED = True
HOME_DEAL_OF_DAY_ENABLED = True
HOME_FEATURED_ENABLED = True
HOME_BESTSELLER_ENABLED = True
HOME_RECENTLY_ADDED_ENABLED = True
ALLOW_ATTRIBUTES_AND_VARIANTS = True
REVIEW_ENABLED = True
FLAT_DELIVERY_CHARGE = 60
MAX_CART_QTY = 10
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "unique-snowflake",  
    },
    "locmem": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "home-cache",
        "OPTIONS": {"MAX_ENTRIES": 500},
    },
}
HOME_CACHE_TTL = 120
SHOP_CACHE_TTL = 60

CAPTCHA_SECRET = config('CAPTCHA_SECRET', default='').strip()
CAPTCHA_SITE_KEY = config('CAPTCHA_SITE_KEY', default='').strip()
CAPTCHA_PROVIDER = config('CAPTCHA_PROVIDER', default='turnstile')
CAPTCHA_VERIFY_URL = 'https://challenges.cloudflare.com/turnstile/v0/siteverify'

EMAIL_BACKEND = 'app.email_backend.CustomEmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = config('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER
ADMIN_NOTIFICATION_EMAILS = ['adithyamc@bthinkx.com']
SITE_PHONE = config('SITE_PHONE', default='+91 7559947750')
SITE_WHATSAPP = config('SITE_WHATSAPP', default='917559947750')
SITE_EMAIL = config('SITE_EMAIL', default='hello@plantsindo.com')
SITE_INSTAGRAM = config('SITE_INSTAGRAM', default='plantsindo.co')
SITE_INSTAGRAM_URL = config(
    'SITE_INSTAGRAM_URL',
    default='https://www.instagram.com/plantsindo.co/',
)
SITE_FACEBOOK_URL = config(
    'SITE_FACEBOOK_URL',
    default='https://www.facebook.com/profile.php?id=61587089061711',
)
SITE_BRAND = config('SITE_BRAND', default='Plantsindo')
SITE_TAGLINE = config('SITE_TAGLINE', default='Calm corners, lush leaves')
RZP_CLIENT_ID = config('RZP_CLIENT_ID')
RZP_CLIENT_SECRET = config('RZP_CLIENT_SECRET')
SHIPROCKET_EMAIL = config('SHIPROCKET_EMAIL')
SHIPROCKET_PASSWORD = config('SHIPROCKET_PASSWORD')
USE_S3 = config('USE_S3', default=False, cast=bool)
if USE_S3:
    AWS_ACCESS_KEY_ID = config('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = config('AWS_SECRET_ACCESS_KEY')
    AWS_STORAGE_BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME')
    AWS_S3_REGION_NAME = config('AWS_S3_REGION_NAME')
    AWS_S3_CUSTOM_DOMAIN = f'{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com'
    base_s3_object_params = {'CacheControl': 'max-age=86400'}
    _s3_tag_dict = {'project': config('AWS_S3_TAG_PROJECT', default='queen-orange'), 'app': config('AWS_S3_TAG_APP', default='media')}
    AWS_S3_CLIENT_TAG = config('AWS_S3_CLIENT_TAG', default='queen-orange')
    if AWS_S3_CLIENT_TAG:
        _s3_tag_dict['client'] = AWS_S3_CLIENT_TAG
    from s3_tagging_utils import build_safe_tags
    _s3_tagging_str = build_safe_tags(_s3_tag_dict)
    if _s3_tagging_str:
        base_s3_object_params['Tagging'] = _s3_tagging_str
    AWS_S3_OBJECT_PARAMETERS = base_s3_object_params
    AWS_DEFAULT_ACL = None
    AWS_S3_FILE_OVERWRITE = False
    AWS_QUERYSTRING_AUTH = False
    STORAGES = {'default': {'BACKEND': 'custom_storage.MediaFileStorage'}, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}
    MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/queen-orange/media/'
else:
    STORAGES = {'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'}, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}
    MEDIA_ROOT = BASE_DIR / 'media'
    MEDIA_URL = '/media/'
# ALLOWED_SERVICE_PINCODES = ('682001', '682002', '682003', '682016', '695001', '695002', '673001', '673002', '686001', '688001')
_CSRF_ORIGINS_STR = config(
    'CSRF_TRUSTED_ORIGINS',
    default=(
        'https://plantsindo.bthinkx.com,'
        'https://plants99.bthinkx.com,'
        'https://www.plantsindo.com,'
        'https://plantsindo.com'
    ),
)
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in _CSRF_ORIGINS_STR.split(',')
    if origin.strip()
]

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")