"""Agent tools — web search with model-aware routing.

Search strategy:
  - Gemma / Gemini 2.x  → built-in google_search (free tier, no config needed)
  - Gemini 3.x          → Tavily API via manual function calling (optional key)
  - Gemini 3.x, no key  → search disabled
"""

import httpx
from google.genai import types


# ── Tool declarations ────────────────────────────────────────────────────────

# Built-in Google search — handled server-side by compatible models
BUILTIN_SEARCH_TOOL = types.Tool(google_search=types.GoogleSearch())

# Manual Tavily search declaration — for models without built-in search access
_WEB_SEARCH_DECLARATION = types.FunctionDeclaration(
    name="web_search",
    description=(
        "Search the web for current information. Use when the user asks about "
        "something not covered in the meeting transcript, or when you need "
        "up-to-date facts, definitions, or context to give a better answer."
    ),
    parameters_json_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query to look up.",
            }
        },
        "required": ["query"],
    },
)

TAVILY_TOOL = types.Tool(function_declarations=[_WEB_SEARCH_DECLARATION])


# ── Model routing ────────────────────────────────────────────────────────────

def _model_supports_builtin_search(model_name: str) -> bool:
    """Return True if the model supports Google's built-in search grounding.

    Gemma models and Gemini 2.x have free-tier grounding quota.
    Gemini 3.x has 0 quota on the free tier.
    """
    if model_name.startswith("gemma"):
        return True
    if model_name.startswith("gemini-2"):
        return True
    return False


def get_tools_for_model(model_name: str, tavily_api_key: str = "") -> list[types.Tool]:
    """Return the appropriate tools list for the given model and config.

    Args:
        model_name: Active model identifier (e.g. 'gemma-4-31b-it').
        tavily_api_key: Optional Tavily API key from user settings.

    Returns:
        List of Tool objects to pass to GenerateContentConfig.
        Empty list means no tools / search disabled.
    """
    if _model_supports_builtin_search(model_name):
        return [BUILTIN_SEARCH_TOOL]
    # Gemini 3.x or unknown — use Tavily if key present
    if tavily_api_key:
        return [TAVILY_TOOL]
    return []


# ── Tool execution ───────────────────────────────────────────────────────────

async def execute_tool(name: str, args: dict, tavily_api_key: str = "") -> dict:
    """Execute a tool call and return a result dict for the model.

    Args:
        name: Tool function name from the model's function_call.
        args: Arguments dict from the model's function_call.
        tavily_api_key: Tavily API key for web_search tool.

    Returns:
        Result dict that will be sent back as a function_response.
    """
    if name == "web_search":
        return await _tavily_search(args.get("query", ""), tavily_api_key)
    return {"error": f"Unknown tool: {name}"}


async def _tavily_search(query: str, api_key: str) -> dict:
    """Call the Tavily Search API and return structured results.

    Returns a dict with:
        - answer: Tavily's pre-synthesized answer paragraph (most useful)
        - results: list of {title, url, content} for the top results
        - error: error message if the request failed
    """
    if not api_key:
        return {"error": "No Tavily API key configured. Search unavailable."}
    if not query.strip():
        return {"error": "Empty search query."}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": api_key,
                    "query": query,
                    "search_depth": "basic",
                    "include_answer": True,
                    "max_results": 5,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        return {
            "answer": data.get("answer", ""),
            "results": [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": r.get("content", ""),
                }
                for r in data.get("results", [])[:5]
            ],
        }

    except httpx.TimeoutException:
        return {"error": "Search timed out. Try again."}
    except httpx.HTTPStatusError as e:
        return {"error": f"Search API error: {e.response.status_code}"}
    except Exception as e:
        return {"error": f"Search failed: {e}"}
