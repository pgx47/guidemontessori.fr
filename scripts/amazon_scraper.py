#!/usr/bin/env python3
"""Scraper Amazon.fr maison, sans API tierce ni crédit.

Le HTML d'Amazon est rendu par le Chromium du système (`--dump-dom`), puis
les champs utiles sont extraits par expressions régulières : fiche produit
(titre, image haute définition, prix, disponibilité, arguments), résultats de
recherche, et `og:image` d'une page quelconque.

Pourquoi un navigateur : en HTTP simple, amazon.fr renvoie 404/503 aux scripts
(empreinte TLS et absence de JS). Chromium passe là où curl échoue.

Contraintes connues :
- à lancer depuis une IP résidentielle ; les runners GitHub Actions (Azure)
  sont filtrés par Amazon, d'où le repli sur ScraperAPI dans les workflows ;
- les sélecteurs suivent le DOM public d'amazon.fr : ils peuvent casser lors
  d'une refonte de la page (le repli API garde le pipeline en marche).

Usage :
    from amazon_scraper import available, product, search, og_image
"""
import html
import json
import re
import shutil
import subprocess
import time
import urllib.parse

CHROME_BINARIES = ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable")
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/131.0.0.0 Safari/537.36")
MIN_INTERVAL = 1.5  # secondes entre deux pages : on reste un visiteur discret
CAPTCHA_MARKERS = (
    "Saisissez les caractères",
    "Enter the characters you see",
    "api-services-support@amazon",
    "Robot Check",
    "Pour continuer vos achats",
)


class Blocked(RuntimeError):
    """Amazon a servi un captcha ou une page d'erreur."""


def chrome() -> str | None:
    for name in CHROME_BINARIES:
        path = shutil.which(name)
        if path:
            return path
    return None


def available() -> bool:
    return chrome() is not None


_last_call = 0.0


def _throttle() -> None:
    global _last_call
    wait = MIN_INTERVAL - (time.time() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.time()


def page(url: str, timeout: int = 60) -> str:
    """DOM rendu de la page. Lève Blocked si Amazon renvoie un captcha."""
    binary = chrome()
    if not binary:
        raise Blocked("chromium introuvable")
    _throttle()
    cmd = [
        binary, "--headless=new", "--disable-gpu", "--no-sandbox",
        "--disable-dev-shm-usage", "--hide-scrollbars", "--mute-audio",
        "--window-size=1280,900", "--virtual-time-budget=8000",
        f"--user-agent={UA}", "--dump-dom", url,
    ]
    try:
        run = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise Blocked(f"délai dépassé ({timeout}s)") from exc

    dom = run.stdout or ""
    if len(dom) < 20000:
        # Amazon sert une vraie page 404 (courte) pour un produit retiré :
        # ce n'est pas un blocage, on la laisse remonter telle quelle.
        if "Page introuvable" in dom or "page you requested cannot be found" in dom:
            return dom
        raise Blocked(f"page trop courte ({len(dom)} octets)")
    if any(marker in dom for marker in CAPTCHA_MARKERS):
        raise Blocked("captcha Amazon")
    return dom


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def _first(dom: str, pattern: str, flags: int = re.S) -> str:
    match = re.search(pattern, dom, flags)
    return _text(match.group(1)) if match else ""


def _image(dom: str) -> str:
    """Image principale en meilleure définition disponible."""
    dyn = re.search(r'id="landingImage"[^>]*data-a-dynamic-image="([^"]+)"', dom, re.S)
    if dyn:
        try:
            sizes = json.loads(html.unescape(dyn.group(1)))
            if sizes:
                return max(sizes, key=lambda url: sizes[url][0] if sizes[url] else 0)
        except Exception:
            pass
    direct = re.search(r'id="landingImage"[^>]*src="([^"]+)"', dom, re.S)
    if direct:
        return html.unescape(direct.group(1))
    hi_res = re.findall(r"https://m\.media-amazon\.com/images/I/[A-Za-z0-9%+_.-]+\.jpg", dom)
    return hi_res[0] if hi_res else ""


def _price(dom: str) -> str:
    for pattern in (
        r'id="corePrice_feature_div".*?class="a-offscreen">([^<]+)<',
        r'class="a-price-whole">([\d\s.,]+)</span>',
        r'"displayPrice"\s*:\s*"([^"]+)"',
    ):
        value = _first(dom, pattern)
        if value:
            return value
    return ""


def _bullets(dom: str) -> list[str]:
    block = re.search(r'id="feature-bullets"(.*?)</div>\s*</div>', dom, re.S)
    if not block:
        return []
    items = re.findall(r'<span class="a-list-item">(.*?)</span>', block.group(1), re.S)
    return [clean for clean in (_text(i) for i in items) if clean][:8]


def product(asin: str) -> dict:
    """{alive, name, price, image, availability, bullets} ; lève Blocked."""
    dom = page(f"https://www.amazon.fr/dp/{asin}")
    name = _first(dom, r'id="productTitle"[^>]*>(.*?)</span>')
    dropped = "Page introuvable" in dom[:20000] or "page you requested" in dom[:20000]
    if not name or dropped:
        return {"asin": asin, "alive": False, "name": "", "price": "", "image": "", "availability": "", "bullets": []}
    return {
        "asin": asin,
        "alive": True,
        "name": name,
        "price": _price(dom),
        "image": _image(dom),
        "availability": _first(dom, r'id="availability".*?<span[^>]*>(.*?)</span>'),
        "bullets": _bullets(dom),
    }


def search(query: str, limit: int = 8) -> list[dict]:
    """Résultats de recherche : [{asin, name, price, image}] ; lève Blocked."""
    url = "https://www.amazon.fr/s?" + urllib.parse.urlencode({"k": query})
    dom = page(url)
    results, seen = [], set()
    for chunk in re.split(r'data-asin="', dom)[1:]:
        asin = chunk[:10]
        if not re.fullmatch(r"[A-Z0-9]{10}", asin) or asin in seen:
            continue
        image = re.search(r'class="s-image"[^>]*src="([^"]+)"', chunk[:6000])
        if not image:
            continue
        seen.add(asin)
        name = _first(chunk, r'<h2[^>]*>.*?<span[^>]*>(.*?)</span>', re.S)
        price = _first(chunk[:8000], r'class="a-offscreen">([^<]+)<')
        results.append({"asin": asin, "name": name, "price": price, "image": html.unescape(image.group(1))})
        if len(results) >= limit:
            break
    return results


def og_image(url: str) -> str:
    """URL de l'og:image d'une page (articles de presse, etc.)."""
    dom = page(url, timeout=45)
    match = re.search(r'property=["\']og:image["\'][^>]*content=["\']([^"\']+)', dom)
    if not match:
        match = re.search(r'content=["\']([^"\']+)["\'][^>]*property=["\']og:image', dom)
    return html.unescape(match.group(1)) if match else ""
