#!/usr/bin/env python3
"""Soumettre le sitemap à Google Search Console après un déploiement.

L'API Indexing est réservée aux offres d'emploi et vidéos en direct : elle
ne convient pas aux articles de ce site. Le compte de service existant doit
avoir accès à la propriété Search Console.
"""
import json
import os
import sys
from urllib.parse import quote

import requests

SITE = 'sc-domain:guidemontessori.fr'
SITEMAP = 'https://www.guidemontessori.fr/sitemap-index.xml'


def submit_sitemap(token: str) -> int:
    endpoint = f'https://www.googleapis.com/webmasters/v3/sites/{quote(SITE, safe="")}/sitemaps/{quote(SITEMAP, safe="")}'
    response = requests.put(endpoint, headers={'Authorization': f'Bearer {token}'}, timeout=30)
    if response.status_code not in (200, 204):
        print(f'::warning::Search Console : soumission du sitemap refusée (HTTP {response.status_code}). Vérifier l’API et les droits du compte de service.')
        return 1
    print('Search Console : sitemap soumis avec succès.')
    return 0


def main() -> int:
    credentials_json = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
    if not credentials_json:
        print('::warning::Search Console : compte de service absent, soumission ignorée.')
        return 0
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request
        credentials = service_account.Credentials.from_service_account_info(
            json.loads(credentials_json), scopes=['https://www.googleapis.com/auth/webmasters'])
        credentials.refresh(Request())
        return submit_sitemap(credentials.token)
    except Exception as error:
        # Never print credentials, access tokens or API response bodies in public CI logs.
        print(f'::warning::Search Console : échec de la soumission ({type(error).__name__}).')
        return 1


if __name__ == '__main__':
    sys.exit(main())
