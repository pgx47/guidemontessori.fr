// @ts-check
import fs from 'node:fs';
import path from 'node:path';
import { parse as parseYaml } from 'yaml';
import { defineConfig } from 'astro/config';
import mdx from '@astrojs/mdx';
import { unified } from '@astrojs/markdown-remark';
import sitemap from '@astrojs/sitemap';
import tailwindcss from '@tailwindcss/vite';
import affiliateLinks, { DEFAULT_AMAZON_TAG } from './src/lib/affiliate-links.mjs';

const contentDates = new Map();
for (const [prefix, dir] of [
  ['/articles/', 'guides'],
  ['/actualites/', 'news'],
]) {
  const base = path.join(process.cwd(), 'src/content', dir);
  if (!fs.existsSync(base)) continue;
  for (const file of fs.readdirSync(base)) {
    if (!/\.mdx?$/.test(file)) continue;
    const source = fs.readFileSync(path.join(base, file), 'utf8');
    const frontmatter = source.match(/^---\r?\n([\s\S]*?)\r?\n---/);
    if (!frontmatter) continue;
    const data = parseYaml(frontmatter[1]);
    const date = new Date(data.updatedDate ?? data.publishDate);
    if (!data.draft && new Date(data.publishDate) <= new Date() && !Number.isNaN(date.valueOf())) {
      contentDates.set(`${prefix}${file.replace(/\.mdx?$/, '')}/`, date);
    }
  }
}

export default defineConfig({
  site: 'https://www.guidemontessori.fr',
  trailingSlash: 'ignore',
  build: { format: 'directory' },
  markdown: { processor: unified({ rehypePlugins: [[affiliateLinks, { tag: process.env.PUBLIC_AMAZON_TAG?.trim() || DEFAULT_AMAZON_TAG }]] }) },
  integrations: [
    mdx(),
    sitemap({
      filter: (page) => !/\/bons-plans\/\d+\/$/.test(page),
      serialize(item) {
        const { pathname } = new URL(item.url);
        const lastmod = contentDates.get(pathname);

        let priority = 0.3;
        let changefreq = 'yearly';

        if (pathname === '/') {
          priority = 1.0;
          changefreq = 'weekly';
        } else if (/^\/(articles|actualites|ecoles)\/$/.test(pathname)) {
          priority = 0.9;
          changefreq = 'weekly';
        } else if (/^\/(lectures-parents|livres-enfants|bons-plans|cadeaux)\/$/.test(pathname)) {
          priority = 0.7;
          changefreq = 'monthly';
        } else if (/^\/(articles|actualites)\/[^/]+\/$/.test(pathname)) {
          priority = 0.8;
          changefreq = 'monthly';
        } else if (/^\/ecoles\/[^/]+\/$/.test(pathname)) {
          priority = 0.6;
        } else if (/^\/(mentions-legales|cgv|politique-confidentialite|politique-cookies)\/$/.test(pathname)) {
          priority = 0.2;
        }

        return {
          ...item,
          ...(lastmod && { lastmod: lastmod.toISOString() }),
          priority,
          changefreq,
        };
      },
    }),
  ],
  vite: { plugins: [tailwindcss()] },
});
