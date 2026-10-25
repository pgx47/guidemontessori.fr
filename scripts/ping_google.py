#!/usr/bin/env python3
"""Google Indexing API : POST les nouvelles URLs (compte de service JSON requis).
Secret : GOOGLE_SERVICE_ACCOUNT_JSON (contenu du fichier de clé du service account)."""
import json, os, sys, requests

HOST = "www.guidemontessori.fr"

def urls() -> list[str]:
    xml = requests.get(f"https://{HOST}/sitemap-0.xml", timeout=30).text
    return [u.split("<loc>")[1].split("</loc>")[0] for u in xml.split("<url>")[1:]]

def token() -> str | None:
    creds = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not creds:
        print("GOOGLE_SERVICE_ACCOUNT_JSON absent — skip", file=sys.stderr)
        return None
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request
        sa = service_account.Credentials.from_service_account_info(
            json.loads(creds), scopes=["https://www.googleapis.com/auth/indexing"])
        sa.refresh(Request())
        return sa.token
    except Exception as e:
        print(f"auth : {e}", file=sys.stderr)
        return None

tok = token()
if tok:
    for u in urls()[-10:]:  # 10 dernières (quota journalier limité)
        r = requests.post("https://indexing.googleapis.com/v3/urlNotifications:publish",
                          headers={"Authorization": f"Bearer {tok}"},
                          json={"url": u, "type": "URL_UPDATED"}, timeout=30)
        print(r.status_code, u)
sys.exit(0)
