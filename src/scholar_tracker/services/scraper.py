import random
import time
from typing import Any, Dict, List

from scholarly import scholarly

from ..utils.logger import logger

# Rate limiting: minimum seconds between Scholar requests
REQUEST_DELAY_MIN = 2.0
REQUEST_DELAY_MAX = 5.0
MAX_RETRIES = 3


def _backoff_sleep(attempt: int = 0) -> None:
    """Sleep with jitter to avoid Google Scholar rate limits."""
    base_delay = random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX)
    delay = base_delay * (2 ** attempt)
    logger.debug(f"Rate-limit sleep: {delay:.1f}s (attempt {attempt})")
    time.sleep(delay)


class ScholarScraper:
    def __init__(self, use_proxy: bool = False):
        if use_proxy:
            self._setup_proxy()

    def _setup_proxy(self) -> None:
        """Configure scholarly to use free proxies."""
        try:
            from scholarly import ProxyGenerator
            pg = ProxyGenerator()
            pg.FreeProxies()
            scholarly.use_proxy(pg)
            logger.info("Configured scholarly with FreeProxies")
        except Exception as e:
            logger.warning(f"Failed to set up proxy, using direct connection: {e}")

    def fetch_author(self, author_id: str) -> Dict[str, Any]:
        """Fetch author details including their publications."""
        logger.info(f"Fetching author profile for ID: {author_id}")
        for attempt in range(MAX_RETRIES):
            try:
                author = scholarly.search_author_id(author_id)
                scholarly.fill(author, sections=["publications", "counts"])
                return author
            except Exception as e:
                logger.warning(
                    f"Attempt {attempt + 1}/{MAX_RETRIES} failed for author {author_id}: {e}")
                if attempt < MAX_RETRIES - 1:
                    _backoff_sleep(attempt)
                else:
                    logger.error(f"All {MAX_RETRIES} attempts failed for author {author_id}")
                    raise

    def find_paper_by_title(self, query: str) -> Dict[str, Any]:
        """Search for a specific paper by its title query."""
        logger.info(f"Searching for paper query: '{query}'")
        for attempt in range(MAX_RETRIES):
            try:
                search_query = scholarly.search_pubs(query)
                pub = next(search_query)
                scholarly.fill(pub)
                return pub
            except StopIteration:
                logger.warning(f"No papers found for query: '{query}'")
                return {}
            except Exception as e:
                logger.warning(
                    f"Attempt {attempt + 1}/{MAX_RETRIES} failed for query '{query}': {e}")
                if attempt < MAX_RETRIES - 1:
                    _backoff_sleep(attempt)
                else:
                    logger.error(f"All {MAX_RETRIES} attempts failed for query '{query}'")
                    raise

    def get_citing_papers_for_pub(self, pub: Dict[str, Any], max_results: int = 3) -> List[Dict]:
        """Given a filled pub dict, fetch the top papers that cite it."""
        title = pub.get('bib', {}).get('title', 'Unknown')
        logger.info(f"Fetching top {max_results} citing papers for: {title}")
        results = []
        try:
            citing_query = scholarly.citedby(pub)
            for _ in range(max_results):
                try:
                    p = next(citing_query)
                    scholarly.fill(p)
                    results.append({
                        "title": p.get("bib", {}).get("title"),
                        "citations": p.get("num_citations", 0),
                        "url": p.get("pub_url", "")
                    })
                    _backoff_sleep()
                except StopIteration:
                    break
            results.sort(key=lambda x: x["citations"], reverse=True)
            return results
        except Exception as e:
            logger.error(f"Error fetching citing papers for '{title}': {e}")
            raise


scraper_client = ScholarScraper()
