#!/usr/bin/env python3
"""Rapatrie la photo Amazon de chaque produit cité dans un encart <AffiliateBox>.

Sans photo, l'encart affiche un emoji 📦 à la place de l'objet. Les images sont
téléchargées une fois puis servies depuis notre domaine
(`public/images/produits/<asin>.webp`), et référencées par ASIN dans
`src/data/produits.json`, que lit le composant AffiliateBox.

Usage :
  python scripts/fetch_product_images.py                 # les ASIN encore sans photo
  python scripts/fetch_product_images.py --asin B0F995MXGZ
  python scripts/fetch_product_images.py --force         # retélécharge tout

Nécessite une clé ScraperAPI (SCRAPER_API_KEYS / SCRAPER_API_KEY, rotation
automatique) ; les ASIN déjà en local sont ignorés.
"""
import argparse
import io
import json
import os
import re
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

from generate_article import ROOT  # noqa: E402
from scraper_api import ScraperExhausted, available, get as scraper_get  # noqa: E402

CONTENT = ROOT / "src" / "content"
OUT_DIR = ROOT / "public" / "images" / "produits"
MAP_FILE = ROOT / "src" / "data" / "produits.json"
COUNTY = "fr"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"

BOX_RE = re.compile(r"<AffiliateBox\b(.*?)/>", re.S)
ASIN_RE = re.compile(r"""asin=["']([A-Z0-9]{10})["']""")
NOM_RE = re.compile(r"""nom=["']([^"']+)["']""")
IMAGE_RE = re.compile(r"""image=["']([^"']+)["']""")


def load_map() -> dict:
    if MAP_FILE.exists():
        try:
            return json.loads(MAP_FILE.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def save_map(data: dict) -> None:
    MAP_FILE.parent.mkdir(parents=True, exist_ok=True)
    MAP_FILE.write_text(json.dumps(dict(sorted(data.items())), ensure_ascii=False, indent=2) + "\n")


def find_products() -> dict:
    """{asin: nom} pour tous les encarts produit des articles."""
    found = {}
    for col in ("guides", "news"):
        d = CONTENT / col
        if not d.exists():
            continue
        for f in sorted(d.glob("*.mdx")):
            text = f.read_text()
            for block in BOX_RE.findall(text):
                asin = ASIN_RE.search(block)
                if not asin:
                    continue
                nom = NOM_RE.search(block)
                # Une image explicite (locale ou distante) rend le rapatriement inutile.
                if IMAGE_RE.search(block):
                    continue
                found[asin.group(1)] = nom.group(1) if nom else ""
    return found


def _looks_like_image(value) -> bool:
    return isinstance(value, str) and value.startswith("http") and any(
        ext in value.lower() for ext in (".jpg", ".jpeg", ".png", ".webp")
    )


def _image_from(payload) -> str | None:
    """Cherche une URL d'image dans une réponse ScraperAPI (schémas variables)."""
    if isinstance(payload, str):
        return payload if _looks_like_image(payload) else None
    if isinstance(payload, list):
        for item in payload:
            url = _image_from(item)
            if url:
                return url
        return None
    if not isinstance(payload, dict):
        return None
    for key in ("image", "image_url", "main_image", "mainImage", "thumbnail", "hiRes", "large"):
        if _looks_like_image(payload.get(key)):
            return payload[key]
    # `high_res_images` avant `images` : même produit, définition supérieure.
    for key in ("high_res_images", "images", "product", "products", "data", "result", "results"):
        if key in payload:
            url = _image_from(payload[key])
            if url:
                return url
    return None


def _get(path: str, params: dict):
    try:
        r = scraper_get(path, params, timeout=90)
    except ScraperExhausted:
        raise
    except Exception as e:
        print(f"    ! {type(e).__name__}: {e}", file=sys.stderr)
        return None
    if not r.ok:
        print(f"    ! HTTP {r.status_code} {path} {r.text[:120]}", file=sys.stderr)
        return None
    try:
        return r.json()
    except Exception:
        print(f"    ! réponse non JSON : {r.text[:120]}", file=sys.stderr)
        return None


def scrape_image_url(asin: str, nom: str) -> str | None:
    """Endpoint produit, puis recherche (par ASIN, puis par nom) en repli."""
    for params in (
        {"asin": asin, "country": COUNTY},
        {"asin": asin, "country_code": COUNTY},
    ):
        payload = _get("structured/amazon/product", params)
        if payload:
            url = _image_from(payload)
            if url:
                return url
            print(f"    ! produit sans image : {str(payload)[:200]}", file=sys.stderr)

    for query in (asin, nom[:120]):
        if not query:
            continue
        payload = _get("structured/amazon/search", {"query": query, "country": COUNTY})
        if not payload:
            continue
        results = payload.get("results") or []
        match = next((it for it in results if str(it.get("asin")) == asin), None)
        if match:
            url = _image_from(match)
            if url:
                return url
        if query == asin:
            # La recherche par ASIN renvoie la fiche exacte : la 1re image est la bonne.
            url = _image_from(results)
            if url:
                return url
    return None


def download_webp(url: str, asin: str) -> str | None:
    """Télécharge, recadre sur fond blanc et enregistre en WebP local."""
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=60)
        r.raise_for_status()
        from PIL import Image

        im = Image.open(io.BytesIO(r.content))
        im.load()
        if im.width < 120 or im.height < 120:
            print(f"    ! image trop petite ({im.width}×{im.height})", file=sys.stderr)
            return None
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            bg = Image.new("RGB", im.size, (255, 255, 255))
            bg.paste(im, mask=im.split()[-1])
            im = bg
        else:
            im = im.convert("RGB")
        im.thumbnail((600, 600), Image.LANCZOS)
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        out = OUT_DIR / f"{asin.lower()}.webp"
        im.save(out, "WEBP", quality=86, method=6)
        return f"/images/produits/{out.name}"
    except Exception as e:
        print(f"    ! téléchargement {type(e).__name__}: {e}", file=sys.stderr)
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--asin", action="append", default=[])
    ap.add_argument("--force", action="store_true", help="retélécharge même si l'image existe")
    args = ap.parse_args()

    produits = load_map()
    wanted = find_products()
    if args.asin:
        wanted = {a: wanted.get(a, "") for a in args.asin}

    if not args.force:
        wanted = {a: n for a, n in wanted.items() if not (OUT_DIR / f"{a.lower()}.webp").exists()}
    if not wanted:
        print("✓ Tous les encarts produit ont une photo.")
        return 0

    if not available():
        print("Aucune clé ScraperAPI : rapatriement des photos ignoré", file=sys.stderr)
        return 0

    ok = 0
    for asin, nom in wanted.items():
        print(f"→ {asin} {nom[:60]}")
        try:
            url = scrape_image_url(asin, nom)
        except ScraperExhausted:
            print("crédits ScraperAPI épuisés sur toutes les clés, on arrête là", file=sys.stderr)
            break
        if not url:
            print(f"  ✗ {asin} : aucune image trouvée", file=sys.stderr)
            continue
        local = download_webp(url, asin)
        if not local:
            continue
        produits[asin] = {"image": local, "nom": nom}
        save_map(produits)
        print(f"  ✓ {local} (source {url[:70]})")
        ok += 1

    print(f"\n{ok}/{len(wanted)} photos produit rapatriées")
    return 0


if __name__ == "__main__":
    sys.exit(main())
