#!/usr/bin/env python3
"""Ping IndexNow (Bing/Yandex) avec les URLs du sitemap."""
import os, sys, requests

HOST = "www.guidemontessori.fr"
KEY = os.environ.get("INDEXNOW_KEY") or "57338eccf0bd7423e81d2ab725406602"
KEY_LOCATION = f"https://{HOST}/{KEY}.txt"

try:
    kf = requests.get(KEY_LOCATION, timeout=30)
    if kf.status_code != 200 or kf.text.strip() != KEY:
        print(f"indexnow: avertissement keyfile {KEY_LOCATION} -> HTTP {kf.status_code}", file=sys.stderr)
except Exception as e:
    print(f"indexnow: avertissement keyfile injoignable {KEY_LOCATION} -> {e}", file=sys.stderr)

try:
    xml = requests.get(f"https://{HOST}/sitemap-0.xml", timeout=30).text
    urls = [u.split("<loc>")[1].split("</loc>")[0] for u in xml.split("<url>")[1:]]
except Exception:
    urls = [f"https://{HOST}/"]

r = requests.post("https://api.indexnow.org/indexnow", json={
    "host": HOST, "key": KEY, "keyLocation": KEY_LOCATION, "urlList": urls[:10000]}, timeout=30)
print("indexnow", r.status_code, len(urls), "urls", "" if r.ok else r.text[:300])
sys.exit(0)  # jamais bloquant
