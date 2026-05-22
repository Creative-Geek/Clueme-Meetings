"""AI client initialization and management."""

import logging
import google.genai as genai

logging.getLogger("google.genai").setLevel(logging.ERROR)

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    """Get or create the genai client singleton."""
    global _client
    if _client is None:
        _client = genai.Client()
    return _client


def reconfigure_client(api_key: str = "") -> None:
    """Recreate the genai client (e.g. after API key change)."""
    global _client
    # Explicitly close the old client's transport to avoid RecursionError
    # when GC finalizes it while httpx connections are still open.
    old = _client
    _client = None
    if old is not None:
        try:
            # genai.Client wraps an httpx client; close it explicitly
            if hasattr(old, "_api_client") and hasattr(
                old._api_client, "_httpx_client"
            ):
                old._api_client._httpx_client.close()  # pyrefly: ignore
        except Exception:
            pass
    if api_key:
        _client = genai.Client(api_key=api_key)
    else:
        _client = genai.Client()
