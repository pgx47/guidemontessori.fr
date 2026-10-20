#!/usr/bin/env python3
"""Veille actu : Google News RSS -> brève MDX (collection news), dedup persisté."""
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


def source_image(link: str) -> str | None:
    """og:image via ScraperAPI (passe le mur Google News), sinon Wikimedia, sinon pool local."""
    if key := os.environ.get("SCRAPER_API_KEY"):
        try:
            r = requests.get("http://api.scraperapi.com",
                             params={"api_key": key, "url": link, "render": "true"}, timeout=60)
            m = re.search(r'property=["\']og:image["\'][^>]+content=["\']([^"\']+)', r.text)
            if m and m.group(1).startswith("http"):
                return m.group(1)
        except Exception as e:
            print(f"⚠ scraper og:image : {e}", file=sys.stderr)
    try:
        r = requests.get("https://en.wikipedia.org/w/api.php",
                         params={"action": "query", "format": "json", "prop": "pageimages",
                                 "generator": "search", "gsrsearch": "montessori school", "pithumbsize": 1024},
                         headers={"User-Agent": "guidemontessori/1.0"}, timeout=20).json()
        import random
        pages = [p for p in r.get("query", {}).get("pages", {}).values() if p.get("thumbnail")]
        if pages:
            return random.choice(pages)["thumbnail"]["source"]
    except Exception:
        pass
    import random
    return random.choice(["/hero-1.png", "/hero-2.png", "/hero-3.png"])


def mark_seen(link: str) -> None:
    st = {"seen": (json.loads(STATE.read_text()).get("seen", []) if STATE.exists() else [])}
    st["seen"] = (st["seen"] + [link])[-200:]
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=2) + "\n")


def main() -> int:
    items = latest_items(limit=int(os.environ.get("NEWS_COUNT", "3")))
    if not items:
        print("Aucune actu nouvelle.")
        return 0
    for link, title, summary in items:
        try:
            _publish(link, title, summary)
        except Exception as e:
            print(f"⚠ '{title[:50]}' : {e}", file=sys.stderr)
    return 0


def _publish(link: str, title: str, summary: str) -> None:
    print(f"actu : {title}")
    topic = {"keyword": title,
             "angle": f"brève d'actualité. Faits réels : {summary} Source : {link}. "
                      "Éclairage Montessori (autonomie, motricité libre) puis impact concret pour les parents. "
                      "Ne rien inventer au-delà des faits fournis.",
             "type": "news", "products": [], "status": "pending",
             "image": source_image(link)}
    data = json.loads(g.TOPICS.read_text())
    a = g.call_llm(topic, "news")
    today = date.today().isoformat()
    slug = g.slugify(a.get("slug") or a["title"])
    taken = {s for s, _ in g.existing_articles()}
    if slug in taken:
        slug += "-" + today
    mdx = g.render_mdx(a, topic, "news", today, slug)
    path = g.DIRS["news"] / f"{slug}.mdx"
    path.write_text(mdx)
    mark_seen(link)
    print(f"✓ {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
