# FlashDecky – Study Card Generator (v3.4.0)

A simple Streamlit app that converts your lists into **8-up** double‑sided printable index cards (US Letter).

## Features
- Paste text, upload screenshot/PDF (optional OCR key), or import spreadsheet.
- Robust parsing for multiple list formats:
  - `1. term - definition`
  - `term: definition`
  - `term (v.) definition` (vocab-style dictionaries)
- Print alignment controls (duplex mode, back-page X/Y offsets, corner markers).
- Long-edge duplex **mirrored backs** default (so fronts/backs align).
- Optional footer: `{subject} • {lesson}` (fully editable) printed on each card.
- Clean white UI and readable controls.

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy to Streamlit Cloud
1. Push these files to a GitHub repo.
2. On streamlit.io, click **Deploy**, set `app.py` as the main file.
3. (Optional) To enable OCR for screenshots, add an **OCR_SPACE_API_KEY** secret (or paste it in the app when needed).

## Notes
- For PDFs that already contain selectable text, OCR is not required.
- For images/screenshots, you can paste an OCR.space API key in the app to enable image OCR. Without a key, the app will still work for text/CSV/XLSX or text-based PDFs.
