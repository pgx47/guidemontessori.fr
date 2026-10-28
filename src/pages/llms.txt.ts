import { getGuides, getNews } from '../lib/content';
import { SITE } from '../site.config';

export const prerender = true;

const trim = (s: string, max = 160) => (s.length > max ? `${s.slice(0, max - 1).trimEnd()}…` : s);

export async function GET() {
  const guides = await getGuides();
  const news = await getNews();

  const lines: string[] = [];

  lines.push(`# ${SITE.name}`);
  lines.push('');
  lines.push('> Le guide francophone de la pédagogie Montessori à la maison : matériel, activités par âge, conseils, annuaire des écoles et sélection de livres.');
  lines.push('');
  lines.push(
    "GuideMontessori.fr est un site indépendant francophone dédié à la pédagogie Montessori à la maison. Il propose des guides de matériel, des activités par âge et des conseils pratiques, ainsi qu'un annuaire d'écoles Montessori en France, une sélection de livres et des contenus en français.",
  );
  lines.push('');

  lines.push('## Guides');
  lines.push('');
  for (const g of guides) {
    lines.push(`- [${g.data.title}](${SITE.url}/articles/${g.id}/): ${trim(g.data.description)}`);
  }
  lines.push('');

  lines.push('## Actualités');
  lines.push('');
  for (const n of news) {
    lines.push(`- [${n.data.title}](${SITE.url}/actualites/${n.id}/): ${trim(n.data.description)}`);
  }
  lines.push('');

  lines.push('## Écoles Montessori');
  lines.push('');
  lines.push(
    `- [Annuaire des écoles Montessori en France](${SITE.url}/ecoles/): Trouvez une école ou une crèche Montessori près de chez vous, avec carte interactive et recherche par ville.`,
  );
  lines.push('');

  lines.push('## Livres');
  lines.push('');
  lines.push(
    `- [Livres Montessori pour enfants](${SITE.url}/livres-enfants/): Albums, imagiers, cahiers d'activités et Grands Récits pour les enfants.`,
  );
  lines.push(
    `- [Lectures pour les parents](${SITE.url}/lectures-parents/): Les livres essentiels pour comprendre et appliquer la pédagogie Montessori à la maison.`,
  );
  lines.push('');

  lines.push('## Bons plans et cadeaux');
  lines.push('');
  lines.push(
    `- [Bons plans Montessori](${SITE.url}/bons-plans/): Offres et promotions sur le matériel et les livres Montessori, mises à jour chaque semaine.`,
  );
  lines.push(
    `- [Idées cadeaux Montessori](${SITE.url}/cadeaux/): Sélection de cadeaux Montessori par âge et par budget, sans plastique ni piles.`,
  );
  lines.push('');

  lines.push('## À propos du site');
  lines.push('');
  lines.push(
    `- [À propos de GuideMontessori.fr](${SITE.url}/a-propos/): Notre mission et notre approche de la pédagogie Montessori.`,
  );
  lines.push(
    `- [Contact](${SITE.url}/contact/): Une question, un établissement manquant ? Contactez-nous.`,
  );

  return new Response(`${lines.join('\n')}\n`, {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
}
