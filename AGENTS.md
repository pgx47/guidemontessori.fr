# GuideMontessori.fr

Astro 7 (static) + MDX + Tailwind 4, deployed by Cloudflare Pages on push to `main`.

## Commands
- `npm run dev` / `npm run build` (build validates the Zod frontmatter schema in `src/content.config.ts`)
- `python scripts/generate_article.py --topic "..." --type guide|news [--dry-run]` (needs `ANTHROPIC_API_KEY`, optional `ANTHROPIC_MODEL`)
- `python scripts/generate_article.py --auto` — next `pending` topic in `scripts/topics.json`
- `python scripts/fetch_deals.py` — refreshes `src/data/deals.json` (needs `SCRAPER_API_KEY`)
- Python deps: `pip install -r scripts/requirements.txt` (local venv in `.venv/`)

## Layout
- Guides → `src/content/guides/*.mdx` → `/articles/<slug>/` (legacy URLs preserved)
- News → `src/content/news/*.mdx` → `/actualites/<slug>/`
- Products in MDX: `<AffiliateBox asin nom pointsForts pointsFaibles />`; tag in `src/site.config.ts` (`PUBLIC_AMAZON_TAG` env override)
- `_legacy/` = original Next.js sources pulled from 192.168.1.200 (gitignored, contains a hardcoded ScraperAPI key)

## Rules
- Never commit with `[skip ci]`: Cloudflare Pages would skip the deploy.
- Only real ASINs in `topics.json` (the LLM must never invent products).
