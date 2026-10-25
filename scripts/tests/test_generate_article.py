import importlib.util
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('generate_article', Path(__file__).parents[1] / 'generate_article.py')
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


class PublisherTests(unittest.TestCase):
    def test_empty_github_variables_use_provider_defaults(self):
        for key, base in [('DEEPSEEK_API_KEY', 'https://api.deepseek.com'), ('OPENROUTER_API_KEY', 'https://openrouter.ai/api/v1')]:
            with self.subTest(provider=key), patch.dict(os.environ, {key: 'test-key', 'LLM_BASE_URL': '', 'LLM_MODEL': ''}, clear=True):
                url, _, model, _ = generator.llm_config()
                self.assertEqual(url, base)
                self.assertTrue(model)

    def test_generation_failure_returns_failure(self):
        with patch.object(sys, 'argv', ['generate_article.py', '--auto']), patch.object(generator, 'refill_topics'), patch.object(generator, 'llm_config', return_value=('https://example.com', 'test', 'test', 'openai')), patch.object(generator, 'call_llm', side_effect=RuntimeError('API unavailable')), patch.object(generator, 'TOPICS') as topics:
            topics.read_text.return_value = '{"topics": [{"keyword": "test topic", "status": "pending", "type": "guide"}]}'
            self.assertEqual(generator.main(), 1)

    def test_custom_provider_configuration_is_preserved(self):
        with patch.dict(os.environ, {'LLM_API_KEY': 'test', 'LLM_BASE_URL': 'https://example.com/v1', 'LLM_MODEL': 'custom-model'}, clear=True):
            self.assertEqual(generator.llm_config(), ('https://example.com/v1', 'test', 'custom-model', 'openai'))


if __name__ == '__main__':
    unittest.main()
