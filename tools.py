"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
    compare_price(item)                              → dict
"""

import json
import math
import os
import re
import statistics

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    listings = load_listings()
    keywords = re.findall(r"\b\w+\b", description.lower())

    if not keywords:
        return []

    requested_size = size.strip().lower() if size is not None else None
    scored_listings = []

    for listing in listings:
        if max_price is not None and listing["price"] > max_price:
            continue

        listing_size = listing["size"].lower()
        if requested_size is not None and requested_size not in listing_size:
            continue

        searchable_text = " ".join(
            [
                listing["title"],
                listing["description"],
                listing["category"],
                *listing["style_tags"],
            ]
        ).lower()

        score = sum(
            len(re.findall(rf"\b{re.escape(keyword)}\b", searchable_text))
            for keyword in keywords
        )
        if score > 0:
            scored_listings.append((score, listing))

    scored_listings.sort(key=lambda result: result[0], reverse=True)
    return [listing for _, listing in scored_listings]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    item = new_item if isinstance(new_item, dict) else {}
    wardrobe_items = wardrobe.get("items", []) if isinstance(wardrobe, dict) else []
    if not isinstance(wardrobe_items, list):
        wardrobe_items = []

    title = item.get("title") or "this item"
    category = item.get("category") or "item"
    colors = item.get("colors") or ["neutral"]
    style_tags = item.get("style_tags") or ["versatile"]

    pairing_by_category = {
        "tops": "relaxed jeans or trousers, neutral shoes, and a simple accessory",
        "bottoms": "a fitted or simple top, a light layer, and neutral shoes",
        "outerwear": "a basic top, straight-leg bottoms, and simple shoes",
        "shoes": "simple bottoms, a coordinated top, and one matching accessory",
        "accessories": "a simple top, relaxed bottoms, and shoes in a matching tone",
    }
    general_pairing = pairing_by_category.get(
        str(category).lower(),
        "simple neutral basics and one coordinating accessory",
    )
    fallback = (
        f"Style {title} with {general_pairing}. "
        f"Its {', '.join(map(str, colors))} colors and "
        f"{', '.join(map(str, style_tags))} style will keep the outfit coordinated."
    )

    if wardrobe_items:
        wardrobe_instruction = (
            "Suggest one or two complete outfits using only pieces named in the "
            "wardrobe below. Do not invent clothing the user owns. If the wardrobe "
            "is too limited for a complete outfit, use the available pieces and "
            "clearly recommend the missing item categories."
        )
    else:
        wardrobe_instruction = (
            "The user's wardrobe is empty. Give one or two general outfit ideas "
            "using item categories, colors, and styles. Do not claim the user owns "
            "any of the suggested pieces."
        )

    prompt = (
        f"{wardrobe_instruction}\n\n"
        f"New item:\n{json.dumps(item, indent=2)}\n\n"
        f"Wardrobe items:\n{json.dumps(wardrobe_items, indent=2)}\n\n"
        "Identify the new item in each outfit, name any wardrobe pieces exactly as "
        "provided, and briefly explain the color or style coordination. Return only "
        "the outfit suggestion in a concise, natural tone."
    )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are FitFindr, a practical personal stylist who creates "
                        "specific outfits without inventing wardrobe items."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.6,
            max_tokens=400,
        )
        suggestion = response.choices[0].message.content
        if suggestion and suggestion.strip():
            return suggestion.strip()
    except Exception:
        pass

    return fallback


# Tool 4: compare_price

def compare_price(item: dict) -> dict:
    """
    Compare an item's price with similar listings in the dataset.

    Similar listings share the same category and at least one style tag.
    Brand and condition are used as extra similarity signals. If fewer than
    two close matches exist, all other listings in the category are used.

    Returns:
        A dictionary with item_price, comparable_count, average_price,
        median_price, price_difference, verdict, and explanation.
        Invalid input or no usable comparables returns an "unknown" verdict.
    """
    unknown_result = {
        "item_price": 0.0,
        "comparable_count": 0,
        "average_price": 0.0,
        "median_price": 0.0,
        "price_difference": 0.0,
        "verdict": "unknown",
        "explanation": (
            "I can't compare this price, but I can still help style the item."
        ),
    }

    if not isinstance(item, dict):
        return unknown_result

    item_price = item.get("price")
    if (
        isinstance(item_price, bool)
        or not isinstance(item_price, (int, float))
        or not math.isfinite(item_price)
        or item_price < 0
    ):
        return unknown_result

    item_price = float(item_price)
    unknown_result["item_price"] = item_price

    category = item.get("category")
    if not isinstance(category, str) or not category.strip():
        return unknown_result

    item_id = item.get("id")
    item_tags = {
        str(tag).strip().lower()
        for tag in (item.get("style_tags") or [])
        if str(tag).strip()
    }
    item_brand = item.get("brand")
    item_condition = item.get("condition")

    try:
        listings = load_listings()
    except Exception:
        return unknown_result

    same_category = []
    close_matches = []

    for listing in listings:
        if not isinstance(listing, dict):
            continue
        if item_id is not None and listing.get("id") == item_id:
            continue
        if str(listing.get("category", "")).lower() != category.lower():
            continue

        price = listing.get("price")
        if (
            isinstance(price, bool)
            or not isinstance(price, (int, float))
            or not math.isfinite(price)
            or price < 0
        ):
            continue

        same_category.append(listing)
        listing_tags = {
            str(tag).strip().lower()
            for tag in (listing.get("style_tags") or [])
            if str(tag).strip()
        }
        if item_tags.intersection(listing_tags):
            close_matches.append(listing)

    used_broad_fallback = len(close_matches) < 2
    comparables = same_category if used_broad_fallback else close_matches
    if not comparables:
        return unknown_result

    def similarity_score(listing: dict) -> tuple[int, int]:
        brand_match = int(
            item_brand is not None
            and listing.get("brand") is not None
            and str(listing["brand"]).lower() == str(item_brand).lower()
        )
        condition_match = int(
            item_condition is not None
            and str(listing.get("condition", "")).lower()
            == str(item_condition).lower()
        )
        return brand_match, condition_match

    comparables.sort(key=similarity_score, reverse=True)
    prices = [float(listing["price"]) for listing in comparables]
    average_price = round(statistics.fmean(prices), 2)
    median_price = round(statistics.median(prices), 2)
    price_difference = round(item_price - median_price, 2)

    if median_price == 0:
        verdict = "fair" if item_price == 0 else "overpriced"
    elif item_price <= median_price * 0.9:
        verdict = "good deal"
    elif item_price <= median_price * 1.1:
        verdict = "fair"
    else:
        verdict = "overpriced"

    comparison_type = (
        "broader same-category listings"
        if used_broad_fallback
        else "similar listings"
    )
    if price_difference == 0:
        comparison_text = f"equal to the ${median_price:.2f} median"
    else:
        difference_position = "below" if price_difference < 0 else "above"
        comparison_text = (
            f"${abs(price_difference):.2f} {difference_position} "
            f"the ${median_price:.2f} median"
        )
    explanation = (
        f"The ${item_price:.2f} price is {comparison_text} of "
        f"{len(comparables)} {comparison_type}, so it is {verdict}."
    )

    return {
        "item_price": item_price,
        "comparable_count": len(comparables),
        "average_price": average_price,
        "median_price": median_price,
        "price_difference": price_difference,
        "verdict": verdict,
        "explanation": explanation,
    }


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    if not isinstance(outfit, str) or not outfit.strip():
        return "I couldn't create the fit card because the outfit suggestion is missing."

    if not isinstance(new_item, dict):
        return "I couldn't create the fit card because the listing details are missing."

    required_fields = ("title", "price", "platform")
    missing_fields = [
        field
        for field in required_fields
        if field not in new_item
        or new_item[field] is None
        or (
            isinstance(new_item[field], str)
            and not new_item[field].strip()
        )
    ]
    if missing_fields:
        return (
            "I couldn't create the fit card because the listing is missing: "
            f"{', '.join(missing_fields)}."
        )

    title = str(new_item["title"]).strip()
    price = new_item["price"]
    platform = str(new_item["platform"]).strip()
    if (
        isinstance(price, bool)
        or not isinstance(price, (int, float))
        or not math.isfinite(price)
        or price < 0
    ):
        return "I couldn't create the fit card because the listing price is invalid."

    style_tags = new_item.get("style_tags") or []
    colors = new_item.get("colors") or []
    clean_outfit = outfit.strip()
    formatted_price = f"${price:g}"

    prompt = (
        "Write a casual outfit-of-the-day caption using the information below.\n\n"
        f"Item name: {title}\n"
        f"Price: {formatted_price}\n"
        f"Platform: {platform}\n"
        f"Colors: {', '.join(map(str, colors)) or 'not provided'}\n"
        f"Style tags: {', '.join(map(str, style_tags)) or 'not provided'}\n"
        f"Outfit: {clean_outfit}\n\n"
        "Requirements:\n"
        "- Write two to four sentences.\n"
        "- Sound casual and authentic, not like a product listing.\n"
        "- Mention the exact item name, price, and platform once each.\n"
        "- Describe the outfit's specific vibe or color coordination.\n"
        "- Return only the caption."
    )

    outfit_sentence = clean_outfit
    if clean_outfit[-1] not in ".!?":
        outfit_sentence += "."
    fallback = (
        f"Found the {title} for {formatted_price} on {platform}. "
        f"{outfit_sentence} The result is an easy, put-together look."
    )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You write short, natural social media captions for "
                        "secondhand outfit finds."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.9,
            max_tokens=220,
        )
        caption = response.choices[0].message.content
        if caption and caption.strip():
            return caption.strip()
    except Exception:
        pass

    return fallback
