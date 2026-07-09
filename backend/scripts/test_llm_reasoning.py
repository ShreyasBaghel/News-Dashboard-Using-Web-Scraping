import os
import sys
import unittest
import asyncio
import json
import httpx
from unittest.mock import patch, MagicMock, AsyncMock

# Ensure project root is in the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.services.llm_reasoning import (
    validate_llm_output,
    get_article_cache_key,
    enrich_articles_with_llm,
    DEFAULT_LLM_INSIGHTS
)
import app.services.llm_reasoning as llm_reasoning

class TestLLMReasoning(unittest.TestCase):
    
    def setUp(self):
        # Enforce settings for tests
        settings.ENABLE_LLM_REASONING = True
        settings.LLM_CACHE_ENABLED = False  # Disabled by default in tests to ensure API calls are exercised
        settings.LLM_BATCH_SIZE = 2
        settings.OLLAMA_TIMEOUT = 5.0
        
        self.dummy_articles = [
            {
                "title": "Smart Automation in Cement Kilns",
                "url": "https://example.com/cement-kilns",
                "source": "Cement Digest",
                "published_at": "2026-07-01T12:00:00Z",
                "summary": "This article discusses automation in cement kilns.",
                "scraped_content": "A detailed look at cement kiln automation using edge AI and robotics.",
                "keyword": "Cement",
                "relevance_score": 2.5,
                "validation_relevance_score": 90.0
            },
            {
                "title": "Robotics in Steel Manufacturing",
                "url": "https://example.com/steel-robots",
                "source": "Steel Insider",
                "published_at": "2026-07-02T12:00:00Z",
                "summary": "This article discusses robotics in steel factories.",
                "scraped_content": "Steel factories are increasingly adopting robotics and automated logistics.",
                "keyword": "Steel",
                "relevance_score": 2.8,
                "validation_relevance_score": 95.0
            }
        ]
        
        self.valid_insights_1 = {
            "executive_summary": "Cement kilns are undergoing optimization using edge computing and analytics.",
            "business_implications": [
                "Reduces fuel consumption in kilns by 10%.",
                "Enables predictive maintenance alerts.",
                "Lowers operational carbon emissions."
            ],
            "ai_relevance": "Edge AI and Predictive Analytics monitor parameters.",
            "industry_categories": ["Cement", "Automation"],
            "innovation_score": 85,
            "sentiment": "Positive"
        }

        self.valid_insights_2 = {
            "executive_summary": "Steel manufacturing plants are integrating heavy robots for material handling.",
            "business_implications": [
                "Optimizes supply chain throughput.",
                "Reduces labor hazards in hot zones.",
                "Saves 15% in daily logistics costs."
            ],
            "ai_relevance": "Robotics and Computer Vision handle tasks.",
            "industry_categories": ["Steel", "Robotics"],
            "innovation_score": 90,
            "sentiment": "Positive"
        }

    def test_schema_validator_valid(self):
        """Test validate_llm_output returns True for correct formats."""
        self.assertTrue(validate_llm_output(self.valid_insights_1))
        self.assertTrue(validate_llm_output(self.valid_insights_2))

    def test_schema_validator_invalid_types(self):
        """Test validate_llm_output returns False for incorrect types or ranges."""
        # Non-dict
        self.assertFalse(validate_llm_output("Not a dict"))
        
        # Missing keys
        bad_insights = self.valid_insights_1.copy()
        del bad_insights["sentiment"]
        self.assertFalse(validate_llm_output(bad_insights))
        
        # Invalid innovation_score range
        bad_insights = self.valid_insights_1.copy()
        bad_insights["innovation_score"] = 120
        self.assertFalse(validate_llm_output(bad_insights))
        
        # Invalid sentiment value
        bad_insights = self.valid_insights_1.copy()
        bad_insights["sentiment"] = "Superb"
        self.assertFalse(validate_llm_output(bad_insights))
        
        # Empty business implications list
        bad_insights = self.valid_insights_1.copy()
        bad_insights["business_implications"] = []
        self.assertFalse(validate_llm_output(bad_insights))

    @patch('app.services.llm_reasoning.get_cached_llm_insights')
    @patch('app.services.llm_reasoning.save_cached_llm_insights')
    def test_caching_mechanics(self, mock_save, mock_get):
        """Test caching mechanism retrieves cached insights without calling Ollama."""
        settings.LLM_CACHE_ENABLED = True
        
        # Return valid cached result
        mock_get.return_value = self.valid_insights_1
        
        # Run enrichment
        loop = asyncio.get_event_loop()
        enriched = loop.run_until_complete(enrich_articles_with_llm([self.dummy_articles[0]]))
        
        # Verify insights were applied
        art = enriched[0]
        self.assertEqual(art["executive_summary"], self.valid_insights_1["executive_summary"])
        self.assertEqual(art["innovation_score"], self.valid_insights_1["innovation_score"])
        
        # Verify cache get was called, but save was NOT called
        mock_get.assert_called_once()
        mock_save.assert_not_called()

    @patch('httpx.AsyncClient.post')
    def test_enrichment_valid_response(self, mock_post):
        """Test enrichment succeeds when Ollama returns a valid JSON matching batch schema."""
        # Mock successful response
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        
        # Batch output response containing results array
        mock_response.json.return_value = {
            "response": json.dumps({
                "results": [
                    {
                        "url": "https://example.com/cement-kilns",
                        **self.valid_insights_1
                    },
                    {
                        "url": "https://example.com/steel-robots",
                        **self.valid_insights_2
                    }
                ]
            })
        }
        mock_post.return_value = mock_response
        
        loop = asyncio.get_event_loop()
        enriched = loop.run_until_complete(enrich_articles_with_llm(self.dummy_articles))
        
        # Check both articles enriched
        self.assertEqual(enriched[0]["executive_summary"], self.valid_insights_1["executive_summary"])
        self.assertEqual(enriched[0]["sentiment"], "Positive")
        
        self.assertEqual(enriched[1]["executive_summary"], self.valid_insights_2["executive_summary"])
        self.assertEqual(enriched[1]["sentiment"], "Positive")
        
        # Check mock post was called once
        mock_post.assert_called_once()

    @patch('httpx.AsyncClient.post')
    def test_retry_on_malformed_json_then_success(self, mock_post):
        """Test that single retry is triggered on malformed JSON and successfully recovers on second attempt."""
        mock_response_fail = MagicMock(spec=httpx.Response)
        mock_response_fail.status_code = 200
        # Malformed response text
        mock_response_fail.json.return_value = {"response": "{ malformed json..."}
        
        mock_response_success = MagicMock(spec=httpx.Response)
        mock_response_success.status_code = 200
        mock_response_success.json.return_value = {
            "response": json.dumps({
                "results": [
                    {
                        "url": "https://example.com/cement-kilns",
                        **self.valid_insights_1
                    },
                    {
                        "url": "https://example.com/steel-robots",
                        **self.valid_insights_2
                    }
                ]
            })
        }
        
        # First call malformed, second call succeeds
        mock_post.side_effect = [mock_response_fail, mock_response_success]
        
        loop = asyncio.get_event_loop()
        enriched = loop.run_until_complete(enrich_articles_with_llm(self.dummy_articles))
        
        # Check enriched correctly
        self.assertEqual(enriched[0]["executive_summary"], self.valid_insights_1["executive_summary"])
        # Check post was called twice (initial + 1 retry)
        self.assertEqual(mock_post.call_count, 2)

    @patch('httpx.AsyncClient.post')
    def test_retry_on_invalid_structure_then_fallback(self, mock_post):
        """Test that if the response has valid JSON but missing schema fields, it retries and falls back gracefully."""
        mock_response_invalid = MagicMock(spec=httpx.Response)
        mock_response_invalid.status_code = 200
        # Missing executive_summary and implications
        mock_response_invalid.json.return_value = {
            "response": json.dumps({
                "results": [
                    {
                        "url": "https://example.com/cement-kilns",
                        "sentiment": "Positive"
                    }
                ]
            })
        }
        
        # Call fails both times
        mock_post.side_effect = [mock_response_invalid, mock_response_invalid]
        
        loop = asyncio.get_event_loop()
        enriched = loop.run_until_complete(enrich_articles_with_llm([self.dummy_articles[0]]))
        
        # Check that we fell back gracefully to DEFAULT_LLM_INSIGHTS
        self.assertEqual(enriched[0]["executive_summary"], DEFAULT_LLM_INSIGHTS["executive_summary"])
        self.assertEqual(mock_post.call_count, 2)

    @patch('httpx.AsyncClient.post')
    def test_ollama_offline_fallback(self, mock_post):
        """Test pipeline operates normally and returns fallback insights if Ollama is completely offline/throws error."""
        # Mock request exception (e.g., ConnectionRefusedError)
        mock_post.side_effect = httpx.ConnectError("Ollama connection refused")
        
        loop = asyncio.get_event_loop()
        enriched = loop.run_until_complete(enrich_articles_with_llm(self.dummy_articles))
        
        # Verify that even when offline, the pipeline runs and returns fallback insights
        # Note: If Ollama fails completely, it assigns DEFAULT_LLM_INSIGHTS so the API doesn't fail
        self.assertEqual(enriched[0]["executive_summary"], DEFAULT_LLM_INSIGHTS["executive_summary"])
        self.assertEqual(enriched[1]["executive_summary"], DEFAULT_LLM_INSIGHTS["executive_summary"])
        self.assertEqual(mock_post.call_count, 2)  # It should try, fail, and retry once

if __name__ == "__main__":
    unittest.main()
