# LocalReceipts AI

A modular, offline Streamlit desktop utility for Indian freelancers and small businesses. PNG/JPEG bills and multi-page PDF invoices become an editable INR expense register, with CSV and JSON downloads.

## Install once (internet needed for packages and model weights)

Requires Python 3.10+ and a recent local [Ollama](https://ollama.com/) installation. Model memory requirements vary substantially; choose one that fits your machine. The default `llama3.2-vision` can be slow without sufficient GPU memory. `minicpm-v` and `llava` are alternatives.

From this directory in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
ollama pull llama3.2-vision
```

Set Ollama to local-only mode **before processing private documents**. Quit the Ollama tray application first, then start its server in a dedicated terminal:

```powershell
$env:OLLAMA_NO_CLOUD = "1"
$env:OLLAMA_HOST = "127.0.0.1:11434"
ollama serve
```

Keep that terminal open. If Ollama reports the port is in use, another Ollama instance is still running; exit it before restarting with these settings. Setting this variable only in the Streamlit terminal does not reconfigure an already-running Ollama server. See [Ollama's local-only configuration](https://docs.ollama.com/faq).

Launch from another terminal:

```powershell
.\start.ps1
```

Or use `.venv\Scripts\python.exe -m streamlit run app.py` from this directory. Open the local address printed in the terminal. On macOS/Linux use `.venv/bin/python -m streamlit run app.py`. Stop with Ctrl+C.

## Workflow

1. Select a downloaded vision model and check the local connection.
2. Upload a batch and inspect each file/page in the preview gallery.
3. Extract new receipts. Individual failures do not discard successful results; click Extract again to retry failed files. Identical file contents are not charged twice in the register, even under different names.
4. Correct fields in the editable table. Totals and exports update with edits. Mark each receipt Reviewed after comparing it with the original.
5. Download CSV for your accountant and/or a JSON backup containing current values, source fingerprints, original extraction, model name, and review notes. JSON does not include source images; retain originals separately.

One file must represent one invoice. For a multi-page invoice, put all pages in one PDF. PDFs are rendered locally with PyMuPDF; pages are extracted individually, then a local text pass reconciles one invoice record. Repeated page totals are not intentionally added. Multi-page results always need manual verification. Unrelated receipts bundled into one PDF must be split before upload.

GSTIN is a text identifier and is separate from the numeric `TaxAmount` (combined printed CGST/SGST or IGST and cess). Amounts are INR. Missing/invalid values remain blank rather than becoming zero. Unknown categories remain blank for review. Dates use ISO YYYY-MM-DD. The six categories are Software, Travel, Meals, Office Supplies, Utilities, Professional Services.

CSV uses UTF-8 with BOM, standard expense-register headers, two decimal places and spreadsheet formula-injection protection. JSON preserves unmodified text. Exports are accountant working papers, not a statutory GST filing format or a determination of deduction/input-credit eligibility. Currency conversion and separate CGST/SGST/IGST ledgers are not included.

## Privacy and operational limits

- Application requests go only to `127.0.0.1:11434`; the SDK ignores proxy environment variables and does not follow redirects. No analytics, cloud SDK, remote fonts, or external UI assets are added. Streamlit usage telemetry is disabled.
- Cloud-named and remote-backed models are rejected before images are submitted. Use Ollama local-only mode as described above for server-side protection, including custom model aliases. A compromised or independently reconfigured Ollama server is outside the app's trust boundary.
- Streamlit binds to loopback. Do not expose this single-user desktop app on a public interface or reverse proxy.
- No receipt files, raw responses, or financial rows are deliberately logged or persisted by the application. Session data lives in process memory and Streamlit's upload/media buffers; the OS may use swap. Clear all session data releases app references; stop the process for full session teardown. This is not secure memory erasure.
- No automatic model downloads, background uploads, or remote fallbacks occur. After installation and model download, the app works without an internet connection.
- 20 MB/file, 20 files and 100 MB/batch, 12 pages/PDF, 30 megapixels/image. Images are converted to RGB JPEG at up to 2200 px on the longest side; very fine print may require a tighter scan/crop. Encrypted PDFs must be unlocked first.
- Inference timeout is five minutes per model request. A timed-out server job may continue in Ollama. Extraction is sequential to avoid concurrent GPU memory pressure. Stop Streamlit/Ollama to cancel a long-running job.
- Model OCR and categorization are probabilistic. Review every invoice; a valid JSON schema does not establish financial correctness. Session data is not durable across server restarts/browser-session resets. There is no JSON restore/import UI in this version.

## Code layout

- `app.py`: sidebar, uploads, previews, extraction orchestration, editor state and dashboard.
- `localreceipts/documents.py`: bounded PDF/image decoding in memory.
- `localreceipts/extraction.py`: local Ollama client, model checks, structured prompts and multi-page reconciliation.
- `localreceipts/schema.py`: safe JSON cleanup, amount/date normalization and review flags.
- `localreceipts/exports.py`: accounting CSV and JSON backup serializers.
- `tests/`: synthetic document, mocked inference, validation, privacy, export and Streamlit checks.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

Tests never require real receipts, internet or model weights. Before relying on OCR, perform a local acceptance pass with representative scans, faded thermal receipts and multi-page invoices on your chosen model. Confirm that edits affect both downloads and disconnect internet access to verify offline operation.

The bounded dependency ranges in `requirements.txt` support Python 3.10+. `requirements-lock.txt`, when present, records the exact environment used in validation; it is a reproducibility snapshot for that Python/platform, not a universal cross-platform lock.

For a synthetic live-model check (fictional data, local inference only):

```powershell
.\.venv\Scripts\python.exe scripts\smoke_local_model.py --model llama3.2-vision
```

PyMuPDF and PyArrow are pinned to official releases verified to load under this Windows machine's Application Control policy. No system security settings were changed.
