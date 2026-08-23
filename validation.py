from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from models import REQUEST_FIELDS, SigningRequest

ACCOUNT_ID_PATTERN = re.compile(r"^acc_[A-Za-z0-9]+$")


class RequestValidationError(ValueError):
    pass


def parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise RequestValidationError("timestamp must be an RFC3339 UTC string ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise RequestValidationError("timestamp is malformed") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RequestValidationError("timestamp must include UTC")
    return parsed.astimezone(timezone.utc)


def validate_request(data: Any) -> SigningRequest:
    if not isinstance(data, dict) or set(data) != set(REQUEST_FIELDS):
        raise RequestValidationError("request fields do not match the fixed contract")

    session_id = data["session_id"]
    if not isinstance(session_id, str):
        raise RequestValidationError("session_id must be a string UUID")
    try:
        UUID(session_id)
    except ValueError as exc:
        raise RequestValidationError("session_id must be a valid UUID") from exc

    customer_id = data["customer_id"]
    if not isinstance(customer_id, str) or not ACCOUNT_ID_PATTERN.fullmatch(customer_id):
        raise RequestValidationError("customer_id is invalid")

    transaction_type = data["transaction_type"]
    if not isinstance(transaction_type, str) or not transaction_type:
        raise RequestValidationError("transaction_type must be a non-empty string")

    amount = data["amount"]
    if isinstance(amount, bool) or not isinstance(amount, (int, str, float, Decimal)):
        raise RequestValidationError("amount must be a positive whole amount")
    try:
        decimal_amount = Decimal(str(amount))
    except (InvalidOperation, ValueError) as exc:
        raise RequestValidationError("amount is invalid") from exc
    if not decimal_amount.is_finite() or decimal_amount <= 0 or decimal_amount != decimal_amount.to_integral_value():
        raise RequestValidationError("amount must be a positive whole amount")

    timestamp = parse_timestamp(data["timestamp"])
    return SigningRequest.from_values(session_id, customer_id, transaction_type, decimal_amount, timestamp)
