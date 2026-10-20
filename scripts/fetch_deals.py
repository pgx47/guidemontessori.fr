#!/usr/bin/env python3
"""Refresh src/data/deals.json from ScraperAPI structured Amazon search (amazon.fr)."""
import json
import os
import sys
from datetime import date
from pathlib import Path

import requests

OUT = Path(__file__).resolve().parent.parent / "src" / "data" / "deals.json"
QUERIES = ["montessori jouets bébé", "matériel montessori", "montessori",
           "tour observation montessori", "triangle pikler", "lit cabane montessori",
           "puzzle montessori bois", "mobile montessori", "arcade eveil montessori",
           "etagere montessori enfant", "perles montessori", "cartes montessori"]
MAX_DEALS = 120
PER_PAGE = 12


def is_dup(nom: str, items: list, t: float = 0.7) -> bool:
    from difflib import SequenceMatcher
    return any(SequenceMatcher(None, nom.lower(), x["name"].lower()).ratio() > t for x in items)


def fmt_price(s: str, n) -> str:
    if "€" in s:
        return s
    if s.startswith("EUR "):
        return s[4:].strip().replace(".", ",") + " €"
    if isinstance(n, (int, float)):
        return f"{n:.2f}".replace(".", ",") + " €"
    return s


def main() -> int:
    key = os.environ.get("SCRAPER_API_KEY")
    if not key:
        print("SCRAPER_API_KEY manquant, deals.json inchangé", file=sys.stderr)
        return 0
    tag = os.environ.get("AMAZON_TAG", "mtssri-21")
    deals, seen = [], set()
    for q in QUERIES:
        if len(deals) >= MAX_DEALS:
            break
        try:
            r = requests.get(
                "https://api.scraperapi.com/structured/amazon/search",
                params={"api_key": key, "query": q, "country": "fr"},
                timeout=90,
            )
            r.raise_for_status()
        except requests.RequestException as e:
            print(f"échec '{q}': {e}", file=sys.stderr)
            continue
        for it in r.json().get("results", []):
            asin, name = str(it.get("asin") or ""), str(it.get("name") or "")
            if not asin or not name or asin in seen or is_dup(name, deals):
                continue
            seen.add(asin)
            deals.append({
                "asin": asin,
                "name": name,
                "image": it.get("image") or "",
                "url": f"https://www.amazon.fr/dp/{asin}?tag={tag}",
                "price": fmt_price(str(it.get("price_string") or ""), it.get("price")),
                "stars": it.get("stars") if isinstance(it.get("stars"), (int, float)) else None,
                "totalReviews": it.get("total_reviews") if isinstance(it.get("total_reviews"), int) else None,
                "isPrime": bool(it.get("has_prime")),
                "isLimitedDeal": bool(it.get("is_limited_deal")),
                "isBestSeller": bool(it.get("is_best_seller")),
                "isAmazonChoice": bool(it.get("is_amazon_choice")),
            })
            if len(deals) >= MAX_DEALS:
                break
    if not deals:
        print("aucun résultat, deals.json inchangé", file=sys.stderr)
        return 0
    if key := os.environ.get("DEEPSEEK_API_KEY"):
        try:
            r = requests.post("https://api.deepseek.com/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": "deepseek-flash", "temperature": 0.2, "max_tokens": 2000,
                      "thinking": {"type": "disabled"},
                      "messages": [{"role": "user", "content":
                        "Traduis chaque titre produit Amazon en français concis (max 10 mots), "
                        "garde les marques. Réponds en JSON {\"noms\": {\"asin\": \"titre fr\"}}.\n"
                        + json.dumps({d["asin"]: d["name"] for d in deals}, ensure_ascii=False)}]},
                timeout=90)
            if r.ok:
                txt = r.json()["choices"][0]["message"]["content"]
                if "{" in txt:
                    noms = json.loads(txt[txt.index("{"):txt.rindex("}") + 1]).get("noms", {})
                else:
                    noms = {}
                    for line in txt.splitlines():
                        if ":" in line:
                            k, _, v = line.partition(":")
                            k = k.strip().strip('"')
                            if k.isdigit() or k.startswith("B0"):
                                noms[k] = v.strip().strip('"').strip(",")
                print(f"traduction : {len(noms)} noms")
                for d in deals:
                    if noms.get(d["asin"]):
                        d["name"] = noms[d["asin"]]
        except Exception as e:
            print(f"⚠ traduction : {e}", file=sys.stderr)
    import random
    random.shuffle(deals)
    OUT.write_text(json.dumps({"updated": date.today().isoformat(), "deals": deals}, ensure_ascii=False, indent=2) + "\n")
    print(f"{len(deals)} offres écrites dans {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
