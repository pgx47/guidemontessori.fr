#!/usr/bin/env python3
"""Ping IndexNow (Bing/Yandex) avec les URLs du sitemap."""
import os, sys, requests

HOST = "guidemontessori.fr"
KEY = os.environ["INDEXNOW_KEY"]
try:
    xml = requests.get(f"https://{HOST}/sitemap-0.xml", timeout=30).text
    urls = [u.split("<loc>")[1].split("</loc>")[0] for u in xml.split("<url>")[1:]]
except Exception:
    urls = [f"https://{HOST}/"]
r = requests.post("https://api.indexnow.org/indexnow", json={
    "host": HOST, "key": KEY, "keyLocation": f"https://{HOST}/{KEY}.txt", "urlList": urls[:100]}, timeout=30)
print("indexnow", r.status_code, len(urls), "urls")
sys.exit(0 if r.ok else 0)  # jamais bloquant
