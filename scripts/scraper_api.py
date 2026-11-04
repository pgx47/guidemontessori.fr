#!/usr/bin/env python3
"""Rotation des clés ScraperAPI.

Un compte ScraperAPI a un quota mensuel de crédits. Dès qu'une clé répond
401/403/429 (quota épuisé, clé révoquée, trop de requêtes), on passe
automatiquement à la suivante.

Ordre de lecture des clés (les doublons sont ignorés) :
  1. SCRAPER_API_KEYS  : liste séparée par des virgules
  2. SCRAPER_API_KEY   : clé historique
  3. SCRAPER_API_KEY_2, _3, … _9

Usage :
    from scraper_api import get, ScraperExhausted

    r = get("structured/amazon/search", {"query": q, "country": "fr"})
"""
import os

import requests

API = "https://api.scraperapi.com"
ROTATE_STATUS = (401, 403, 429)

_exhausted: set[str] = set()


class ScraperExhausted(RuntimeError):
    """Plus aucune clé ScraperAPI disponible."""


def keys() -> list[str]:
    found: list[str] = []

    def add(value: str | None) -> None:
        for chunk in (value or "").split(","):
            key = chunk.strip()
            if key and key not in found:
                found.append(key)

    add(os.environ.get("SCRAPER_API_KEYS"))
    add(os.environ.get("SCRAPER_API_KEY"))
    for i in range(2, 10):
        add(os.environ.get(f"SCRAPER_API_KEY_{i}"))
    return found


def available() -> bool:
    return any(k not in _exhausted for k in keys())


def get(path: str = "", params: dict | None = None, timeout: int = 90):
    """GET ScraperAPI en essayant les clés à tour de rôle.

    `path` est relatif (`structured/amazon/search`), vide pour le proxy brut.
    Lève ScraperExhausted quand toutes les clés sont épuisées, et la dernière
    erreur réseau si aucune requête n'a abouti.
    """
    candidates = [k for k in keys() if k not in _exhausted]
    if not candidates:
        raise ScraperExhausted("aucune clé ScraperAPI disponible")

    url = f"{API}/{path}" if path else API
    last_error: Exception | None = None

    for key in candidates:
        payload = dict(params or {})
        payload["api_key"] = key
        try:
            response = requests.get(url, params=payload, timeout=timeout)
        except requests.RequestException as exc:  # réseau : on tente la clé suivante
            last_error = exc
            continue

        if response.status_code in ROTATE_STATUS:
            _exhausted.add(key)
            last_error = None
            continue

        return response

    if last_error is not None:
        raise last_error
    raise ScraperExhausted("crédits épuisés sur toutes les clés ScraperAPI")
