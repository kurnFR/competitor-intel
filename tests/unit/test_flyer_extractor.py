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


def test_flyer_extractor_parses_indonesian_dates_and_banner_dates(extractor):
    sample_response = json.dumps({
        "banner_date": "Periode: 12 - 14 Mei 2026",
        "promotions": [
            {
                "product_name": "Oreo Biscuit Vanilla 133g",
                "category": "COOKIE",
                "pack_size": "133g",
                "regular_price": "Rp 10.500",
                "promo_price": "Rp 8.200",
                "promotion_type": "DISCOUNT",
                "evidence_quote": "Oreo Vanilla 133g Rp 8.200",
                "confidence": 0.95,
            },
            {
                "product_name": "Roma Malkist Keju Manis 120g",
                "category": "CRACKER",
                "pack_size": "120g",
                "promo_price": 7500.0,
                "start_date": "12 Mei 2026",
                "end_date": "14 Mei 2026",
                "promotion_type": "DISCOUNT",
                "evidence_quote": "Roma Malkist Rp 7.500 Berlaku 12-14 Mei 2026",
                "confidence": 0.9,
            },
            {
                "product_name": "Beng Beng Share It 10x9.5g",
                "category": "SNACK",
                "pack_size": "10x9.5g",
                "promo_price": 12900.0,
                "start_date": "12 - 14 Mei 2026",
                "promotion_type": "DISCOUNT",
                "evidence_quote": "Beng Beng Share It Rp 12.900",
                "confidence": 0.9,
            },
        ]
    })
    mock_choice = MagicMock()
    mock_choice.message.content = sample_response
    extractor.client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])

    result = extractor.extract_from_data_url("data:image/jpeg;base64,abc123")
    assert result.parser_status == "SUCCESS"
    assert len(result.items) == 3

    # Item 1 inherits from flyer banner date, and price string is normalized
    assert result.items[0].start_date == "2026-05-12"
    assert result.items[0].end_date == "2026-05-14"
    assert result.items[0].regular_price == 10500.0
    assert result.items[0].promo_price == 8200.0
    assert result.items[0].pack_size == "133g"

    # Item 2 parses Indonesian date formats
    assert result.items[1].start_date == "2026-05-12"
    assert result.items[1].end_date == "2026-05-14"

    # Item 3 splits date range from start_date
    assert result.items[2].start_date == "2026-05-12"
    assert result.items[2].end_date == "2026-05-14"


def test_flyer_extractor_parses_cross_month_and_multi_week_validity(extractor):
    sample_response = json.dumps({
        "promotions": [
            {
                "product_name": "Tango Wafer Chocolate 176g",
                "category": "WAFER",
                "pack_size": "176g",
                "promo_price": 11500.0,
                "validity_period": "28 Oktober - 3 November 2026",
                "promotion_type": "DISCOUNT",
                "evidence_quote": "Tango Wafer Rp 11.500 Periode 28 Okt - 3 Nov 2026",
            },
            {
                "product_name": "Khong Guan Classic Assorted 350g",
                "category": "BISCUIT",
                "pack_size": "350g",
                "promo_price": 45000.0,
                "validity_period": "Minggu ke-1: 1 - 7 Juni 2026",
                "promotion_type": "DISCOUNT",
                "evidence_quote": "Khong Guan Assorted Rp 45.000 Minggu ke-1: 1 - 7 Juni 2026",
            },
            {
                "product_name": "Serena Cheese Cookies 150g",
                "category": "COOKIE",
                "pack_size": "150g",
                "promo_price": 18000.0,
                "validity_period": "28 Des 2025 - 5 Jan 2026",
                "promotion_type": "DISCOUNT",
                "evidence_quote": "Serena Cheese Cookies Rp 18.000 (28 Des 2025 - 5 Jan 2026)",
            },
        ]
    })
    mock_choice = MagicMock()
    mock_choice.message.content = sample_response
    extractor.client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])

    result = extractor.extract_from_data_url("data:image/jpeg;base64,abc123")
    assert result.parser_status == "SUCCESS"
    assert len(result.items) == 3

    # Cross-month
    assert result.items[0].start_date == "2026-10-28"
    assert result.items[0].end_date == "2026-11-03"

    # Multi-week
    assert result.items[1].start_date == "2026-06-01"
    assert result.items[1].end_date == "2026-06-07"

    # Cross-year
    assert result.items[2].start_date == "2025-12-28"
    assert result.items[2].end_date == "2026-01-05"


def test_flyer_extractor_extracts_pack_size_when_missing(extractor):
    sample_response = json.dumps({
        "promotions": [
            {
                "product_name": "Oreo Biscuit Vanilla 133g",
                "category": "COOKIE",
                "promo_price": 8200.0,
                "promotion_type": "DISCOUNT",
                "evidence_quote": "Oreo Vanilla 133g Rp 8.200",
            },
            {
                "product_name": "Nissin Wafer Chocolate 12 x 25g",
                "category": "WAFER",
                "promo_price": 14000.0,
                "promotion_type": "DISCOUNT",
                "evidence_quote": "Nissin Wafer Chocolate 12 x 25g Rp 14.000",
            },
        ]
    })
    mock_choice = MagicMock()
    mock_choice.message.content = sample_response
    extractor.client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])

    result = extractor.extract_from_data_url("data:image/jpeg;base64,abc123")
    assert result.parser_status == "SUCCESS"
    assert len(result.items) == 2
    assert result.items[0].pack_size == "133g"
    assert result.items[1].pack_size == "12 x 25g"

