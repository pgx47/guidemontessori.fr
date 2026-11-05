#!/usr/bin/env python3
"""Vérifie que les ASIN du site sont encore en vente sur Amazon.fr.

Un produit retiré de la vente laisse un lien mort et, dans les encarts, une
photo manquante. Ce script interroge l'endpoint produit ScraperAPI pour chaque
ASIN des données (`deals.json`, `cadeaux.json`, `topics.json`) et des articles
(`<AffiliateBox asin="…">`).

Usage :
  python scripts/audit_asins.py                     # rapport seul
  python scripts/audit_asins.py --prune             # retire les ASIN morts des données
  python scripts/audit_asins.py --json /tmp/asins.json
  python scripts/audit_asins.py --source scraper    # Chromium local, 0 crédit

Sources (--source auto, par défaut) : Chromium local (`amazon_scraper`), puis
ScraperAPI (1 crédit par ASIN, rotation de clés automatique).
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import amazon_scraper  # noqa: E402
from scraper_api import ScraperExhausted, available, get as scraper_get  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "src" / "data"
CONTENT = ROOT / "src" / "content"
DEALS = DATA / "deals.json"
CADEAUX = DATA / "cadeaux.json"
TOPICS = ROOT / "scripts" / "topics.json"
BOX_RE = re.compile(r'<AffiliateBox\b[^>]*asin=["\']([A-Z0-9]{10})["\']', re.S)


def collect() -> dict[str, list[str]]:
    """{asin: [provenance, …]}"""
    found: dict[str, list[str]] = {}

    def add(asin: str, source: str) -> None:
        if asin:
            found.setdefault(asin, [])
            if source not in found[asin]:
                found[asin].append(source)

    if DEALS.exists():
        for it in json.loads(DEALS.read_text()).get("deals", []):
            add(str(it.get("asin") or ""), "deals")
    if CADEAUX.exists():
        for it in json.loads(CADEAUX.read_text()):
            if isinstance(it, dict):
                add(str(it.get("asin") or ""), "cadeaux")
    if TOPICS.exists():
        for topic in json.loads(TOPICS.read_text()).get("topics", []):
            for product in topic.get("products", []):
                add(str(product.get("asin") or ""), "topics")
    for col in ("guides", "news"):
        for path in sorted((CONTENT / col).glob("*.mdx")):
            for asin in BOX_RE.findall(path.read_text()):
                add(asin, f"{col}/{path.stem}")
    return found


def check(asin: str, source: str = "auto") -> tuple[str, str]:
    """('live'|'dead'|'unknown', libellé)."""
    if source in ("auto", "scraper") and amazon_scraper.available():
        try:
            data = amazon_scraper.product(asin)
            if data["alive"]:
                return "live", data["name"][:70]
            # Le navigateur peut recevoir un 404 de filtrage géographique :
            # en mode auto on demande confirmation à l'API avant de condamner.
            if source == "scraper":
                return "dead", "fiche introuvable (navigateur)"
        except amazon_scraper.Blocked as exc:
            if source == "scraper":
                return "unknown", f"scraper bloqué : {exc}"

    try:
        r = scraper_get("structured/amazon/product", {"asin": asin, "country": "fr"}, timeout=60)
    except ScraperExhausted:
        raise
    except Exception as exc:
        return "unknown", f"{type(exc).__name__}: {exc}"

    if r.status_code == 404:
        return "dead", "HTTP 404"
    if not r.ok:
        return "unknown", f"HTTP {r.status_code}"

    try:
        payload = r.json()
    except Exception:
        return "unknown", "réponse non JSON"

    name = str(payload.get("name") or "").strip()
    if not name:
        return "dead", "fiche sans nom (produit retiré)"
    return "live", name[:70]


def prune(dead: set[str]) -> list[str]:
    """Retire les ASIN morts des fichiers de données. Retourne les fichiers touchés."""
    touched = []

    if DEALS.exists():
        data = json.loads(DEALS.read_text())
        before = len(data.get("deals", []))
        data["deals"] = [d for d in data.get("deals", []) if str(d.get("asin")) not in dead]
        if len(data["deals"]) != before:
            DEALS.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
            touched.append(f"deals.json (-{before - len(data['deals'])})")

    if CADEAUX.exists():
        data = json.loads(CADEAUX.read_text())
        before = len(data)
        data = [d for d in data if str(d.get("asin")) not in dead]
        if len(data) != before:
            CADEAUX.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
            touched.append(f"cadeaux.json (-{before - len(data)})")

    if TOPICS.exists():
        data = json.loads(TOPICS.read_text())
        removed = 0
        for topic in data.get("topics", []):
            products = topic.get("products", [])
            kept = [p for p in products if str(p.get("asin")) not in dead]
            removed += len(products) - len(kept)
            topic["products"] = kept
        if removed:
            TOPICS.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
            touched.append(f"topics.json (-{removed})")

    return touched


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prune", action="store_true", help="retire les ASIN morts des données")
    ap.add_argument("--json", help="écrit le rapport détaillé dans ce fichier")
    ap.add_argument("--source", choices=("auto", "scraper", "api"), default="auto",
                    help="auto : Chromium local puis ScraperAPI")
    args = ap.parse_args()

    if args.source == "api" and not available():
        print("Aucune clé ScraperAPI disponible", file=sys.stderr)
        return 0
    if args.source != "api" and not amazon_scraper.available() and not available():
        print("Ni Chromium ni clé ScraperAPI disponible", file=sys.stderr)
        return 0

    targets = collect()
    print(f"{len(targets)} ASIN à vérifier…\n")

    report, dead = {}, set()
    try:
        for i, (asin, sources) in enumerate(sorted(targets.items()), 1):
            status, detail = check(asin, args.source)
            report[asin] = {"status": status, "detail": detail, "sources": sources}
            if status == "dead":
                dead.add(asin)
                print(f"[{i}/{len(targets)}] ✗ {asin} ({', '.join(sources)}) — {detail}")
            elif status == "unknown":
                print(f"[{i}/{len(targets)}] ? {asin} ({', '.join(sources)}) — {detail}")
    except ScraperExhausted:
        print("crédits ScraperAPI épuisés en cours d'audit, rapport partiel", file=sys.stderr)

    live = [a for a, r in report.items() if r["status"] == "live"]
    unknown = [a for a, r in report.items() if r["status"] == "unknown"]
    print(f"\n{len(report)} vérifiés : {len(live)} en vente, {len(dead)} morts, {len(unknown)} indéterminés")
    for asin in sorted(dead):
        print(f"  mort : {asin} — {', '.join(report[asin]['sources'])}")

    if args.json:
        Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(f"rapport écrit dans {args.json}")

    if args.prune and dead:
        for line in prune(dead):
            print(f"nettoyé : {line}")
    elif dead:
        print("\nRelancer avec --prune pour retirer ces références des données.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
