import json
from unittest.mock import MagicMock, patch

import pytest

from app.services.extraction.flyer_extractor import FlyerVisionExtractor


@pytest.fixture
def extractor():
    with patch("app.services.extraction.flyer_extractor.OpenAI"):
        ext = FlyerVisionExtractor(model="test-vision-model", base_url="http://mock-llm", api_key="dummy")
        return ext


def test_flyer_extractor_parse_valid_json(extractor):
    sample_response = json.dumps({
        "promotions": [
            {
                "product_name": "Oreo Biscuit Vanilla 133g",
                "category": "COOKIE",
                "regular_price": 10500.0,
                "promo_price": 8200.0,
                "discount_percentage": 21.9,
                "promotion_type": "DISCOUNT",
                "evidence_quote": "Oreo Vanilla 133g Rp 8.200 (Hemat 21%)",
                "confidence": 0.95,
            },
            {
                "product_name": "Tango Wafer Cokelat 176g",
                "category": "WAFER",
                "regular_price": 14000.0,
                "promo_price": 14000.0,
                "promotion_type": "BUY_X_GET_Y",
                "buy_quantity": 2,
                "free_quantity": 1,
                "evidence_quote": "Tango Wafer Beli 2 Gratis 1",
                "confidence": 0.9,
            },
        ]
    })

    # Mock completion call
    mock_choice = MagicMock()
    mock_choice.message.content = sample_response
    mock_response = MagicMock(choices=[mock_choice])
    extractor.client.chat.completions.create.return_value = mock_response

    # Fake 1x1 GIF bytes
    fake_gif = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
    result = extractor.extract_from_image_bytes(fake_gif, mime_type="image/gif")

    assert result.parser_status == "SUCCESS"
    assert len(result.items) == 2
    assert result.items[0].product_name == "Oreo Biscuit Vanilla 133g"
    assert result.items[0].promo_price == 8200.0
    assert result.items[1].promotion_type == "BUY_X_GET_Y"
    assert result.items[1].buy_quantity == 2


def test_flyer_extractor_handles_markdown_codeblocks(extractor):
    raw_markdown = """```json
    {
        "promotions": [
            {
                "product_name": "Roma Malkist Crackers 135g",
                "category": "CRACKER",
                "promo_price": 7500.0,
                "promotion_type": "DISCOUNT",
                "evidence_quote": "Roma Malkist Rp 7.500"
            }
        ]
    }
    ```"""
    mock_choice = MagicMock()
    mock_choice.message.content = raw_markdown
    extractor.client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])

    result = extractor.extract_from_data_url("data:image/jpeg;base64,abc123")
    assert result.parser_status == "SUCCESS"
    assert len(result.items) == 1
    assert result.items[0].product_name == "Roma Malkist Crackers 135g"


def test_flyer_extractor_handles_llm_error_cleanly(extractor):
    extractor.client.chat.completions.create.side_effect = RuntimeError("Connection timeout to vision model")

    result = extractor.extract_from_data_url("data:image/jpeg;base64,abc123")
    assert result.parser_status == "LLM_ERROR"
    assert len(result.items) == 0
    assert len(result.rejected_items) == 1
    assert "Connection timeout" in result.rejected_items[0]["error"]


def test_flyer_extractor_handles_invalid_json(extractor):
    mock_choice = MagicMock()
    mock_choice.message.content = "Not a json payload from vision"
    extractor.client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])

    result = extractor.extract_from_data_url("data:image/jpeg;base64,abc123")
    assert result.parser_status == "JSON_ERROR"
    assert len(result.items) == 0
