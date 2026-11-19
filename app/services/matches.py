"""Carry an analyst's product mapping across sightings of the same competitor pack."""

import json

from sqlalchemy import text


def offer_key(offer):
    identity = [
        str(getattr(offer, "competitor_id", None) or ""),
        (offer.product_name or "").strip().casefold(),
        (offer.pack_size or "").strip().casefold(),
        (offer.category or "").upper(),
    ]
    return json.dumps(identity, ensure_ascii=False, separators=(",", ":"))


def reviewed_matches(db):
    return {
        (row.own_id, row.offer_key): row.accepted
        for row in db.execute(text("SELECT own_id,offer_key,accepted FROM competitor_intel.product_matches"))
    }
