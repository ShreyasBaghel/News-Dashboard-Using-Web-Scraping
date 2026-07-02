import sys
import os
import unittest
import logging

# Ensure project root is in the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.diversity import getNormalizedDomain, selectDiverseArticles

class TestDomainDiversity(unittest.TestCase):
    def setUp(self):
        # Configure logging to see warnings during tests
        logging.basicConfig(level=logging.WARNING)

    def test_getNormalizedDomain(self):
        # Basic domain extraction
        self.assertEqual(getNormalizedDomain("https://reuters.com/news-story"), "reuters.com")
        self.assertEqual(getNormalizedDomain("http://www.reuters.com/news-story"), "reuters.com")
        self.assertEqual(getNormalizedDomain("https://news.reuters.com/news-story"), "reuters.com")
        
        # Subdomains
        self.assertEqual(getNormalizedDomain("https://sub.sub2.example.com/path?query=1"), "example.com")
        self.assertEqual(getNormalizedDomain("http://blog.tech.google.com"), "google.com")
        
        # Double-suffixes (co.uk, org.uk, com.au, etc.)
        self.assertEqual(getNormalizedDomain("https://news.bbc.co.uk/world-news"), "bbc.co.uk")
        self.assertEqual(getNormalizedDomain("https://www.example.co.uk"), "example.co.uk")
        self.assertEqual(getNormalizedDomain("http://example.com.au"), "example.com.au")
        self.assertEqual(getNormalizedDomain("https://something.net.in/path"), "something.net.in")
        
        # Ports and query strings
        self.assertEqual(getNormalizedDomain("https://localhost:8000/api"), "localhost")
        self.assertEqual(getNormalizedDomain("https://example.com:80/xyz"), "example.com")
        
        # Bad/empty URLs
        self.assertEqual(getNormalizedDomain(""), "")
        self.assertEqual(getNormalizedDomain(None), "")

    def test_selectDiverseArticles_preferred_only(self):
        # All domains are preferred, enough candidates
        candidates = [
            {"title": "Art 1", "url": "https://reuters.com/1"},
            {"title": "Art 2", "url": "https://reuters.com/2"},
            {"title": "Art 3", "url": "https://bloomberg.com/3"},
            {"title": "Art 4", "url": "https://cnbc.com/4"},
            {"title": "Art 5", "url": "https://techcrunch.com/5"},
            {"title": "Art 6", "url": "https://nytimes.com/6"},
            {"title": "Art 7", "url": "https://wsj.com/7"}
        ]
        # Should pick one from each domain, keeping original rank preference
        selected = selectDiverseArticles(candidates, count=5, excludeDomains=[])
        
        self.assertEqual(len(selected), 5)
        domains = [getNormalizedDomain(a["url"]) for a in selected]
        
        # All domains must be unique
        self.assertEqual(len(set(domains)), 5)
        # Should have picked Art 1 (reuters.com), Art 3 (bloomberg.com), Art 4 (cnbc.com), Art 5 (techcrunch.com), Art 6 (nytimes.com)
        self.assertEqual(selected[0]["title"], "Art 1")
        self.assertEqual(selected[1]["title"], "Art 3")
        self.assertEqual(selected[2]["title"], "Art 4")
        self.assertEqual(selected[3]["title"], "Art 5")
        self.assertEqual(selected[4]["title"], "Art 6")

    def test_selectDiverseArticles_with_excludes(self):
        # Pinned domains: microsoft.com, openai.com
        exclude = ["microsoft.com", "openai.com"]
        candidates = [
            {"title": "Art 1", "url": "https://microsoft.com/1"},  # excluded
            {"title": "Art 2", "url": "https://reuters.com/2"},    # preferred
            {"title": "Art 3", "url": "https://openai.com/3"},     # excluded
            {"title": "Art 4", "url": "https://techcrunch.com/4"}, # preferred
            {"title": "Art 5", "url": "https://bloomberg.com/5"},  # preferred
            {"title": "Art 6", "url": "https://nytimes.com/6"},    # preferred
            {"title": "Art 7", "url": "https://wsj.com/7"},        # preferred
        ]
        
        # We need 5. There are 5 preferred domains (reuters, techcrunch, bloomberg, nytimes, wsj).
        # It should ignore microsoft and openai entirely since enough preferred exist.
        selected = selectDiverseArticles(candidates, count=5, excludeDomains=exclude)
        self.assertEqual(len(selected), 5)
        
        domains = [getNormalizedDomain(a["url"]) for a in selected]
        self.assertEqual(set(domains), {"reuters.com", "techcrunch.com", "bloomberg.com", "nytimes.com", "wsj.com"})

    def test_selectDiverseArticles_reuse_excludes_when_needed(self):
        exclude = ["microsoft.com", "openai.com"]
        candidates = [
            {"title": "Art 1", "url": "https://microsoft.com/1"},  # excluded
            {"title": "Art 2", "url": "https://reuters.com/2"},    # preferred
            {"title": "Art 3", "url": "https://openai.com/3"},     # excluded
            {"title": "Art 4", "url": "https://techcrunch.com/4"}, # preferred
            {"title": "Art 5", "url": "https://bloomberg.com/5"},  # preferred
            # Not enough other preferred domains to reach 5
        ]
        
        # We have 3 preferred domains (reuters, techcrunch, bloomberg) and 2 excluded (microsoft, openai).
        # Total unique domains = 5.
        # It should select 3 preferred first, then fill the remaining 2 with the excluded ones (microsoft and openai).
        # And no two articles should share a domain.
        selected = selectDiverseArticles(candidates, count=5, excludeDomains=exclude)
        self.assertEqual(len(selected), 5)
        
        domains = [getNormalizedDomain(a["url"]) for a in selected]
        self.assertEqual(len(set(domains)), 5)
        self.assertEqual(set(domains), {"reuters.com", "techcrunch.com", "bloomberg.com", "microsoft.com", "openai.com"})

    def test_selectDiverseArticles_repeat_domains_fallback(self):
        # Only 3 unique domains available, need 5 articles
        candidates = [
            {"title": "Art 1", "url": "https://reuters.com/1"},
            {"title": "Art 2", "url": "https://reuters.com/2"},
            {"title": "Art 3", "url": "https://bloomberg.com/3"},
            {"title": "Art 4", "url": "https://bloomberg.com/4"},
            {"title": "Art 5", "url": "https://nytimes.com/5"},
            {"title": "Art 6", "url": "https://nytimes.com/6"},
        ]
        
        # Should pick one from each domain first: Art 1, Art 3, Art 5.
        # Then, fill the remaining 2 slots using the next best available articles: Art 2, Art 4.
        selected = selectDiverseArticles(candidates, count=5)
        self.assertEqual(len(selected), 5)
        
        titles = [a["title"] for a in selected]
        self.assertEqual(titles, ["Art 1", "Art 3", "Art 5", "Art 2", "Art 4"])

if __name__ == "__main__":
    unittest.main()
