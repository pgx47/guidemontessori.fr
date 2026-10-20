#!/usr/bin/env python3
"""Generate an MDX article (guide or news) with Claude and write it to src/content/.

Usage:
  python scripts/generate_article.py --topic "meilleur lit cabane montessori" --type guide
  python scripts/generate_article.py --auto            # next pending topic in topics.json
  python scripts/generate_article.py --auto --dry-run  # print MDX, write nothing
"""
import argparse
import json
import os
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
TOPICS = ROOT / "scripts" / "topics.json"
CONTENT = ROOT / "src" / "content"
DIRS = {"guide": CONTENT / "guides", "news": CONTENT / "news"}
IMAGES_DIR = ROOT / "public" / "images" / "generated"
R2_PUBLIC_URL = os.environ.get("R2_PUBLIC_URL", "https://images.guidemontessori.fr")
API_URL = "https://api.anthropic.com/v1/messages"
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")

SYSTEM = """Tu es rédacteur web senior pour GuideMontessori.fr, site français destiné aux jeunes parents qui appliquent la pédagogie Montessori à la maison.

Style :
- Français impeccable avec accents, ton bienveillant, clair et rassurant, phrases variées. Pas de jargon clinique : tu écris pour des parents, pas pour un mémo.
- Interdits : "dans un monde où", "plongeons", "il est crucial", "en conclusion", "n'hésitez pas", "il convient de noter", "véritable", "incontournable", "que vous soyez", listes à rallonge, emojis dans le corps.
- Concret : âges, dimensions, matériaux, normes (EN 71, FSC), gestes de présentation, erreurs fréquentes.
- Jamais de prix précis, jamais de promesse médicale, jamais d'invention de marque ou de référence produit.
- INTERDIT : mentionner un tag partenaire (suffixe "-21"), "affilié", "affiliation" ou "commission" dans le texte. Pas de lien HTML texte brut vers Amazon — seuls les marqueurs [[PRODUIT:n]] insèrent des produits.
- Insert un encadré "> 💡 **L'œil de l'éducateur** :" (astuce maison) et un encadré "> ⚠️ **Erreur fréquente** :" dans chaque guide, en blockquote Markdown.
- Cite Maria Montessori seulement avec des citations réelles et connues.

Format du corps (champ body) : Markdown pur, sans titre H1, sections en ## et ###, paragraphes courts, au moins un tableau Markdown comparatif pour un guide.
Pour placer un produit, écris seul sur sa ligne le marqueur [[PRODUIT:n]] (n = index 0-based dans la liste fournie). Chaque produit fourni doit apparaître une fois.
N'utilise ni HTML, ni accolades { }, ni chevrons < >."""

TOOL = {
    "name": "publish_article",
    "description": "Publie l'article structuré.",
    "input_schema": {
        "type": "object",
        "required": ["title", "description", "slug", "keywords", "emoji", "body", "faq", "products"],
        "properties": {
            "title": {"type": "string", "description": "Titre SEO 40-70 caractères, mot-clé principal au début."},
            "description": {"type": "string", "description": "Meta description 120-160 caractères, incitative."},
            "slug": {"type": "string", "description": "kebab-case ascii, 3-7 mots."},
            "keywords": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 8},
            "emoji": {"type": "string", "description": "Un seul emoji représentatif."},
            "body": {"type": "string", "description": "Corps Markdown (1200-1800 mots pour un guide, 400-700 pour une news)."},
            "faq": {
                "type": "array",
                "minItems": 3,
                "maxItems": 5,
                "items": {
                    "type": "object",
                    "required": ["question", "answer"],
                    "properties": {"question": {"type": "string"}, "answer": {"type": "string"}},
                },
            },
            "imagePrompt": {
                "type": "string",
                "description": "Prompt EN anglais pour une illustration photo éditoriale de l'article : scène Montessori, bois naturel, tons chauds neutres, lumière douce, photoréaliste, sans texte ni personnage identifiable.",
            },
            "products": {
                "type": "array",
                "description": "Un élément par produit fourni, dans le même ordre.",
                "items": {
                    "type": "object",
                    "required": ["pointsForts", "pointsFaibles"],
                    "properties": {
                        "pointsForts": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 4},
                        "pointsFaibles": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 3},
                    },
                },
            },
        },
    },
}


def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def existing_articles() -> list[tuple[str, str]]:
    out = []
    for d in DIRS.values():
        for f in d.glob("*.md*"):
            m = re.search(r'^title:\s*"?(.*?)"?\s*$', f.read_text(), re.M)
            out.append((f.stem, m.group(1) if m else f.stem))
    return out


def llm_config() -> tuple[str, str, str, str]:
    """(base_url, key, model, api): api = 'openai' | 'anthropic'."""
    for env in ("DEEPSEEK_API_KEY", "OPENROUTER_API_KEY", "LLM_API_KEY"):
        if key := os.environ.get(env):
            default_base = "https://openrouter.ai/api/v1" if "OPENROUTER" in env else "https://api.deepseek.com"
            default_model = "deepseek/deepseek-v4.1-flash" if "OPENROUTER" in env else "deepseek-flash"
            return (os.environ.get("LLM_BASE_URL", default_base), key, os.environ.get("LLM_MODEL", default_model), "openai")
    if key := os.environ.get("ANTHROPIC_API_KEY"):
        return (API_URL, key, MODEL, "anthropic")
    sys.exit("Aucune clé LLM : DEEPSEEK_API_KEY, OPENROUTER_API_KEY ou ANTHROPIC_API_KEY requis")


def tool_for(api: str) -> list:
    if api == "anthropic":
        return [TOOL]
    return [{"type": "function", "function": {"name": TOOL["name"], "description": TOOL["description"], "parameters": TOOL["input_schema"]}}]


def call_llm(topic: dict, kind: str) -> dict:
    url, key, model, api = llm_config()
    products = topic.get("products", [])
    links = "\n".join(f"- /articles/{s}/ : {t}" for s, t in existing_articles())
    prompt = f"""Type : {"guide evergreen / comparatif" if kind == "guide" else "brève d'actualité"}
Mot-clé principal : {topic["keyword"]}
Angle : {topic.get("angle", "répondre précisément à l'intention de recherche du parent")}

Produits à intégrer (n'invente aucun autre produit) :
{json.dumps(products, ensure_ascii=False, indent=2) if products else "aucun"}

Articles existants pour 2 à 4 liens internes Markdown pertinents :
{links}

Appelle l'outil publish_article."""
    if api == "anthropic":
        r = requests.post(
            url,
            headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={
                "model": model,
                "max_tokens": 8000,
                "system": SYSTEM,
                "tools": tool_for(api),
                "tool_choice": {"type": "tool", "name": TOOL["name"]},
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=300,
        )
        if not r.ok:
            sys.exit(f"Erreur API {r.status_code}: {r.text[:500]}")
        block = next(b for b in r.json()["content"] if b["type"] == "tool_use")
        return block["input"]

    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]
    for attempt in range(3):
        r = requests.post(
            f"{url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "temperature": 0.4,
                "max_tokens": 16000,
                "tools": tool_for(api),
                "tool_choice": "auto",
                "messages": messages,
            },
            timeout=300,
        )
        if not r.ok:
            sys.exit(f"Erreur API {r.status_code}: {r.text[:500]}")
        msg = r.json()["choices"][0]["message"]
        if calls := msg.get("tool_calls"):
            for c in calls:
                if c["function"]["name"] == TOOL["name"]:
                    try:
                        return json.loads(c["function"]["arguments"])
                    except json.JSONDecodeError:
                        print("arguments tronqués, retry", file=sys.stderr)
                        break
        print(f"pas de tool_call (tentative {attempt + 1})", file=sys.stderr)
        messages += [msg, {"role": "user", "content": "Réponds uniquement via l'outil publish_article, sans texte libre."}]
    sys.exit("3 tentatives sans tool_call")


def esc(s: str) -> str:
    return s.replace("{", "&#123;").replace("}", "&#125;").replace("<", "&lt;")


def jsx_list(items: list[str]) -> str:
    return "{" + json.dumps(items, ensure_ascii=False) + "}"


IMG_STYLE = (
    "A candid, real-life photograph, shot indoors on a digital camera, 35mm, natural soft lighting, "
    "realistic textures, real warm domestic environment. NO illustrations, NO 3D renders, NO cartoon, "
    "NO cliparts, NO vectors, NO isolated object on flat solid background, NO emojis, NO graphic design, NO text."
)


def inspect_image(data: bytes) -> bool:
    """Vision QC via deepseek-flash : rejette clipart/emoji/3D. Fallback : accepte."""
    import base64
    url, key, model, _api = llm_config()
    if _api != "openai":
        return True
    prompt = (
        "Image destinée à un blog Montessori. Réponds par OUI ou NON uniquement. "
        "Cette image ressemble-t-elle à un emoji, un clipart, une illustration 3D, un dessin, "
        "un objet isolé sur fond uni, ou une image avec du texte lisible ? Réponds NON si c'est une vraie photo naturelle."
    )
    try:
        r = requests.post(
            f"{url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": model, "temperature": 0, "max_tokens": 5, "messages": [
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": "data:image/webp;base64," + base64.b64encode(data).decode()}},
                ]}]},
            timeout=60,
        )
        verdict = r.json()["choices"][0]["message"]["content"].strip().upper()
        ok = "NON" in verdict or "NO" == verdict[:2]
        if not ok:
            print("🚨 image rejetée (clipart/emoji détecté)", file=sys.stderr)
        return ok
    except Exception as e:
        print(f"vision QC indisponible, image acceptée : {e}", file=sys.stderr)
        return True


def _to_webp(raw: bytes) -> bytes:
    from io import BytesIO
    from PIL import Image
    im = Image.open(BytesIO(raw)).convert("RGB")
    w, h = im.size
    im = im.crop((0, 0, w, int(h * 0.93)))  # retire le watermark pollinations en bas
    buf = BytesIO()
    im.save(buf, "WEBP", quality=82, method=6)
    return buf.getvalue()


def fetch_stock(query: str, slug: str) -> bytes | None:
    """Fallback photo libre de droits : Openverse puis Wikimedia Commons, sans clé."""
    try:
        r = requests.get("https://api.openverse.org/v1/images/",
                         params={"q": query, "page_size": 5, "license": "by,by-sa,cc0,pdm", "filter_dead": "false"},
                         headers={"User-Agent": "guidemontessori/1.0"}, timeout=30)
        for p in r.json().get("results", []):
            if (p.get("width") or 0) < 600:
                continue
            img = requests.get(p["url"], timeout=60)
            if img.ok and len(img.content) > 20000:
                return _to_webp(img.content)
    except Exception as e:
        print(f"⚠ openverse : {e}", file=sys.stderr)
    try:
        r = requests.get("https://commons.wikimedia.org/w/api.php",
                         params={"action": "query", "list": "search", "srsearch": query + " filetype:bitmap",
                                 "srnamespace": 6, "srlimit": 5, "format": "json"},
                         headers={"User-Agent": "guidemontessori/1.0"}, timeout=30)
        for hit in r.json()["query"]["search"]:
            info = requests.get("https://commons.wikimedia.org/w/api.php",
                                params={"action": "query", "titles": hit["title"], "prop": "imageinfo",
                                        "iiprop": "url|size", "iiurlwidth": 1024, "format": "json"},
                                headers={"User-Agent": "guidemontessori/1.0"}, timeout=30).json()
            ii = next(iter(info["query"]["pages"].values())).get("imageinfo", [{}])[0]
            if ii.get("thumburl"):
                img = requests.get(ii["thumburl"], timeout=60)
                if img.ok:
                    return _to_webp(img.content)
    except Exception as e:
        print(f"⚠ wikimedia : {e}", file=sys.stderr)
    return None


def generate_image(prompt: str, slug: str) -> bytes | None:
    """Image réaliste : retry x3 avec vision QC, fallback Pexels."""
    full_prompt = f"{IMG_STYLE} Scene: {prompt}"
    try:
        cf_acct, cf_tok = os.environ.get("CLOUDFLARE_ACCOUNT_ID"), os.environ.get("CLOUDFLARE_API_TOKEN")
        if cf_acct and cf_tok:
            r = requests.post(
                f"https://api.cloudflare.com/client/v4/accounts/{cf_acct}/ai/run/@cf/black-forest-labs/flux-1-schnell",
                headers={"Authorization": f"Bearer {cf_tok}"},
                json={"prompt": full_prompt}, timeout=180)
            if r.ok:
                j = r.json()
                raw = requests.get(j["result"]["image"], timeout=60).content if str(j["result"]["image"]).startswith("http") else __import__("base64").b64decode(j["result"]["image"])
                data = _to_webp(raw)
                return data if inspect_image(data) else None
        if key := os.environ.get("OPENAI_API_KEY"):
            r = requests.post(
                "https://api.openai.com/v1/images/generations",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": "dall-e-3", "prompt": full_prompt, "size": "1024x1024", "quality": "standard", "n": 1},
                timeout=180,
            )
            r.raise_for_status()
            img = requests.get(r.json()["data"][0]["url"], timeout=120)
        else:
            img = requests.get(
                f"https://image.pollinations.ai/prompt/{requests.utils.quote(full_prompt)}",
                params={"width": 1024, "height": 768, "nologo": "true", "seed": abs(hash(slug)) % 10**6},
                timeout=180,
            )
        img.raise_for_status()
        from io import BytesIO
        from PIL import Image
        data = _to_webp(img.content)
        return data if inspect_image(data) else None
    except Exception as e:
        print(f"⚠ image non générée : {e}", file=sys.stderr)
        return None


def article_image(prompt: str, slug: str, query: str | None = None) -> str | None:
    for attempt in range(3):
        if data := generate_image(prompt, slug):
            return store_image(data, slug)
    if data := fetch_stock(query or prompt, slug):
        return store_image(data, slug)
    return None


def store_image(data: bytes, slug: str) -> str | None:
    """R2 si configuré, sinon public/images/generated/ (webp léger)."""
    fname = f"{slug}.webp"
    ak, sk, acct = (os.environ.get(k) for k in ("R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "CLOUDFLARE_ACCOUNT_ID"))
    if ak and sk and acct:
        try:
            import boto3
            from io import BytesIO
            boto3.client(
                "s3",
                endpoint_url=f"https://{acct}.r2.cloudflarestorage.com",
                aws_access_key_id=ak,
                aws_secret_access_key=sk,
                region_name="auto",
            ).upload_fileobj(BytesIO(data), os.environ.get("R2_BUCKET", "images-montessori"), fname,
                             ExtraArgs={"ContentType": "image/webp"})
            return f"{R2_PUBLIC_URL}/{fname}"
        except Exception as e:
            print(f"⚠ upload R2 impossible, fallback local : {e}", file=sys.stderr)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    (IMAGES_DIR / fname).write_bytes(data)
    return f"/images/generated/{fname}"


def make_pin(img_path: Path, slug: str, title: str) -> None:
    """Pin Pinterest 1000x1500 : image recadrée 2:3 + bandeau titre."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        im = Image.open(img_path).convert("RGB")
        w, h = im.size
        tw, th = (w, int(w * 1.5)) if h / w >= 1.5 else (int(h / 1.5), h)
        x, y = (w - tw) // 2, (h - th) // 2
        pin = im.crop((x, y, x + tw, y + th)).resize((1000, 1500)).convert("RGBA")
        pin.alpha_composite(Image.new("RGBA", (1000, 170), (44, 62, 45, 210)), (0, 1330))
        d = ImageDraw.Draw(pin)
        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", 46)
        except OSError:
            font = ImageFont.load_default()
        txt = title[:60]
        bbox = d.textbbox((0, 0), txt, font=font)
        d.text(((1000 - (bbox[2] - bbox[0])) / 2, 1380), txt, font=font, fill="white")
        pin.convert("RGB").save(img_path.with_name(f"{slug}-pin.webp"), "WEBP", quality=85)
    except Exception as e:
        print(f"⚠ pin : {e}", file=sys.stderr)


def render_mdx(a: dict, topic: dict, kind: str, today: str, slug: str) -> str:
    products = topic.get("products", [])
    image = topic.get("image")
    if not image and a.get("imagePrompt"):
        image = article_image(a["imagePrompt"], slug, topic.get("keyword"))
        if image and image.startswith("/images/generated/"):
            make_pin(ROOT / "public" / image.lstrip("/"), slug, a["title"])
    fm = {
        "title": a["title"].strip(),
        "description": a["description"].strip(),
        "publishDate": today,
        "category": "guides" if kind == "guide" else "news",
        "author": "Rédaction GuideMontessori",
        "keywords": a["keywords"],
        "emoji": a["emoji"],
        "faq": a["faq"],
    }
    if image:
        fm["image"] = image
    if products:
        fm["asin"] = products[0]["asin"]
    lines = ["---"] + [f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in fm.items()] + ["---", ""]
    if products:
        lines += ["import AffiliateBox from '../../components/AffiliateBox.astro';", ""]

    body = esc(a["body"].strip())
    used = set()

    img_by_asin = {}
    for jf in ("deals.json", "cadeaux.json"):
        fp = ROOT / "src" / "data" / jf
        if fp.exists():
            for x in json.loads(fp.read_text()).get("deals", []) if jf == "deals.json" else json.loads(fp.read_text()):
                if x.get("asin") and x.get("image"):
                    img_by_asin[x["asin"]] = x["image"]

    def box(i: int) -> str:
        if i >= len(products):
            return ""
        used.add(i)
        p, g = products[i], (a["products"][i] if i < len(a["products"]) else {"pointsForts": [], "pointsFaibles": []})
        img = p.get("image") or img_by_asin.get(p["asin"])
        return (
            "<AffiliateBox\n"
            f"  asin={json.dumps(p['asin'])}\n"
            + (f"  image={json.dumps(img)}\n" if img else "")
            + f"  nom={json.dumps(p['nom'], ensure_ascii=False)}\n"
            f"  pointsForts={jsx_list(g['pointsForts'])}\n"
            f"  pointsFaibles={jsx_list(g['pointsFaibles'])}\n"
            "/>"
        )

    body = re.sub(r"^[ \t]*\[\[PRODUIT:(\d+)\]\][ \t]*$", lambda m: "\n" + box(int(m.group(1))) + "\n", body, flags=re.M)
    missing = [i for i in range(len(products)) if i not in used]
    if missing:
        body += "\n\n## Notre sélection\n\n" + "\n\n".join(box(i) for i in missing)
    return "\n".join(lines) + "\n" + re.sub(r"\n{3,}", "\n\n", body) + "\n"


def refill_topics(data: dict) -> None:
    """Si <= 2 sujets pending, génère 15 nouvelles idées via le LLM."""
    pending = [t for t in data["topics"] if t.get("status") == "pending"]
    if len(pending) > 2:
        return
    url, key, model, api = llm_config()
    if api != "openai":
        print("refill: provider sans tool calls, skip", file=sys.stderr)
        return
    done = [t["keyword"] for t in data["topics"]]
    prompt = f"""Propose 15 nouveaux sujets SEO français pour GuideMontessori.fr.
Règles : mots-clés longue traîne à intention d'achat ou de recherche parentale (mobilier, jouets, activités, âge précis, livres), jamais de doublon avec : {json.dumps(done, ensure_ascii=False)}.
Appelle l'outil avec topics = liste d'objets {{keyword, type (guide|news), angle}}. 80% guide."""
    tool = {"type": "function", "function": {"name": "topics", "parameters": {
        "type": "object", "required": ["topics"], "properties": {"topics": {"type": "array", "items": {
            "type": "object", "required": ["keyword", "type", "angle"],
            "properties": {"keyword": {"type": "string"}, "type": {"type": "string"}, "angle": {"type": "string"}}}}}}}}
    try:
        r = requests.post(f"{url.rstrip('/')}/chat/completions",
                          headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                          json={"model": model, "temperature": 0.7, "max_tokens": 4000, "tools": [tool],
                                "tool_choice": "auto", "messages": [{"role": "user", "content": prompt}]},
                          timeout=180)
        calls = r.json()["choices"][0]["message"].get("tool_calls") or []
        new = json.loads(calls[0]["function"]["arguments"]).get("topics", []) if calls else []
        lower = {k.lower() for k in done}
        added = 0
        for t in new:
            kw = t["keyword"].strip()
            if kw.lower() in lower or t.get("type") not in ("guide", "news"):
                continue
            data["topics"].append({"keyword": kw, "type": t["type"], "angle": t["angle"], "status": "pending", "products": []})
            lower.add(kw.lower())
            added += 1
        print(f"refill: {added} nouveaux sujets")
    except Exception as e:
        print(f"⚠ refill échoué : {e}", file=sys.stderr)


def validate(a: dict) -> list[str]:
    errs = []
    if not 10 <= len(a["title"]) <= 110:
        errs.append(f"title {len(a['title'])} car.")
    if not 50 <= len(a["description"]) <= 200:
        errs.append(f"description {len(a['description'])} car.")
    if re.search(r"^#\s", a["body"], re.M):
        errs.append("H1 dans le corps")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", help="mot-clé principal")
    ap.add_argument("--type", choices=["guide", "news"], default="guide")
    ap.add_argument("--auto", action="store_true", help="prend le prochain sujet 'pending' de topics.json")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = json.loads(TOPICS.read_text())
    if not args.dry_run:
        refill_topics(data)
    if args.auto:
        topic = next((t for t in data["topics"] if t.get("status") == "pending"), None)
        if not topic:
            print("Aucun sujet en attente.")
            return 0
        kind = topic.get("type", "guide")
    elif args.topic:
        topic = next((t for t in data["topics"] if t["keyword"].lower() == args.topic.lower()), None)
        if topic is None:
            topic = {"keyword": args.topic, "type": args.type, "status": "pending", "products": []}
            data["topics"].append(topic)
        kind = args.type
    else:
        ap.error("--topic ou --auto requis")

    print(f"→ {kind} : {topic['keyword']} ({llm_config()[2]})")
    try:
        a = call_llm(topic, kind)
    except Exception as e:
        print(f"⚠ génération échouée, run non bloquant : {e}", file=sys.stderr)
        return 0
    if errs := validate(a):
        print("⚠ " + ", ".join(errs), file=sys.stderr)

    today = date.today().isoformat()
    slug = slugify(a.get("slug") or a["title"])
    taken = {s for s, _ in existing_articles()}
    if slug in taken:
        slug = f"{slug}-{today[:7]}"
    mdx = render_mdx(a, topic, kind, today, slug)

    if args.dry_run:
        print(mdx)
        return 0

    path = DIRS[kind] / f"{slug}.mdx"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(mdx)
    topic.update(status="published", slug=slug, publishedAt=today)
    TOPICS.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"✓ {path.relative_to(ROOT)}")
    if out := os.environ.get("GITHUB_OUTPUT"):
        with open(out, "a") as f:
            f.write(f"path={path.relative_to(ROOT)}\nslug={slug}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
