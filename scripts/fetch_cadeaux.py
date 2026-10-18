#!/usr/bin/env python3
"""Refresh src/data/cadeaux.json : ScraperAPI + DeepSeek (filtre anti-plastique/électronique)."""
import json
import os
import sys
from difflib import SequenceMatcher
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "data" / "cadeaux.json"
TAG = os.environ.get("AMAZON_TAG", "mtssri-21")
SCRAPER = os.environ.get("SCRAPER_API_KEY")

QUERIES = [
    # 0-12m
    "hochet bois bebe", "mobile montessori bois bebe", "arche eveil bois bebe",
    "chariot marcheur bois bebe", "anneau dentition bois", "tapis eveil coton bio",
    # 1-3ans
    "boite permanence objet montessori", "puzzle encastrement bois", "cylindres gradues bois",
    "planche equilibre enfant bois", "boite serrures enfant", "tour observation montessori bois",
    "lit cabane bois enfant", "triangle pikler bois", "bibliotheque enfant bois montessori",
    # 3-6ans
    "lettres rugueuses montessori", "cartes nomenclature montessori", "tour rose montessori",
    "barres rouges montessori", "globe montessori bois", "perles dorees montessori",
    "bureau enfant bois reglable", "perles lacage enfant bois",
    # renfort cases faibles
    "portique eveil bois bebe", "etagere basse bois bebe", "chariot marche bois bebe",
    "set vaisselle enfant bois", "table activites bois enfant", "encastrements bois montessori",
    "materiel sensoriel montessori bois", "jeu tri bois enfant", "rouleau rain stick bois",
    "porte bebe marche bois", "cube activite bois enfant", "perles enfilage bois enfant",
]
PER_QUERY = 3
MIN_PER_CELL = 6
MAX_ITEMS = 70


def scraper_search(q: str) -> list[dict]:
    r = requests.get("https://api.scraperapi.com/structured/amazon/search",
                     params={"api_key": SCRAPER, "query": q, "country": "fr"}, timeout=90)
    r.raise_for_status()
    out = []
    for it in r.json().get("results", [])[:PER_QUERY]:
        if it.get("asin") and it.get("name"):
            price = it.get("price") or (it.get("price_string") and float(
                "".join(c for c in it["price_string"] if c.isdigit() or c == ".") or 0))
            out.append({"asin": str(it["asin"]), "title": str(it["name"]).strip(),
                        "price": float(price) if price else None,
                        "image": it.get("image")})
    return out


def is_duplicate(nom: str, items: list[dict], threshold: float = 0.75) -> bool:
    return any(SequenceMatcher(None, nom.lower(), x["nom"].lower()).ratio() > threshold for x in items)


def budget_of(price) -> str:
    return "moins-30" if (price or 0) < 30 else ("30-70" if (price or 0) <= 70 else "plus-70")


def llm_curate(items: list[dict]) -> dict:
    key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENROUTER_API_KEY")
    if not key:
        return {}
    base = "https://api.deepseek.com" if os.environ.get("DEEPSEEK_API_KEY") else "https://openrouter.ai/api/v1"
    model = "deepseek-flash" if os.environ.get("DEEPSEEK_API_KEY") else "deepseek/deepseek-v4.1-flash"
    tool = {"type": "function", "function": {
        "name": "cadeaux",
        "parameters": {
            "type": "object", "required": ["items"],
            "properties": {"items": {"type": "array", "items": {
                "type": "object", "required": ["id", "nom", "age", "axe", "description", "pointsForts"],
                "properties": {
                    "id": {"type": "string"},
                    "nom": {"type": "string", "description": "titre FR concis, marque conservée"},
                    "age": {"type": "string", "enum": ["0-12m", "1-3ans", "3-6ans"]},
                    "axe": {"type": "string", "enum": ["sensoriel", "motricite", "autonomie"]},
                    "description": {"type": "string", "description": "15 mots max, parents"},
                    "pointsForts": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 2},
                }}}},
        }}}
    prompt = """Tu es expert Montessori. Pour chaque produit (id=asin) :
- REJETTE (ne renvoie pas) tout jouet en plastique, électronique, à piles, lumineux ou sonore, et tout produit non-jouet.
- Garde uniquement bois/naturel/vraie pédagogie. Détermine âge et axe pédagogique.
- Rédige nom FR, description 15 mots, 2 points forts.
Produits :
""" + json.dumps([{"id": i["asin"], "titre": i["title"]} for i in items], ensure_ascii=False)
    try:
        r = requests.post(f"{base}/chat/completions", headers={"Authorization": f"Bearer {key}"},
                          json={"model": model, "temperature": 0.3, "max_tokens": 6000,
                                "thinking": {"type": "disabled"} if base.endswith("deepseek.com") else {},
                                "tools": [tool], "tool_choice": "auto",
                                "messages": [{"role": "user", "content": prompt}]},
                          timeout=240)
        calls = r.json()["choices"][0]["message"].get("tool_calls") or []
        if calls:
            data = json.loads(calls[0]["function"]["arguments"]).get("items", [])
            return {x["id"]: x for x in data}
    except Exception as e:
        print(f"⚠ LLM : {e}", file=sys.stderr)
    return {}


def main() -> int:
    if not SCRAPER:
        sys.exit("SCRAPER_API_KEY manquant")
    seen, raw = set(), []
    for q in QUERIES:
        try:
            for it in scraper_search(q):
                if it["asin"] not in seen:
                    seen.add(it["asin"])
                    raw.append(it)
        except requests.RequestException as e:
            print(f"⚠ '{q}' : {e}", file=sys.stderr)
    print(f"{len(raw)} produits scrapés")
    curated = llm_curate(raw)
    out = []
    for it in raw:
        if (c := curated.get(it["asin"])) and not is_duplicate(c["nom"], out):
            out.append({"id": it["asin"].lower(), "asin": it["asin"], "nom": c["nom"],
                        "age": c["age"], "axe": c["axe"], "budget": budget_of(it.get("price")),
                        "image": it.get("image"), "description": c["description"],
                        "pointsForts": c["pointsForts"]})
    # Fusion : on garde les anciens produits des cases non couvertes par le nouveau lot
    old = {x["asin"]: x for x in (json.loads(OUT.read_text()) if OUT.exists() else [])}
    merged = {x["asin"]: x for x in out}
    for asin, x in old.items():
        cell = sum(1 for m in merged.values() if m["age"] == x["age"] and m["budget"] == x["budget"])
        if asin not in merged and cell < MIN_PER_CELL:
            merged[asin] = x
    out = list(merged.values())[:MAX_ITEMS]
    if not out:
        print("aucun cadeau validé, cadeaux.json inchangé", file=sys.stderr)
        return 0
    missing = [(a, b) for a in ("0-12m", "1-3ans", "3-6ans") for b in ("moins-30", "30-70", "plus-70")
               if sum(1 for x in out if x["age"] == a and x["budget"] == b) < MIN_PER_CELL]
    if missing:
        print(f"⚠ cases < {MIN_PER_CELL} : {missing}", file=sys.stderr)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(f"✓ {len(out)} cadeaux → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
