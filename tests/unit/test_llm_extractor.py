import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

from app.services.extraction.llm_extractor import LLMExtractor


class LLMExtractorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.extractor = LLMExtractor()
        self.extractor.client = Mock()

    def _mock_response(self, content: str):
        self.extractor.client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )

    def test_omitted_year_uses_supplied_runtime_date_context(self) -> None:
        self._mock_response(
            '{"promotions": [{"product_name": "Roma", "end_date": "2027-09-07", "evidence_quote": "Sampai 7 Sep"}]}'
        )

        result = self.extractor.extract_with_metadata(
            "Roma promo sampai 7 Sep",
            current_date=date(2027, 8, 20),
        )

        self.assertEqual(result.parser_status, "SUCCESS")
        self.assertEqual(len(result.items), 1)
        prompt = self.extractor.client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
        self.assertIn("CURRENT_DATE: 2027-08-20", prompt)
        self.assertNotIn("current year 2026", prompt.lower())

    def test_invalid_item_is_rejected_without_dropping_valid_items(self) -> None:
        self._mock_response(
            '{"promotions": ['
            '{"product_name": "Valid Biscuit", "evidence_quote": "Diskon 10%", "confidence": 0.9},'
            '{"product_name": "Invalid Biscuit", "evidence_quote": "bad", "confidence": 1.5}'
            ']}'
        )

        result = self.extractor.extract_with_metadata("catalog text", current_date=date(2026, 9, 5))

        self.assertEqual(len(result.items), 1)
        self.assertEqual(len(result.rejected_items), 1)
        self.assertEqual(result.rejected_items[0]["index"], 1)
        self.assertEqual(result.parser_status, "PARTIAL_SUCCESS")

    def test_malformed_json_is_visible_in_result(self) -> None:
        self._mock_response("not-json")

        result = self.extractor.extract_with_metadata("catalog text", current_date=date(2026, 9, 5))

        self.assertEqual(result.parser_status, "INVALID_JSON")
        self.assertEqual(result.items, [])
        self.assertEqual(result.raw_response, "not-json")

    def test_indonesian_dates_pack_size_and_prices_are_normalized(self) -> None:
        self._mock_response(
            '{"promotions": ['
            '{"product_name": "Oreo Vanilla 133g", "promo_price": "Rp 8.500", "regular_price": "10.500", "start_date": "12 - 14 Mei 2026", "evidence_quote": "Oreo Vanilla 133g Rp 8.500"}'
            ']}'
        )

        result = self.extractor.extract_with_metadata("catalog text", current_date=date(2026, 5, 1))
        self.assertEqual(result.parser_status, "SUCCESS")
        self.assertEqual(len(result.items), 1)
        item = result.items[0]
        self.assertEqual(item.start_date, "2026-05-12")
        self.assertEqual(item.end_date, "2026-05-14")
        self.assertEqual(item.pack_size, "133g")
        self.assertEqual(item.promo_price, 8500.0)
        self.assertEqual(item.regular_price, 10500.0)


if __name__ == "__main__":
    unittest.main()
