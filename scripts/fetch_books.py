#!/usr/bin/env python3
"""Refresh src/data/books.json : ScraperAPI (amazon.fr) + DeepSeek pour résumé & catégorisation."""
import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "data" / "books.json"
TAG = os.environ.get("AMAZON_TAG", "duckurbate-21")
SCRAPER = os.environ.get("SCRAPER_API_KEY")

# (audience, category/level, requête amazon)
QUERIES = [
    ("child", "Éveil", "livre montessori eveil 0-3 ans"),
    ("child", "Lecture", "livre montessori lecture 4-7 ans"),
    ("child", "Mathématiques", "livre montessori mathematiques enfant"),
    ("child", "Grands Récits", "grands recits montessori livre"),
    ("parent", "Essentiel", "livre maria montessori pedagogie"),
    ("parent", "Approfondi", "montessori education positive livre parents"),
    ("parent", "Pratique", "activites montessori a la maison guide"),
]
PER_QUERY = 4
MAX_NEW = 8  # nouveautés max par run pour limiter les appels LLM


def scraper_search(q: str) -> list[dict]:
    r = requests.get("https://api.scraperapi.com/structured/amazon/search",
                     params={"api_key": SCRAPER, "query": q, "country": "fr"}, timeout=90)
    r.raise_for_status()
    out = []
    for it in r.json().get("results", [])[:PER_QUERY]:
        if it.get("asin") and it.get("name"):
            out.append({"asin": str(it["asin"]), "title": str(it["name"]).strip(),
                        "author": it.get("author") or "", "stars": it.get("stars"),
                        "price": str(it.get("price_string") or "").replace("EUR ", "").replace(".", ",") + " €"
                                 if it.get("price_string") else ""})
    return out


def llm_summarize(books: list[dict]) -> list[dict]:
    key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENROUTER_API_KEY")
    if not key:
        return books
    base = "https://api.deepseek.com" if os.environ.get("DEEPSEEK_API_KEY") else "https://openrouter.ai/api/v1"
    model = "deepseek-flash" if os.environ.get("DEEPSEEK_API_KEY") else "deepseek/deepseek-v4.1-flash"
    tool = {"type": "function", "function": {
        "name": "books",
        "parameters": {
            "type": "object", "required": ["books"],
            "properties": {"books": {"type": "array", "items": {
                "type": "object", "required": ["id", "description", "ageRange"],
                "properties": {
                    "id": {"type": "string"},
                    "description": {"type": "string", "description": "2 phrases max, parents, sans prix"},
                    "ageRange": {"type": "string", "description": "ex '0-3 ans' ou '' pour parent"},
                }}}},
        }}}
    items = [{"id": b["asin"], "titre": b["title"], "auteur": b.get("author")} for b in books]
    r = requests.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": model, "temperature": 0.3, "max_tokens": 3000, "tools": [tool],
              "tool_choice": "auto",
              "messages": [{"role": "user", "content":
                  "Pour chaque livre (id=asin), rédige une description 2 phrases pour parents sur un site Montessori, "
                  "et la tranche d'âge (vide si livre pour adultes).\n" + json.dumps(items, ensure_ascii=False)}]},
        timeout=180)
    if not r.ok:
        print(f"⚠ LLM {r.status_code}", file=sys.stderr)
        return books
    calls = r.json()["choices"][0]["message"].get("tool_calls") or []
    if not calls:
        return books
    data = json.loads(calls[0]["function"]["arguments"]).get("books", [])
    by_id = {x["id"]: x for x in data}
    for b in books:
        if u := by_id.get(b["asin"]):
            b["description"], b["ageRange"] = u["description"], u.get("ageRange") or ""
    return books


def main() -> int:
    if not SCRAPER:
        sys.exit("SCRAPER_API_KEY manquant")
    existing = {b["id"]: b for b in json.loads(OUT.read_text())} if OUT.exists() else {}
    known_asins = {b.get("asin") for b in existing.values() if b.get("asin")}
    new_books, seen = [], set()
    for audience, cat, q in QUERIES:
        try:
            for it in scraper_search(q):
                if it["asin"] in seen or it["asin"] in known_asins:
                    continue
                seen.add(it["asin"])
                new_books.append({**it, "category" if audience == "child" else "level": cat,
                                  "targetAudience": audience})
        except requests.RequestException as e:
            print(f"⚠ '{q}': {e}", file=sys.stderr)
    new_books = new_books[:MAX_NEW]
    if not new_books:
        print("Aucun nouveau livre.")
        return 0
    print(f"{len(new_books)} nouveaux livres")
    llm_summarize(new_books)
    out = list(existing.values())
    for b in new_books:
        bid = "b-" + b["asin"].lower()
        out.append({"id": bid, "title": b["title"], "author": b.get("author", ""),
                    "ageRange": b.get("ageRange", ""), "description": b.get("description", b["title"]),
                    "amazonUrl": f"https://www.amazon.fr/dp/{b['asin']}?tag={TAG}",
                    "price": b.get("price") or "Voir Amazon", "category": b.get("category"),
                    "level": b.get("level"), "targetAudience": b["targetAudience"], "asin": b["asin"]})
    out = [{k: v for k, v in b.items() if v is not None} for b in out]
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(f"✓ {OUT} ({len(out)} livres)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
