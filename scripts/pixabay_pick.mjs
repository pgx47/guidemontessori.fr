/**
 * Collecte des candidats Pixabay par slug, puis applique une sélection visuelle.
 *
 *   node scripts/pixabay_pick.mjs collect   -> /tmp/pb/<slug>/*.jpg + manifest.json
 *   node scripts/pixabay_pick.mjs sheets    -> /tmp/pb/sheet-N.jpg
 *   node scripts/pixabay_pick.mjs apply     -> applique /tmp/pb/selection.json
 */
import fs from 'node:fs';
import path from 'node:path';
import sharp from 'sharp';

const MODE = process.argv[2];
const WORK = '/tmp/pb';
const KEY = process.env.PIXABAY_API_KEY;
const UA = 'GuideMontessori/1.0';

/** Plusieurs variantes par slug : Pixabay est littéral, il faut viser juste. */
const PLAN = {
  'etagere-montessori-jouets-rotation': ['montessori shelf nursery', 'wooden toy shelf child room', 'low shelf wooden toys'],
  'tour-observation-montessori-age-stabilite': ['learning tower toddler kitchen', 'child standing kitchen counter', 'toddler kitchen helper stool'],
  'amenager-un-coin-lecture-montessori': ['children reading nook cushions', 'kids bookshelf front facing', 'child reading corner home'],
  'preparation-environnement-montessori': ['montessori classroom shelf', 'wooden toys shelf playroom', 'child room low furniture'],
  'apprentissage-vie-pratique-montessori-vaisselle': ['child washing dishes sink', 'kid helping dishes kitchen', 'toddler pouring water bowl'],
  'la-tour-pink-montessori-developpement-equilibre-enfant': ['pink wooden cubes tower', 'stacking cubes children wooden', 'wooden building blocks tower'],
  'agent-accueil-petite-enfance-offres-salaires': ['daycare entrance hall', 'kindergarten reception room', 'nursery interior wooden'],
  'accueil-grand-age-methode-montessori-france-tv': ['elderly woman activity hands', 'senior care hands table', 'old people craft activity'],
  'atelier-montessori-rochechouart-aide-moi-a-faire-seul': ['children painting workshop table', 'kids hands crafting wood', 'workshop children activity indoors'],
  'bougeotheque-municipale-bordeaux-petite-enfance': ['toddler balance beam gym', 'children movement class indoor', 'kids physical activity indoor'],
  'ecole-montessori-irisia-aix-chantier-cour': ['school courtyard plane trees', 'schoolyard trees shade', 'french school building trees'],
};

const api = async (params) => {
  const url = `https://pixabay.com/api/?${new URLSearchParams({ key: KEY, image_type: 'photo', orientation: 'horizontal', min_width: '1600', per_page: '20', safesearch: 'true', ...params })}`;
  const r = await fetch(url, { headers: { 'User-Agent': UA }, signal: AbortSignal.timeout(25000) });
  if (!r.ok) throw new Error(`http ${r.status}`);
  return r.json();
};

async function collect() {
  fs.rmSync(WORK, { recursive: true, force: true });
  fs.mkdirSync(WORK, { recursive: true });
  const manifest = {};
  for (const [slug, queries] of Object.entries(PLAN)) {
    const dir = path.join(WORK, slug);
    fs.mkdirSync(dir, { recursive: true });
    const seen = new Set();
    const picked = [];
    for (const q of queries) {
      let data;
      try { data = await api({ q }); } catch (e) { console.log(`  ! ${q}: ${e.message}`); continue; }
      for (const hit of data.hits ?? []) {
        if (picked.length >= 8) break;
        if (seen.has(hit.id)) continue;
        const ratio = hit.imageWidth / hit.imageHeight;
        if (ratio < 1.2 || ratio > 2.2) continue;
        seen.add(hit.id);
        const url = hit.largeImageURL;
        try {
          const r = await fetch(url, { signal: AbortSignal.timeout(25000) });
          if (!r.ok) continue;
          const buf = Buffer.from(await r.arrayBuffer());
          const idx = picked.length;
          await sharp(buf).resize(420, 280, { fit: 'cover' }).jpeg({ quality: 82 }).toFile(path.join(dir, `${idx}.jpg`));
          picked.push({
            idx, id: hit.id, tags: (hit.tags || '').slice(0, 70),
            w: hit.imageWidth, h: hit.imageHeight,
            full: hit.fullHDURL || hit.largeImageURL,
            page: hit.pageURL, user: hit.user, user_id: hit.user_id,
          });
        } catch { /* suivant */ }
      }
      if (picked.length >= 8) break;
    }
    manifest[slug] = picked;
    console.log(`${String(picked.length).padStart(2)}  ${slug}`);
  }
  fs.writeFileSync(path.join(WORK, 'manifest.json'), JSON.stringify(manifest, null, 2));
}

async function sheets() {
  const manifest = JSON.parse(fs.readFileSync(path.join(WORK, 'manifest.json'), 'utf8'));
  const slugs = Object.keys(manifest);
  const CW = 430, CH = 280, PAD = 8, LAB = 30;
  let n = 0;
  for (let i = 0; i < slugs.length; i += 3) {
    const group = slugs.slice(i, i + 3);
    const cols = Math.max(...group.map((s) => manifest[s].length));
    const W = cols * (CW + PAD) + PAD;
    const H = group.length * (CH + LAB + PAD) + PAD;
    const composites = [];
    const labels = [];
    group.forEach((slug, r) => {
      manifest[slug].forEach((c, col) => {
        const x = PAD + col * (CW + PAD);
        const y = PAD + r * (CH + LAB + PAD);
        composites.push({ input: path.join(WORK, slug, `${c.idx}.jpg`), left: x, top: y + LAB });
        labels.push({ x, y, text: `${r}:${col}` });
      });
    });
    const svg = `<svg width="${W}" height="${H}" xmlns="http://www.w3.org/2000/svg">
      <rect width="100%" height="100%" fill="#0d0d0d"/>
      ${labels.map((l) => `<text x="${l.x + 3}" y="${l.y + 21}" fill="#4ade80" font-size="18" font-family="monospace">${l.text} — ${group[+l.text.split(':')[0]].slice(0, 30)}</text>`).join('')}
    </svg>`;
    await sharp(Buffer.from(svg)).composite(composites).jpeg({ quality: 84 }).toFile(path.join(WORK, `sheet-${n}.jpg`));
    n++;
  }
  console.log(`${n} planches dans ${WORK}`);
}

async function apply() {
  const manifest = JSON.parse(fs.readFileSync(path.join(WORK, 'manifest.json'), 'utf8'));
  const selection = JSON.parse(fs.readFileSync(path.join(WORK, 'selection.json'), 'utf8'));
  const credits = fs.existsSync('src/data/image_credits.json')
    ? JSON.parse(fs.readFileSync('src/data/image_credits.json', 'utf8')) : {};

  for (const [slug, idx] of Object.entries(selection)) {
    const cand = manifest[slug]?.find((c) => c.idx === idx);
    if (!cand) { console.log(`✗ ${slug}: index ${idx} absent`); continue; }
    const col = fs.existsSync(`src/content/guides/${slug}.mdx`) ? 'guides' : 'news';
    const file = `src/content/${col}/${slug}.mdx`;
    let src = fs.readFileSync(file, 'utf8');

    const r = await fetch(cand.full, { signal: AbortSignal.timeout(40000) });
    const buf = Buffer.from(await r.arrayBuffer());
    const out = path.join('public', 'images', 'photos', slug);
    await sharp(buf).rotate().resize({ width: 1200, withoutEnlargement: true }).webp({ quality: 82 }).toFile(`${out}.webp`);
    await sharp(buf).rotate().resize({ width: 640, withoutEnlargement: true }).webp({ quality: 78 }).toFile(`${out}-640.webp`);

    src = src.replace(/^image:.*$/m, `image: "/images/photos/${slug}.webp"`);
    src = src.replace(/^imageCredit:.*\n/m, '');
    src = src.replace(/^image:.*$/m, (m) => `${m}\nimageCredit: "Photo : ${cand.user} / Pixabay"`);
    fs.writeFileSync(file, src);

    credits[slug] = {
      photographer: cand.user,
      profile: `https://pixabay.com/users/${cand.user}-${cand.user_id}/`,
      source: cand.page,
      license: 'Pixabay Content License',
    };
    const kb = (fs.statSync(`${out}.webp`).size / 1024).toFixed(0);
    console.log(`✓ ${slug} [${idx}] ${kb} Ko — ${cand.tags}`);
  }
  fs.writeFileSync('src/data/image_credits.json', JSON.stringify(credits, null, 2) + '\n');
}

({ collect, sheets, apply })[MODE]?.().catch((e) => { console.error(e); process.exit(1); });
