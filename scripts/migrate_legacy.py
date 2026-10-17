#!/usr/bin/env python3
"""One-shot migration: legacy Next.js JSON articles -> Astro MDX (src/content/guides)."""
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "_legacy" / "content" / "articles"
DST = ROOT / "src" / "content" / "guides"
PUBLIC = ROOT / "public"

PLACEHOLDER_FIX = {
    "amenager-un-coin-lecture-montessori": "https://www.amazon.fr/s?k=bibliotheque+montessori+enfant&tag=missstream-21",
    "la-tour-pink-montessori-developpement-equilibre-enfant": "https://www.amazon.fr/s?k=tour+rose+montessori&tag=missstream-21",
}

_cache: dict[str, str] = {}


def resolve(url: str) -> str:
    if url not in _cache:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "curl/8"})
        opener = urllib.request.build_opener(NoRedirect)
        try:
            opener.open(req, timeout=10)
            _cache[url] = url
        except urllib.error.HTTPError as e:
            _cache[url] = e.headers.get("Location") or url
    return _cache[url]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def yaml_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def mdx_safe(c: str) -> str:
    c = re.sub(r"https://is\.gd/\w+", lambda m: resolve(m.group()), c)
    c = re.sub(r"</?article[^>]*>", "", c)
    c = re.sub(r"^\s*<h1>.*?</h1>", "", c, count=1, flags=re.S)
    c = re.sub(r"<br\s*/?>", "<br />", c)
    c = re.sub(r"<img([^>]*?)\s*/?>", r"<img\1 />", c)
    c = re.sub(r"<(?![a-zA-Z/!])", "&lt;", c)
    return c.replace("{", "&#123;").replace("}", "&#125;").strip() + "\n"


def asin_of(url: str) -> str | None:
    m = re.search(r"/dp/([A-Z0-9]{10})", url)
    return m.group(1) if m else None


def main() -> int:
    DST.mkdir(parents=True, exist_ok=True)
    for f in sorted(SRC.glob("*.json")):
        a = json.loads(f.read_text())
        slug = a["slug"]
        amazon = PLACEHOLDER_FIX.get(slug) or a["amazonUrl"]
        if "is.gd" in amazon:
            amazon = resolve(amazon)
        image = a.get("image")
        if image and not (PUBLIC / image.lstrip("/")).exists():
            image = None
        fm = [
            "---",
            f"title: {yaml_str(a['title'])}",
            f"description: {yaml_str(a['description'])}",
            f"publishDate: {a['date']}",
            "category: guides",
            'author: "Rédaction GuideMontessori"',
            f"keywords: {json.dumps(a.get('keywords', []), ensure_ascii=False)}",
            f"emoji: {yaml_str(a.get('emoji', '📘'))}",
        ]
        if image:
            fm.append(f"image: {yaml_str(image)}")
        fm.append(f"amazonUrl: {yaml_str(amazon)}")
        if asin := asin_of(amazon):
            fm.append(f"asin: {yaml_str(asin)}")
        fm.append("---")
        (DST / f"{slug}.mdx").write_text("\n".join(fm) + "\n\n" + mdx_safe(a["content"]))
        print("ok", slug)
    return 0


if __name__ == "__main__":
    sys.exit(main())
