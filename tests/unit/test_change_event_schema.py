import uuid
from datetime import datetime, timezone

import pytest

from app.schemas.promotion import PromotionChangeEventOut


@pytest.mark.parametrize("old,new", [(7000.0, 6500.0), (7000, 6500), ("DISCOUNT", "BUY_X_GET_Y"), ("2026-10-15", "2026-10-20"), (None, 30),
                                     ({"amount": 7000}, {"amount": 6500}), ([1, 2], [3]), (None, None)])
def test_change_events_accept_any_kind_of_changed_value(old, new):
    """A price change is a number, not a dictionary; this endpoint used to fail for every price change."""
    event = PromotionChangeEventOut(id=uuid.uuid4(), promotion_id=uuid.uuid4(), event_type="PRICE_OR_VALUE_CHANGED", field_name="promo_price",
                                    previous_value=old, new_value=new, change_impact=0.5, observed_at=datetime.now(timezone.utc))
    assert event.previous_value == old and event.new_value == new
