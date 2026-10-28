import { getGuides, getNews } from '../lib/content';
import { SITE } from '../site.config';

export const prerender = true;

const escapeXml = (s: string) =>
  s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');

export async function GET() {
  const guides = await getGuides();
  const news = await getNews();

  const items = [...guides, ...news]
    .sort((a, b) => b.data.publishDate.valueOf() - a.data.publishDate.valueOf())
    .slice(0, 30);

  const xml = [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<rss version="2.0">',
    '<channel>',
    `<title>${escapeXml(SITE.title)}</title>`,
    `<link>${escapeXml(SITE.url)}</link>`,
    `<description>${escapeXml(SITE.description)}</description>`,
    '<language>fr</language>',
    `<lastBuildDate>${new Date().toUTCString()}</lastBuildDate>`,
    ...items.map((e) => {
      const url = `${SITE.url}${e.collection === 'guides' ? '/articles/' : '/actualites/'}${e.id}/`;
      return [
        '<item>',
        `<title>${escapeXml(e.data.title)}</title>`,
        `<link>${escapeXml(url)}</link>`,
        `<guid isPermaLink="true">${escapeXml(url)}</guid>`,
        `<pubDate>${e.data.publishDate.toUTCString()}</pubDate>`,
        `<description>${escapeXml(e.data.description)}</description>`,
        `<category>${escapeXml(e.data.category)}</category>`,
        '</item>',
      ].join('');
    }),
    '</channel>',
    '</rss>',
  ].join('\n');

  return new Response(xml, {
    headers: { 'Content-Type': 'application/rss+xml; charset=utf-8' },
  });
}
