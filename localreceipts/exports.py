"""Consistent accounting headers and spreadsheet-safe UTF-8 CSV downloads."""
import json
from datetime import datetime, timezone
import pandas as pd

HEADERS = {
    "SourceFile": "Source File", "VendorName": "Vendor Name", "InvoiceDate": "Invoice Date",
    "TaxHead": "Expense Category", "GSTIN": "Vendor GSTIN", "Subtotal": "Subtotal (INR)",
    "TaxAmount": "GST / Tax Amount (INR)", "TotalAmount": "Total Amount (INR)",
    "LineItems": "Line Item Summary", "Reviewed": "Reviewed",
}


def export_to_csv(frame: pd.DataFrame) -> bytes:
    result = frame.reindex(columns=HEADERS).copy()
    for col in ("Subtotal", "TaxAmount", "TotalAmount"):
        result[col] = pd.to_numeric(result[col], errors="coerce").astype(float)
    for col in result.select_dtypes(include=["object", "string"]).columns:
        result[col] = result[col].map(
            lambda v: "'" + v if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n")) else v
        )
    return result.rename(columns=HEADERS).to_csv(index=False, float_format="%.2f", lineterminator="\n").encode("utf-8-sig")


def export_to_json(frame: pd.DataFrame, audit: dict) -> bytes:
    payload = {
        "application": "LocalReceipts AI", "schema_version": 1, "currency": "INR",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "receipts": json.loads(frame.to_json(orient="records", date_format="iso", force_ascii=False)),
        "extraction_audit": audit,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")
