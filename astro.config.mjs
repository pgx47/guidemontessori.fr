// @ts-check
import fs from 'node:fs';
import path from 'node:path';
import { defineConfig } from 'astro/config';
import mdx from '@astrojs/mdx';
import sitemap from '@astrojs/sitemap';
import tailwindcss from '@tailwindcss/vite';

const contentDates = new Map();
for (const [prefix, dir] of [
  ['/articles/', 'guides'],
  ['/actualites/', 'news'],
]) {
  const base = path.join(process.cwd(), 'src/content', dir);
  if (!fs.existsSync(base)) continue;
  for (const file of fs.readdirSync(base)) {
    if (!/\.mdx?$/.test(file)) continue;
    contentDates.set(`${prefix}${file.replace(/\.mdx?$/, '')}/`, fs.statSync(path.join(base, file)).mtime);
  }
}

export default defineConfig({
  site: 'https://www.guidemontessori.fr',
  trailingSlash: 'ignore',
  build: { format: 'directory' },
  integrations: [
    mdx(),
    sitemap({
      filter: (page) => !/\/bons-plans\/\d+\/$/.test(page),
      serialize(item) {
        const { pathname } = new URL(item.url);
        const lastmod = contentDates.get(pathname);
        return {
          ...item,
          ...(lastmod && { lastmod: lastmod.toISOString() }),
          priority: pathname === '/' ? 1 : /^\/(articles|actualites)\/[^/]+\/$/.test(pathname) ? 0.8 : 0.5,
          changefreq: /^\/(articles|actualites)\//.test(pathname) ? 'weekly' : 'monthly',
        };
      },
    }),
  ],
  vite: { plugins: [tailwindcss()] },
});
