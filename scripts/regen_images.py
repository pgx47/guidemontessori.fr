#!/usr/bin/env python3
"""Génère une illustration pour les articles qui n'ont qu'une carte de marque.

Usage :
  python scripts/regen_images.py --all
  python scripts/regen_images.py --slug etagere-montessori-jouets-rotation

Écrit `public/images/photos/<slug>.webp` et met à jour le frontmatter.
Chaîne : génération IA (Flux/OpenAI) -> stock libre -> carte de marque.
Nécessite CLOUDFLARE_ACCOUNT_ID/CLOUDFLARE_API_TOKEN ou OPENAI_API_KEY.

Aucune dépendance YAML : le frontmatter est manipulé par regex + json.loads,
ce qui évite d'ajouter pyyaml aux requirements du workflow.
"""
import argparse
import base64
import json
import os
import re
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

from generate_article import (  # noqa: E402
    IMG_STYLE,
    ROOT,
    _to_webp,
    fetch_stock,
    make_brand_card,
)

FLUX_URL = "https://api.cloudflare.com/client/v4/accounts/{acct}/ai/run/@cf/black-forest-labs/flux-1-schnell"
UNSPLASH_SEARCH = "https://api.unsplash.com/search/photos"
PIXABAY_API = "https://pixabay.com/api/"

# Requêtes Pixabay (EN) : termes concrets, orientés photo.
PIXABAY_QUERIES = {
    "etagere-montessori-jouets-rotation": "wooden shelf toys nursery",
    "tour-observation-montessori-age-stabilite": "child kitchen step stool",
    "amenager-un-coin-lecture-montessori": "child books bookshelf reading",
    "preparation-environnement-montessori": "montessori classroom wooden toys",
    "apprentissage-vie-pratique-montessori-vaisselle": "child washing dishes hands",
    "la-tour-pink-montessori-developpement-equilibre-enfant": "wooden blocks tower",
    "agent-accueil-petite-enfance-offres-salaires": "nursery room interior",
    "accueil-grand-age-methode-montessori-france-tv": "elderly hands care",
    "atelier-montessori-rochechouart-aide-moi-a-faire-seul": "children craft table hands",
    "bougeotheque-municipale-bordeaux-petite-enfance": "toddler playing indoor",
    "ecole-montessori-irisia-aix-chantier-cour": "courtyard trees school building",
}


def generate_pixabay(slug: str):
    """Vraie photo depuis Pixabay (clé gratuite, 100 req/min). -> (bytes, credit)"""
    key = os.environ.get("PIXABAY_API_KEY")
    if not key:
        print("    ✗ Pixabay : aucune clé configurée")
        return None, None
    query = PIXABAY_QUERIES.get(slug)
    if not query:
        return None, None

    import hashlib
    used = _existing_hashes()
    try:
        r = requests.get(PIXABAY_API, params={
            "key": key, "q": query, "image_type": "photo", "orientation": "horizontal",
            "min_width": "1600", "per_page": "30", "safesearch": "true", "order": "popular",
        }, timeout=30)
    except Exception as e:
        print(f"    ✗ Pixabay : {type(e).__name__}")
        return None, None
    if not r.ok:
        print(f"    ✗ Pixabay : HTTP {r.status_code} — {r.text[:120]}")
        return None, None

    for hit in r.json().get("hits", []):
        w, h = hit.get("imageWidth") or 0, hit.get("imageHeight") or 0
        if w < 1600 or h == 0 or not (1.2 <= w / h <= 2.2):
            continue
        url = hit.get("fullHDURL") or hit.get("largeImageURL")
        if not url:
            continue
        try:
            img = requests.get(url, timeout=60)
            if not img.ok or len(img.content) < 80_000:
                continue
            if not _valid_image(img.content):
                continue
            if hashlib.sha1(img.content).hexdigest() in used:
                continue
            credit = {
                "photographer": hit.get("user"),
                "profile": f"https://pixabay.com/users/{hit.get('user')}-{hit.get('user_id')}/",
                "source": hit.get("pageURL"),
                "license": "Pixabay Content License",
            }
            print(f"    ✓ Pixabay — {hit.get('tags','')[:60]} ({w}×{h})")
            return img.content, credit
        except Exception:
            continue
    return None, None

# Requêtes Unsplash (EN) par slug.
UNSPLASH_QUERIES = {
    "etagere-montessori-jouets-rotation": "wooden shelf toys child room",
    "tour-observation-montessori-age-stabilite": "child learning tower kitchen",
    "amenager-un-coin-lecture-montessori": "children bookshelf reading corner",
    "preparation-environnement-montessori": "montessori playroom wooden shelf",
    "agent-accueil-petite-enfance-offres-salaires": "nursery reception interior",
    "accueil-grand-age-methode-montessori-france-tv": "elderly hands activity care",
    "atelier-montessori-rochechouart-aide-moi-a-faire-seul": "children hands wooden toys table",
    "bougeotheque-municipale-bordeaux-petite-enfance": "toddler balance beam indoor play",
    "apprentissage-vie-pratique-montessori-vaisselle": "child washing dishes hands kitchen",
    "la-tour-pink-montessori-developpement-enfant": "wooden blocks tower pink cubes",
    "ecole-montessori-irisia-aix-chantier-cour": "school courtyard plane trees",
}


def _existing_hashes() -> set[str]:
    """Empreintes des photos déjà en place, pour ne jamais réutiliser la même."""
    import hashlib
    out = set()
    for f in PHOTOS.glob("*.webp"):
        if f.name.endswith("-640.webp"):
            continue
        out.add(hashlib.sha1(f.read_bytes()).hexdigest())
    return out


def _valid_image(raw: bytes) -> bytes | None:
    """Contrôles qualité communs : taille, largeur, ratio."""
    import io
    from PIL import Image
    try:
        im = Image.open(io.BytesIO(raw))
        w, h = im.size
    except Exception:
        return None
    if w < 1200 or h == 0:
        return None
    ratio = w / h
    if not (1.2 <= ratio <= 2.2):
        return None
    return raw


def generate_openverse(slug: str):
    """Vraie photo CC depuis Openverse (aucune clé). -> (bytes, credit)"""
    query = UNSPLASH_QUERIES.get(slug)
    if not query:
        return None, None
    import hashlib
    used = _existing_hashes()
    bad = re.compile(r"logo|icon\b|\bmap\b|carte\b|diagram|schema|\.svg|\bplan\b|chart|graph|poster", re.I)
    try:
        r = requests.get(
            "https://api.openverse.org/v1/images/",
            params={"q": query, "page_size": "20", "license": "cc0,pdm,by", "size": "large", "filter_dead": "false"},
            headers={"User-Agent": "GuideMontessori/1.0"},
            timeout=45,
        )
    except Exception as e:
        print(f"    ✗ Openverse : {type(e).__name__}")
        return None, None
    if not r.ok:
        print(f"    ✗ Openverse : HTTP {r.status_code}")
        return None, None

    for it in r.json().get("results", []):
        if bad.search(it.get("title") or "") or bad.search(it.get("url") or ""):
            continue
        w, h = it.get("width") or 0, it.get("height") or 0
        if w < 1200 or h == 0 or not (1.2 <= w / h <= 2.2):
            continue
        try:
            img = requests.get(it["url"], headers={"User-Agent": "GuideMontessori/1.0"}, timeout=60)
            if not img.ok or len(img.content) < 80_000:
                continue
            if not _valid_image(img.content):
                continue
            if hashlib.sha1(img.content).hexdigest() in used:
                continue
            credit = {
                "photographer": it.get("creator"),
                "profile": it.get("creator_url"),
                "source": it.get("foreign_landing_url"),
                "license": it.get("license"),
            }
            print(f"    ✓ Openverse — {it.get('title') or query} ({w}×{h}, {it.get('license')})")
            return img.content, credit
        except Exception:
            continue
    return None, None


def generate_pollinations(prompt: str) -> bytes | None:
    """Génération gratuite sans clé (Pollinations)."""
    import hashlib
    full = f"{IMG_STYLE} Scene: {prompt}"
    seed = int(hashlib.sha1(prompt.encode()).hexdigest()[:8], 16) % 10**6
    try:
        r = requests.get(
            f"https://image.pollinations.ai/prompt/{requests.utils.quote(full)}",
            params={"width": 1280, "height": 853, "nologo": "true", "model": "flux", "seed": seed},
            timeout=180,
        )
    except Exception as e:
        print(f"    ✗ Pollinations : {type(e).__name__}")
        return None
    if not r.ok:
        print(f"    ✗ Pollinations : HTTP {r.status_code}")
        return None
    return _valid_image(r.content)


def unsplash_keys() -> list[str]:
    """Rotation sur plusieurs applications : chacune plafonne à 50 req/h."""
    keys = []
    for env in ("UNSPLASH_ACCESS_KEY", "UNSPLASH_ACCESS_KEY_2", "UNSPLASH_ACCESS_KEY_3"):
        v = os.environ.get(env)
        if v and v.strip():
            keys.append(v.strip())
    return keys


def generate_unsplash(slug: str):
    """(bytes, credit) depuis Unsplash, ou (None, None)."""
    keys = unsplash_keys()
    if not keys:
        print("    ✗ Unsplash : aucune clé configurée")
        return None, None
    query = UNSPLASH_QUERIES.get(slug)
    if not query:
        return None, None

    for i, key in enumerate(keys, 1):
        try:
            r = requests.get(
                UNSPLASH_SEARCH,
                headers={"Authorization": f"Client-ID {key}", "Accept-Version": "v1"},
                params={"query": query, "per_page": "20", "orientation": "landscape", "content_filter": "high"},
                timeout=30,
            )
        except Exception as e:
            print(f"    ✗ Unsplash clé {i} : {type(e).__name__}")
            continue

        if r.status_code in (401, 403):
            print(f"    ✗ Unsplash clé {i} : HTTP {r.status_code} — {r.text[:120]}")
            continue
        if not r.ok:
            print(f"    ✗ Unsplash clé {i} : HTTP {r.status_code}")
            continue

        for ph in r.json().get("results", []):
            if ph.get("premium"):
                continue
            w, h = ph.get("width") or 0, ph.get("height") or 0
            if w < 1600 or h == 0 or not (1.2 <= w / h <= 2.2):
                continue
            try:
                img = requests.get(ph["urls"]["raw"] + "&w=1600&fm=jpg&q=85", timeout=60)
                if not img.ok or len(img.content) < 80_000:
                    continue
                # Exigé par les guidelines Unsplash : signaler le téléchargement.
                try:
                    requests.get(ph["links"]["download_location"],
                                 headers={"Authorization": f"Client-ID {key}"}, timeout=15)
                except Exception:
                    pass
                credit = {
                    "photographer": (ph.get("user") or {}).get("name"),
                    "profile": (ph.get("user") or {}).get("links", {}).get("html"),
                    "source": ph.get("links", {}).get("html"),
                    "license": "Unsplash License",
                }
                print(f"    ✓ Unsplash — {ph.get('alt_description') or query} ({w}×{h}) — clé {i}")
                return img.content, credit
            except Exception as e:
                print(f"    ! Unsplash image ignorée : {type(e).__name__}")
                continue
    return None, None


def generate_flux(prompt: str) -> bytes | None:
    """Génère via Cloudflare Workers AI, en logguant la vraie raison d'un échec."""
    acct = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    tok = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not (acct and tok):
        print("    ✗ Cloudflare : credentials absents")
        return None

    full = f"{IMG_STYLE} Scene: {prompt}"
    try:
        r = requests.post(
            FLUX_URL.format(acct=acct),
            headers={"Authorization": f"Bearer {tok}"},
            json={"prompt": full, "steps": 6},
            timeout=180,
        )
    except Exception as e:
        print(f"    ✗ Cloudflare : exception réseau {type(e).__name__}: {e}")
        return None

    if not r.ok:
        print(f"    ✗ Cloudflare : HTTP {r.status_code} — {r.text[:300]}")
        return None

    try:
        payload = r.json()
        image = payload["result"]["image"]
    except Exception as e:
        print(f"    ✗ Cloudflare : réponse inattendue ({e}) — {r.text[:200]}")
        return None

    try:
        raw = requests.get(image, timeout=60).content if str(image).startswith("http") else base64.b64decode(image)
    except Exception as e:
        print(f"    ✗ Cloudflare : récupération de l'image impossible ({e})")
        return None

    try:
        data = _to_webp(raw)
    except Exception as e:
        print(f"    ✗ conversion WebP impossible : {type(e).__name__}: {e}")
        return None

    # On ne passe PAS par inspect_image() : il interroge llm_config(), qui pointe
    # sur deepseek-flash via DEEPSEEK_API_KEY — un modèle sans vision. Il répondait
    # donc du texte au hasard et rejetait 100 % des images générées.
    # Les prompts imposent déjà le style photo, et la sélection se fait à l'œil.
    return data

CONTENT = ROOT / "src" / "content"
PHOTOS = ROOT / "public" / "images" / "photos"

PROMPTS = {
    "etagere-montessori-jouets-rotation": (
        "A low wooden Montessori shelf at child height in a warm home bedroom, "
        "three shallow wooden trays with simple natural materials arranged from simple to complex, "
        "bare wood floor, soft morning light from a window, no text, no visible face"
    ),
    "tour-observation-montessori-age-stabilite": (
        "A wooden learning tower standing beside a kitchen counter in a warm family kitchen, "
        "a toddler's hands resting on the counter, bowl and wooden spoon, soft daylight, "
        "natural wood textures, no text, no visible face"
    ),
    "amenager-un-coin-lecture-montessori": (
        "A cosy children's reading corner in a warm home, a low front-facing wooden bookshelf "
        "displaying picture books, a folded blanket and cushions on a wool rug, soft window light, "
        "no text, no people"
    ),
    "preparation-environnement-montessori": (
        "A prepared Montessori playroom in a family home, low open shelf with a few wooden trays, "
        "a small table and chair at child height, a green plant, warm daylight, "
        "calm and uncluttered, no text, no people"
    ),
    "agent-accueil-petite-enfance-offres-salaires": (
        "A small welcoming reception area of a nursery, light wooden counter, a plant and a chair, "
        "soft daylight through a window, warm and calm atmosphere, no text, no people"
    ),
    "accueil-grand-age-methode-montessori-france-tv": (
        "Close-up of an elderly person's hands and a caregiver's hands sorting simple objects "
        "in a shallow wooden tray on a table, warm indoor light, soft focus, respectful atmosphere, "
        "no text, no identifiable face"
    ),
    "atelier-montessori-rochechouart-aide-moi-a-faire-seul": (
        "Children's hands manipulating wooden Montessori materials on a wooden table during a workshop, "
        "small bowls and sorting trays, warm natural light from a large window, "
        "no text, no identifiable face"
    ),
    "bougeotheque-municipale-bordeaux-petite-enfance": (
        "A toddler balancing barefoot on a low wooden beam in a bright indoor movement play space, "
        "soft mat and cushions on the floor, warm daylight, gentle motion, "
        "no text, no identifiable face"
    ),
    "apprentissage-vie-pratique-montessori-vaisselle": (
        "A child's hands washing a small ceramic bowl and cup at a low basin in a warm kitchen, "
        "wooden dish brush and a linen drying cloth, soft daylight, no text, no identifiable face"
    ),
    "la-tour-pink-montessori-developpement-equilibre-enfant": (
        "Ten graded wooden pink cubes stacked into a tower on a small wooden table in a calm playroom, "
        "warm natural light, shallow depth of field, no text, no people"
    ),
    "ecole-montessori-irisia-aix-chantier-cour": (
        "A French school courtyard with large plane trees casting dappled light on gravel and paving, "
        "edge of an old stone building in the background, late afternoon light, "
        "no text, no people"
    ),
}


def find_entry(slug: str):
    for col in ("guides", "news"):
        p = CONTENT / col / f"{slug}.mdx"
        if p.exists():
            return p
    return None


def split_frontmatter(text: str):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        raise ValueError("frontmatter introuvable")
    return m.group(1), text[m.end():]


def read_str(fm: str, key: str, default: str = "") -> str:
    m = re.search(rf"^{key}:\s*(.+)$", fm, re.M)
    if not m:
        return default
    raw = m.group(1).strip()
    try:
        value = json.loads(raw)
        if isinstance(value, str):
            return value
    except Exception:
        pass
    return raw.strip('"').strip("'")


def set_str(fm: str, key: str, value: str) -> str:
    line = f"{key}: {json.dumps(value, ensure_ascii=False)}"
    if re.search(rf"^{key}:", fm, re.M):
        return re.sub(rf"^{key}:.*$", lambda _: line, fm, count=1, flags=re.M)
    return fm.rstrip("\n") + "\n" + line


def process(slug: str, prompt: str) -> bool:
    path = find_entry(slug)
    if not path:
        print(f"✗ {slug}: fichier introuvable", file=sys.stderr)
        return False

    text = path.read_text()
    fm, body = split_frontmatter(text)
    title = read_str(fm, "title", slug)
    emoji = read_str(fm, "emoji", "")

    data = None
    credit = None

    # 1. Vraie photo : Pixabay (clé gratuite) puis Openverse puis Unsplash
    data, credit = generate_pixabay(slug)
    if not data:
        data, credit = generate_openverse(slug)
    if not data:
        data, credit = generate_unsplash(slug)

    # 2. Génération IA si Unsplash n'a rien donné
    if not data:
        for attempt in range(1, 4):
            print(f"  génération {slug} — essai {attempt}/3")
            data = generate_flux(prompt)
            if data:
                break
        if not data:
            print(f"  {slug} — repli Pollinations (gratuit, sans clé)")
            data = generate_pollinations(prompt)

    if not data:
        print(f"  ⚠ IA indisponible pour {slug}, tentative stock libre")
        try:
            data = fetch_stock(f"{title} montessori", slug)
        except Exception as e:
            print(f"    ✗ stock libre : {type(e).__name__}: {e}")

    if not data:
        print(f"  ⚠ stock libre indisponible pour {slug}, carte de marque")
        fm = set_str(fm, "image", make_brand_card(slug, title, emoji))
        path.write_text(f"---\n{fm}\n---\n{body}")
        return False

    PHOTOS.mkdir(parents=True, exist_ok=True)
    out = PHOTOS / f"{slug}.webp"
    out.write_bytes(_to_webp(data))
    fm = set_str(fm, "image", f"/images/photos/{slug}.webp")
    if credit and credit.get("photographer"):
        # La source réelle est dans le crédit (Pixabay, Openverse, Unsplash…).
        src_label = "Unsplash" if "Unsplash" in (credit.get("license") or "") else (
            "Pixabay" if "Pixabay" in (credit.get("license") or "") else "Openverse")
        fm = set_str(fm, "imageCredit", f"Photo : {credit['photographer']} / {src_label}")
    path.write_text(f"---\n{fm}\n---\n{body}")
    print(f"  ✓ {out.relative_to(ROOT)} ({out.stat().st_size // 1024} Ko)")
    return True


def _unused_diagnose() -> None:
    """Vérifie chaque fournisseur d'images et affiche l'erreur réelle."""
    import os
    import requests

    acct = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    tok = os.environ.get("CLOUDFLARE_API_TOKEN")
    print(f"CLOUDFLARE_ACCOUNT_ID: {'oui' if acct else 'non'}")
    print(f"CLOUDFLARE_API_TOKEN: {'oui' if tok else 'non'}")
    print(f"OPENAI_API_KEY: {'oui' if os.environ.get('OPENAI_API_KEY') else 'non'}")

    if acct and tok:
        try:
            r = requests.post(
                f"https://api.cloudflare.com/client/v4/accounts/{acct}/ai/run/@cf/black-forest-labs/flux-1-schnell",
                headers={"Authorization": f"Bearer {tok}"},
                json={"prompt": "a wooden shelf", "steps": 4},
                timeout=120,
            )
            print(f"→ Workers AI : HTTP {r.status_code}")
            if not r.ok:
                print("   " + r.text[:500])
        except Exception as e:
            print(f"→ Workers AI : exception {e}")

    try:
        r = requests.get("https://api.openverse.org/v1/images/?q=montessori&page_size=1", timeout=15)
        print(f"→ Openverse : HTTP {r.status_code}")
    except Exception as e:
        print(f"→ Openverse : exception {type(e).__name__}")

    try:
        r = requests.get(
            "https://commons.wikimedia.org/w/api.php",
            params={"action": "query", "format": "json", "list": "search",
                    "srsearch": "montessori filetype:bitmap", "srnamespace": "6", "srlimit": "3"},
            headers={"User-Agent": "GuideMontessori/1.0"}, timeout=15,
        )
        hits = len(r.json().get("query", {}).get("search", []))
        print(f"→ Wikimedia : HTTP {r.status_code}, {hits} résultats")
    except Exception as e:
        print(f"→ Wikimedia : exception {type(e).__name__}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", action="append", default=[])
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--diagnose", action="store_true")
    args = ap.parse_args()

    if args.diagnose:
        diagnose()
        return 0

    slugs = list(PROMPTS) if (args.all or not args.slug) else args.slug
    ok = 0
    for slug in slugs:
        if slug not in PROMPTS:
            print(f"⚠ {slug}: pas de prompt défini", file=sys.stderr)
            continue
        print(f"→ {slug}")
        if process(slug, PROMPTS[slug]):
            ok += 1
    print(f"\n{ok}/{len(slugs)} illustrations générées")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
