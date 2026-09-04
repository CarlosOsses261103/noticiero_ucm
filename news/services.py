import hashlib
import json
import logging
import re
import unicodedata
from pathlib import Path

from django.conf import settings


logger = logging.getLogger(__name__)
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def get_broadcast_context():
    ensure_media_directories()
    articles = get_articles()

    if not articles:
        articles = [get_empty_article()]

    first_article = articles[0]

    return {
        "title": first_article["title"],
        "body": first_article["body"],
        "image_urls": first_article["image_urls"],
        "audio_url": first_article["audio_url"],
        "audio_generated": first_article["audio_generated"],
        "video_url": media_url(settings.NEWS_VIDEO_PATH) if settings.NEWS_VIDEO_PATH.exists() else "",
        "article_name": first_article["article_name"],
        "broadcast_items": articles,
        "broadcast_count": len(articles),
    }


def ensure_media_directories():
    settings.NEWS_TEXT_DIR.mkdir(parents=True, exist_ok=True)
    settings.NEWS_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    settings.NEWS_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    settings.NEWS_VIDEO_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_articles():
    cached_articles = get_cached_broadcast_articles()
    if cached_articles:
        return cached_articles

    article_paths = get_article_paths()
    use_legacy_images = len(article_paths) == 1
    return [
        build_article_item(article_path, index, use_legacy_images)
        for index, article_path in enumerate(article_paths)
    ]


def get_article_paths():
    return sorted(settings.NEWS_TEXT_DIR.glob("*.txt"), key=natural_sort_key)


def build_article_item(article_path: Path, index: int, use_legacy_images: bool):
    title, body = load_article(article_path)
    audio_path = get_cached_audio_path(title, body)

    return {
        "id": build_article_id(article_path),
        "order": index + 1,
        "article_name": article_path.name,
        "title": title,
        "body": body,
        "image_urls": get_image_urls_for_article(article_path, use_legacy_images),
        "audio_url": media_url(audio_path) if audio_path else "",
        "audio_api_url": f"/api/audio/{build_article_id(article_path)}/",
        "audio_generated": audio_path is not None,
    }


def get_empty_article():
    return {
        "id": "sin-noticias",
        "order": 1,
        "article_name": "",
        "title": "Noticiero con IA",
        "body": "Crea archivos .txt en media/noticias/textos. La primera linea sera el titulo y el resto sera el cuerpo de la noticia.",
        "image_urls": [],
        "audio_url": "",
        "audio_api_url": "",
        "audio_generated": False,
    }


def get_cached_broadcast_articles():
    if not settings.NEWS_CACHE_PATH.exists():
        return []

    try:
        cache = json.loads(settings.NEWS_CACHE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

    raw_items = cache.get("items", []) if isinstance(cache, dict) else []
    articles = []

    for index, item in enumerate(raw_items):
        title = str(item.get("title") or "").strip()
        body = str(item.get("body") or "").strip()

        if not title or not body:
            continue

        article_id = normalize_article_id(item.get("id") or title)
        audio_path = get_cached_audio_path(title, body)

        articles.append(
            {
                "id": article_id,
                "order": index + 1,
                "article_name": str(item.get("source_url") or f"{article_id}.json"),
                "title": title,
                "body": body,
                "image_urls": normalize_url_list(item.get("image_urls")),
                "source_url": str(item.get("source_url") or ""),
                "published_at": str(item.get("published_at") or ""),
                "audio_url": media_url(audio_path) if audio_path else "",
                "audio_api_url": f"/api/audio/{article_id}/",
                "audio_generated": audio_path is not None,
            }
        )

    return articles


def get_cached_article_by_id(article_id: str):
    for item in get_cached_broadcast_articles():
        if item["id"] == article_id:
            return item
    return None


def get_or_create_article_audio(article_id: str):
    cached_article = get_cached_article_by_id(article_id)
    if cached_article:
        return generate_audio(cached_article["title"], cached_article["body"])

    article_path = get_article_path_by_id(article_id)
    if article_path is None:
        return None

    title, body = load_article(article_path)
    return generate_audio(title, body)


def get_article_path_by_id(article_id: str):
    for article_path in get_article_paths():
        if build_article_id(article_path) == article_id:
            return article_path
    return None


def load_article(article_path: Path | None):
    if article_path is None:
        return (
            "Noticiero con IA",
            "Crea un archivo .txt en media/noticias/textos. La primera linea sera el titulo y el resto sera el cuerpo de la noticia.",
        )

    raw_text = article_path.read_text(encoding="utf-8-sig").strip()
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]

    if not lines:
        return "Noticiero con IA", "El archivo de texto esta vacio."

    title = normalize_title(lines[0])
    body = "\n\n".join(lines[1:]).strip() or title
    return title, body


def normalize_title(first_line: str):
    title = first_line.strip().lstrip("#").strip()
    lower_title = title.lower()

    for prefix in ("titulo:", "título:"):
        if lower_title.startswith(prefix):
            return title[len(prefix) :].strip()

    return title


def get_image_urls_for_article(article_path: Path, use_legacy_images: bool = False):
    image_folder = settings.NEWS_IMAGES_DIR / article_path.stem

    if image_folder.exists() and image_folder.is_dir():
        return get_image_urls_from_folder(image_folder)

    prefixed_images = get_prefixed_image_urls(article_path.stem)
    if prefixed_images:
        return prefixed_images

    if use_legacy_images:
        return get_image_urls_from_folder(settings.NEWS_IMAGES_DIR)

    return []


def get_image_urls_from_folder(folder: Path):
    images = []
    for path in sorted(folder.iterdir(), key=natural_sort_key):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            images.append(media_url(path))
    return images


def get_prefixed_image_urls(article_stem: str):
    images = []
    valid_prefixes = (f"{article_stem}_".lower(), f"{article_stem}-".lower())

    for path in sorted(settings.NEWS_IMAGES_DIR.iterdir(), key=natural_sort_key):
        lower_name = path.name.lower()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS and lower_name.startswith(valid_prefixes):
            images.append(media_url(path))

    return images


def generate_audio(title: str, body: str):
    text = f"{title}. {body}".strip()
    mp3_path, wav_path = get_audio_paths(text)

    if is_valid_file(mp3_path):
        return mp3_path

    if is_valid_file(wav_path):
        return wav_path

    generated = generate_with_gtts(text, mp3_path)
    if generated:
        return generated

    generated = generate_with_edge_tts(text, mp3_path)
    if generated:
        return generated

    return generate_with_pyttsx3(text, wav_path)


def get_cached_audio_path(title: str, body: str):
    text = f"{title}. {body}".strip()
    mp3_path, wav_path = get_audio_paths(text)

    if is_valid_file(mp3_path):
        return mp3_path

    if is_valid_file(wav_path):
        return wav_path

    return None


def get_audio_paths(text: str):
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return (
        settings.NEWS_AUDIO_DIR / f"noticia_{digest}.mp3",
        settings.NEWS_AUDIO_DIR / f"noticia_{digest}.wav",
    )


def generate_with_gtts(text: str, output_path: Path):
    try:
        from gtts import gTTS

        tts = gTTS(text=text, lang=settings.NEWS_TTS_LANG)
        tts.save(str(output_path))

        if is_valid_file(output_path):
            return output_path
    except Exception as exc:
        logger.warning("No se pudo generar audio con gTTS: %s", exc)

    return None


def generate_with_edge_tts(text: str, output_path: Path):
    try:
        import asyncio

        import edge_tts

        communicate = edge_tts.Communicate(text, settings.NEWS_EDGE_TTS_VOICE)
        asyncio.run(communicate.save(str(output_path)))

        if is_valid_file(output_path):
            return output_path
    except Exception as exc:
        logger.warning("No se pudo generar audio con edge-tts: %s", exc)

    return None


def generate_with_pyttsx3(text: str, output_path: Path):
    try:
        import pyttsx3

        engine = pyttsx3.init()
        select_spanish_voice(engine)
        engine.setProperty("rate", 160)
        engine.save_to_file(text, str(output_path))
        engine.runAndWait()
        engine.stop()

        if is_valid_file(output_path):
            return output_path
    except Exception as exc:
        logger.warning("No se pudo generar audio con pyttsx3: %s", exc)

    return None


def select_spanish_voice(engine):
    for voice in engine.getProperty("voices") or []:
        voice_text = f"{getattr(voice, 'id', '')} {getattr(voice, 'name', '')} {getattr(voice, 'languages', '')}".lower()
        if "spanish" in voice_text or "es-" in voice_text or "es_" in voice_text or "espa" in voice_text:
            engine.setProperty("voice", voice.id)
            return


def is_valid_file(path: Path):
    return path.exists() and path.stat().st_size > 0


def media_url(path: Path):
    relative_path = path.relative_to(settings.MEDIA_ROOT).as_posix()
    return f"{settings.MEDIA_URL}{relative_path}"


def build_article_id(article_path: Path):
    safe_stem = slugify_filename(article_path.stem) or "noticia"
    digest = hashlib.sha1(article_path.name.encode("utf-8")).hexdigest()[:8]
    return f"{safe_stem}-{digest}"


def normalize_article_id(value: str):
    safe_id = slugify_filename(str(value)) or "noticia"
    return safe_id[:90]


def slugify_filename(value: str):
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", normalized).strip("-").lower()
    return re.sub(r"-{2,}", "-", normalized)


def normalize_url_list(value):
    if not isinstance(value, list):
        return []

    urls = []
    for url in value:
        text_url = str(url or "").strip()
        if text_url:
            urls.append(text_url)
    return urls


def natural_sort_key(path: Path):
    return [
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", path.stem)
    ]
