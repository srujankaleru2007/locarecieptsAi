from pathlib import Path
from streamlit.testing.v1 import AppTest


def test_empty_app_and_model_selection():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=20).run()
    assert not app.exception
    assert "messy bills" in app.title[0].value
    app.sidebar.selectbox[0].select("minicpm-v").run()
    assert app.sidebar.text_input[0].value == "minicpm-v"
    assert not app.exception


def test_dashboard_and_clear():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=20).run()
    app.session_state["records"] = {"hash": {"SourceFile": "x.png", "VendorName": "Vendor", "InvoiceDate": "2026-10-19", "TaxHead": "Meals", "GSTIN": None, "Subtotal": 100., "TaxAmount": 18., "TotalAmount": 118., "LineItems": "Lunch", "Reviewed": False}}
    app.run()
    assert not app.exception
    assert app.metric[1].value == "₹118.00"
    assert len(app.get("download_button")) == 2
    app.sidebar.button[1].click().run()
    assert not app.exception and not app.session_state["records"]


def test_editor_changes_persist_and_update_metrics():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=15).run()
    app.session_state["records"] = {"hash": {"SourceFile": "x.png", "VendorName": "Vendor", "InvoiceDate": None, "TaxHead": None, "GSTIN": None, "Subtotal": None, "TaxAmount": None, "TotalAmount": None, "LineItems": None, "Reviewed": False}}
    app.run()
    assert not app.exception
    # Verify reruns do not discard canonical corrections (the callback itself
    # is exercised in a script context below).
    app.session_state["records"]["hash"]["TotalAmount"] = 236.
    app.run()
    assert app.metric[1].value == "₹236.00"
    app.run()
    assert app.metric[1].value == "₹236.00"


def test_editor_callback_applies_delta():
    script = """
import streamlit as st
from app import initialize, commit_edits, render_dashboard
initialize()
st.session_state.records = {"hash": {"SourceFile": "x.png", "VendorName": "Vendor", "InvoiceDate": None, "TaxHead": None, "GSTIN": None, "Subtotal": None, "TaxAmount": None, "TotalAmount": None, "LineItems": None, "Reviewed": False}}
st.session_state.delta = {"edited_rows": {0: {"TotalAmount": 236., "TaxAmount": 36., "Subtotal": 200., "Reviewed": True, "InvoiceDate": "2026-10-19"}}}
commit_edits("delta", ["hash"])
render_dashboard()
"""
    app = AppTest.from_string(script, default_timeout=15).run()
    assert not app.exception
    assert app.metric[1].value == "₹236.00"
    assert app.metric[2].value == "₹36.00"
    assert app.session_state["records"]["hash"]["Reviewed"] is True
    assert app.session_state["records"]["hash"]["InvoiceDate"] == "2026-10-19"
