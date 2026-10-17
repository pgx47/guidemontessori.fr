export const SITE = {
  name: 'GuideMontessori.fr',
  url: 'https://www.guidemontessori.fr',
  title: 'GuideMontessori.fr | Le Guide pour une Parentalité Bienveillante',
  description:
    'Découvrez les meilleurs matériels Montessori pour accompagner le développement de votre enfant. Guides détaillés, conseils pédagogiques et sélections de produits.',
  author: 'Rédaction GuideMontessori',
  gaId: 'G-SFEFV3XZDZ',
  amazonTag: import.meta.env.PUBLIC_AMAZON_TAG ?? 'missstream-21',
};

export const amazonUrl = (asin: string) => `https://www.amazon.fr/dp/${asin}?tag=${SITE.amazonTag}`;

export const formatDate = (d: Date) =>
  d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' });
