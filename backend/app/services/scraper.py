import httpx
import logging
from bs4 import BeautifulSoup
import asyncio

logger = logging.getLogger(__name__)

async def scrape_article(url: str, title: str = "") -> str:
    """
    Scrapes the text paragraphs of an article from a URL.
    Returns a truncated version of the body text (first 2-3 paragraphs, capped at 250 words) for LLM consumption.
    Bypasses real requests for mock URLs.
    """
    # Check for mock URLs
    if "-mock.com" in url:
        return f"Mock content details for article: '{title}'. This describes the progress, trends, and technologies surrounding the topic in detail."
        
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5"
    }
    
    try:
        # Be polite: Wait 3.0s before requesting to avoid hitting rate limits
        await asyncio.sleep(3.0)
        
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            
            if response.status_code != 200:
                logger.warning(f"Could not scrape {url}: Status {response.status_code}")
                return f"Unable to fetch full text. Summary will be based on title: {title}"
                
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Remove script and style elements
            for script in soup(["script", "style", "nav", "footer", "header"]):
                script.decompose()
                
            # Get the first 2-3 paragraphs
            paragraphs = soup.find_all("p")
            text_blocks = []
            for p in paragraphs:
                p_text = p.get_text().strip()
                if len(p_text) > 30:
                    p_clean = " ".join(p_text.split())
                    text_blocks.append(p_clean)
                    if len(text_blocks) >= 3:
                        break
            
            # Combine text
            full_text = " ".join(text_blocks)
            
            if not full_text:
                return f"No readable paragraph text found on the page. Title: {title}"
                
            # Limit length to ~150-250 words
            words = full_text.split()
            if len(words) > 250:
                full_text = " ".join(words[:250])
                
            return full_text
            
    except Exception as e:
        logger.error(f"Error scraping {url}: {str(e)}")
        return f"Error occurred during scraping: {str(e)}. Title: {title}"
