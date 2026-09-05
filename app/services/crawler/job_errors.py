"""Exceptions used by the durable crawler worker."""


class CrawlJobError(Exception):
    """Base class for a crawl-job processing failure."""

    retryable = True


class PermanentCrawlJobError(CrawlJobError):
    """Failure that should not consume the retry budget."""

    retryable = False
