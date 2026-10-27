#!/usr/bin/env python3
"""Validate built internal links and affiliate markup before deploying."""
import os
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, unquote, urljoin, urlsplit

ROOT = Path(__file__).resolve().parent.parent / 'dist'
TAG = os.environ.get('PUBLIC_AMAZON_TAG', '').strip() or 'mtssri-21'


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.h1 = 0

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.links.append(dict(attrs))
        if tag == 'h1':
            self.h1 += 1


def main():
    pages = list(ROOT.rglob('*.html'))
    if not pages:
        print('No built HTML. Run npm run build first.', file=sys.stderr)
        return 1
    errors = []
    amazon = 0
    for path in pages:
        page = Page()
        page.feed(path.read_text())
        relative = path.relative_to(ROOT)
        if page.h1 != 1:
            errors.append(f'{relative}: expected one H1, found {page.h1}')
        base = 'https://www.guidemontessori.fr/' + str(relative)
        for anchor in page.links:
            href = anchor.get('href', '')
            url = urlsplit(urljoin(base, href))
            if url.hostname == 'www.guidemontessori.fr' and not url.path.startswith('/cdn-cgi/'):
                target = ROOT / unquote(url.path).lstrip('/')
                if not target.is_file() and not (target / 'index.html').is_file():
                    errors.append(f'{relative}: broken internal link {href}')
            elif url.hostname == 'amzn.to':
                errors.append(f'{relative}: unchecked short affiliate link {href}')
            elif url.hostname in ('amazon.fr', 'www.amazon.fr'):
                amazon += 1
                if parse_qs(url.query).get('tag') != [TAG]:
                    errors.append(f'{relative}: wrong Amazon tag {href}')
                if 'sponsored' not in anchor.get('rel', '').split():
                    errors.append(f'{relative}: missing sponsored {href}')
    for error in errors:
        print(error, file=sys.stderr)
    print(f'Site check: {len(pages)} pages, {amazon} Amazon links, {len(errors)} errors.')
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
