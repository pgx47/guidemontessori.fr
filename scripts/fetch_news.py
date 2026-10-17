#!/usr/bin/env python3
"""Veille actu : Google News RSS -> brève MDX (collection news), dedup persisté."""
import json
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
RSS = ('https://news.google.com/rss/search?q=montessori+OR+"petite+enfance"'
       '+OR+"motricit%C3%A9+libre"&hl=fr&gl=FR&ceid=FR:fr')


def latest_item() -> tuple[str, str, str] | None:
    done = set(json.loads(STATE.read_text()).get("seen", [])) if STATE.exists() else set()
    xml = requests.get(RSS, timeout=30, headers={"User-Agent": "guidemontessori/1.0"}).content
    for it in ET.fromstring(xml).iter("item"):
        link = it.findtext("link") or ""
        if link in done:
            continue
        title = it.findtext("title") or ""
        return (link, title, re.sub(r"<[^>]+>", " ", it.findtext("description") or "")[:500])
    return None


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
    item = latest_item()
    if not item:
        print("Aucune actu nouvelle.")
        return 0
    link, title, summary = item
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
