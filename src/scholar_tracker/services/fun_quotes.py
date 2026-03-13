"""Fun quotes service — ZenQuotes.io (free, no API key)."""
import httpx

from ..utils.logger import logger


def get_random_quote() -> str:
    """Fetch a random inspirational quote from ZenQuotes."""
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get("https://zenquotes.io/api/random")
            resp.raise_for_status()
            data = resp.json()
            if data and isinstance(data, list):
                q = data[0]
                text = q.get("q", "")
                author = q.get("a", "Unknown")
                return f'💬 *Quote*\n\n"{text}"\n— {author}'
        return "Couldn't fetch a quote. Try again!"
    except Exception as e:
        logger.error(f"ZenQuotes error: {e}")
        return "Quote service is down. Try again later!"
