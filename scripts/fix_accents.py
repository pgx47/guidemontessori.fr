#!/usr/bin/env python3
"""Restore missing French accents in legacy MDX articles via LLM (body + title/description)."""
import json
import os
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
FMT = re.compile(r"\A(---\n.*?\n---\n)\n?(.*)\Z", re.S)
FIELDS = ("title", "description")

PROMPT = """Corrige l'orthographe française de ce contenu : restaure tous les accents manquants (é, è, ê, à, ù, ç, œ, apostrophes typographiques si présentes).
Règles STRICTES : ne change que l'orthographe des mots français. Ne touche pas à la syntaxe Markdown, aux liens, aux URLs, aux balises HTML/JSX, aux classes, aux entités (&#123; &lt;), aux noms propres, aux anglicismes, au contenu du frontmatter autre que title/description.
Rends title, description et body corrigés via l'outil."""

TOOL = {
    "type": "function",
    "function": {
        "name": "fix_accents",
        "description": "Renvoie le contenu avec accents restaurés.",
        "parameters": {
            "type": "object",
            "required": ["title", "description", "body"],
            "properties": {
                "title": {"type": "string"},
                "description": {"type": "string"},
                "body": {"type": "string"},
            },
        },
    },
}


def fm_field(fm: str, key: str) -> str:
    m = re.search(rf"^{key}:\s*(.+)$", fm, re.M)
    if not m:
        sys.exit(f"{key} absent")
    return json.loads(m.group(1)) if m.group(1).startswith('"') else m.group(1)


def set_field(fm: str, key: str, val: str) -> str:
    return re.sub(rf"^{key}:\s*.+$", f"{key}: {json.dumps(val, ensure_ascii=False)}", fm, count=1, flags=re.M)


def main() -> int:
    key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("LLM_API_KEY")
    if not key:
        sys.exit("DEEPSEEK_API_KEY requis")
    base = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com")
    model = os.environ.get("LLM_MODEL", "deepseek-flash")
    only = set(sys.argv[1:])

    for f in sorted((ROOT / "src/content/guides").glob("*.mdx")):
        if only and f.stem not in only:
            continue
        m = FMT.match(f.read_text())
        if not m:
            continue
        fm, body = m.group(1), m.group(2)
        if re.search(r"[àâäéèêëîïôöùûüçœ]", body + fm_field(fm, "title")) and f.stem != "amenager-un-coin-lecture-montessori":
            print("skip (déjà accentué)", f.stem)
            continue
        payload = {"title": fm_field(fm, "title"), "description": fm_field(fm, "description"), "body": body}
        r = requests.post(
            f"{base.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": model, "temperature": 0.1, "max_tokens": 16000, "tools": [TOOL],
                  "tool_choice": "auto", "messages": [
                      {"role": "system", "content": "Tu corriges l'orthographe française sans rien réécrire."},
                      {"role": "user", "content": PROMPT + "\n\n" + json.dumps(payload, ensure_ascii=False)}]},
            timeout=300,
        )
        r.raise_for_status()
        args = next((c["function"]["arguments"] for c in r.json()["choices"][0]["message"].get("tool_calls") or []
                     if c["function"]["name"] == "fix_accents"), None)
        if not args:
            print("skip (pas de tool_call)", f.stem)
            continue
        a = json.loads(args)
        # sanity: ne pas casser liens/JSX
        if len(re.findall(r"\]\(", a["body"])) != len(re.findall(r"\]\(", body)) or \
           len(re.findall(r"<[a-zA-Z/]", a["body"])) != len(re.findall(r"<[a-zA-Z/]", body)):
            print("skip (structure modifiée)", f.stem)
            continue
        new = set_field(fm, "title", a["title"].strip())
        new = set_field(new, "description", a["description"].strip())
        f.write_text(new + "\n" + a["body"].strip() + "\n")
        print("ok", f.stem)
    return 0


if __name__ == "__main__":
    sys.exit(main())
