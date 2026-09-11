"""Stable serialization for signed licensing envelopes."""
from __future__ import annotations

import base64
import json
from typing import Any, Mapping


def canonical_json(payload: Mapping[str, Any]) -> bytes:
    """Encode a JSON object deterministically and reject non-finite values."""
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def b64url_decode(value: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise ValueError("Expected a non-empty base64url string.")
    if any(char.isspace() for char in value):
        raise ValueError("Whitespace is not allowed in base64url data.")
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, UnicodeEncodeError) as error:
        raise ValueError("Invalid base64url data.") from error
