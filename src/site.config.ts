import { DEFAULT_AMAZON_TAG, normalizeAmazonUrl } from './lib/affiliate-links.mjs';

export const SITE = {
  name: 'GuideMontessori.fr',
  url: 'https://www.guidemontessori.fr',
  title: 'Montessori à la maison : activités, matériel et conseils | GuideMontessori.fr',
  description:
    'Découvrez les meilleurs matériels Montessori pour accompagner le développement de votre enfant. Guides détaillés, conseils pédagogiques et sélections de produits.',
  author: 'Rédaction GuideMontessori',
  gaId: 'G-SFEFV3XZDZ',
  amazonTag: import.meta.env.PUBLIC_AMAZON_TAG?.trim() || DEFAULT_AMAZON_TAG,
  googleVerification: import.meta.env.PUBLIC_GOOGLE_SITE_VERIFICATION as string | undefined,
  bingVerification: import.meta.env.PUBLIC_BING_SITE_VERIFICATION as string | undefined,
};

export const amazonUrl = (asin: string) => `https://www.amazon.fr/dp/${asin}?tag=${SITE.amazonTag}`;

export const formatDate = (d: Date) =>
  d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' });

export const affiliateUrl = (url: string) => normalizeAmazonUrl(url, SITE.amazonTag);
