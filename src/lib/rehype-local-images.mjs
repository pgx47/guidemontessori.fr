import fs from 'node:fs';
import path from 'node:path';

/**
 * Rehype : images Markdown locales -> <picture> WebP + dimensions intrinsèques.
 *
 * Les images du corps des articles étaient servies en PNG pleine résolution
 * (jusqu'à 950 Ko) alors que des variantes WebP 1200w/640w existent déjà dans
 * `public/images`. On émet donc un <picture> avec srcset, et on ajoute les
 * `width`/`height` intrinsèques pour supprimer le décalage de mise en page.
 */
const PUBLIC_DIR = path.join(process.cwd(), 'public');
const SIZES = '(min-width: 768px) 768px, 100vw';

async function variantsFor(src, sharp) {
  const base = src.replace(/\.(png|jpe?g|webp)$/i, '');
  const candidates = [`${base}-640.webp`, `${base}.webp`].filter((v) =>
    fs.existsSync(path.join(PUBLIC_DIR, v)),
  );
  const variants = [];
  for (const file of candidates) {
    try {
      const meta = await sharp(path.join(PUBLIC_DIR, file)).metadata();
      if (meta.width) variants.push({ path: file, width: meta.width });
    } catch {
      // variante illisible : on ignore
    }
  }
  return variants.sort((a, b) => a.width - b.width);
}

async function enhance(img, sharp) {
  const src = String(img.properties?.src ?? '');
  if (!src.startsWith('/images/')) return null;
  const file = src.split('?')[0];

  let width;
  let height;
  try {
    const meta = await sharp(path.join(PUBLIC_DIR, file)).metadata();
    width = meta.width;
    height = meta.height;
  } catch {
    return null;
  }
  if (!width || !height) return null;

  const variants = await variantsFor(file, sharp);
  const props = {
    src,
    alt: img.properties?.alt ?? '',
    width,
    height,
    loading: 'lazy',
    decoding: 'async',
  };

  const children = [];
  if (variants.length > 0) {
    children.push({
      type: 'element',
      tagName: 'source',
      properties: {
        type: 'image/webp',
        srcSet: variants.map((v) => `${v.path} ${v.width}w`).join(', '),
        sizes: SIZES,
      },
      children: [],
    });
    // Le PNG/JPEG d'origine reste le repli : il porte les dimensions réelles.
    children.push({ type: 'element', tagName: 'img', properties: props, children: [] });
    return { type: 'element', tagName: 'picture', properties: {}, children };
  }

  return { type: 'element', tagName: 'img', properties: props, children: [] };
}

export default function rehypeLocalImages() {
  return async function transformer(tree) {
    const { default: sharp } = await import('sharp');

    async function walk(node) {
      if (!Array.isArray(node.children)) return;
      for (let i = 0; i < node.children.length; i += 1) {
        const child = node.children[i];
        if (child?.type === 'element' && child.tagName === 'img') {
          const replaced = await enhance(child, sharp);
          if (replaced) {
            node.children[i] = replaced;
            continue;
          }
        }
        await walk(child);
      }
    }

    await walk(tree);
  };
}
