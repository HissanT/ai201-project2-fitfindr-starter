import app


ITEM = {
    "title": "Graphic Tee",
    "price": 24,
    "platform": "Depop",
    "size": "L",
    "condition": "good",
    "brand": None,
    "colors": ["black"],
    "style_tags": ["vintage", "streetwear"],
}


def test_handle_query_rejects_empty_query(monkeypatch):
    def unexpected_call(*args, **kwargs):
        raise AssertionError("run_agent should not be called for an empty query")

    monkeypatch.setattr(app, "run_agent", unexpected_call)

    result = app.handle_query("   ", "Example wardrobe")

    assert result == (
        "Please enter a description of the item you want to find.",
        "",
        "",
    )


def test_handle_query_uses_example_wardrobe(monkeypatch):
    example_wardrobe = {"items": [{"name": "Example jeans"}]}
    captured = {}
    monkeypatch.setattr(
        app,
        "get_example_wardrobe",
        lambda: example_wardrobe,
    )

    def run_agent(query, wardrobe):
        captured["query"] = query
        captured["wardrobe"] = wardrobe
        return {"error": "No results"}

    monkeypatch.setattr(app, "run_agent", run_agent)

    result = app.handle_query("  graphic tee  ", "Example wardrobe")

    assert captured == {
        "query": "graphic tee",
        "wardrobe": example_wardrobe,
    }
    assert result == ("No results", "", "")


def test_handle_query_uses_empty_wardrobe(monkeypatch):
    empty_wardrobe = {"items": []}
    captured = {}
    monkeypatch.setattr(app, "get_empty_wardrobe", lambda: empty_wardrobe)

    def run_agent(query, wardrobe):
        captured["wardrobe"] = wardrobe
        return {"error": "No results"}

    monkeypatch.setattr(app, "run_agent", run_agent)

    app.handle_query("graphic tee", "Empty wardrobe (new user)")

    assert captured["wardrobe"] is empty_wardrobe


def test_handle_query_maps_successful_session_to_panels(monkeypatch):
    monkeypatch.setattr(
        app,
        "run_agent",
        lambda query, wardrobe: {
            "error": None,
            "selected_item": ITEM,
            "price_comparison": {
                "verdict": "overpriced",
                "explanation": "The item is $4.50 above the median.",
            },
            "outfit_suggestion": "Wear it with baggy jeans.",
            "fit_card": "A casual vintage fit.",
        },
    )

    listing, outfit, fit_card = app.handle_query(
        "graphic tee",
        "Example wardrobe",
    )

    assert "Graphic Tee" in listing
    assert "Price: $24" in listing
    assert "Platform: Depop" in listing
    assert "Size: L" in listing
    assert "Brand: Unbranded" in listing
    assert "Price check: Overpriced" in listing
    assert "The item is $4.50 above the median." in listing
    assert outfit == "Wear it with baggy jeans."
    assert fit_card == "A casual vintage fit."
