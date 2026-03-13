"""Fun jokes service — JokeAPI (free, no API key)."""
import httpx

from ..utils.logger import logger


def get_random_joke() -> str:
    """Fetch a random joke from JokeAPI (safe mode)."""
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                "https://v2.jokeapi.dev/joke/Any",
                params={"safe-mode": "", "type": "twopart,single"},
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("error"):
                return "Couldn't fetch a joke. Try again!"

            if data.get("type") == "twopart":
                setup = data.get("setup", "")
                delivery = data.get("delivery", "")
                return f"😂 *Joke*\n\n{setup}\n\n_{delivery}_"
            else:
                joke = data.get("joke", "")
                return f"😂 *Joke*\n\n{joke}"

    except Exception as e:
        logger.error(f"JokeAPI error: {e}")
        return "Joke service is down. Try again later!"
