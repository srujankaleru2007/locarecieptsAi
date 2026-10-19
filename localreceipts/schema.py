"""Strict model-output parsing and review validation. Missing money is never zero."""
import json
import math
import re
from datetime import date
from decimal import Decimal, InvalidOperation

CATEGORIES = ("Software", "Travel", "Meals", "Office Supplies", "Utilities", "Professional Services")
MONEY_FIELDS = ("Subtotal", "TaxAmount", "TotalAmount")
FIELDS = ("VendorName", "InvoiceDate", "TaxHead", "GSTIN", *MONEY_FIELDS, "LineItems")
SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        **{k: {"type": ["string", "null"]} for k in ("VendorName", "InvoiceDate", "GSTIN", "LineItems")},
        "TaxHead": {"type": ["string", "null"], "enum": [*CATEGORIES, None]},
        **{k: {"type": ["number", "null"]} for k in MONEY_FIELDS},
    },
    "required": list(FIELDS),
}


class ReceiptError(ValueError):
    """A safe, actionable error suitable for the UI."""


def parse_json_response(text: str) -> dict:
    """Accept plain JSON or a single fenced/prefixed object; never execute output."""
    if not text or len(text) > 100_000:
        raise ReceiptError("The model returned empty or oversized output. Try another model.")
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        try:
            data = json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError as exc:
            raise ReceiptError("The model did not return valid JSON. Retry extraction.") from exc
    if not isinstance(data, dict):
        raise ReceiptError("Expected one receipt object, but the model returned another JSON type.")
    # Compatibility with the originally requested combined label. GSTIN remains text.
    if "TaxAmount" not in data and "GSTIN / Tax Amount" in data:
        data["TaxAmount"] = data.pop("GSTIN / Tax Amount")
    if not all(key in data for key in ("VendorName", "TotalAmount")):
        raise ReceiptError("Model output is missing receipt fields. Retry with a vision model.")
    return data


def money(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("Boolean is not an amount")
    value = re.sub(r"(?i)\bINR\b|₹|,", "", str(value)).strip()
    if value.startswith("(") and value.endswith(")"):
        value = "-" + value[1:-1]
    try:
        amount = Decimal(value)
        if not amount.is_finite() or abs(amount) > Decimal("1e12"):
            raise ValueError("Invalid amount")
        return float(amount.quantize(Decimal("0.01")))
    except InvalidOperation as exc:
        raise ValueError("Invalid amount") from exc


def normalize_receipt(data: dict) -> tuple[dict, list[str]]:
    row, issues = {}, []
    for field in FIELDS:
        value = data.get(field)
        if field in MONEY_FIELDS:
            try:
                row[field] = money(value)
            except (ValueError, TypeError):
                row[field] = None
                issues.append(f"Unreadable {field}; enter it manually.")
        else:
            row[field] = value.strip() if isinstance(value, str) else None
            if value is not None and not isinstance(value, str):
                issues.append(f"Invalid {field}; enter it manually.")
    if row["InvoiceDate"]:
        try:
            if date.fromisoformat(row["InvoiceDate"]).isoformat() != row["InvoiceDate"]:
                raise ValueError()
        except ValueError:
            issues.append("Invoice date must be YYYY-MM-DD.")
            row["InvoiceDate"] = None
    if row["TaxHead"] not in CATEGORIES:
        row["TaxHead"] = None
    issues.extend(review_issues(row))
    return row, list(dict.fromkeys(issues))


def review_issues(row: dict) -> list[str]:
    issues = []
    for field in FIELDS:
        value = row.get(field)
        if value is None or value == "" or (isinstance(value, float) and math.isnan(value)):
            if field != "GSTIN":
                issues.append(f"Missing {field}.")
    if row.get("GSTIN") and not re.fullmatch(r"\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]", row["GSTIN"]):
        issues.append("Check GSTIN format.")
    amounts = [row.get(k) for k in MONEY_FIELDS]
    if all(isinstance(v, (int, float)) and math.isfinite(v) for v in amounts):
        if abs(amounts[0] + amounts[1] - amounts[2]) > 1:
            issues.append("Subtotal + tax differs from total; check discounts/rounding.")
    return issues
