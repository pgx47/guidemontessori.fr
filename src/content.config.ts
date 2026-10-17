import { defineCollection } from 'astro:content';
import { glob } from 'astro/loaders';
import { z } from 'astro/zod';

const faq = z.array(z.object({ question: z.string(), answer: z.string() }));

const article = z.object({
  title: z.string().min(10).max(110),
  description: z.string().min(50).max(200),
  publishDate: z.coerce.date(),
  updatedDate: z.coerce.date().optional(),
  category: z.enum(['guides', 'news']),
  author: z.string().default('Rédaction GuideMontessori'),
  keywords: z.array(z.string()).default([]),
  emoji: z.string().default('📘'),
  image: z.string().optional(),
  amazonUrl: z.string().url().optional(),
  asin: z.string().regex(/^[A-Z0-9]{10}$/).optional(),
  faq: faq.optional(),
  draft: z.boolean().default(false),
});

export const collections = {
  guides: defineCollection({ loader: glob({ pattern: '**/*.{md,mdx}', base: './src/content/guides' }), schema: article }),
  news: defineCollection({ loader: glob({ pattern: '**/*.{md,mdx}', base: './src/content/news' }), schema: article }),
};
