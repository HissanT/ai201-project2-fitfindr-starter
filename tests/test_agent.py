import agent


ITEM = {
    "id": "lst_006",
    "title": "Graphic Tee - 2003 Tour Bootleg Style",
    "category": "tops",
    "style_tags": ["vintage", "streetwear"],
    "colors": ["black"],
    "price": 24,
    "platform": "Depop",
}


def test_parse_query_extracts_description_size_and_price():
    parsed = agent._parse_query(
        "looking for a vintage graphic tee size M under $30"
    )

    assert parsed == {
        "description": "vintage graphic tee",
        "size": "M",
        "max_price": 30.0,
    }


def test_parse_query_removes_conversational_filler_and_currency_words():
    parsed = agent._parse_query("I want an underwear for under 30 dollars")

    assert parsed == {
        "description": "underwear",
        "size": None,
        "max_price": 30.0,
    }


def test_parse_query_removes_wear_request_filler():
    parsed = agent._parse_query("I want to wear leaves for under 30 dollars")

    assert parsed == {
        "description": "leaves",
        "size": None,
        "max_price": 30.0,
    }


def test_run_agent_stores_results_and_calls_tools_in_order(monkeypatch):
    calls = []
    wardrobe = {"items": [{"name": "Baggy jeans"}]}

    def search_listings(**parsed):
        calls.append(("search", parsed))
        return [ITEM]

    def compare_price(item):
        calls.append(("compare", item))
        return {"verdict": "fair", "explanation": "Fair price."}

    def suggest_outfit(item, supplied_wardrobe):
        calls.append(("outfit", item, supplied_wardrobe))
        return "Wear it with Baggy jeans."

    def create_fit_card(outfit, item):
        calls.append(("card", outfit, item))
        return "A shareable fit card."

    monkeypatch.setattr(agent, "search_listings", search_listings)
    monkeypatch.setattr(agent, "compare_price", compare_price)
    monkeypatch.setattr(agent, "suggest_outfit", suggest_outfit)
    monkeypatch.setattr(agent, "create_fit_card", create_fit_card)

    session = agent.run_agent(
        "vintage graphic tee size M under $30",
        wardrobe,
    )

    assert [call[0] for call in calls] == ["search", "compare", "outfit", "card"]
    assert session["parsed"] == {
        "description": "vintage graphic tee",
        "size": "M",
        "max_price": 30.0,
    }
    assert session["search_results"] == [ITEM]
    assert session["selected_item"] == ITEM
    assert session["price_comparison"]["verdict"] == "fair"
    assert session["outfit_suggestion"] == "Wear it with Baggy jeans."
    assert session["fit_card"] == "A shareable fit card."
    assert session["error"] is None


def test_run_agent_stops_after_empty_search_results(monkeypatch):
    monkeypatch.setattr(agent, "search_listings", lambda **kwargs: [])

    def unexpected_call(*args, **kwargs):
        raise AssertionError("A downstream tool was called after an empty search")

    monkeypatch.setattr(agent, "compare_price", unexpected_call)
    monkeypatch.setattr(agent, "suggest_outfit", unexpected_call)
    monkeypatch.setattr(agent, "create_fit_card", unexpected_call)

    session = agent.run_agent(
        "designer ballgown size XXS under $5",
        {"items": []},
    )

    assert session["search_results"] == []
    assert session["selected_item"] is None
    assert session["price_comparison"] is None
    assert session["outfit_suggestion"] is None
    assert session["fit_card"] is None
    assert "couldn't find" in session["error"]
    assert "remove the size filter" in session["error"]


def test_run_agent_continues_after_unknown_price_comparison(monkeypatch):
    monkeypatch.setattr(agent, "search_listings", lambda **kwargs: [ITEM])
    monkeypatch.setattr(
        agent,
        "compare_price",
        lambda item: {
            "verdict": "unknown",
            "explanation": "I can still help style the item.",
        },
    )
    monkeypatch.setattr(
        agent,
        "suggest_outfit",
        lambda item, wardrobe: "Wear it with relaxed jeans.",
    )
    monkeypatch.setattr(
        agent,
        "create_fit_card",
        lambda outfit, item: "Finished fit card.",
    )

    session = agent.run_agent("graphic tee", {"items": []})

    assert session["price_comparison"]["verdict"] == "unknown"
    assert session["outfit_suggestion"] == "Wear it with relaxed jeans."
    assert session["fit_card"] == "Finished fit card."
    assert session["error"] is None


def test_run_agent_supplies_fallbacks_for_blank_tool_results(monkeypatch):
    monkeypatch.setattr(agent, "search_listings", lambda **kwargs: [ITEM])
    monkeypatch.setattr(
        agent,
        "compare_price",
        lambda item: {"verdict": "fair", "explanation": "Fair price."},
    )
    monkeypatch.setattr(agent, "suggest_outfit", lambda item, wardrobe: " ")
    monkeypatch.setattr(agent, "create_fit_card", lambda outfit, item: "")

    session = agent.run_agent("graphic tee", {"items": []})

    assert session["outfit_suggestion"].strip()
    assert ITEM["title"] in session["outfit_suggestion"]
    assert session["fit_card"].strip()
    assert ITEM["title"] in session["fit_card"]
