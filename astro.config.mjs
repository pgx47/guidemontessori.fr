// @ts-check
import { defineConfig } from 'astro/config';
import mdx from '@astrojs/mdx';
import sitemap from '@astrojs/sitemap';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  site: 'https://www.guidemontessori.fr',
  trailingSlash: 'ignore',
  build: { format: 'directory' },
  integrations: [mdx(), sitemap()],
  vite: { plugins: [tailwindcss()] },
});
