#!/usr/bin/env python3
"""Génère une illustration pour les articles qui n'ont qu'une carte de marque.

Usage :
  python scripts/regen_images.py --all
  python scripts/regen_images.py --slug etagere-montessori-jouets-rotation

Écrit `public/images/photos/<slug>.webp` et met à jour le frontmatter.
Chaîne : génération IA (Flux/OpenAI) -> stock libre -> carte de marque.
Nécessite CLOUDFLARE_ACCOUNT_ID/CLOUDFLARE_API_TOKEN ou OPENAI_API_KEY.
"""
import argparse
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from generate_article import _to_webp, fetch_stock, generate_image, make_brand_card, ROOT  # noqa: E402

CONTENT = ROOT / "src" / "content"
PHOTOS = ROOT / "public" / "images" / "photos"

# Prompt éditorial par slug. On décrit une scène réelle, sans texte, sans
# visage identifiable, dans la continuité de la charte du site.
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


def frontmatter_split(text: str):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        raise ValueError("frontmatter introuvable")
    return m.group(1), text[m.end():]


def write_image(slug: str, data: bytes) -> Path:
    PHOTOS.mkdir(parents=True, exist_ok=True)
    out = PHOTOS / f"{slug}.webp"
    out.write_bytes(_to_webp(data))
    return out


def process(slug: str, prompt: str) -> bool:
    path = find_entry(slug)
    if not path:
        print(f"✗ {slug}: fichier introuvable", file=sys.stderr)
        return False

    text = path.read_text()
    fm_raw, body = frontmatter_split(text)
    fm = yaml.safe_load(fm_raw) or {}
    title = fm.get("title", slug)
    emoji = fm.get("emoji", "")

    data = None
    for attempt in range(1, 4):
        print(f"  génération {slug} — essai {attempt}/3")
        data = generate_image(prompt, slug)
        if data:
            break
    if not data:
        print(f"  ⚠ génération IA indisponible pour {slug}, tentative stock libre")
        data = fetch_stock(f"{title} montessori", slug)
    if not data:
        print(f"  ⚠ stock libre indisponible pour {slug}, carte de marque")
        fm["image"] = make_brand_card(slug, title, emoji)
        path.write_text(f"---\n{yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).strip()}\n---\n{body}")
        return False

    out = write_image(slug, data)
    fm["image"] = f"/images/photos/{slug}.webp"
    fm.pop("imageSource", None)
    path.write_text(f"---\n{yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).strip()}\n---\n{body}")
    print(f"  ✓ {out.relative_to(ROOT)} ({out.stat().st_size // 1024} Ko)")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", action="append", default=[])
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    slugs = list(PROMPTS) if args.all or not args.slug else args.slug
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
