import sys
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).parents[1]))
import ping_google

class GoogleSitemapTests(unittest.TestCase):
    def test_submits_sitemap_to_search_console_not_indexing_api(self):
        with patch.object(ping_google.requests, 'put', return_value=Mock(status_code=204)) as put:
            self.assertEqual(ping_google.submit_sitemap('test-token'), 0)
            self.assertEqual(put.call_args.args[0], 'https://www.googleapis.com/webmasters/v3/sites/sc-domain%3Aguidemontessori.fr/sitemaps/https%3A%2F%2Fwww.guidemontessori.fr%2Fsitemap-index.xml')
            self.assertEqual(put.call_args.kwargs['headers']['Authorization'], 'Bearer test-token')

    def test_rejected_sitemap_is_a_visible_failure(self):
        with patch.object(ping_google.requests, 'put', return_value=Mock(status_code=403)):
            self.assertEqual(ping_google.submit_sitemap('test-token'), 1)
