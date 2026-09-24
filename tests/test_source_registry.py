from types import SimpleNamespace
from uuid import uuid4
import pytest
from fastapi import HTTPException

from app.services.source_registry import transition_source


def source(status="DISCOVERED", adapter_key=None, access_status="UNKNOWN"):
    return SimpleNamespace(id=uuid4(), lifecycle_status=status, adapter_key=adapter_key, access_status=access_status, is_active=False)


def test_discovered_source_can_become_candidate_but_not_active_directly():
    item = source()
    transition_source(item, "CANDIDATE")
    assert item.lifecycle_status == "CANDIDATE"
    assert item.is_active is False
    with pytest.raises(HTTPException):
        transition_source(item, "ACTIVE")


def test_active_requires_explicit_adapter():
    item = source("APPROVED")
    with pytest.raises(HTTPException):
        transition_source(item, "ACTIVE")


def test_active_rejects_blocked_access():
    item = source("APPROVED", adapter_key="SUPERINDO", access_status="CAPTCHA_REQUIRED")
    with pytest.raises(HTTPException):
        transition_source(item, "ACTIVE")


def test_active_source_can_be_disabled_without_deleting_history():
    item = source("ACTIVE", adapter_key="SUPERINDO")
    item.is_active = True
    transition_source(item, "DISABLED")
    assert item.lifecycle_status == "DISABLED"
    assert item.is_active is False


def test_invalid_transition_is_rejected():
    item = source("DISCOVERED")
    with pytest.raises(HTTPException):
        transition_source(item, "ACTIVE")
