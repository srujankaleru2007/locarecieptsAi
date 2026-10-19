"""LocalReceipts AI — run with: python -m streamlit run app.py."""
from datetime import date
import pandas as pd
import streamlit as st

from localreceipts.documents import prepare_document
from localreceipts.extraction import connection_status, extract_receipt_data
from localreceipts.exports import export_to_csv, export_to_json
from localreceipts.schema import CATEGORIES, MONEY_FIELDS, ReceiptError, review_issues

st.set_page_config(page_title="LocalReceipts AI", page_icon="🧾", layout="wide")


def initialize():
    defaults = {"records": {}, "audit": {}, "documents": {}, "failures": {},
                "editor_version": 0, "upload_version": 0}
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def clear_session():
    for key in ("records", "audit", "documents", "failures"):
        st.session_state[key] = {}
    st.session_state.editor_version += 1
    st.session_state.upload_version += 1


def render_sidebar():
    with st.sidebar:
        st.title("🧾 LocalReceipts AI")
        st.caption("PRIVATE BY DESIGN · MADE FOR INDIA")
        st.divider()
        preset = st.selectbox("Vision model", ["llama3.2-vision", "minicpm-v", "llava", "Custom"])
        model = st.text_input("Ollama model name", value="llama3.2-vision" if preset == "Custom" else preset, key=f"model_{preset}").strip()
        st.caption("Only downloaded local vision models are supported.")
        if st.button("Check local connection", use_container_width=True):
            st.session_state.connection = connection_status()
        if "connection" in st.session_state:
            online, names, message = st.session_state.connection
            (st.success if online else st.error)(message)
            if online:
                st.caption("Installed: " + (", ".join(names) or "No models installed"))
        st.caption("Endpoint: localhost:11434 · No cloud API")
        st.divider()
        st.markdown("**Before you begin**\n\n1. Start Ollama in local-only mode.\n2. Download a vision model once.\n3. Upload, extract, and review.")
        st.code('OLLAMA_NO_CLOUD=1', language="text")
        st.caption("Set this in Ollama's environment and restart Ollama. See README for Windows setup.")
        st.button("Clear all session data", on_click=clear_session, use_container_width=True)
        st.caption("Receipts stay in this browser session's server memory. Downloads are saved only when you choose.")
    return model


def commit_edits(editor_key, ids):
    """Apply widget deltas to canonical records before the next script run."""
    for position, changes in st.session_state[editor_key].get("edited_rows", {}).items():
        record = st.session_state.records[ids[int(position)]]
        for field, value in changes.items():
            if field == "InvoiceDate" and value:
                value = date.fromisoformat(str(value)[:10]).isoformat()
            record[field] = value
    # A fresh baseline avoids reapplying old deltas and keeps edits on every rerun.
    st.session_state.editor_version += 1


def render_uploads():
    st.subheader("1. Add your receipts")
    uploads = st.file_uploader("Drop invoices and bills here", type=["png", "jpg", "jpeg", "pdf"], accept_multiple_files=True,
                               key=f"uploads_{st.session_state.upload_version}", help="20 MB per file, 12 pages per PDF, 20 files / 100 MB per batch.")
    docs = []
    if uploads:
        if len(uploads) > 20 or sum(f.size for f in uploads) > 100 * 1024 * 1024:
            st.error("Keep each batch within 20 files and 100 MB.")
            return []
        import hashlib
        active = set()
        for upload in uploads:
            content = upload.getvalue()
            fingerprint = hashlib.sha256(content).hexdigest()
            if fingerprint in active:
                continue
            active.add(fingerprint)
            try:
                if fingerprint not in st.session_state.documents:
                    st.session_state.documents[fingerprint] = prepare_document(upload.name, content)
                docs.append(st.session_state.documents[fingerprint])
            except ReceiptError as exc:
                st.error(f"{upload.name}: {exc}")
        st.session_state.documents = {key: value for key, value in st.session_state.documents.items() if key in active}
        if docs:
            with st.expander("Preview documents", expanded=True):
                selected = st.selectbox("Document", range(len(docs)), format_func=lambda i: f"{docs[i].name} · {len(docs[i].pages)} page(s)")
                doc = docs[selected]
                page = st.number_input("Page", min_value=1, max_value=len(doc.pages), value=1, key=f"page_{doc.fingerprint}")
                st.image(doc.pages[page - 1], caption=f"{doc.name} · Page {page}", width=650)
    else:
        st.session_state.documents = {}
    return docs


def process_documents(docs, model):
    pending = [doc for doc in docs if doc.fingerprint not in st.session_state.records]
    st.caption("One file = one invoice. Combine pages of the same invoice in one PDF. Identical files are skipped automatically.")
    if st.button(f"Extract {len(pending)} new receipt(s)", type="primary", disabled=not pending or not model):
        progress = st.progress(0, text="Starting local extraction…")
        for i, doc in enumerate(pending):
            progress.progress(i / len(pending), text=f"Reading {doc.name} locally…")
            try:
                row, issues = extract_receipt_data(doc, model)
                st.session_state.records[doc.fingerprint] = {"SourceFile": doc.name, **row, "Reviewed": False}
                st.session_state.audit[doc.fingerprint] = {"source_file": doc.name, "model": model, "page_count": len(doc.pages), "original_extraction": row.copy(), "warnings": issues}
                st.session_state.failures.pop(doc.fingerprint, None)
            except ReceiptError as exc:
                st.session_state.failures[doc.fingerprint] = f"{doc.name}: {exc}"
            progress.progress((i + 1) / len(pending))
        st.session_state.editor_version += 1
        progress.empty()
    for doc in docs:
        if doc.fingerprint in st.session_state.failures:
            st.error(st.session_state.failures[doc.fingerprint])


def render_dashboard():
    st.subheader("2. Review & reconcile")
    if not st.session_state.records:
        st.info("Your extracted receipts will appear here. All processing runs on your laptop.")
        return
    ids = list(st.session_state.records)
    frame = pd.DataFrame(st.session_state.records.values())
    for col in MONEY_FIELDS:
        frame[col] = pd.to_numeric(frame[col], errors="coerce").astype(float)
    a, b, c = st.columns(3)
    a.metric("Receipts processed", len(frame))
    b.metric("Total expenses", f"₹{frame.TotalAmount.sum():,.2f}")
    c.metric("Total tax component", f"₹{frame.TaxAmount.sum():,.2f}")
    st.caption("Totals include known amounts only. Blank amounts are unknown, not zero. Review model output against the original receipt.")
    frame["InvoiceDate"] = pd.to_datetime(frame.InvoiceDate, errors="coerce").dt.date
    config = {
        "SourceFile": st.column_config.TextColumn("Source file"),
        "VendorName": st.column_config.TextColumn("Vendor name"),
        "InvoiceDate": st.column_config.DateColumn("Invoice date", format="YYYY-MM-DD"),
        "TaxHead": st.column_config.SelectboxColumn("Expense category", options=list(CATEGORIES)),
        "GSTIN": st.column_config.TextColumn("Vendor GSTIN"),
        "LineItems": st.column_config.TextColumn("Line item summary", width="large"),
        "Reviewed": st.column_config.CheckboxColumn("Reviewed"),
        **{col: st.column_config.NumberColumn({"Subtotal": "Subtotal (INR)", "TaxAmount": "Tax (INR)", "TotalAmount": "Total (INR)"}[col], format="%.2f", step=0.01) for col in MONEY_FIELDS},
    }
    editor_key = f"editor_{st.session_state.editor_version}"
    st.data_editor(frame, key=editor_key, column_config=config, disabled=["SourceFile"], hide_index=True,
                   use_container_width=True, on_change=commit_edits, args=(editor_key, ids))
    issues = []
    for row in st.session_state.records.values():
        warnings = review_issues(row)
        if warnings:
            issues.append(f"{row['SourceFile']}: " + " ".join(warnings))
    if st.session_state.audit:
        with st.expander("Original extraction notes"):
            for audit in st.session_state.audit.values():
                for note in audit["warnings"]:
                    st.caption(f"{audit['source_file']}: {note}")
    if issues:
        with st.expander(f"Review notes · {len(issues)} receipt(s)", expanded=True):
            for warning in issues:
                st.warning(warning)
    st.subheader("3. Export for your accountant")
    unreviewed = sum(not row["Reviewed"] for row in st.session_state.records.values())
    if unreviewed:
        st.warning(f"{unreviewed} receipt(s) are not marked reviewed. Exports include their review status.")
    export_frame = pd.DataFrame(st.session_state.records.values())
    left, right = st.columns(2)
    left.download_button("Download accounting CSV", export_to_csv(export_frame), "localreceipts_expenses.csv", "text/csv", use_container_width=True)
    right.download_button("Download JSON backup", export_to_json(export_frame, st.session_state.audit), "localreceipts_backup.json", "application/json", use_container_width=True)
    st.caption("INR expense register for accountant review. Not a GST return or a determination of input tax credit eligibility. JSON includes original extraction and edits, not source images.")


def main():
    initialize()
    model = render_sidebar()
    st.title("From messy bills to clear books.")
    st.caption("LOCALRECEIPTS AI  /  YOUR PRIVATE EXPENSE WORKSPACE")
    st.write("Extract receipts on your laptop, correct the details, and send a clean expense register to your CA.")
    docs = render_uploads()
    process_documents(docs, model)
    st.divider()
    render_dashboard()


if __name__ == "__main__":
    main()
