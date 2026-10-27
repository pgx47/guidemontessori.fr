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
