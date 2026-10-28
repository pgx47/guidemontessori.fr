import fs from 'node:fs';

/**
 * Chemin public de la carte Open Graph 1200x630 d'une route, si elle a été
 * générée par `scripts/generate_og.mjs`. Retourne `undefined` sinon.
 *
 * `/articles/barres-rouges/` -> `/og/articles/barres-rouges.jpg`
 * `/`                        -> `/og/default.jpg`
 */
export function ogImagePath(pathname: string): string | undefined {
  const clean = pathname.replace(/\/+$/, '');
  const candidates = clean ? [`/og${clean}.jpg`, '/og/default.jpg'] : ['/og/default.jpg'];
  return candidates.find((p) => fs.existsSync(`public${p}`));
}
