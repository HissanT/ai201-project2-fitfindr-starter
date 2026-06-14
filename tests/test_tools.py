from types import SimpleNamespace

import pytest

import tools


ITEM = {
    "id": "item_1",
    "title": "Graphic Tee - 2003 Tour Bootleg Style",
    "category": "tops",
    "condition": "good",
    "brand": "Unbranded",
    "price": 24,
    "platform": "Depop",
    "colors": ["black"],
    "style_tags": ["vintage", "streetwear"],
}
OUTFIT = (
    "Wear it with baggy dark-wash jeans, chunky white sneakers, and a black "
    "crossbody bag."
)


def _client_returning(content):
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )
    return SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=lambda **kwargs: response),
        )
    )


def _listing(listing_id, price, category="tops", style_tags=None):
    return {
        "id": listing_id,
        "category": category,
        "style_tags": style_tags or ["casual"],
        "brand": "Unbranded",
        "condition": "good",
        "price": price,
    }


# Tool 1: search_listings


def test_search_returns_results():
    results = tools.search_listings(
        "vintage graphic tee",
        size=None,
        max_price=50,
    )

    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    results = tools.search_listings(
        "designer ballgown",
        size="XXS",
        max_price=5,
    )

    assert results == []


def test_search_price_filter():
    results = tools.search_listings("jacket", size=None, max_price=10)

    assert all(item["price"] <= 10 for item in results)


def test_search_size_filter_is_case_insensitive():
    results = tools.search_listings("tee", size="l", max_price=None)

    assert results
    assert all("l" in item["size"].lower() for item in results)


def test_search_empty_description_returns_empty_list():
    assert tools.search_listings("   ", size=None, max_price=None) == []


# Tool 2: suggest_outfit


def test_suggest_outfit_uses_llm_for_named_wardrobe_items(monkeypatch):
    wardrobe = {
        "items": [
            {
                "name": "Baggy dark-wash jeans",
                "category": "bottoms",
                "colors": ["blue"],
                "style_tags": ["streetwear"],
            }
        ]
    }
    monkeypatch.setattr(
        tools,
        "_get_groq_client",
        lambda: _client_returning(
            "Pair the tee with Baggy dark-wash jeans for a vintage streetwear look."
        ),
    )

    result = tools.suggest_outfit(ITEM, wardrobe)

    assert "Baggy dark-wash jeans" in result


@pytest.mark.parametrize("wardrobe", [{"items": []}, {}, None, {"items": "invalid"}])
def test_suggest_outfit_handles_empty_or_invalid_wardrobe(monkeypatch, wardrobe):
    captured = {}
    client = _client_returning("Try relaxed jeans and neutral sneakers.")

    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="Try relaxed jeans and neutral sneakers."
                    )
                )
            ]
        )

    client.chat.completions.create = create
    monkeypatch.setattr(tools, "_get_groq_client", lambda: client)

    result = tools.suggest_outfit(ITEM, wardrobe)

    assert result == "Try relaxed jeans and neutral sneakers."
    assert "wardrobe is empty" in captured["messages"][1]["content"].lower()


@pytest.mark.parametrize("content", [None, "", "   "])
def test_suggest_outfit_falls_back_for_blank_llm_response(monkeypatch, content):
    monkeypatch.setattr(tools, "_get_groq_client", lambda: _client_returning(content))

    result = tools.suggest_outfit(ITEM, {"items": []})

    assert result.strip()
    assert ITEM["title"] in result
    assert "streetwear" in result


def test_suggest_outfit_falls_back_when_llm_raises(monkeypatch):
    def raise_error():
        raise RuntimeError("Groq is unavailable")

    monkeypatch.setattr(tools, "_get_groq_client", raise_error)

    result = tools.suggest_outfit(ITEM, {"items": []})

    assert result.strip()
    assert ITEM["title"] in result


# Tool 3: create_fit_card


@pytest.mark.parametrize("outfit", ["", "   ", None])
def test_create_fit_card_rejects_empty_outfit(outfit):
    result = tools.create_fit_card(outfit, ITEM)

    assert "outfit suggestion is missing" in result


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        (None, "listing details are missing"),
        ({"price": 24, "platform": "Depop"}, "title"),
        ({"title": "Tee", "price": 24, "platform": "  "}, "platform"),
        ({"title": "Tee", "price": float("nan"), "platform": "Depop"}, "price"),
        ({"title": "Tee", "price": -1, "platform": "Depop"}, "price"),
    ],
)
def test_create_fit_card_rejects_invalid_listing(item, expected):
    result = tools.create_fit_card(OUTFIT, item)

    assert expected in result


def test_create_fit_card_calls_llm_with_creative_temperature(monkeypatch):
    captured = {}
    client = _client_returning("A fresh two-sentence fit card. Easy vintage energy.")

    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="A fresh two-sentence fit card. Easy vintage energy."
                    )
                )
            ]
        )

    client.chat.completions.create = create
    monkeypatch.setattr(tools, "_get_groq_client", lambda: client)

    result = tools.create_fit_card(OUTFIT, ITEM)

    assert result == "A fresh two-sentence fit card. Easy vintage energy."
    assert captured["temperature"] == 0.9
    prompt = captured["messages"][1]["content"]
    assert ITEM["title"] in prompt
    assert "$24" in prompt
    assert ITEM["platform"] in prompt
    assert OUTFIT in prompt


@pytest.mark.parametrize("content", [None, "", "   "])
def test_create_fit_card_falls_back_for_blank_llm_response(monkeypatch, content):
    monkeypatch.setattr(tools, "_get_groq_client", lambda: _client_returning(content))

    result = tools.create_fit_card(OUTFIT, ITEM)

    assert ITEM["title"] in result
    assert "$24" in result
    assert ITEM["platform"] in result
    assert "baggy dark-wash jeans" in result


def test_create_fit_card_falls_back_when_llm_raises(monkeypatch):
    def raise_error():
        raise RuntimeError("Groq is unavailable")

    monkeypatch.setattr(tools, "_get_groq_client", raise_error)

    result = tools.create_fit_card(OUTFIT, ITEM)

    assert result.startswith(
        "Found the Graphic Tee - 2003 Tour Bootleg Style for $24 on Depop."
    )


# Tool 4: compare_price


def test_compare_price_returns_expected_result_shape(monkeypatch):
    monkeypatch.setattr(
        tools,
        "load_listings",
        lambda: [
            _listing("similar_1", 20, style_tags=["vintage"]),
            _listing("similar_2", 30, style_tags=["streetwear"]),
        ],
    )

    result = tools.compare_price(ITEM)

    assert result["item_price"] == 24
    assert result["comparable_count"] == 2
    assert result["median_price"] == 25
    assert result["verdict"] == "fair"


def test_compare_price_uses_broader_category_when_close_matches_are_limited(
    monkeypatch,
):
    monkeypatch.setattr(
        tools,
        "load_listings",
        lambda: [
            _listing("other_1", 18, style_tags=["minimal"]),
            _listing("other_2", 22, style_tags=["preppy"]),
        ],
    )

    result = tools.compare_price(ITEM)

    assert result["comparable_count"] == 2
    assert "broader same-category listings" in result["explanation"]


@pytest.mark.parametrize("price", [None, "24", True, -1, float("nan")])
def test_compare_price_returns_unknown_for_invalid_price(price):
    result = tools.compare_price({**ITEM, "price": price})

    assert result["verdict"] == "unknown"
    assert "still help style" in result["explanation"]


def test_compare_price_returns_unknown_with_no_comparables(monkeypatch):
    monkeypatch.setattr(tools, "load_listings", lambda: [])

    result = tools.compare_price(ITEM)

    assert result["verdict"] == "unknown"
    assert result["comparable_count"] == 0


def test_compare_price_returns_unknown_when_data_loading_fails(monkeypatch):
    def raise_error():
        raise OSError("listings unavailable")

    monkeypatch.setattr(tools, "load_listings", raise_error)

    result = tools.compare_price(ITEM)

    assert result["verdict"] == "unknown"
    assert "still help style" in result["explanation"]


@pytest.mark.parametrize(
    ("item_price", "comparable_price", "expected_verdict"),
    [
        (80, 100, "good deal"),
        (100, 100, "fair"),
        (120, 100, "overpriced"),
    ],
)
def test_compare_price_applies_ten_percent_verdict_rules(
    monkeypatch,
    item_price,
    comparable_price,
    expected_verdict,
):
    monkeypatch.setattr(
        tools,
        "load_listings",
        lambda: [
            _listing("similar_1", comparable_price, style_tags=["vintage"]),
            _listing("similar_2", comparable_price, style_tags=["streetwear"]),
        ],
    )

    result = tools.compare_price({**ITEM, "price": item_price})

    assert result["verdict"] == expected_verdict
