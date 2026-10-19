# Validation notes

Validated on Windows with Python 3.13.15. Python 3.10+ is the source/dependency target; other Python/OS combinations were not executed here.

- `python -m pytest -q`: **35 passed**.
- `python -m compileall -q app.py localreceipts scripts`: passed.
- `python -m pip check`: no broken requirements.
- Streamlit started on `127.0.0.1:8501`; `/_stcore/health` returned `ok`.
- Streamlit AppTest verified empty state, model selection, dashboard, editing callback, persistence across reruns, download controls, and session clearing.
- Core tests covered JSON cleanup and malformed output; missing/invalid financial values; PDF rendering, page limits and password handling; image transparency; local-only transport; remote model metadata; model failures; multi-page reconciliation requests; CSV formula safety; and JSON backup values.
- The browser preview tool could not attach; no manual visual browser review is claimed.
- The installed `moondream:latest` model completed a synthetic receipt request but failed the amount-accuracy check. Do not treat JSON validity as OCR accuracy.

Windows Application Control blocked native libraries in PyMuPDF 1.28.2 and PyArrow 26.0.0. The official PyMuPDF 1.26.7 and PyArrow 19.0.1 releases loaded successfully and are pinned in requirements.txt. System security settings were not changed.

Use `scripts/smoke_local_model.py --model YOUR_LOCAL_MODEL` to repeat a synthetic live-model acceptance test. A pass on one synthetic image does not establish accuracy on real receipts or multi-page invoices. Test representative documents locally and review all extracted rows.

Live acceptance result: installed `qwen3.5:4b` passed the generated receipt test, returning the correct vendor, ISO date, Software category, null GSTIN, subtotal INR 1000.00, tax INR 180.00 and total INR 1180.00, with no normalization warnings. This model can be selected via Custom in the sidebar; the requested default remains llama3.2-vision.
