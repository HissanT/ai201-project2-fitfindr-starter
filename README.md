# FitFindr

FitFindr is a Gradio shopping assistant that searches a mock secondhand
marketplace, compares the selected item's price with similar listings, suggests
an outfit using the user's wardrobe, and creates a short shareable fit card.

## Setup and Run

```bash
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```text
GROQ_API_KEY=your_key_here
```

Run the application:

```bash
python app.py
```

Run the test suite:

```bash
python -m pytest -q
```

The current suite contains 50 tests covering the tools, planning loop, query
handler, state transitions, and fallback behavior.

## Tool Inventory

### `search_listings`

- **Signature:** `search_listings(description: str, size: str | None = None, max_price: float | None = None) -> list[dict]`
- **Inputs:**
  - `description` (`str`): Search keywords such as `"vintage graphic tee"`.
  - `size` (`str | None`): Optional case-insensitive size filter.
  - `max_price` (`float | None`): Optional inclusive price ceiling.
- **Output:** A `list[dict]` of matching listing records, sorted by descending
  whole-word keyword score. It returns an empty list when nothing matches.
- **Purpose:** Narrow the local listings dataset by price and size, then rank
  the remaining items by relevance to the requested description.

### `compare_price`

- **Signature:** `compare_price(item: dict) -> dict`
- **Input:** `item` (`dict`): The selected listing, including its ID, category,
  style tags, brand, condition, and numeric price.
- **Output:** A `dict` containing `item_price`, `comparable_count`,
  `average_price`, `median_price`, `price_difference`, `verdict`, and
  `explanation`. The verdict is `"good deal"`, `"fair"`, `"overpriced"`, or
  `"unknown"`.
- **Purpose:** Compare the selected price with listings in the same category,
  preferring records that share at least one style tag.

### `suggest_outfit`

- **Signature:** `suggest_outfit(new_item: dict, wardrobe: dict) -> str`
- **Inputs:**
  - `new_item` (`dict`): The selected marketplace listing.
  - `wardrobe` (`dict`): A wardrobe object whose `items` field is a list of
    clothing records.
- **Output:** A non-empty `str` containing specific wardrobe-based outfit ideas
  or general styling advice when the wardrobe is empty.
- **Purpose:** Use the selected item and available wardrobe pieces to create one
  or two coordinated outfits.

### `create_fit_card`

- **Signature:** `create_fit_card(outfit: str, new_item: dict) -> str`
- **Inputs:**
  - `outfit` (`str`): The suggestion produced by `suggest_outfit`.
  - `new_item` (`dict`): The selected listing.
- **Output:** A `str` containing a two-to-four-sentence social caption, a
  deterministic fallback caption, or a descriptive validation error.
- **Purpose:** Turn the selected listing and styling result into a concise,
  shareable outfit-of-the-day caption.

## Planning Loop

The agent uses a deterministic planning loop because each successful step
depends on the output of the previous one:

1. `run_agent()` creates a fresh session and parses the query with regular
   expressions. It extracts `size` and `max_price`, removes those filter phrases
   and conversational filler, and stores the remaining text as `description`.
2. It calls `search_listings(**session["parsed"])`.
3. If search returns an empty list, the loop sets `session["error"]` to a
   message that names the attempted filters and suggests which constraints to
   relax. It then returns immediately. Price comparison, outfit generation, and
   fit-card generation are not called because they require a selected item.
4. If results exist, the first result becomes `session["selected_item"]`
   because the search tool has already ranked the list by relevance.
5. The agent calls `compare_price(selected_item)`. An `"unknown"` verdict is
   non-fatal: the explanation is stored and the loop continues because styling
   does not depend on a successful price comparison.
6. It calls `suggest_outfit(selected_item, wardrobe)`. If the tool returns
   blank or non-string output, the agent creates a rule-based outfit suggestion
   from the item's category, colors, and style tags.
7. It calls `create_fit_card(outfit_suggestion, selected_item)`. If that tool
   returns blank or non-string output, the agent builds a basic caption from the
   title, price, platform, and outfit suggestion.
8. The completed session is returned. `handle_query()` maps an error to the
   first Gradio panel, or maps the listing, outfit, and fit card to the three
   success panels.

This means the agent does not blindly run every tool. It stops when no item can
be selected, tolerates an unavailable price judgment, and substitutes usable
content when either generative step fails.

## State Management

Each request gets a new session dictionary, which is the single source of truth
for that interaction. It stores:

- `query`: original user text
- `parsed`: `description`, `size`, and `max_price`
- `search_results`: ranked listing dictionaries
- `selected_item`: the first search result
- `price_comparison`: result from `compare_price`
- `wardrobe`: the selected example or empty wardrobe
- `outfit_suggestion`: generated or fallback styling text
- `fit_card`: generated or fallback caption
- `error`: fatal early-termination message, otherwise `None`

Results are written before the next tool is called. The parsed dictionary is
expanded into `search_listings`; `selected_item` is passed to both
`compare_price` and `suggest_outfit`; then `outfit_suggestion` and
`selected_item` are passed to `create_fit_card`. State is local to one call to
`run_agent()`, so separate Gradio requests do not share mutable session data.

## Error Handling and Tested Examples

### `search_listings`

No match is represented by `[]`, not an exception. The planning loop treats
this as fatal because all later tools need an item. In testing,
`"designer ballgown size XXS under $5"` returned no results; the agent stopped
before calling downstream tools and suggested a broader description, a higher
budget, or removing the size filter.

### `compare_price`

If fewer than two style-overlap records exist, the tool broadens the comparison
to valid listings in the same category. Invalid prices, data-loading failures,
or no comparables return an `"unknown"` result rather than raising. Tests
simulated `load_listings()` raising `OSError("listings unavailable")`; the
result remained `"unknown"` and the agent still produced the outfit and fit
card.

### `suggest_outfit`

An empty or invalid wardrobe changes the prompt to request general advice and
prevents the model from claiming the user owns named pieces. Groq exceptions
and blank model responses are caught and replaced by a rule-based suggestion.
Tests forced `RuntimeError("Groq is unavailable")`; the returned text was still
non-empty and included the selected item's title and style.

### `create_fit_card`

The tool validates the outfit plus the listing's `title`, `price`, and
`platform`. Missing or invalid input returns a descriptive string. Groq
exceptions and blank responses produce a deterministic caption. Tests supplied
a negative price and received a price-validation message; another test forced
the Groq client to fail and still received a caption beginning with the item
name, `$24`, and `Depop`.

### Gradio Handler

`handle_query()` rejects empty or whitespace-only input before calling the
agent. Its test confirms that `"   "` returns an instruction to enter a
description and leaves the outfit and fit-card panels empty.

## Spec Reflection

The spec helped by making the data dependencies explicit in the planning-loop
and architecture sections. In particular, it clarified that an empty search
must terminate the run before `suggest_outfit`, while an unknown price
comparison should not. That distinction directly shaped the conditional logic
and its tests.

The implementation diverged from the idea of a general model-driven planner.
The agent uses a fixed, deterministic sequence with explicit branches because
the four tools have a stable dependency order and only one valid next step at
each stage. This is easier to test, avoids unnecessary model calls, and prevents
the planner from attempting outfit generation without a selected listing. The
LLM is reserved for the two tasks that benefit from natural-language
generation: outfit suggestions and fit cards.

## AI Usage

### Tool implementation and validation

I gave Codex the four **Tools** sections, the related **Error Handling** rows,
`data/listings.json`, `data/wardrobe_schema.json`, and the tool nodes and edges
from the Mermaid **Architecture** diagram. I directed it to implement each
function with tests for normal results, no results, invalid inputs, empty
wardrobes, unavailable comparables, and Groq failures.

It produced the keyword search, price-comparison logic, Groq prompts, fallback
text, and unit tests. Before using the result, I kept search and price
comparison deterministic instead of asking the model to perform those tasks,
added strict numeric validation for prices, and ensured model exceptions or
blank responses return usable fallback text.

### Planning loop and query parsing

I gave Codex the **Planning Loop**, **State Management**, and **Error Handling**
sections, all four tool signatures, `agent.py`'s numbered TODO, and the full
Mermaid diagram. I directed it to implement the session transitions, preserve
the early-return branch, continue after an unknown price verdict, and test the
exact tool-call order.

It produced the session-based orchestration, regex query parser, fallback
checks, and planning-loop tests. I then revised the parser to remove additional
conversational phrases such as `"I want to wear"` and currency words such as
`"30 dollars"` or `"30 bucks"`, because leaving those tokens in the description
reduced search relevance. I also retained explicit assertions that no
downstream tool runs after an empty search.
