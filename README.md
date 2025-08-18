# FlashDecky — study cards from any list (v3)
- 3‑step wizard (Upload → Review → Download)
- OCR retry + tips
- Robust parsing (bullets/numbers + —/–/-/: + continuation line join)
- Editable review table + mini 8-card preview
- Advanced print options (duplex, offsets, markers, subject/lesson, subtext)
- Sticky footer download CTA
- Brand header + theme

## Run locally
pip install -r requirements.txt
streamlit run app.py

## Deploy
Repo must include: app.py, requirements.txt, .streamlit/config.toml, assets/wordmark.png, assets/icon.png, flashdecky_header.css
Main file path: app.py
