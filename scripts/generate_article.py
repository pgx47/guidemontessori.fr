#!/usr/bin/env python3
"""Generate an MDX article (guide or news) with Claude and write it to src/content/.

Usage:
  python scripts/generate_article.py --topic "meilleur lit cabane montessori" --type guide
  python scripts/generate_article.py --auto            # next pending topic in topics.json
  python scripts/generate_article.py --auto --dry-run  # print MDX, write nothing
"""
import argparse
import json
import os
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
TOPICS = ROOT / "scripts" / "topics.json"
CONTENT = ROOT / "src" / "content"
DIRS = {"guide": CONTENT / "guides", "news": CONTENT / "news"}
API_URL = "https://api.anthropic.com/v1/messages"
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")

SYSTEM = """Tu es rédacteur web senior pour GuideMontessori.fr, site français destiné aux parents qui appliquent la pédagogie Montessori à la maison.

Style :
- Français impeccable avec accents, ton chaleureux mais précis, phrases variées.
- Interdits : "dans un monde où", "plongeons", "il est crucial", "en conclusion", "n'hésitez pas", "véritable", "incontournable", "que vous soyez", listes à rallonge, emojis dans le corps.
- Concret : âges, dimensions, matériaux, normes (EN 71, FSC), gestes de présentation, erreurs fréquentes.
- Jamais de prix précis, jamais de promesse médicale, jamais d'invention de marque ou de référence produit.
- Cite Maria Montessori seulement avec des citations réelles et connues.

Format du corps (champ body) : Markdown pur, sans titre H1, sections en ## et ###, paragraphes courts, au moins un tableau Markdown comparatif pour un guide.
Pour placer un produit, écris seul sur sa ligne le marqueur [[PRODUIT:n]] (n = index 0-based dans la liste fournie). Chaque produit fourni doit apparaître une fois.
N'utilise ni HTML, ni accolades { }, ni chevrons < >."""

TOOL = {
    "name": "publish_article",
    "description": "Publie l'article structuré.",
    "input_schema": {
        "type": "object",
        "required": ["title", "description", "slug", "keywords", "emoji", "body", "faq", "products"],
        "properties": {
            "title": {"type": "string", "description": "Titre SEO 40-70 caractères, mot-clé principal au début."},
            "description": {"type": "string", "description": "Meta description 120-160 caractères, incitative."},
            "slug": {"type": "string", "description": "kebab-case ascii, 3-7 mots."},
            "keywords": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 8},
            "emoji": {"type": "string", "description": "Un seul emoji représentatif."},
            "body": {"type": "string", "description": "Corps Markdown (1200-1800 mots pour un guide, 400-700 pour une news)."},
            "faq": {
                "type": "array",
                "minItems": 3,
                "maxItems": 5,
                "items": {
                    "type": "object",
                    "required": ["question", "answer"],
                    "properties": {"question": {"type": "string"}, "answer": {"type": "string"}},
                },
            },
            "products": {
                "type": "array",
                "description": "Un élément par produit fourni, dans le même ordre.",
                "items": {
                    "type": "object",
                    "required": ["pointsForts", "pointsFaibles"],
                    "properties": {
                        "pointsForts": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 4},
                        "pointsFaibles": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 3},
                    },
                },
            },
        },
    },
}


def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def existing_articles() -> list[tuple[str, str]]:
    out = []
    for d in DIRS.values():
        for f in d.glob("*.md*"):
            m = re.search(r'^title:\s*"?(.*?)"?\s*$', f.read_text(), re.M)
            out.append((f.stem, m.group(1) if m else f.stem))
    return out


def call_llm(topic: dict, kind: str) -> dict:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        sys.exit("ANTHROPIC_API_KEY manquant")
    products = topic.get("products", [])
    links = "\n".join(f"- /articles/{s}/ : {t}" for s, t in existing_articles())
    prompt = f"""Type : {"guide evergreen / comparatif" if kind == "guide" else "brève d'actualité"}
Mot-clé principal : {topic["keyword"]}
Angle : {topic.get("angle", "répondre précisément à l'intention de recherche du parent")}

Produits à intégrer (n'invente aucun autre produit) :
{json.dumps(products, ensure_ascii=False, indent=2) if products else "aucun"}

Articles existants pour 2 à 4 liens internes Markdown pertinents :
{links}

Appelle l'outil publish_article."""
    r = requests.post(
        API_URL,
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={
            "model": MODEL,
            "max_tokens": 8000,
            "system": SYSTEM,
            "tools": [TOOL],
            "tool_choice": {"type": "tool", "name": TOOL["name"]},
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=300,
    )
    if not r.ok:
        sys.exit(f"Erreur API {r.status_code}: {r.text[:500]}")
    block = next(b for b in r.json()["content"] if b["type"] == "tool_use")
    return block["input"]


def esc(s: str) -> str:
    return s.replace("{", "&#123;").replace("}", "&#125;").replace("<", "&lt;")


def jsx_list(items: list[str]) -> str:
    return "{" + json.dumps(items, ensure_ascii=False) + "}"


def render_mdx(a: dict, topic: dict, kind: str, today: str) -> str:
    products = topic.get("products", [])
    fm = {
        "title": a["title"].strip(),
        "description": a["description"].strip(),
        "publishDate": today,
        "category": "guides" if kind == "guide" else "news",
        "author": "Rédaction GuideMontessori",
        "keywords": a["keywords"],
        "emoji": a["emoji"],
        "faq": a["faq"],
    }
    if topic.get("image"):
        fm["image"] = topic["image"]
    if products:
        fm["asin"] = products[0]["asin"]
    lines = ["---"] + [f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in fm.items()] + ["---", ""]
    if products:
        lines += ["import AffiliateBox from '../../components/AffiliateBox.astro';", ""]

    body = esc(a["body"].strip())
    used = set()

    def box(i: int) -> str:
        if i >= len(products):
            return ""
        used.add(i)
        p, g = products[i], (a["products"][i] if i < len(a["products"]) else {"pointsForts": [], "pointsFaibles": []})
        return (
            "<AffiliateBox\n"
            f"  asin={json.dumps(p['asin'])}\n"
            f"  nom={json.dumps(p['nom'], ensure_ascii=False)}\n"
            f"  pointsForts={jsx_list(g['pointsForts'])}\n"
            f"  pointsFaibles={jsx_list(g['pointsFaibles'])}\n"
            "/>"
        )

    body = re.sub(r"^[ \t]*\[\[PRODUIT:(\d+)\]\][ \t]*$", lambda m: "\n" + box(int(m.group(1))) + "\n", body, flags=re.M)
    missing = [i for i in range(len(products)) if i not in used]
    if missing:
        body += "\n\n## Notre sélection\n\n" + "\n\n".join(box(i) for i in missing)
    return "\n".join(lines) + "\n" + re.sub(r"\n{3,}", "\n\n", body) + "\n"


def validate(a: dict) -> list[str]:
    errs = []
    if not 10 <= len(a["title"]) <= 110:
        errs.append(f"title {len(a['title'])} car.")
    if not 50 <= len(a["description"]) <= 200:
        errs.append(f"description {len(a['description'])} car.")
    if re.search(r"^#\s", a["body"], re.M):
        errs.append("H1 dans le corps")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", help="mot-clé principal")
    ap.add_argument("--type", choices=["guide", "news"], default="guide")
    ap.add_argument("--auto", action="store_true", help="prend le prochain sujet 'pending' de topics.json")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = json.loads(TOPICS.read_text())
    if args.auto:
        topic = next((t for t in data["topics"] if t.get("status") == "pending"), None)
        if not topic:
            print("Aucun sujet en attente.")
            return 0
        kind = topic.get("type", "guide")
    elif args.topic:
        topic = next((t for t in data["topics"] if t["keyword"].lower() == args.topic.lower()), None)
        if topic is None:
            topic = {"keyword": args.topic, "type": args.type, "status": "pending", "products": []}
            data["topics"].append(topic)
        kind = args.type
    else:
        ap.error("--topic ou --auto requis")

    print(f"→ {kind} : {topic['keyword']} ({MODEL})")
    a = call_llm(topic, kind)
    if errs := validate(a):
        print("⚠ " + ", ".join(errs), file=sys.stderr)

    today = date.today().isoformat()
    slug = slugify(a.get("slug") or a["title"])
    taken = {s for s, _ in existing_articles()}
    if slug in taken:
        slug = f"{slug}-{today[:7]}"
    mdx = render_mdx(a, topic, kind, today)

    if args.dry_run:
        print(mdx)
        return 0

    path = DIRS[kind] / f"{slug}.mdx"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(mdx)
    topic.update(status="published", slug=slug, publishedAt=today)
    TOPICS.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"✓ {path.relative_to(ROOT)}")
    if out := os.environ.get("GITHUB_OUTPUT"):
        with open(out, "a") as f:
            f.write(f"path={path.relative_to(ROOT)}\nslug={slug}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
