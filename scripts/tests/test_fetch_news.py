import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))
import fetch_news


class NewsPublisherTests(unittest.TestCase):
    def test_failed_generation_reports_failure_and_keeps_processing(self):
        items = [('https://example.com/1', 'First', ''), ('https://example.com/2', 'Second', '')]
        with patch.object(fetch_news, 'latest_items', return_value=items), patch.object(fetch_news, '_publish', side_effect=[RuntimeError('API unavailable'), None]) as publish:
            self.assertEqual(fetch_news.main(), 1)
            self.assertEqual(publish.call_count, 2)

    def test_no_new_items_is_success(self):
        with patch.object(fetch_news, 'latest_items', return_value=[]):
            self.assertEqual(fetch_news.main(), 0)
