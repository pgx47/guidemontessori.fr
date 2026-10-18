# GuideMontessori.fr — Architecture & Contenus

Site statique **Astro 7 + MDX + Tailwind 4**, hébergé sur **Cloudflare Pages**, piloté 100 % Git/CLI.
Repo : `github.com/pgx47/guidemontessori.fr` (privé), branche `main` = production.

## Pile de déploiement

```
push sur main
  └─ .github/workflows/deploy.yml  →  npm ci → astro build → wrangler pages deploy  (~35 s)

cron lundi & jeudi 6h UTC  (publish.yml)
  └─ generate_article.py (LLM) → MDX + image → build → commit → deploy.yml

cron quotidien 5h UTC  (deals.yml)
  └─ fetch_deals.py (ScraperAPI) → src/data/deals.json → commit → deploy.yml
```

Les pushes du bot (`GITHUB_TOKEN`) ne redéclenchent pas les workflows `push` : `publish`/`deals` appellent donc `deploy.yml` via `workflow_call`.

## Inventaire des pages

| URL | Source | Contenu | Génération |
|---|---|---|---|
| `/` | `src/pages/index.astro` | Hero, cartes, 6 articles vedettes (3+3) | **Auto** (lit les collections) |
| `/articles/` | `src/pages/articles/index.astro` | Grille des 15 guides | **Auto** |
| `/articles/<slug>/` | `src/pages/articles/[slug].astro` → `src/content/guides/*.mdx` | 14 articles migrés du legacy + articles IA | **Auto** (nouveaux articles via LLM) |
| `/actualites/` | `src/pages/actualites/index.astro` | Grille des brèves | **Auto** |
| `/actualites/<slug>/` | `src/pages/actualites/[slug].astro` → `src/content/news/*.mdx` | News IA | **Auto** (collection `news`) |
| `/livres-enfants/` | `src/pages/livres-enfants.astro` + `src/data/books.json` | Livres par catégorie | Semi-auto (JSON manuel) |
| `/lectures-parents/` | `src/pages/lectures-parents.astro` + `books.json` | Livres par niveau | Semi-auto (JSON manuel) |
| `/bons-plans/` | `src/pages/bons-plans.astro` + `src/data/deals.json` | Offres Amazon | **Auto** (cron `deals.yml` + ScraperAPI) |
| `/a-propos/`, `/contact/`, `/cgv/`, `/mentions-legales/`, `/politique-*` | `src/pages/*.astro` | Pages statiques | Manuel |
| `404` | `src/pages/404.astro` | noindex | Manuel |
| `/sitemap-*.xml` | `@astrojs/sitemap` | SEO | **Auto** |
| `/robots.txt`, `/_redirects` | `public/` | Redirects `/articles.html`, `/admin*` | Manuel |

Pages **sans contenu automatique** : a-propos, contact, cgv, mentions-legales, politique-confidentialite, politique-cookies.
Pages **entièrement automatiques** : articles, actualités, bons-plans, sitemap, home (listes).

## Pipeline de génération (`scripts/generate_article.py`)

1. `--auto` pioche le 1er sujet `pending` de `scripts/topics.json` (ou `--topic "..."` manuel).
2. LLM via tool call structuré → `title, description, slug, keywords, emoji, body, faq, products, imagePrompt`.
   - Providers : `DEEPSEEK_API_KEY` (deepseek-flash, actif) → `OPENROUTER_API_KEY` → `ANTHROPIC_API_KEY` (fallback). `LLM_BASE_URL`/`LLM_MODEL` pour override.
   - Produits : uniquement les ASIN réels de `topics.json` → `<AffiliateBox>` ; l'IA n'invente rien.
3. Image : prompt blindé anti-clipart → **DALL-E 3** (`OPENAI_API_KEY`) sinon pollinations.ai → **vision QC** (deepseek-flash, rejette emoji/3D/clipart) → retry ×3 → fallback photo libre Openverse → Wikimedia.
4. Stockage image : **R2** (`R2_*` + `CLOUDFLARE_ACCOUNT_ID`) → `images.guidemontessori.fr`, sinon `public/images/generated/<slug>.webp` (~80 Ko).
5. Écrit `src/content/{guides|news}/<slug>.mdx`, marque le sujet `published`, workflow commit + build + deploy.

## Autres scripts (`scripts/`)

| Script | Rôle |
|---|---|
| `fetch_deals.py` | Recherche ScraperAPI (amazon.fr) → `deals.json` (20 offres, tag `mtssri-21`) |
| `fix_accents.py` | Restauration des accents legacy via LLM (one-shot fait) |
| `migrate_legacy.py` | JSON Next.js → MDX (one-shot fait, résout is.gd, ASINs) |
| `topics.json` | Matrice sujets : keyword, type, angle, produits, statut |

## Composants clés (`src/`)

- `components/AffiliateBox.astro` — carte produit (asin, nom, +/-, CTA Amazon taggé)
- `components/SeoSchema.astro` — JSON-LD Article/FAQ/Breadcrumb/WebSite
- `layouts/BaseLayout.astro` — header/footer, GA `G-SFEFV3XZDZ`, meta OG
- `layouts/ArticleLayout.astro` — article : breadcrumb, prose, FAQ, partage, CTA Amazon, à-lire-aussi
- `site.config.ts` — domaine, tag `mtssri-21` (override `PUBLIC_AMAZON_TAG`)
- `content.config.ts` — schéma Zod frontmatter (rejeté au build si invalide)

## Secrets GitHub

| Secret | Usage |
|---|---|
| `CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_ACCOUNT_ID` | deploy (Pages + DNS) |
| `DEEPSEEK_API_KEY` | génération articles + vision QC |
| `SCRAPER_API_KEY` | bons plans |
| `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `R2_*` | optionnels (providers/stockage alternatifs) |

## Legacy

`_legacy/` (gitignored) = sources Next.js récupérées sur 192.168.1.200 (site mort : tunnels cloudflared arrêtés). URLs `/articles/<slug>` conservées à l'identique.
