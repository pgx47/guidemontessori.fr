#!/usr/bin/env python3
"""Ping IndexNow (Bing/Yandex) avec les URLs réellement modifiées.

IndexNow attend « les URLs nouvelles, mises à jour ou supprimées », pas le
sitemap complet à chaque déploiement : renvoyer 127 URLs identiques à chaque
push dilue le signal et fait gonfler le compteur « URLs submitted » dans la
Search Console (4,1 K pour un site de 127 pages).

Stratégie :
  1. on déduit du dernier commit les fichiers modifiés (`git diff HEAD~1`) ;
  2. on les traduit en routes (guides, actualités, pages statiques, data) ;
  3. tout changement de gabarit (layout, composant, config, style, page
     dynamique) => on resoumet le sitemap complet, par prudence ;
  4. rien à soumettre => on ne fait aucun appel.
Repli : si l'historique git est indisponible ou la traduction vide, on
resoumet le sitemap complet (comportement historique, jamais bloquant).
"""
import os
import re
import subprocess
import sys

import requests

HOST = "www.guidemontessori.fr"
KEY = os.environ.get("INDEXNOW_KEY") or "57338eccf0bd7423e81d2ab725406602"
KEY_LOCATION = f"https://{HOST}/{KEY}.txt"
DRY_RUN = os.environ.get("INDEXNOW_DRY_RUN") == "1"

TEMPLATE_PREFIXES = (
    "src/layouts/",
    "src/components/",
    "src/lib/",
    "src/styles/",
    "astro.config",
    "src/site.config",
    "src/content.config",
    "public/_headers",
    "public/_redirects",
    "public/robots.txt",
)

# Fichiers qui ne changent aucune page : aucun envoi nécessaire.
IGNORED_PREFIXES = (
    "scripts/",
    ".github/",
    "docs/",
    "_legacy/",
    ".venv/",
    "AGENTS.md",
    "ARCHITECTURE.md",
    "README.md",
)

# Pages statiques : fichier de page -> route(s) du sitemap.
STATIC_PAGES = {
    "index": [""],
    "a-propos": ["a-propos"],
    "contact": ["contact"],
    "cadeaux": ["cadeaux"],
    "cgv": ["cgv"],
    "mentions-legales": ["mentions-legales"],
    "politique-confidentialite": ["politique-confidentialite"],
    "politique-cookies": ["politique-cookies"],
    "lectures-parents": ["lectures-parents"],
    "livres-enfants": ["livres-enfants"],
    "bons-plans": ["bons-plans"],
}

# Données : fichier de données -> routes dépendantes.
DATA_PAGES = {
    "src/data/cadeaux.json": ["cadeaux"],
    "src/data/books.json": ["lectures-parents", "livres-enfants"],
    "src/data/deals.json": ["bons-plans"],
    "src/data/ecoles.json": ["ecoles"],
    "src/data/villes_coords.json": ["ecoles"],
}


def sitemap_urls() -> list[str]:
    try:
        xml = requests.get(f"https://{HOST}/sitemap-0.xml", timeout=30).text
        return [u.split("<loc>")[1].split("</loc>")[0] for u in xml.split("<url>")[1:]]
    except Exception as exc:  # pragma: no cover - réseau
        print(f"indexnow: sitemap injoignable ({exc})", file=sys.stderr)
        return []


def changed_files() -> list[str]:
    base = os.environ.get("INDEXNOW_BASE") or "HEAD~1"
    try:
        out = subprocess.run(
            ["git", "diff", "--name-only", base, "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return [line.strip() for line in out.stdout.splitlines() if line.strip()]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []


def routes_for(files: list[str]) -> tuple[set[str], bool, list[str]]:
    """Retourne (routes simples, besoin du sitemap complet, fichiers publics)."""
    routes: set[str] = set()
    full = False
    touched: list[str] = []
    for path in files:
        if path.startswith(IGNORED_PREFIXES):
            continue
        touched.append(path)
        if path.startswith(TEMPLATE_PREFIXES):
            full = True
            continue
        match = re.match(r"src/content/(guides|news)/(.+)\.mdx?$", path)
        if match:
            section = "articles" if match.group(1) == "guides" else "actualites"
            routes.add(f"{section}/{match.group(2)}")
            routes.add(section)
            continue
        match = re.match(r"src/pages/(.+)\.astro$", path)
        if match:
            page = match.group(1)
            if "[" in page:
                full = True  # page dynamique : tout le gabarit peut changer
                continue
            for route in STATIC_PAGES.get(page, []):
                routes.add(route)
            continue
        if path in DATA_PAGES:
            for route in DATA_PAGES[path]:
                routes.add(route)
                if route == "ecoles":
                    full = True  # une ville ajoutée/retirée ne se déduit pas du diff
    return routes, full, touched


def main() -> int:
    urls = sitemap_urls()
    if not urls:
        print("indexnow: aucun URL récupérée, rien à faire", file=sys.stderr)
        return 0

    files = changed_files()
    routes, full, touched = routes_for(files)
    if not files:
        # Historique indisponible : on resoumet tout, comme avant.
        full = True
    elif not touched:
        print("indexnow: aucun fichier public modifié, aucun appel", file=sys.stderr)
        return 0
    elif not routes:
        full = True

    if full:
        targets = urls
        mode = "sitemap complet"
    else:
        def abs_url(route: str) -> str:
            return f"https://{HOST}/{route}/" if route else f"https://{HOST}/"

        known = {re.sub(r"/+$", "", u): u for u in urls}
        targets = sorted(
            {known[key] for key in (re.sub(r"/+$", "", abs_url(r)) for r in routes) if key in known}
        )
        mode = f"{len(targets)} URL(s) modifiée(s)"

    if not targets:
        print("indexnow: aucune URL modifiée, aucun appel", file=sys.stderr)
        return 0

    print(f"indexnow: {mode} sur {len(files)} fichier(s) modifié(s)")
    if DRY_RUN:
        for url in targets[:20]:
            print("  ", url)
        print(f"  ({len(targets)} au total)")
        return 0

    try:
        kf = requests.get(KEY_LOCATION, timeout=30)
        if kf.status_code != 200 or kf.text.strip() != KEY:
            print(f"indexnow: avertissement keyfile {KEY_LOCATION} -> HTTP {kf.status_code}", file=sys.stderr)
    except Exception as exc:  # pragma: no cover - réseau
        print(f"indexnow: avertissement keyfile injoignable -> {exc}", file=sys.stderr)

    try:
        response = requests.post(
            "https://api.indexnow.org/indexnow",
            json={"host": HOST, "key": KEY, "keyLocation": KEY_LOCATION, "urlList": targets[:10000]},
            timeout=30,
        )
        print("indexnow", response.status_code, len(targets), "urls", "" if response.ok else response.text[:300])
    except Exception as exc:  # pragma: no cover - réseau
        print(f"indexnow: envoi impossible ({exc})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
