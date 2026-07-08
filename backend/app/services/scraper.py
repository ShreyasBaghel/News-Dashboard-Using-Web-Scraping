import httpx
import logging
from bs4 import BeautifulSoup
import asyncio
import re
from app.services.validator import is_valid_url, is_valid_source_type, validate_content_quality

logger = logging.getLogger(__name__)

async def scrape_article(url: str, title: str = "") -> str:
    """
    Scrapes the text paragraphs of an article from a URL.
    Returns a truncated version of the body text (first 2-3 paragraphs, capped at 250 words) for LLM consumption.
    Raises ValueError on scraping or validation failures to allow the pipeline to retry.
    """
    # 1. Check for mock URLs
    if "-mock.com" in url:
        return (
            f"This is a detailed mock report regarding '{title}'. "
            f"The current developments in the industry highlight rapid progress and emerging trends "
            f"across multiple sectors. Companies are actively investing in new solutions to optimize "
            f"their operations, reduce carbon emissions, and improve productivity.\n\n"
            f"Key stakeholders are emphasizing the integration of smart automation technologies "
            f"to streamline workflows. These initiatives are expected to yield significant cost savings "
            f"and enhance manufacturing performance over the next decade."
        )

    # 2. Pre-scrape URL check
    url_ok, reason = is_valid_url(url)
    if not url_ok:
        logger.warning(f"Skipping scrape for {url}: {reason}")
        raise ValueError(f"Invalid URL: {reason}")
        
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
                raise ValueError(f"HTTP Status {response.status_code}")
                
            html_content = response.text
            
            # Stage 1: Standard Extraction Method
            full_text, paragraphs_count = _extract_with_standard_p_tags(html_content)
            
            # Stage 2: Alternative Extraction Method 1 (Targeted Containers)
            if not full_text or len(full_text.split()) < 60 or paragraphs_count < 2:
                logger.info(f"Standard extraction yielded insufficient content for {url}. Retrying with targeted containers...")
                full_text, paragraphs_count = _extract_with_containers(html_content)
                
            # Stage 3: Alternative Extraction Method 2 (Aggressive HTML Cleaning & Density checking)
            if not full_text or len(full_text.split()) < 60 or paragraphs_count < 2:
                logger.info(f"Container extraction yielded insufficient content for {url}. Retrying with aggressive text density cleaning...")
                full_text, paragraphs_count = _extract_with_text_density(html_content)
                
            if not full_text:
                raise ValueError("No readable text found on the page after all extraction methods.")
                
            # Validate source type and quality
            source_ok, source_reason = is_valid_source_type(url, title, full_text)
            if not source_ok:
                raise ValueError(f"Invalid source type: {source_reason}")
                
            quality_ok, quality_reason = validate_content_quality(full_text)
            if not quality_ok:
                raise ValueError(f"Invalid content quality: {quality_reason}")
                
            # Limit length to ~150-250 words
            words = full_text.split()
            if len(words) > 250:
                full_text = " ".join(words[:250])
                
            return full_text
            
    except Exception as e:
        logger.error(f"Error scraping {url}: {str(e)}")
        raise ValueError(f"Scraping failed: {str(e)}")


def _extract_with_standard_p_tags(html: str) -> tuple[str, int]:
    """Helper method to extract paragraphs using standard soup.find_all('p')."""
    soup = BeautifulSoup(html, "html.parser")
    
    # Remove script and style elements
    for element in soup(["script", "style", "nav", "footer", "header", "aside"]):
        element.decompose()
        
    paragraphs = soup.find_all("p")
    text_blocks = []
    word_count = 0
    for p in paragraphs:
        p_text = p.get_text().strip()
        if len(p_text) > 30:
            p_clean = " ".join(p_text.split())
            text_blocks.append(p_clean)
            word_count += len(p_clean.split())
            if word_count >= 250 or len(text_blocks) >= 8:
                break
                
    return " ".join(text_blocks), len(text_blocks)


def _extract_with_containers(html: str) -> tuple[str, int]:
    """Helper method targeting typical article or main content containers."""
    soup = BeautifulSoup(html, "html.parser")
    for element in soup(["script", "style", "nav", "footer", "header", "aside"]):
        element.decompose()
        
    # Search for common main content tags
    containers = soup.find_all(["article", "main"])
    if not containers:
        # Search by class names
        class_regex = re.compile(r"post-content|entry-content|article-body|story-body|article-content|story-content")
        containers = soup.find_all(class_=class_regex)
        
    if not containers:
        # Search by ID names
        id_regex = re.compile(r"article-body|story-body|content-body|main-content")
        containers = soup.find_all(id=id_regex)
        
    if not containers:
        return "", 0
        
    text_blocks = []
    word_count = 0
    for container in containers:
        # Extract direct paragraphs or divs with text
        elements = container.find_all(["p", "div"])
        for el in elements:
            # Skip if nested p/div exists to avoid double text extraction
            if el.name == "div" and el.find(["p", "div"]):
                continue
            el_text = el.get_text().strip()
            if len(el_text) > 40:
                el_clean = " ".join(el_text.split())
                text_blocks.append(el_clean)
                word_count += len(el_clean.split())
                if word_count >= 250 or len(text_blocks) >= 8:
                    break
        if len(text_blocks) >= 2 or word_count >= 150:
            break
            
    return " ".join(text_blocks), len(text_blocks)


def _extract_with_text_density(html: str) -> tuple[str, int]:
    """Helper method doing aggressive cleaning and selecting text based on line density."""
    soup = BeautifulSoup(html, "html.parser")
    for element in soup(["script", "style", "nav", "footer", "header", "aside", "form", "button"]):
        element.decompose()
        
    # Get raw text with cleaned lines
    raw_lines = [line.strip() for line in soup.get_text().split("\n") if line.strip()]
    
    # Filter out navigation links, copyright notes, and boilerplate
    filtered_lines = []
    nav_boilerplate_keywords = [
        "login", "sign in", "sign up", "subscribe", "terms of", "privacy policy",
        "all rights reserved", "copyright", "home", "search", "menu", "share on",
        "facebook", "twitter", "linkedin", "contact us", "about us", "newsletter"
    ]
    
    word_count = 0
    for line in raw_lines:
        line_lower = line.lower()
        if len(line) < 35:
            continue
        if any(kw in line_lower for kw in nav_boilerplate_keywords):
            continue
        # Check if line seems to be a code block
        if "{" in line or "}" in line or "const " in line or "import " in line:
            continue
        clean_line = " ".join(line.split())
        filtered_lines.append(clean_line)
        word_count += len(clean_line.split())
        if word_count >= 250 or len(filtered_lines) >= 8:
            break
            
    return " ".join(filtered_lines), len(filtered_lines)
