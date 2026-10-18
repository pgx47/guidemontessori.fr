#!/usr/bin/env python3
"""Annuaire écoles : OSM/Overpass -> enrichissement DeepSeek -> src/data/ecoles.json."""
import json
import os
import sys
import unicodedata
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "data" / "ecoles.json"

GOUV = ("https://data.education.gouv.fr/api/explore/v2.1/catalog/datasets/"
        "fr-en-annuaire-education/records")


def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return "".join(c if c.isalnum() else "-" for c in s.lower()).strip("-")


def fetch_osm() -> list[dict]:
    """Annuaire officiel data.education.gouv.fr : toutes les écoles 'Montessori'."""
    r = requests.get(GOUV, params={
        "where": 'search(nom_etablissement,"montessori")', "limit": 100,
        "select": "nom_etablissement,nom_commune,code_postal,type_etablissement,"
                  "statut_public_prive,adresse_1,code_commune"},
        headers={"User-Agent": "guidemontessori/1.0"}, timeout=60)
    r.raise_for_status()
    out = []
    for rec in r.json().get("results", []):
        out.append({"osm_id": f"{rec.get('code_commune')}-{slugify(rec['nom_etablissement'])}",
                    "nom": rec["nom_etablissement"],
                    "ville": rec.get("nom_commune") or "",
                    "code_postal": str(rec.get("code_postal") or ""),
                    "adresse": rec.get("adresse_1") or "",
                    "site": "",
                    "amenity": rec.get("type_etablissement") or "École"})
    return out


def infer_ville(e: dict) -> None:
    """Ville absente -> dernière part du nom ou code postal."""
    if not e["ville"]:
        parts = [p.strip() for p in e["nom"].replace("-", " ").split(",")]
        e["ville"] = parts[-1] if len(parts) > 1 else ""
    if e["ville"]:
        e["slug_ville"] = slugify(e["ville"])


def enrich(new: list[dict]) -> dict:
    key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENROUTER_API_KEY")
    if not key:
        return {}
    base = "https://api.deepseek.com" if os.environ.get("DEEPSEEK_API_KEY") else "https://openrouter.ai/api/v1"
    model = "deepseek-flash" if os.environ.get("DEEPSEEK_API_KEY") else "deepseek/deepseek-v4.1-flash"
    tool = {"type": "function", "function": {
        "name": "ecoles",
        "parameters": {
            "type": "object", "required": ["items"],
            "properties": {"items": {"type": "array", "items": {
                "type": "object", "required": ["id", "ville", "description_ia", "avantages"],
                "properties": {
                    "id": {"type": "string"},
                    "ville": {"type": "string", "description": "ville réelle FR corrigée"},
                    "description_ia": {"type": "string", "description": "présentation 50 mots, neutre et générique"},
                    "avantages": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3},
                }}}},
        }}}
    prompt = """Tu rédiges pour un annuaire d'écoles Montessori en France.
Pour chaque école (id=osm_id) : ville réelle en titre propre, présentation neutre 50 mots
(ne JAMAIS affirmer de fait non vérifiable sur l'établissement : reste générique sur la
pédagogie Montessori et le cadre type), 3 avantages génériques bien formulés.
Écoles :
"""
    merged = {}
    for i in range(0, len(new), 25):
        batch = new[i:i + 25]
        items = [{"id": e["osm_id"], "nom": e["nom"], "ville_osm": e["ville"],
                  "cp": e["code_postal"], "type": e["amenity"]} for e in batch]
        p = prompt + json.dumps(items, ensure_ascii=False)
        try:
            r = requests.post(f"{base}/chat/completions", headers={"Authorization": f"Bearer {key}"},
                              json={"model": model, "temperature": 0.3, "max_tokens": 8000,
                                    "thinking": {"type": "disabled"} if base.endswith("deepseek.com") else {},
                                    "tools": [tool], "tool_choice": "auto",
                                    "messages": [{"role": "user", "content": p}]},
                              timeout=240)
            calls = r.json()["choices"][0]["message"].get("tool_calls") or []
            if calls:
                merged.update({x["id"]: x for x in
                               json.loads(calls[0]["function"]["arguments"]).get("items", [])})
        except Exception as e:
            print(f"⚠ LLM batch {i} : {e}", file=sys.stderr)
    return merged


def main() -> int:
    existing = {e["osm_id"]: e for e in json.loads(OUT.read_text())} if OUT.exists() else {}
    try:
        raw = fetch_osm()
    except Exception as e:
        print(f"source indisponible, ecoles.json inchangé : {e}", file=sys.stderr)
        return 0
    print(f"{len(raw)} établissements OSM, {len(existing)} en base")
    new = [e for e in raw if e["osm_id"] not in existing or not existing[e["osm_id"]].get("description_ia")]
    for e in new:
        infer_ville(e)
    new = [e for e in new if e["ville"]]
    enriched = enrich(new) if new else {}
    for e in new:
        c = enriched.get(e["osm_id"])
        if c and c["ville"]:
            e["ville"] = c["ville"]
            e["slug_ville"] = slugify(c["ville"])
            e["description_ia"] = c["description_ia"]
            e["avantages"] = c["avantages"]
        else:
            e["description_ia"] = ""
            e["avantages"] = []
        existing[e["osm_id"]] = e
    out = sorted(existing.values(), key=lambda e: (e.get("slug_ville") or "zzz", e["nom"]))
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    villes = {e["slug_ville"] for e in out if e.get("slug_ville")}
    print(f"✓ {len(out)} écoles, {len(villes)} villes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
