#!/usr/bin/env node
/**
 * generate_og.mjs
 * ----------------------------------------------------------------------------
 * 1. Génère les images Open Graph (1200×630, JPEG q82) pour chaque article
 *    (guides + news) ainsi qu'une image par défaut.
 *    - image locale existante -> crop "attention" de la source
 *    - URL http(s)              -> jamais téléchargée (droits) -> carte de marque
 *    - pas d'image              -> carte de marque SVG (dégradé, emoji, titre, bandeau)
 * 2. Génère des déclinaisons WebP (1200w q80 + 640w q78) pour les images de
 *    contenu (public/images/*.png, public/images/articles/*, public/hero-*.png).
 *    Idempotent : ne régénère pas si le .webp est plus récent que la source.
 *    Ne supprime jamais le PNG/JPG d'origine.
 *
 * Contrat (consommé par BaseLayout) :
 *   /og/articles/<slug>.jpg, /og/actualites/<slug>.jpg, /og/default.jpg
 *   1200×630, JPEG q82, < 180 Ko.
 */

import fs from 'node:fs';
import path from 'node:path';
import sharp from 'sharp';
import { parse as parseYaml } from 'yaml';

const ROOT = process.cwd();
const PUBLIC = path.join(ROOT, 'public');
const OG_DIR = path.join(PUBLIC, 'og');

const OG_W = 1200;
const OG_H = 630;
const MAX_OG_KB = 180;

const BRAND = 'GuideMontessori.fr';
const TERRACOTTA = '#CF4D5E';
const FONT_TITLE = "'Liberation Serif', 'DejaVu Serif', Georgia, serif";

/* ------------------------------------------------------------------ utils */

function escapeXml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

/** Coupe un titre en max 3 lignes (mots entiers, troncature « … »). */
function wrapTitle(title, maxChars = 36, maxLines = 3) {
  const words = String(title ?? '').trim().split(/\s+/).filter(Boolean);
  const lines = [];
  let line = '';

  for (const w of words) {
    const test = line ? `${line} ${w}` : w;
    if (test.length <= maxChars) {
      line = test;
      continue;
    }
    if (line) lines.push(line);
    // mot très long : découpe dure
    if (w.length > maxChars) {
      let rest = w;
      while (rest.length > maxChars) {
        lines.push(rest.slice(0, maxChars));
        rest = rest.slice(maxChars);
      }
      line = rest;
    } else {
      line = w;
    }
  }
  if (line) lines.push(line);

  if (lines.length <= maxLines) return lines;

  const out = lines.slice(0, maxLines);
  let last = out[maxLines - 1];
  while (`${last}…`.length > maxChars && last.length > 0) last = last.slice(0, -1);
  out[maxLines - 1] = `${last}…`;
  return out;
}

/** Construit le SVG d'une carte de marque 1200×630. */
function buildCardSvg({ title, emoji, disc = false }) {
  const lines = wrapTitle(title);
  const emojiChar = emoji && typeof emoji === 'string' && emoji.trim() ? emoji.trim() : '📘';

  const titleSvg = lines
    .map((line, i) => {
      const y = 390 + i * 60;
      return `<text x="600" y="${y}" text-anchor="middle" font-family="${FONT_TITLE}" font-size="50" font-weight="bold" fill="#3a322b">${escapeXml(line)}</text>`;
    })
    .join('\n    ');

  const emojiSvg = disc
    ? `<circle cx="600" cy="225" r="84" fill="${TERRACOTTA}"/>`
    : `<text x="600" y="225" text-anchor="middle" dominant-baseline="central" font-family="Noto Color Emoji, 'Noto Sans Symbols', 'Noto Sans Symbols2', sans-serif" font-size="168" fill="#4a3f36">${escapeXml(emojiChar)}</text>`;

  return `<svg width="${OG_W}" height="${OG_H}" viewBox="0 0 ${OG_W} ${OG_H}" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#f5f0e8"/>
      <stop offset="1" stop-color="#e8ddd0"/>
    </linearGradient>
  </defs>
  <rect width="${OG_W}" height="${OG_H}" fill="url(#bg)"/>
  ${emojiSvg}
  ${titleSvg}
  <rect x="0" y="540" width="${OG_W}" height="90" fill="${TERRACOTTA}"/>
  <text x="600" y="585" text-anchor="middle" dominant-baseline="middle" font-family="${FONT_TITLE}" font-size="40" font-weight="bold" fill="#ffffff">${escapeXml(BRAND)}</text>
</svg>`;
}

/** Superposition pour l'image par défaut (photo + textes). */
function buildDefaultOverlaySvg() {
  return `<svg width="${OG_W}" height="${OG_H}" viewBox="0 0 ${OG_W} ${OG_H}" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="scrim" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0.45" stop-color="#000000" stop-opacity="0"/>
      <stop offset="1" stop-color="#000000" stop-opacity="0.38"/>
    </linearGradient>
  </defs>
  <rect width="${OG_W}" height="${OG_H}" fill="url(#scrim)"/>
  <text x="600" y="470" text-anchor="middle" dominant-baseline="middle" font-family="${FONT_TITLE}" font-size="62" font-weight="bold" fill="#ffffff" stroke="#00000033" stroke-width="1">Montessori à la maison</text>
  <rect x="0" y="540" width="${OG_W}" height="90" fill="${TERRACOTTA}"/>
  <text x="600" y="585" text-anchor="middle" dominant-baseline="middle" font-family="${FONT_TITLE}" font-size="40" font-weight="bold" fill="#ffffff">${escapeXml(BRAND)}</text>
</svg>`;
}

/* ------------------------------------------------------------ frontmatter */

function readFrontmatter(file) {
  const raw = fs.readFileSync(file, 'utf8');
  const m = raw.match(/^---\r?\n([\s\S]*?)\r?\n---/);
  if (!m) return null;
  try {
    return parseYaml(m[1]) || {};
  } catch (e) {
    console.warn(`  [warn] frontmatter illisible : ${path.relative(ROOT, file)} (${e.message})`);
    return null;
  }
}

function listMdx(dir) {
  if (!fs.existsSync(dir)) return [];
  return fs
    .readdirSync(dir)
    .filter((f) => f.endsWith('.mdx'))
    .map((f) => path.join(dir, f))
    .sort();
}

/* -------------------------------------------------------------- rendu OG */

async function renderJpegFromBuffer(buffer) {
  return sharp(buffer).jpeg({ quality: 82, mozjpeg: true }).toBuffer();
}

async function generateOgFromLocalImage(srcPath, outPath) {
  await sharp(srcPath)
    .resize(OG_W, OG_H, { fit: 'cover', position: 'attention' })
    .jpeg({ quality: 82, mozjpeg: true })
    .toFile(outPath);
}

async function generateBrandCard(outPath, { title, emoji }) {
  const svg = buildCardSvg({ title, emoji });
  try {
    await renderJpegFromBuffer(Buffer.from(svg)).then((b) => fs.writeFileSync(outPath, b));
  } catch (e) {
    // Rendu emoji impossible -> disque terracotta décoratif (ne plante pas).
    console.warn(`  [warn] échec rendu emoji, repli disque : ${outPath} (${e.message})`);
    const fallbackSvg = buildCardSvg({ title, emoji, disc: true });
    const b = await renderJpegFromBuffer(Buffer.from(fallbackSvg));
    fs.writeFileSync(outPath, b);
  }
}

/* ------------------------------------------------------------- default.jpg */

async function generateDefault() {
  const outPath = path.join(OG_DIR, 'default.jpg');
  const maison = path.join(PUBLIC, 'images', 'montessori-maison.webp');
  const overlay = Buffer.from(buildDefaultOverlaySvg());

  let base;
  if (fs.existsSync(maison)) {
    base = await sharp(maison)
      .resize(OG_W, OG_H, { fit: 'cover', position: 'attention' })
      .jpeg({ quality: 82, mozjpeg: true })
      .toBuffer();
  } else {
    const svg = buildCardSvg({ title: '', emoji: '📘' }).replace(
      /<text x="600" y="225"[^>]*>.*?<\/text>/,
      '',
    );
    base = await renderJpegFromBuffer(Buffer.from(svg));
  }

  const out = await sharp(base)
    .composite([{ input: overlay, left: 0, top: 0 }])
    .jpeg({ quality: 82, mozjpeg: true })
    .toBuffer();
  fs.writeFileSync(outPath, out);
  return outPath;
}

/* ---------------------------------------------------------------- WebP --- */

const WEBP_SETS = [
  { width: 1200, quality: 80, suffix: '' },
  { width: 640, quality: 78, suffix: '-640' },
];

function listContentImages() {
  const files = [];

  const pushDir = (dir, filter) => {
    if (!fs.existsSync(dir)) return;
    for (const f of fs.readdirSync(dir)) {
      const full = path.join(dir, f);
      if (!fs.statSync(full).isFile()) continue;
      if (filter(f)) files.push(full);
    }
  };

  // public/images/*.{png,jpg,jpeg} (niveau supérieur uniquement)
  pushDir(path.join(PUBLIC, 'images'), (f) => /\.(png|jpe?g)$/i.test(f));
  // public/images/articles/*
  pushDir(path.join(PUBLIC, 'images', 'articles'), (f) => /\.(png|jpe?g)$/i.test(f));
  // public/hero-*.png
  pushDir(PUBLIC, (f) => /^hero-.+\.png$/i.test(f));

  return files.sort();
}

async function makeWebp(srcFile, set) {
  const ext = path.extname(srcFile);
  const base = srcFile.slice(0, -ext.length);
  const outFile = `${base}${set.suffix}.webp`;

  const srcStat = fs.statSync(srcFile);
  if (fs.existsSync(outFile)) {
    const outStat = fs.statSync(outFile);
    if (outStat.mtimeMs >= srcStat.mtimeMs) {
      return { skipped: true, outFile };
    }
  }

  try {
    await sharp(srcFile)
      .resize({ width: set.width, withoutEnlargement: true })
      .webp({ quality: set.quality })
      .toFile(outFile);
  } catch (e) {
    console.warn(`  [warn] WebP ignoré (source illisible) : ${path.relative(ROOT, srcFile)} (${e.message})`);
    return { skipped: true, outFile, error: true };
  }

  return { skipped: false, outFile };
}

/* ------------------------------------------------------------------ main */

async function main() {
  fs.mkdirSync(path.join(OG_DIR, 'articles'), { recursive: true });
  fs.mkdirSync(path.join(OG_DIR, 'actualites'), { recursive: true });

  const collections = [
    { dir: path.join(ROOT, 'src', 'content', 'guides'), out: 'articles' },
    { dir: path.join(ROOT, 'src', 'content', 'news'), out: 'actualites' },
  ];

  const ogResults = [];
  const generatedCards = [];
  let totalBytes = 0;
  let alerts = [];

  for (const col of collections) {
    for (const file of listMdx(col.dir)) {
      const fm = readFrontmatter(file);
      if (!fm) continue;
      if (fm.draft === true) continue;

      const slug = path.basename(file, '.mdx');
      const outPath = path.join(OG_DIR, col.out, `${slug}.jpg`);
      const image = fm.image;
      const title = fm.title ?? slug;
      const emoji = fm.emoji ?? '📘';

      let source;
      if (typeof image === 'string' && !/^https?:\/\//i.test(image) && image.startsWith('/')) {
        const localPath = path.join(PUBLIC, image);
        // L'image de l'article EST déjà la carte OG (contenu sans visuel propre) :
        // réécrire le fichier sur lui-même ferait échouer sharp. Mais si la carte
        // n'a jamais été générée, il faut la créer — sinon `image:` pointe sur un 404.
        if (path.resolve(localPath) === path.resolve(outPath) && fs.existsSync(outPath)) {
          source = 'card (existante)';
        } else if (path.resolve(localPath) === path.resolve(outPath)) {
          await generateBrandCard(outPath, { title, emoji });
          source = 'card';
        } else if (fs.existsSync(localPath)) {
          await generateOgFromLocalImage(localPath, outPath);
          source = 'photo';
        } else {
          await generateBrandCard(outPath, { title, emoji });
          source = 'card';
          generatedCards.push(slug);
        }
      } else {
        // URL http(s) -> jamais téléchargée ; ou champ absent.
        await generateBrandCard(outPath, { title, emoji });
        source = 'card';
        generatedCards.push(slug);
      }

      const size = fs.statSync(outPath).size;
      totalBytes += size;
      if (size > MAX_OG_KB * 1024) alerts.push(`${slug} (${(size / 1024).toFixed(0)} Ko)`);
      ogResults.push({ slug, source, kb: (size / 1024).toFixed(0) });

      console.log(`  [og] ${col.out}/${slug}  <-  ${source}  (${(size / 1024).toFixed(0)} Ko)`);
    }
  }

  const defaultPath = await generateDefault();
  const defaultSize = fs.statSync(defaultPath).size;
  totalBytes += defaultSize;
  if (defaultSize > MAX_OG_KB * 1024) alerts.push(`default.jpg (${(defaultSize / 1024).toFixed(0)} Ko)`);
  console.log(`  [og] default.jpg  <-  default  (${(defaultSize / 1024).toFixed(0)} Ko)`);

  // WebP
  const contentImages = listContentImages();
  let webpGenerated = 0;
  let webpSkipped = 0;
  for (const src of contentImages) {
    for (const set of WEBP_SETS) {
      const r = await makeWebp(src, set);
      if (r.skipped) webpSkipped++;
      else webpGenerated++;
    }
  }

  // Récapitulatif
  console.log('\n=== Récapitulatif ===');
  console.log(`Images OG générées : ${ogResults.length + 1} (articles + default)`);
  console.log(`Poids total OG     : ${(totalBytes / 1024).toFixed(0)} Ko`);
  console.log(`WebP générés       : ${webpGenerated} (${webpSkipped} déjà à jour)`);
  console.log(`Cartes de marque (sans image source) : ${generatedCards.length}`);
  if (generatedCards.length) console.log(`  -> ${generatedCards.join(', ')}`);
  if (alerts.length) {
    console.log(`\n⚠️  ALERTE poids > ${MAX_OG_KB} Ko : ${alerts.join(', ')}`);
  } else {
    console.log('✅ Aucune image OG au-dessus de 180 Ko.');
  }
}

main().catch((e) => {
  console.error('Erreur :', e);
  process.exit(1);
});
