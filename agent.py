"""
agent.py

The FitFindr planning loop. Orchestrates the four tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import re

from tools import compare_price, create_fit_card, search_listings, suggest_outfit


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "price_comparison": None,    # dict returned by compare_price
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
    }


def _parse_query(query: str) -> dict:
    """Extract search text, an optional size, and an optional maximum price."""
    clean_query = query.strip() if isinstance(query, str) else ""

    size_match = re.search(
        r"\b(?:in\s+)?size\s+([a-z0-9]+(?:/[a-z0-9]+)?)\b",
        clean_query,
        flags=re.IGNORECASE,
    )
    size = size_match.group(1) if size_match else None

    price_match = re.search(
        r"\b(?:under|below|up\s+to|less\s+than|max(?:imum)?"
        r"(?:\s+price)?(?:\s+of)?)\s*\$?\s*(\d+(?:\.\d{1,2})?)"
        r"(?:\s*(?:dollars?|bucks?))?\b",
        clean_query,
        flags=re.IGNORECASE,
    )
    if price_match is None:
        price_match = re.search(
            r"\$(\d+(?:\.\d{1,2})?)"
            r"(?:\s*(?:dollars?|bucks?))?"
            r"\s*(?:or\s+less|max(?:imum)?)?\b",
            clean_query,
            flags=re.IGNORECASE,
        )
    max_price = float(price_match.group(1)) if price_match else None

    description = clean_query
    if size_match:
        description = description.replace(size_match.group(0), " ")
    if price_match:
        description = description.replace(price_match.group(0), " ")

    description = re.sub(
        r"^\s*(?:"
        r"(?:i(?:'m|\s+am)?\s+)?(?:looking|searching)\s+for"
        r"|i\s+(?:want|need)(?:\s+to\s+wear)?"
        r"|i(?:'d|\s+would)\s+like(?:\s+to\s+wear)?"
        r")\s+(?:(?:a|an|the)\s+)?",
        "",
        description,
        flags=re.IGNORECASE,
    )
    description = re.sub(
        r"^\s*(?:find|show\s+me)\s+",
        "",
        description,
        flags=re.IGNORECASE,
    )
    description = re.sub(
        r"^\s*to\s+(?:wear|buy|find)\s+",
        "",
        description,
        flags=re.IGNORECASE,
    )
    description = re.sub(r"\s+\bfor\b\s*$", "", description, flags=re.IGNORECASE)
    description = re.sub(r"\s+", " ", description).strip(" ,.-")

    return {
        "description": description,
        "size": size,
        "max_price": max_price,
    }


def _no_results_message(parsed: dict) -> str:
    description = parsed["description"] or "that item"
    filters = []
    if parsed["size"] is not None:
        filters.append(f"in size {parsed['size']}")
    if parsed["max_price"] is not None:
        filters.append(f"under ${parsed['max_price']:g}")

    requested_item = " ".join([description, *filters])
    suggestions = ["a broader description"]
    if parsed["max_price"] is not None:
        suggestions.append("a higher budget")
    if parsed["size"] is not None:
        suggestions.append("remove the size filter")

    if len(suggestions) == 1:
        suggestion_text = suggestions[0]
    else:
        suggestion_text = ", ".join(suggestions[:-1]) + f", or {suggestions[-1]}"
    return f"I couldn't find {requested_item}. Try {suggestion_text}."


def _fallback_outfit(item: dict) -> str:
    title = item.get("title") or "this item"
    colors = ", ".join(map(str, item.get("colors") or ["neutral"]))
    styles = ", ".join(map(str, item.get("style_tags") or ["versatile"]))
    return (
        f"Style {title} with simple neutral basics and coordinating shoes. "
        f"The {colors} colors support an easy {styles} look."
    )


def _fallback_fit_card(item: dict, outfit: str) -> str:
    title = item.get("title") or "this thrifted find"
    price = item.get("price")
    price_text = (
        f"${price:g}"
        if isinstance(price, (int, float)) and not isinstance(price, bool)
        else "its listed price"
    )
    platform = item.get("platform") or "the resale platform"
    return f"Found the {title} for {price_text} on {platform}. {outfit}"


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.

    Implementation steps from the planning loop in planning.md:

        Step 1: Initialize the session with _new_session().

        Step 2: Parse the user's query to extract a description, size, and
                max_price. You can use regex, string splitting, or ask the LLM
                to parse it — document your choice in planning.md.
                Store the result in session["parsed"].

        Step 3: Call search_listings() with the parsed parameters.
                Store results in session["search_results"].
                If no results: set session["error"] to a helpful message and
                return the session early. Do NOT proceed to suggest_outfit
                with empty input.

        Step 4: Select the item to use (e.g., the top result).
                Store it in session["selected_item"].

        Step 5: Call compare_price() with the selected item and store the result.
                An unknown verdict is non-fatal, so continue to outfit creation.

        Step 6: Call suggest_outfit() with the selected item and wardrobe.
                Store the result in session["outfit_suggestion"].

        Step 7: Call create_fit_card() with the outfit suggestion and selected item.
                Store the result in session["fit_card"].

        Step 8: Return the session.

    Before writing code, complete the Planning Loop and State Management sections
    of planning.md — your implementation should match what you described there.
    """
    session = _new_session(query, wardrobe)
    session["parsed"] = _parse_query(query)

    session["search_results"] = search_listings(**session["parsed"])
    if not session["search_results"]:
        session["error"] = _no_results_message(session["parsed"])
        return session

    session["selected_item"] = session["search_results"][0]
    session["price_comparison"] = compare_price(session["selected_item"])

    outfit = suggest_outfit(session["selected_item"], session["wardrobe"])
    if not isinstance(outfit, str) or not outfit.strip():
        outfit = _fallback_outfit(session["selected_item"])
    session["outfit_suggestion"] = outfit.strip()

    fit_card = create_fit_card(
        session["outfit_suggestion"],
        session["selected_item"],
    )
    if not isinstance(fit_card, str) or not fit_card.strip():
        fit_card = _fallback_fit_card(
            session["selected_item"],
            session["outfit_suggestion"],
        )
    session["fit_card"] = fit_card.strip()

    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
