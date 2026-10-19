from io import BytesIO
import json
from types import SimpleNamespace
from unittest.mock import Mock

import fitz
import httpx
import pandas as pd
from PIL import Image
import pytest
from ollama import ResponseError

from localreceipts.documents import Document, prepare_document
from localreceipts.extraction import extract_receipt_data, local_client
from localreceipts.exports import export_to_csv, export_to_json
from localreceipts.schema import ReceiptError, normalize_receipt, parse_json_response


def receipt(**changes):
    return {"VendorName": "Test Vendor", "InvoiceDate": "2026-10-19", "TaxHead": "Software", "GSTIN": None,
            "Subtotal": 100, "TaxAmount": 18, "TotalAmount": 118, "LineItems": "Subscription", **changes}


@pytest.mark.parametrize("wrapper", ["{}", "```json\n{}\n```", "Here is the JSON: {} Done."])
def test_json_wrappers(wrapper):
    assert parse_json_response(wrapper.format(json.dumps(receipt())))["TotalAmount"] == 118


@pytest.mark.parametrize("bad", ["", "[]", "null", "garbage", '{"x":1}', '{"VendorName":"x", "TotalAmount":'])
def test_invalid_json(bad):
    with pytest.raises(ReceiptError):
        parse_json_response(bad)


def test_missing_invalid_amounts_never_zero():
    row, issues = normalize_receipt(receipt(Subtotal="₹1,23,456.78", TaxAmount="NaN", TotalAmount=True, InvoiceDate="2026-02-30", TaxHead="Other"))
    assert row["Subtotal"] == 123456.78
    assert row["TaxAmount"] is None and row["TotalAmount"] is None
    assert row["InvoiceDate"] is None and row["TaxHead"] is None
    assert issues


def test_totals_flagged():
    _, issues = normalize_receipt(receipt(TotalAmount=200))
    assert any("differs" in issue for issue in issues)


def test_pdf_pages_and_images():
    with fitz.open() as pdf:
        pdf.new_page().insert_text((30, 30), "Invoice first page")
        pdf.new_page().insert_text((30, 30), "Invoice final total")
        doc = prepare_document("invoice.pdf", pdf.tobytes())
    assert len(doc.pages) == 2
    for page in doc.pages:
        with Image.open(BytesIO(page)) as img:
            assert img.format == "JPEG" and max(img.size) <= 2200


def test_image_transparency():
    source = BytesIO()
    Image.new("RGBA", (20, 20), (0, 0, 0, 0)).save(source, "PNG")
    doc = prepare_document("test.png", source.getvalue())
    with Image.open(BytesIO(doc.pages[0])) as img:
        assert img.getpixel((0, 0)) == (255, 255, 255)


@pytest.mark.parametrize("name,content", [("x.pdf", b"bad"), ("x.jpg", b"bad"), ("x.txt", b"data"), ("x.png", b"")])
def test_bad_documents(name, content):
    with pytest.raises(ReceiptError):
        prepare_document(name, content)


def test_pdf_limits_and_password():
    with fitz.open() as pdf:
        for _ in range(13):
            pdf.new_page()
        with pytest.raises(ReceiptError, match="1–12"):
            prepare_document("big.pdf", pdf.tobytes())
    with fitz.open() as pdf:
        pdf.new_page()
        data = pdf.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="owner")
        with pytest.raises(ReceiptError, match="password"):
            prepare_document("locked.pdf", data)


def client_stub():
    client = Mock()
    client.show.return_value.model_dump.return_value = {"capabilities": ["vision", "completion"]}
    client.chat.return_value = SimpleNamespace(message=SimpleNamespace(content=json.dumps(receipt())))
    return client


def test_inference_uses_schema_and_bytes():
    client = client_stub()
    row, _ = extract_receipt_data(Document("x", "hash", (b"jpeg",)), "llava", client)
    assert row["TotalAmount"] == 118
    assert client.chat.call_args.kwargs["messages"][0]["images"] == [b"jpeg"]
    assert client.chat.call_args.kwargs["format"]["type"] == "object"


@pytest.mark.parametrize("metadata", [{"remote_host": "https://example.com"}, {"remote_model": "x"}, {"capabilities": ["completion"]}])
def test_remote_and_text_models_rejected(metadata):
    client = client_stub()
    client.show.return_value.model_dump.return_value = metadata
    with pytest.raises(ReceiptError):
        extract_receipt_data(Document("x", "hash", (b"jpeg",)), "custom", client)
    client.chat.assert_not_called()


def test_cloud_model_rejected():
    client = client_stub()
    with pytest.raises(ReceiptError, match="Cloud"):
        extract_receipt_data(Document("x", "hash", (b"jpeg",)), "vision:cloud", client)
    client.chat.assert_not_called()


@pytest.mark.parametrize("error,match", [(ResponseError("missing",404), "not installed"), (httpx.ConnectError("offline"), "Cannot reach"), (httpx.ReadTimeout("slow"), "timed out")])
def test_friendly_errors(error, match):
    client = client_stub()
    client.chat.side_effect = error
    with pytest.raises(ReceiptError, match=match):
        extract_receipt_data(Document("x", "hash", (b"jpeg",)), "llava", client)


def test_loopback_ignores_environment(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "https://example.com")
    monkeypatch.setenv("HTTP_PROXY", "http://example.com")
    client = local_client()
    assert str(client._client.base_url) == "http://127.0.0.1:11434"
    assert client._client.trust_env is False
    assert client._client.follow_redirects is False


def test_exports_safe_and_complete():
    frame = pd.DataFrame([{**receipt(VendorName="=HYPERLINK(1)", TaxAmount=None), "SourceFile": "invoice.pdf", "Reviewed": True}])
    csv = export_to_csv(frame).decode("utf-8-sig")
    assert "'=HYPERLINK(1)" in csv and "118.00" in csv
    payload = json.loads(export_to_json(frame, {}))
    assert payload["receipts"][0]["TaxAmount"] is None
    assert payload["receipts"][0]["Reviewed"] is True


def test_remote_metadata_survives_sdk_validation():
    from localreceipts.extraction import LocalModelInfo
    info = LocalModelInfo.model_validate({"remote_host": "https://example.com", "capabilities": ["vision"]})
    assert info.model_dump()["remote_host"] == "https://example.com"


def test_multipage_reconciliation_without_double_counting():
    client = client_stub()
    row, issues = extract_receipt_data(Document("x.pdf", "hash", (b"page1", b"page2")), "llava", client)
    assert client.chat.call_count == 3
    assert client.chat.call_args_list[0].kwargs["messages"][0]["images"] == [b"page1"]
    assert client.chat.call_args_list[1].kwargs["messages"][0]["images"] == [b"page2"]
    assert "images" not in client.chat.call_args_list[2].kwargs["messages"][0]
    assert row["TotalAmount"] == 118 and any("Multi-page" in issue for issue in issues)


def test_thinking_models_use_json_without_reasoning_budget():
    client = client_stub()
    client.show.return_value.model_dump.return_value = {"capabilities": ["vision", "thinking"]}
    extract_receipt_data(Document("x", "hash", (b"jpeg",)), "local-vision", client)
    assert client.chat.call_args.kwargs["think"] is False
