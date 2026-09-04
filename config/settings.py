import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-noticiero-ia")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"


def env_list(name, default):
    value = os.environ.get(name)
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


ALLOWED_HOSTS = env_list(
    "DJANGO_ALLOWED_HOSTS",
    ["*"] if DEBUG else ["127.0.0.1", "localhost"],
)

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "news",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

LANGUAGE_CODE = "es-cl"
TIME_ZONE = "America/Santiago"

USE_I18N = True
USE_TZ = True


# =========================
# ARCHIVOS ESTÁTICOS
# =========================

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Permite que WhiteNoise encuentre los archivos dentro de
# news/static/ durante el despliegue en Cloud Run.
WHITENOISE_USE_FINDERS = True

# Almacenamiento optimizado para producción.
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}


# =========================
# ARCHIVOS MULTIMEDIA
# =========================

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

NEWS_TEXT_DIR = MEDIA_ROOT / "noticias" / "textos"
NEWS_IMAGES_DIR = MEDIA_ROOT / "noticias" / "imagenes"
NEWS_AUDIO_DIR = MEDIA_ROOT / "noticias" / "audio"
NEWS_CACHE_PATH = MEDIA_ROOT / "noticias" / "noticias_cache.json"
NEWS_VIDEO_PATH = MEDIA_ROOT / "video" / "video.mp4"

NEWS_TTS_LANG = os.environ.get(
    "NEWS_TTS_LANG",
    "es",
)

NEWS_EDGE_TTS_VOICE = os.environ.get(
    "NEWS_EDGE_TTS_VOICE",
    "es-CL-CatalinaNeural",
)


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"