from pathlib import Path
from datetime import timedelta
import os
from corsheaders.defaults import default_headers, default_methods

BASE_DIR = Path(__file__).resolve().parent.parent

# ---------- БАЗОВЫЕ НАСТРОЙКИ ----------

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "dev-secret-change-me"  # локальный дефолт, в проде обязательно переопределяется
)

DEBUG = True
CORS_ALLOW_ALL_ORIGINS = True

_raw_hosts = os.environ.get("DJANGO_ALLOWED_HOSTS", "")
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "https://dev.mysite.ru:3443"]

# ---------- ПРИЛОЖЕНИЯ ----------

INSTALLED_APPS = [
    "colorfield",
    "admin_interface",
    "storages",

    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",

    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",

    "kodik.apps.KodikConfig",
    "users",
    "blog",
    "manga",
    "forum",
    "craft",
    "economy.apps.EconomyConfig",
    "customitem.apps.CustomItemConfig",
    "shop.apps.ShopConfig",

    "django_filters",
    "django_countries",

    # сторонние для админки
    "rangefilter",
    "django_extensions",
    "django_admin_listfilter_dropdown",
    "django_object_actions",
    "django_summernote",
    "import_export",

    "channels",
    "chats",
    "promo",
    "tinymce",
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
]

ROOT_URLCONF = "aki_backend.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
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

ASGI_APPLICATION = "aki_backend.asgi.application"

# ---------- БАЗА ДАННЫХ ----------

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "aki_beta",
        "USER": "postgres",
        "PASSWORD": "14060514",
        "HOST": "127.0.0.1",       # не 'localhost', чтобы не лез в SSL/IPv6
        "PORT": "5432",
        "OPTIONS": {"sslmode": "disable"},  # сервер без SSL — отключаем требование
    }
}

# ---------- ПАРОЛИ / ЛОКАЛИ ----------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "Asia/Almaty"
USE_I18N = True
USE_TZ = True

# ---------- СТАТИКА / МЕДИА ----------

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ---------- S3 MEDIA (django-storages) ----------

USE_S3_FOR_MEDIA = os.environ.get("USE_S3_FOR_MEDIA", "False").lower() == "true"

if USE_S3_FOR_MEDIA:
    AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
    AWS_STORAGE_BUCKET_NAME = os.environ.get("AWS_STORAGE_BUCKET_NAME")
    AWS_S3_ENDPOINT_URL = os.environ.get("AWS_S3_ENDPOINT_URL")
    AWS_S3_REGION_NAME = os.environ.get("AWS_S3_REGION_NAME", None)

    AWS_S3_CUSTOM_DOMAIN = os.environ.get("AWS_S3_CUSTOM_DOMAIN", "")

    AWS_S3_OBJECT_PARAMETERS = {
        "CacheControl": "max-age=86400",
    }

    DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"

    if AWS_S3_CUSTOM_DOMAIN:
        MEDIA_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/"
    else:
        MEDIA_URL = f"{AWS_S3_ENDPOINT_URL}/{AWS_STORAGE_BUCKET_NAME}/"

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "users.User"

X_FRAME_OPTIONS = "SAMEORIGIN"

# ---------- DRF / JWT ----------

REST_FRAMEWORK = {
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 24,
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "AUTH_HEADER_TYPES": ("Bearer", "JWT"),
    "SIGNING_KEY": SECRET_KEY,
    "ROTATE_REFRESH_TOKENS": False,
    "BLACKLIST_AFTER_ROTATION": False,
}

# ---------- CORS / CSRF ----------

CORS_ALLOW_CREDENTIALS = True

_raw_cors = os.environ.get("DJANGO_CORS_ORIGINS", "")
if _raw_cors:
    CORS_ALLOWED_ORIGINS = [o.strip() for o in _raw_cors.split(",") if o.strip()]
else:
    CORS_ALLOWED_ORIGINS = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        'https://akimori.ru',
    ]

_raw_csrf = os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "")
if _raw_csrf:
    CSRF_TRUSTED_ORIGINS = [o.strip() for o in _raw_csrf.split(",") if o.strip()]
else:
    CSRF_TRUSTED_ORIGINS = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        'https://akimori.ru',
    ]

CORS_ALLOW_HEADERS = list(default_headers) + [
    "authorization",
    "content-type",
    "x-requested-with",
]
CORS_ALLOW_METHODS = list(default_methods) + ["PATCH"]

SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# ---------- KODIK ----------

KODIK_PUBLIC_KEY = os.getenv("KODIK_PUBLIC_KEY", "")
KODIK_PRIVATE_KEY = os.getenv("KODIK_PRIVATE_KEY", "")
KODIK_VIDEO_LINKS_URL = os.getenv(
    "KODIK_VIDEO_LINKS_URL",
    "https://kodik.biz/api/video-links",
)
KODIK_DEADLINE_HOURS = int(os.getenv("KODIK_DEADLINE_HOURS", "6"))

KODIK_IMPORT = {
    "TOKEN": "ab83c7000f60d4266448b0507f673163",
    "BASE_URL": "https://kodikapi.com/list",
    "LIMIT": 100,
    "TYPES": "anime,anime-serial",
    "SORT": "updated_at",
    "ORDER": "desc",
    "all_status": "anons,ongoing,released",
    "WITH_MATERIAL_DATA": True,
    "WITH_EPISODES_DATA": True,
    "WITH_PAGE_LINKS": False,
    "SLEEP_BETWEEN_PAGES": 0.6,
    "HTTP_TIMEOUT": 30,
    "MAX_PAGES": None,
    "PAGE_HARD_TIMEOUT": 120,
    "VERBOSE_BY_DEFAULT": True,
}

# ---------- REDIS / CHANNELS ----------

REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [REDIS_URL],
        },
    },
}

# ---------- EMAIL ----------

if DEBUG:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    DEFAULT_FROM_EMAIL = "noreply@akimori.local"
else:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
    EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
    EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "True").lower() == "true"
    EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
    DEFAULT_FROM_EMAIL = EMAIL_HOST_USER or "noreply@akimori.local"

# ---------- TINYMCE ----------

TINYMCE_DEFAULT_CONFIG = {
    "plugins": (
        "advlist anchor autolink autosave charmap code codesample "
        "directionality emoticons fullscreen help image importcss "
        "insertdatetime link lists media nonbreaking pagebreak paste "
        "preview quickbars searchreplace table visualblocks visualchars "
        "wordcount autoresize"
    ),
    "menubar": "file edit view insert format tools table help",
    "toolbar": (
        "undo redo | blocks | bold italic underline strikethrough | "
        "forecolor backcolor | alignleft aligncenter alignright alignjustify | "
        "outdent indent | bullist numlist checklist | link image media table | "
        "codesample code | removeformat | fullscreen preview searchreplace"
    ),
    "block_formats": "Абзац=p; Заголовок 1=h1; Заголовок 2=h2; Заголовок 3=h3; Код=pre",
    "quickbars_selection_toolbar": "bold italic underline | h2 h3 blockquote | link",
    "quickbars_insert_toolbar": "image media table | hr pagebreak",

    "images_upload_url": "/tinymce/upload/",
    "images_upload_credentials": True,
    "automatic_uploads": True,
    "convert_urls": True,
    "relative_urls": False,
    "remove_script_host": False,

    "image_caption": True,
    "image_title": True,
    "image_dimensions": True,
    "media_live_embeds": True,

    "branding": False,
    "statusbar": True,
    "paste_data_images": False,
    "autoresize_bottom_margin": 40,
    "autoresize_overflow_padding": 16,

    "language": "ru",

    "content_style": """
      body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial; line-height:1.6;}
      img{max-width:100%; height:auto;}
      pre, code {font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;}
    """,

    "extended_valid_elements": (
        "iframe[src|frameborder|allowfullscreen|allow|referrerpolicy|width|height]"
    ),

    "autosave_ask_before_unload": True,
    "autosave_interval": "10s",
    "autosave_prefix": "{path}{query}-{id}-",
    "autosave_restore_when_empty": True,
}
