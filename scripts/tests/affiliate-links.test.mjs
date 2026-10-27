import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizeAmazonUrl, default as affiliateLinks } from '../../src/lib/affiliate-links.mjs';

test('Amazon URLs use the configured tag while preserving product/search', () => {
  const url = new URL(normalizeAmazonUrl('https://www.amazon.fr/dp/B0882N7PS8?tag=old-21&th=1', 'mtssri-21'));
  assert.equal(url.pathname, '/dp/B0882N7PS8');
  assert.equal(url.searchParams.get('tag'), 'mtssri-21');
  assert.equal(url.searchParams.get('th'), '1');
  assert.equal(normalizeAmazonUrl('https://example.com/?tag=old', 'mtssri-21'), 'https://example.com/?tag=old');
});

test('MDX affiliate links have sponsored and preserve existing rel values', () => {
  const link = {type:'element', tagName:'a', properties:{href:'https://www.amazon.fr/s?k=montessori', rel:['external']}, children:[]};
  const short = {type:'element', tagName:'a', properties:{href:'https://amzn.to/example'}, children:[]};
  affiliateLinks({tag:'mtssri-21'})({type:'root', children:[link, short]});
  assert.match(link.properties.href, /tag=mtssri-21/);
  assert.deepEqual(new Set(link.properties.rel), new Set(['external','nofollow','sponsored','noopener']));
  assert.ok(short.properties.rel.includes('sponsored'));
});

test('raw HTML anchors in MDX are normalized too', () => {
  const link = {type:'mdxJsxTextElement',name:'a',attributes:[{type:'mdxJsxAttribute',name:'href',value:'https://www.amazon.fr/dp/B0882N7PS8?tag=old-21'}],children:[]};
  affiliateLinks({tag:'mtssri-21'})({type:'root',children:[link]});
  assert.match(link.attributes.find(a=>a.name==='href').value, /tag=mtssri-21/);
  assert.match(link.attributes.find(a=>a.name==='rel').value, /sponsored/);
});
