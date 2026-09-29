import pytest

from app.core.config import settings


@pytest.fixture(autouse=True)
def _no_network_robots(monkeypatch):
    """Unit tests use mocked HTTP clients; robots.txt lookups are tested separately."""
    monkeypatch.setattr(settings, "CRAWLER_RESPECT_ROBOTS", False)
