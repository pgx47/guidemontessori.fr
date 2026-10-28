#!/usr/bin/env python3
"""Veille actu : Google News RSS -> brève MDX (collection news), dedup persisté."""
import hashlib
import html
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
import generate_article as g

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "src" / "data" / "news_state.json"
RSS_FEEDS = [
    "https://news.google.com/rss/search?q=montessori+OR+%22p%C3%A9dagogie+montessori%22&hl=fr&gl=FR&ceid=FR:fr",
    "https://news.google.com/rss/search?q=motricit%C3%A9+libre+OR+%22jeu+libre%22+enfant&hl=fr&gl=FR&ceid=FR:fr",
    "https://news.google.com/rss/search?q=%C3%A9ducation+bienveillante+OR+%22neurosciences+enfant%22&hl=fr&gl=FR&ceid=FR:fr",
    "https://news.google.com/rss/search?q=%C3%A9veil+enfant+nature+OR+%22activit%C3%A9s+enfants%22&hl=fr&gl=FR&ceid=FR:fr",
]
EXCLUDE = ("liquidation", "fermeture", "tribunal", "procès", "accident", "grève",
           "licenciement", "violence", "agression", "décès", "homicide",
           "manifestation", "police", "policier", "catéchisme")
USED = ROOT / "src" / "data" / "used_images.json"
IMAGE_FILTER = re.compile(r"logo|icon|map|carte|plan|diagram|schema|seal|coat|svg", re.I)


def latest_items(limit: int = 3) -> list[tuple[str, str, str]]:
    done = set(json.loads(STATE.read_text()).get("seen", [])) if STATE.exists() else set()
    out = []
    for url in RSS_FEEDS:
        try:
            xml = requests.get(url, timeout=30, headers={"User-Agent": "guidemontessori/1.0"}).content
            for it in ET.fromstring(xml).iter("item"):
                link = it.findtext("link") or ""
                title = it.findtext("title") or ""
                if link in done or any(w in title.lower() for w in EXCLUDE):
                    continue
                out.append((link, title, re.sub(r"<[^>]+>", " ", it.findtext("description") or "")[:500]))
                if len(out) >= limit:
                    return out
        except Exception as e:
            print(f"⚠ RSS {url[:50]} : {e}", file=sys.stderr)
    return out


def _used_images() -> dict:
    try:
        return json.loads(USED.read_text())
    except Exception:
        return {}


def _is_used(sha1: str, slug: str) -> bool:
    reg = _used_images()
    return sha1 in reg and reg[sha1].get("slug") != slug


def _mark_used(sha1: str, url: str, slug: str) -> None:
    reg = _used_images()
    reg[sha1] = {"url": url, "slug": slug}
    USED.parent.mkdir(parents=True, exist_ok=True)
    USED.write_text(json.dumps(reg, ensure_ascii=False, indent=2) + "\n")


def _normalize_wikimedia(url: str) -> str:
    return re.sub(r"https?://thumb\.wikimedia\.org", "https://upload.wikimedia.org", url)


def _extract_og_image(page_html: str) -> str | None:
    m = re.search(r'<meta[^>]*(?:property|name)=["\']og:image["\'][^>]*>', page_html)
    if not m:
        return None
    cm = re.search(r'content=["\']([^"\']+)["\']', m.group(0))
    if not cm:
        return None
    url = html.unescape(cm.group(1))
    if url.startswith("//"):
        url = "https:" + url
    return url if url.startswith("http") else None


def _og_image_from_source(link: str) -> str | None:
    """og:image de l'article source, via ScraperAPI puis fetch direct."""
    if key := os.environ.get("SCRAPER_API_KEY"):
        try:
            r = requests.get("http://api.scraperapi.com",
                             params={"api_key": key, "url": link, "render": "true"}, timeout=60)
            if r.ok:
                if u := _extract_og_image(r.text):
                    return u
        except Exception as e:
            print(f"⚠ scraper og:image : {e}", file=sys.stderr)
    try:
        r = requests.get(link, timeout=30, headers={"User-Agent": "guidemontessori/1.0"})
        if r.ok:
            return _extract_og_image(r.text)
    except Exception as e:
        print(f"⚠ fetch direct og:image : {e}", file=sys.stderr)
    return None


def _save_image(raw: bytes, url: str, slug: str) -> str | None:
    """Filtre (nom, taille, ratio) + dedup, puis écrit le WebP local. None si rejeté."""
    from io import BytesIO
    from PIL import Image, ImageOps
    if IMAGE_FILTER.search(url):
        return None
    try:
        im = Image.open(BytesIO(raw))
        im = ImageOps.exif_transpose(im)
        im.load()
    except Exception:
        return None
    w, h = im.size
    if w < 800:
        return None
    if not (1.2 <= w / h <= 2.2):
        return None
    sha1 = hashlib.sha1(raw).hexdigest()
    if _is_used(sha1, slug):
        print(f"⚠ image déjà utilisée par un autre article : {url[:60]}", file=sys.stderr)
        return None
    if w > 1200:
        im = im.resize((1200, int(h * 1200 / w)), Image.Resampling.LANCZOS)
    im = im.convert("RGB")
    g.IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    out = g.IMAGES_DIR / f"{slug}.webp"
    im.save(out, "WEBP", quality=82, method=6)
    _mark_used(sha1, url, slug)
    return f"/images/generated/{slug}.webp"


def _download_and_save(url: str, slug: str) -> str | None:
    try:
        r = requests.get(url, timeout=60, headers={"User-Agent": "guidemontessori/1.0"})
        if not r.ok or not r.content:
            return None
        return _save_image(r.content, url, slug)
    except Exception as e:
        print(f"⚠ téléchargement {url[:60]} : {e}", file=sys.stderr)
        return None


def source_image(link: str, slug: str, title: str, emoji: str = "") -> str:
    """Image locale garantie : og:image de la source > Wikimedia filtré > carte de marque."""
    if u := _og_image_from_source(link):
        if path := _download_and_save(u, slug):
            return path
    try:
        r = requests.get("https://en.wikipedia.org/w/api.php",
                         params={"action": "query", "format": "json", "prop": "pageimages",
                                 "generator": "search", "gsrsearch": "montessori school", "pithumbsize": 1024},
                         headers={"User-Agent": "guidemontessori/1.0"}, timeout=20).json()
        pages = [p for p in r.get("query", {}).get("pages", {}).values() if p.get("thumbnail")]
        pages.sort(key=lambda p: p.get("pageid", 0))
        for p in pages:
            if path := _download_and_save(_normalize_wikimedia(p["thumbnail"]["source"]), slug):
                return path
    except Exception as e:
        print(f"⚠ wikimedia : {e}", file=sys.stderr)
    print(f"⚠ image générée localement (carte de marque) pour {slug}")
    return g.make_brand_card(slug, title, emoji)


def mark_seen(link: str) -> None:
    st = {"seen": (json.loads(STATE.read_text()).get("seen", []) if STATE.exists() else [])}
    st["seen"] = (st["seen"] + [link])[-200:]
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=2) + "\n")


def main() -> int:
    items = latest_items(limit=int(os.environ.get("NEWS_COUNT", "3")))
    if not items:
        print("Aucune actu nouvelle.")
        return 0
    failed = False
    for link, title, summary in items:
        try:
            _publish(link, title, summary)
        except Exception as e:
            failed = True
            print(f"⚠ '{title[:50]}' : {e}", file=sys.stderr)
    return 1 if failed else 0


def _publish(link: str, title: str, summary: str) -> None:
    print(f"actu : {title}")
    topic = {"keyword": title,
             "angle": f"brève d'actualité. Faits réels : {summary} Source : {link}. "
                      "Éclairage Montessori (autonomie, motricité libre) puis impact concret pour les parents. "
                      "Ne rien inventer au-delà des faits fournis.",
             "type": "news", "products": [], "status": "pending"}
    data = json.loads(g.TOPICS.read_text())
    a = g.call_llm(topic, "news")
    today = date.today().isoformat()
    slug = g.slugify(a.get("slug") or a["title"])
    taken = {s for s, _ in g.existing_articles()}
    if slug in taken:
        slug += "-" + today
    topic["image"] = source_image(link, slug, a["title"], a.get("emoji", ""))
    mdx = g.render_mdx(a, topic, "news", today, slug)
    path = g.DIRS["news"] / f"{slug}.mdx"
    path.write_text(mdx)
    mark_seen(link)
    print(f"✓ {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
