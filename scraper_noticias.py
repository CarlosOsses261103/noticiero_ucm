import argparse
import json
import mimetypes
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


PROJECT_DIR = Path(__file__).resolve().parent
TEXT_DIR = PROJECT_DIR / "media" / "noticias" / "textos"
IMAGE_DIR = PROJECT_DIR / "media" / "noticias" / "imagenes"
CACHE_PATH = PROJECT_DIR / "media" / "noticias" / "noticias_cache.json"
METADATA_PATH = PROJECT_DIR / "media" / "noticias" / "scraper_metadata.json"

DEFAULT_URL = "https://www.ucm.cl/facultades/facultad-de-ciencias-basicas/"
NEWS_SECTION_TITLE = "Noticias de la Facultad"
DEFAULT_GEMINI_MODEL = "gemini-1.5-flash"
REQUEST_TIMEOUT = 30

GEMINI_PROMPT = (
    "Actúa como un guionista de noticieros. Toma la siguiente noticia y redacta "
    "lo que diría un presentador de televisión al dar esta información. El tono "
    "debe ser formal, informativo y entusiasta. No transcribas la noticia completa: "
    "resume solo los hechos principales. El guion debe tener un máximo de 300 palabras."
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36 NoticieroIA/1.0"
    )
}


@dataclass
class ScrapedNews:
    title: str
    body: str
    source_url: str
    image_urls: list[str]
    published_at: str = ""


def main():
    load_env_file()
    args = parse_args()
    ensure_directories()
    limit = normalize_limit(args.limit)

    print(f"Buscando noticias en: {args.url}")
    news_items = scrape_news(args.url, limit=limit, max_images=args.max_images)

    if not news_items:
        raise SystemExit("No se encontraron noticias en la seccion solicitada.")

    metadata = load_metadata() if args.guardar_archivos else {"items": {}}
    cache_items = []
    saved = 0

    for index, news in enumerate(news_items, start=1):
        print(f"Procesando noticia {index}/{len(news_items)}: {news.title}")
        script_text = generate_summary_script(news, use_gemini=not args.sin_gemini)

        cache_items.append(build_cache_item(news, script_text, order=index))
        saved += 1

        if args.guardar_archivos:
            existing_stem = find_existing_stem(metadata, news.source_url)
            if existing_stem and not args.force:
                print(f"Ya existe archivo local: {news.title} -> {existing_stem}.txt")
                continue

            stem = existing_stem if existing_stem and args.force else next_news_stem(news.title)
            text_path = save_script_file(stem, news.title, script_text)
            image_paths = download_images(news.image_urls, stem, max_images=args.max_images)

            metadata["items"][news.source_url] = {
                "stem": stem,
                "title": news.title,
                "text_path": str(text_path.relative_to(PROJECT_DIR)),
                "image_paths": [str(path.relative_to(PROJECT_DIR)) for path in image_paths],
                "published_at": news.published_at,
                "saved_at": datetime.now(timezone.utc).isoformat(),
            }

            print(f"Guardado texto local: {text_path}")
            print(f"Guardadas imagenes locales: {len(image_paths)}")

    save_news_cache(args.url, cache_items)

    if args.guardar_archivos:
        save_metadata(metadata)

    print(f"Cache actualizado: {CACHE_PATH}")
    print(f"Proceso finalizado. Noticias disponibles para el noticiero: {saved}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Extrae noticias UCM, genera guion con Gemini y guarda archivos para Django."
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="URL de la pagina fuente.")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Cantidad maxima de noticias. Usa 0 para tomar todas las disponibles.",
    )
    parser.add_argument(
        "--max-images",
        type=int,
        default=3,
        help="Cantidad maxima de imagenes a descargar por noticia.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Sobrescribe una noticia ya guardada si la URL fuente coincide.",
    )
    parser.add_argument(
        "--guardar-archivos",
        action="store_true",
        help="Ademas del cache, guarda .txt e imagenes locales como el flujo anterior.",
    )
    parser.add_argument(
        "--sin-gemini",
        action="store_true",
        help="Modo de prueba: guarda el texto limpio sin llamar a Gemini.",
    )
    return parser.parse_args()


def ensure_directories():
    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)


def normalize_limit(value: int):
    return value if value and value > 0 else None


def limit_items(items: list, limit: int | None):
    return items if limit is None else items[:limit]


def reached_limit(items: list, limit: int | None):
    return limit is not None and len(items) >= limit


def scrape_news(url: str, limit: int | None, max_images: int):
    html = fetch_text(url)
    soup = BeautifulSoup(html, "html.parser")

    section_items = extract_rendered_news_from_section(soup, url, limit)
    if section_items:
        return limit_items(section_items, limit)

    page_data_items = extract_news_from_gatsby_page_data(url, limit, max_images)
    if page_data_items:
        return limit_items(page_data_items, limit)

    return limit_items(extract_news_links_fallback(soup, url, limit), limit)


def extract_rendered_news_from_section(soup: BeautifulSoup, base_url: str, limit: int | None):
    heading = find_heading(soup, NEWS_SECTION_TITLE)
    if not heading:
        return []

    section = heading.find_parent("section") or heading.find_parent("div")
    if not section:
        return []

    items = []
    seen_urls = set()

    for link in section.find_all("a", href=True):
        href = urljoin(base_url, link["href"])
        if "/noticias/" not in href or href in seen_urls:
            continue

        seen_urls.add(href)
        title = clean_text(link.get_text(" ", strip=True))
        detail = fetch_detail_news(href)

        if detail:
            items.append(detail)
        elif title:
            image_url = find_nearby_image_url(link, base_url)
            body = fetch_readable_page_text(href)
            items.append(ScrapedNews(title=title, body=body, source_url=href, image_urls=[image_url] if image_url else []))

        if reached_limit(items, limit):
            break

    return items


def extract_news_from_gatsby_page_data(url: str, limit: int | None, max_images: int):
    page_data_url = build_gatsby_page_data_url(url)
    data = fetch_json(page_data_url)
    modules = find_news_distributor_modules(data)

    items = []
    for module in modules:
        title_content = ((module.get("title") or {}).get("content") or "").strip()
        if NEWS_SECTION_TITLE.lower() not in clean_text(title_content).lower():
            continue

        for raw_item in module.get("queriedItems") or []:
            parsed = parse_gatsby_news_item(raw_item, url, max_images)
            if parsed:
                items.append(parsed)
            if reached_limit(items, limit):
                return items

    return items


def parse_gatsby_news_item(raw_item: dict, base_url: str, max_images: int):
    content = raw_item.get("content") or {}
    related_page = raw_item.get("relatedPage") or {}

    title = clean_text(content.get("title") or "")
    source_url = related_page.get("url") or related_page.get("urlCanonical") or base_url
    subtitle = html_to_text(content.get("subtitle") or "")
    body = html_to_text(content.get("content") or "")
    published_at = content.get("newsDate") or raw_item.get("published") or ""

    if not title:
        return None

    image_urls = collect_gatsby_image_urls(content, base_url, max_images=max_images)

    if source_url:
        detail = fetch_detail_news(source_url, max_images=max_images)
        if detail:
            if len(detail.body) >= len(body):
                body = detail.body
                subtitle = ""
            if detail.image_urls:
                image_urls = detail.image_urls

    full_body = clean_text("\n\n".join(part for part in [subtitle, body] if part))

    return ScrapedNews(
        title=title,
        body=full_body or title,
        source_url=source_url,
        image_urls=image_urls,
        published_at=published_at,
    )


def fetch_detail_news(url: str, max_images: int = 3):
    try:
        data = fetch_json(build_gatsby_page_data_url(url))
    except requests.RequestException:
        return None
    except json.JSONDecodeError:
        return None

    detail = extract_news_detail_from_page_context(data, url, max_images)
    if detail:
        return detail

    news_dict = find_first_structured_news(data)
    if not news_dict:
        return None

    content = news_dict.get("content") or news_dict
    title = clean_text(content.get("title") or "")
    subtitle = html_to_text(content.get("subtitle") or "")
    body = html_to_text(content.get("content") or "")
    image_urls = collect_gatsby_image_urls(content, url, max_images=max_images)

    if not title or not body:
        return None

    return ScrapedNews(
        title=title,
        body=clean_text("\n\n".join(part for part in [subtitle, body] if part)),
        source_url=url,
        image_urls=image_urls,
        published_at=content.get("newsDate") or news_dict.get("published") or "",
    )


def extract_news_detail_from_page_context(data: dict, url: str, max_images: int):
    page = (((data.get("result") or {}).get("pageContext") or {}).get("page") or {})
    template = page.get("template") or {}

    if template.get("templateType") != "NewsDetail":
        return None

    title = clean_text(((template.get("newsTitle") or {}).get("content")) or page.get("title") or "")
    subtitle = html_to_text(template.get("subtitle") or page.get("metaDescription") or "")
    body = html_to_text(template.get("content") or "")
    image_urls = collect_gatsby_image_urls(template, url, max_images=max_images)

    if not title or not body:
        return None

    return ScrapedNews(
        title=title,
        body=clean_text("\n\n".join(part for part in [subtitle, body] if part)),
        source_url=url,
        image_urls=image_urls,
        published_at=template.get("newsDate") or page.get("published") or "",
    )


def extract_news_links_fallback(soup: BeautifulSoup, base_url: str, limit: int | None):
    items = []
    seen_urls = set()

    for link in soup.find_all("a", href=True):
        href = urljoin(base_url, link["href"])
        if "/noticias/" not in href or href in seen_urls:
            continue

        title = clean_text(link.get_text(" ", strip=True))
        if not title:
            continue

        seen_urls.add(href)
        body = fetch_readable_page_text(href)
        image_url = find_nearby_image_url(link, base_url)
        items.append(ScrapedNews(title=title, body=body, source_url=href, image_urls=[image_url] if image_url else []))

        if reached_limit(items, limit):
            break

    return items


def find_heading(soup: BeautifulSoup, text: str):
    pattern = re.compile(re.escape(text), re.IGNORECASE)
    return soup.find(["h1", "h2", "h3", "h4", "h5", "h6"], string=pattern) or soup.find(string=pattern)


def find_nearby_image_url(link, base_url: str):
    container = link.find_parent(["article", "li", "div", "section"])
    image = container.find("img") if container else None
    if image and image.get("src"):
        return urljoin(base_url, image["src"])
    return ""


def collect_gatsby_image_urls(content: dict, base_url: str, max_images: int):
    image_urls = []
    main_image = content.get("image")

    if isinstance(main_image, dict):
        image_urls.append(main_image.get("url") or main_image.get("thumb") or "")
    elif isinstance(main_image, str):
        image_urls.append(main_image)

    image_urls.extend(extract_image_urls_from_html(content.get("subtitle") or "", base_url))
    image_urls.extend(extract_image_urls_from_html(content.get("content") or "", base_url))

    return dedupe_urls([optimize_image_url(url) for url in image_urls])[:max_images]


def extract_image_urls_from_html(html: str, base_url: str):
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    return [optimize_image_url(urljoin(base_url, img["src"])) for img in soup.find_all("img", src=True)]


def generate_summary_script(news: ScrapedNews, use_gemini: bool = True):
    if use_gemini:
        script_text = generate_tv_script_with_gemini(news)
    else:
        script_text = generate_extractive_tv_script(news)

    return limit_words(clean_generated_text(script_text), 300)


def generate_tv_script_with_gemini(news: ScrapedNews):
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Falta GEMINI_API_KEY. Crea un archivo .env o define la variable de entorno antes de ejecutar el scraper."
        )

    import google.generativeai as genai

    genai.configure(api_key=api_key)
    model_name = os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    model = genai.GenerativeModel(model_name)

    prompt = f"""
{GEMINI_PROMPT}

Devuelve solo el guion final del presentador, sin markdown, sin listas y sin explicar tu proceso.
No superes las 300 palabras.
No copies parrafos completos de la noticia original.

Titulo original:
{news.title}

Fecha:
{news.published_at or "No informada"}

Fuente:
{news.source_url}

Texto de la noticia:
{news.body}
""".strip()

    response = model.generate_content(
        prompt,
        generation_config={
            "temperature": 0.45,
            "max_output_tokens": 900,
        },
    )
    return response.text.strip()


def generate_extractive_tv_script(news: ScrapedNews):
    sentences = split_sentences(news.body)
    selected = []
    word_count = 0

    for sentence in sentences:
        sentence_words = len(sentence.split())
        if sentence_words < 5:
            continue

        if word_count + sentence_words > 220 and selected:
            break

        selected.append(sentence)
        word_count += sentence_words

        if len(selected) >= 5:
            break

    summary = " ".join(selected) or news.body
    return (
        f"En noticias de la Universidad Catolica del Maule, destacamos: {news.title}. "
        f"{summary}"
    )


def build_cache_item(news: ScrapedNews, script_text: str, order: int):
    return {
        "id": build_news_id(news),
        "order": order,
        "title": news.title,
        "body": script_text.strip(),
        "summary_word_count": len(script_text.split()),
        "original_word_count": len(news.body.split()),
        "source_url": news.source_url,
        "published_at": news.published_at,
        "image_urls": dedupe_urls(news.image_urls),
    }


def save_news_cache(source_url: str, items: list[dict]):
    payload = {
        "source_url": source_url,
        "section": NEWS_SECTION_TITLE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(items),
        "items": items,
    }
    CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def save_script_file(stem: str, title: str, script_text: str):
    text_path = TEXT_DIR / f"{stem}.txt"
    text_path.write_text(f"{title}\n\n{script_text.strip()}\n", encoding="utf-8")
    return text_path


def download_images(image_urls: list[str], stem: str, max_images: int):
    destination = IMAGE_DIR / stem
    destination.mkdir(parents=True, exist_ok=True)
    saved_paths = []

    for index, image_url in enumerate(dedupe_urls(image_urls)[:max_images], start=1):
        try:
            response = requests.get(image_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as exc:
            print(f"No se pudo descargar imagen {image_url}: {exc}")
            continue

        content_type = response.headers.get("Content-Type", "")
        if not content_type.lower().startswith("image/"):
            print(f"La URL no devolvio una imagen valida: {image_url}")
            continue

        extension = guess_extension(image_url, content_type)
        image_path = destination / f"imagen_{index:02d}{extension}"
        image_path.write_bytes(response.content)
        saved_paths.append(image_path)

    return saved_paths


def guess_extension(url: str, content_type: str):
    path_extension = Path(urlparse(url).path).suffix.lower()
    if path_extension in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return path_extension

    clean_content_type = content_type.split(";")[0].strip().lower()
    return mimetypes.guess_extension(clean_content_type) or ".jpg"


def optimize_image_url(url: str):
    if not url:
        return ""

    parsed = urlparse(url)
    if parsed.netloc != "images.griddo.ucm.cl":
        return url

    image_id = parsed.path.strip("/")
    if not image_id or image_id.startswith(("c/", "w/", "f/")):
        return url

    return f"{parsed.scheme}://{parsed.netloc}/c/inside/q/80/w/1280/f/jpeg/{image_id}"


def fetch_text(url: str):
    response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.text


def fetch_json(url: str):
    response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


def fetch_readable_page_text(url: str):
    html = fetch_text(url)
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header"]):
        tag.decompose()

    article = soup.find("article") or soup.find("main") or soup.body or soup
    return clean_text(article.get_text(" ", strip=True))


def build_gatsby_page_data_url(url: str):
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    base = f"{parsed.scheme}://{parsed.netloc}"
    return f"{base}/page-data/{path}/page-data.json"


def find_news_distributor_modules(data):
    modules = []

    def walk(value):
        if isinstance(value, dict):
            if value.get("component") == "NewsDistributor":
                modules.append(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(data)
    return modules


def find_first_structured_news(data):
    if isinstance(data, dict):
        if data.get("structuredData") == "NEWS" and isinstance(data.get("content"), dict):
            return data

        for value in data.values():
            found = find_first_structured_news(value)
            if found:
                return found

    if isinstance(data, list):
        for value in data:
            found = find_first_structured_news(value)
            if found:
                return found

    return None


def html_to_text(html: str):
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()

    for br in soup.find_all("br"):
        br.replace_with("\n")

    return clean_text(soup.get_text(" ", strip=True))


def clean_text(value: str):
    value = BeautifulSoup(value or "", "html.parser").get_text(" ", strip=True)
    value = value.replace("\xa0", " ")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def clean_generated_text(value: str):
    value = value.strip()
    value = re.sub(r"^```[a-zA-Z]*", "", value)
    value = re.sub(r"```$", "", value)
    return clean_text(value)


def split_sentences(text: str):
    normalized = clean_text(text)
    parts = re.split(r"(?<=[.!?])\s+", normalized)
    return [part.strip() for part in parts if part.strip()]


def limit_words(text: str, max_words: int):
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]).rstrip(" ,.;:") + "."


def dedupe_urls(urls: list[str]):
    clean_urls = []
    seen = set()

    for url in urls:
        if not url:
            continue

        clean_url = url.strip()
        if clean_url and clean_url not in seen:
            clean_urls.append(clean_url)
            seen.add(clean_url)

    return clean_urls


def next_news_stem(title: str):
    sequence = next_sequence_number()
    slug = slugify(title)[:70] or "noticia"
    return f"{sequence:03d}_{slug}"


def next_sequence_number():
    highest = 0

    for path in TEXT_DIR.glob("*.txt"):
        match = re.match(r"^(\d+)", path.stem)
        if match:
            highest = max(highest, int(match.group(1)))

    return highest + 1


def slugify(value: str):
    normalized = unicodedata.normalize("NFKD", value)
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower()
    return re.sub(r"-{2,}", "-", normalized)


def build_news_id(news: ScrapedNews):
    source_key = news.source_url.rstrip("/").split("/")[-1] or news.title
    slug = slugify(source_key)[:76] or "noticia"
    digest = hashlib_sha1(news.source_url or news.title)[:8]
    return f"{slug}-{digest}"


def hashlib_sha1(value: str):
    import hashlib

    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def load_env_file():
    env_path = PROJECT_DIR / ".env"
    if not env_path.exists():
        return

    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    load_dotenv(env_path)


def load_metadata():
    if not METADATA_PATH.exists():
        return {"items": {}}

    try:
        data = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"items": {}}

    data.setdefault("items", {})
    return data


def save_metadata(metadata: dict):
    METADATA_PATH.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


def find_existing_stem(metadata: dict, source_url: str):
    item = metadata.get("items", {}).get(source_url) or {}
    stem = item.get("stem")
    if stem and (TEXT_DIR / f"{stem}.txt").exists():
        return stem
    return ""


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nProceso cancelado por el usuario.")
