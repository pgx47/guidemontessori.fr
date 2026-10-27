export const DEFAULT_AMAZON_TAG = 'mtssri-21';

export function normalizeAmazonUrl(href, tag = DEFAULT_AMAZON_TAG) {
  try {
    const url = new URL(href);
    if (url.protocol === 'https:' && /(^|\.)amazon\.fr$/.test(url.hostname)) {
      url.searchParams.set('tag', tag);
      return url.toString();
    }
  } catch { /* Leave relative and non-URL links unchanged. */ }
  return href;
}

export default function affiliateLinks({ tag = DEFAULT_AMAZON_TAG } = {}) {
  return function walk(node) {
    const jsx = /^(mdxJsxTextElement|mdxJsxFlowElement)$/.test(node.type) && node.name === 'a';
    const html = node.type === 'element' && node.tagName === 'a';
    if (html || jsx) {
      const hrefAttribute = jsx && node.attributes?.find(a => a.name === 'href');
      const href = jsx ? hrefAttribute?.value : node.properties?.href;
      let url;
      try { url = typeof href === 'string' ? new URL(href) : null; } catch { /* Internal link. */ }
      if (url && (/(^|\.)amazon\.fr$/.test(url.hostname) || url.hostname === 'amzn.to')) {
        const relAttribute = jsx && node.attributes.find(a => a.name === 'rel');
        const oldRel = jsx ? relAttribute?.value : node.properties.rel;
        const rel = [...new Set([...(Array.isArray(oldRel) ? oldRel : typeof oldRel === 'string' ? oldRel.split(/\s+/) : []), 'nofollow', 'sponsored', 'noopener'])];
        if (jsx) {
          hrefAttribute.value = normalizeAmazonUrl(href, tag);
          if (relAttribute) relAttribute.value = rel.join(' ');
          else node.attributes.push({type: 'mdxJsxAttribute', name: 'rel', value: rel.join(' ')});
        } else {
          node.properties.href = normalizeAmazonUrl(href, tag);
          node.properties.rel = rel;
        }
      }
    }
    node.children?.forEach(walk);
  };
}
