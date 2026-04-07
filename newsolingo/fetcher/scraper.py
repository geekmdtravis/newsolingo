"""Article fetching and text extraction using trafilatura."""

from __future__ import annotations

import logging
import random
import re
from urllib.parse import urljoin, urlparse

import httpx
import trafilatura
from bs4 import BeautifulSoup

from newsolingo.fetcher.sources import Source

logger = logging.getLogger(__name__)

# Minimum article length in characters to be considered useful
MIN_ARTICLE_LENGTH = 200

# Patterns that strongly suggest a URL IS an article
ARTICLE_PATH_PATTERNS = [
    r"/\d{4}/",  # Year in path like /2024/
    r"/\d{4}-",  # Date prefix
    r"/artigo",  # Portuguese for article
    r"/post",
    r"/blog/.+",  # Blog with a subpath
    r"/article",
    r"/news/.+",
    r"/noticias?/.+",
    r"/כתבה/",  # Hebrew for article
    r"/מאמר/",  # Hebrew for article
    r"\.html$",  # .html extension is almost always an article
    r"\.htm$",
    r"/\d+-",  # ID prefix patterns common in news sites
]

# Patterns that suggest a URL is NOT an article
NON_ARTICLE_PATTERNS = [
    r"/tag/",
    r"/tags/",
    r"/category/",
    r"/categorias?/",
    r"/author/",
    r"/autor/",
    r"/page/\d+",
    r"/search",
    r"/login",
    r"/signup",
    r"/register",
    r"#",
    r"/feed$",
    r"/rss$",
    r"\.xml$",
    r"\.pdf$",
    r"\.jpg$",
    r"\.png$",
    r"\.gif$",
    r"\.svg$",
    r"\.css$",
    r"\.js$",
    r"/wp-content/uploads/",
    r"/type/",  # Category-like pages (e.g., diolinux.com.br/type/video)
    r"/contato$",
    r"/newsletter$",
    r"/anunci",  # Advertising pages
    r"/politica-de-privacidade",
    r"/ofertas$",
    r"/links$",
]

# Known category-only path segments (1 segment, no extension = likely a category page)
CATEGORY_SEGMENTS = {
    "aplicativos",
    "editorial",
    "noticias",
    "games",
    "design",
    "flatpak",
    "gnome",
    "kde",
    "open-source",
    "podcast",
    "diocast",
    "sistemas-operacionais",
    "ofertas",
    "newsletter",
    "links",
    "contato",
    "rss",
    "feed",
    "videos",
}


def _is_likely_article_url(url: str, base_domain: str) -> bool:
    """Heuristic check if a URL is likely an article."""
    parsed = urlparse(url)

    # Must be on the same domain (or subdomain)
    base_clean = base_domain.replace("www.", "")
    if not parsed.netloc.endswith(base_clean):
        return False

    path = parsed.path

    # Skip the homepage
    if path in ("", "/"):
        return False

    # Skip non-article patterns
    for pattern in NON_ARTICLE_PATTERNS:
        if re.search(pattern, url, re.IGNORECASE):
            return False

    segments = [s for s in path.split("/") if s]

    # Single-segment paths are usually categories, not articles
    if len(segments) == 1:
        seg = segments[0].lower()
        # Unless it has an extension like .html
        if not re.search(r"\.\w{2,5}$", seg):
            return False

    # Check for strong article indicators
    for pattern in ARTICLE_PATH_PATTERNS:
        if re.search(pattern, path, re.IGNORECASE):
            return True

    # 2+ segments where the last segment looks like an article slug
    if len(segments) >= 2:
        last_seg = segments[-1]
        has_extension = bool(re.search(r"\.\w{2,5}$", last_seg))
        has_hyphens = "-" in last_seg
        is_long_slug = len(last_seg) > 15  # Article slugs tend to be longer

        # Article slugs typically have hyphens AND are relatively long, or have an extension
        if has_extension:
            return True
        if has_hyphens and is_long_slug:
            return True
        # Deep paths (3+ segments) with a hyphenated slug
        if len(segments) >= 3 and has_hyphens:
            return True

    return False


def discover_article_urls(source: Source, max_urls: int = 20) -> list[str]:
    """Discover article URLs from a source's homepage.

    Fetches the source URL and extracts links that look like articles.

    Args:
        source: The source to crawl.
        max_urls: Maximum number of article URLs to return.

    Returns:
        List of discovered article URLs.
    """
    logger.info("Discovering articles from %s (%s)", source.name, source.url)

    try:
        response = httpx.get(
            source.url,
            follow_redirects=True,
            timeout=30.0,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
            },
        )
        response.raise_for_status()
    except httpx.HTTPError as e:
        logger.error("Failed to fetch %s: %s", source.url, e)
        return []

    # Parse the HTML and extract links
    soup = BeautifulSoup(response.text, "html.parser")
    base_domain = urlparse(source.url).netloc

    article_urls: list[str] = []
    seen: set[str] = set()

    for link in soup.find_all("a", href=True):
        href = link["href"]
        # Resolve relative URLs
        full_url = urljoin(source.url, href)
        # Normalize - remove trailing slash and fragment
        full_url = full_url.rstrip("/").split("#")[0]

        if full_url in seen:
            continue
        seen.add(full_url)

        if _is_likely_article_url(full_url, base_domain):
            article_urls.append(full_url)
            if len(article_urls) >= max_urls:
                break

    # Sort: prioritize URLs with file extensions (.html) and longer slugs
    def _article_score(url: str) -> int:
        """Higher score = more likely to be an article."""
        score = 0
        path = urlparse(url).path
        if re.search(r"\.\w{2,5}$", path):
            score += 10  # Has file extension
        slug = path.rstrip("/").split("/")[-1]
        score += min(len(slug) // 5, 5)  # Longer slugs score higher
        if "-" in slug:
            score += 3  # Hyphenated slugs are more likely articles
        return score

    article_urls.sort(key=_article_score, reverse=True)

    logger.info(
        "Found %d potential article URLs from %s", len(article_urls), source.name
    )
    return article_urls


_HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,pt-BR;q=0.8,he;q=0.7",
}


def extract_article_text(url: str) -> str | None:
    """Fetch a URL and extract the main article text.

    Uses httpx for fetching (with a browser-like User-Agent to avoid blocks)
    and trafilatura for text extraction.

    Args:
        url: The article URL to fetch and extract.

    Returns:
        Extracted article text, or None if extraction failed.
    """
    logger.info("Extracting article from %s", url)

    try:
        # Use httpx with a real browser user-agent instead of trafilatura's fetch_url
        # because many sites block trafilatura's default user-agent
        response = httpx.get(
            url,
            follow_redirects=True,
            timeout=30.0,
            headers=_HTTP_HEADERS,
        )
        response.raise_for_status()

        text = trafilatura.extract(
            response.text,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
        )

        if text and len(text) >= MIN_ARTICLE_LENGTH:
            logger.info("Extracted %d characters from %s", len(text), url)
            return text
        else:
            logger.warning(
                "Extracted text too short (%d chars) from %s",
                len(text) if text else 0,
                url,
            )
            return None

    except httpx.HTTPError as e:
        logger.error("HTTP error fetching %s: %s", url, e)
        return None
    except Exception as e:
        logger.error("Error extracting article from %s: %s", url, e)
        return None


def fetch_random_article(source: Source) -> tuple[str, str] | None:
    """Discover articles from a source and fetch a random one.

    Args:
        source: The source to crawl.

    Returns:
        Tuple of (article_url, article_text) or None if no article could be fetched.
    """
    urls = discover_article_urls(source)
    if not urls:
        logger.warning("No article URLs found for %s", source.name)
        return None

    # Shuffle and try until we find one that works
    random.shuffle(urls)

    for url in urls[:5]:  # Try up to 5 URLs
        text = extract_article_text(url)
        if text:
            return url, text

    logger.warning("Could not extract any article from %s", source.name)
    return None
