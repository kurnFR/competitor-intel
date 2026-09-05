import unittest
from unittest.mock import patch

from app.services.crawler.rate_limiter import RateLimitConfig, SourceRateLimiter


class RateLimiterTests(unittest.TestCase):
    def test_config_rejects_invalid_values(self):
        with self.assertRaises(ValueError):
            RateLimitConfig(requests_per_second=0)
        with self.assertRaises(ValueError):
            RateLimitConfig(max_concurrency=0)

    def test_interval_uses_requests_per_second(self):
        config = RateLimitConfig(requests_per_second=2.0)
        self.assertEqual(config.interval_seconds, 0.5)

    @patch("app.services.crawler.rate_limiter.time.sleep")
    @patch("app.services.crawler.rate_limiter.time.monotonic", side_effect=[10.0, 10.0, 10.1])
    def test_second_request_waits_for_source_interval(self, monotonic, sleep):
        limiter = SourceRateLimiter()
        config = RateLimitConfig(requests_per_second=1.0)

        with limiter.acquire("source-1", config):
            pass
        with limiter.acquire("source-1", config):
            pass

        sleep.assert_called_once()
        self.assertAlmostEqual(sleep.call_args.args[0], 0.9, places=6)

    @patch("app.services.crawler.rate_limiter.time.sleep")
    @patch("app.services.crawler.rate_limiter.time.monotonic", side_effect=[10.0, 10.8])
    def test_different_sources_do_not_share_pacing(self, monotonic, sleep):
        limiter = SourceRateLimiter()
        config = RateLimitConfig(requests_per_second=1.0)

        with limiter.acquire("source-a", config):
            pass
        with limiter.acquire("source-b", config):
            pass

        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
