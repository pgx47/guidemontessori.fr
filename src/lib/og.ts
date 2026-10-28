import fs from 'node:fs';
import crypto from 'node:crypto';

const versions = new Map<string, string>();

/**
 * Anti-cache pour les cartes OG : `/og/articles/x.jpg` -> `/og/articles/x.jpg?v=<hash>`.
 *
 * Les cartes sont régénérées (photo ajoutée/corrigée) mais leur URL ne change
 * jamais : sans ce suffixe, CDN et navigateurs continuent de servir l'ancienne
 * version (l'ancienne directive `immutable` les figeait pour un an).
 * Le suffixe est le hash du contenu : il ne change que si l'image change.
 */
export function ogCardVersion(publicPath: string): string {
  const cached = versions.get(publicPath);
  if (cached) return cached;
  try {
    const hash = crypto.createHash('md5').update(fs.readFileSync(`public${publicPath}`)).digest('hex').slice(0, 8);
    const url = `${publicPath}?v=${hash}`;
    versions.set(publicPath, url);
    versions.set(url, url);
    return url;
  } catch {
    return publicPath;
  }
}

/**
 * Chemin public de la carte Open Graph 1200x630 d'une route, si elle a été
 * générée par `scripts/generate_og.mjs`. Retourne `undefined` sinon.
 *
 * `/articles/barres-rouges/` -> `/og/articles/barres-rouges.jpg?v=...`
 * `/`                        -> `/og/default.jpg?v=...`
 */
export function ogImagePath(pathname: string): string | undefined {
  const clean = pathname.replace(/\/+$/, '');
  const candidates = clean ? [`/og${clean}.jpg`, '/og/default.jpg'] : ['/og/default.jpg'];
  const found = candidates.find((p) => fs.existsSync(`public${p}`));
  return found ? ogCardVersion(found) : undefined;
}
