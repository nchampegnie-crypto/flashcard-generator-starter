
import io, re, math, json, base64, pathlib, textwrap
from typing import List, Tuple
import streamlit as st
import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.pdfbase.pdfmetrics import stringWidth
from pdfminer.high_level import extract_text
from PIL import Image

APP_TITLE = "FlashDecky – Study Card Generator"
BRAND_CSS = pathlib.Path("styles.css").read_text() if pathlib.Path("styles.css").exists() else ""

def inject_css():
    st.markdown(f"<style>{BRAND_CSS}</style>", unsafe_allow_html=True)

def mm_to_points(mm: float) -> float:
    return mm * 72.0 / 25.4

# ---------------------- PARSING ----------------------

DELIMS = [" — ", " – ", " - ", " : ", " :",
          " —", " –", " -", ":", "—", "–", "-"]

def smart_split_term_def(line: str) -> Tuple[str, str]:
    s = line.strip()
    # remove leading numbering like "1. " or "3) " or "3 - "
    s = re.sub(r'^\s*\d+\s*[\.\)\-–—]\s*', '', s)
    # 1) Try common explicit delimiters
    for d in [" - ", " — ", " – ", ":", " : "]:
        if d in s:
            parts = s.split(d, 1)
            return parts[0].strip(), parts[1].strip()
    # 2) Try vocab-style "word (v.) rest-of-definition"
    m = re.match(r'^\s*([A-Za-z][A-Za-z\'\-]*)\s*\(([^)]+)\)\s*(.+)$', s)
    if m:
        term = m.group(1).strip()
        definition = f"({m.group(2).strip()}) {m.group(3).strip()}"
        return term, definition
    # 3) Fallback: first word is term, rest is definition
    parts = s.split(None, 1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    else:
        return s, ""

def split_into_items(raw: str) -> List[str]:
    t = raw.replace("\r\n", "\n")
    t = re.sub(r'\n{2,}', '\n', t)
    # Primary: split when a new numbered item appears
    items = re.split(r'\n(?=\s*\d+[\.\)]\s+)', t.strip())
    if len(items) > 1:
        return [x.strip() for x in items if x.strip()]
    # Secondary: split when a line looks like a term start (word + delimiter)
    items = re.split(r'\n(?=[A-Za-z][^\n]{0,50}?(?:\s[\-–—:]\s|\s\([^)]+\)))', t.strip())
    return [x.strip() for x in items if x.strip()]

def parse_text_to_df(raw: str) -> pd.DataFrame:
    items = split_into_items(raw)
    terms, defs = [], []
    for it in items:
        term, definition = smart_split_term_def(it)
        if term or definition:
            terms.append(term)
            defs.append(definition)
    return pd.DataFrame({"Front of Flash Card (term)": terms,
                         "Back of Flash Card (definition)": defs})

# ---------------------- OCR / FILE INGEST ----------------------

def ocrspace_image(img_bytes: bytes, api_key: str) -> str:
    import requests
    url = "https://api.ocr.space/parse/image"
    files = {"filename": ("upload.png", img_bytes, "application/octet-stream")}
    data = {"language": "eng", "isOverlayRequired": False}
    headers = {"apikey": api_key}
    r = requests.post(url, files=files, data=data, headers=headers, timeout=60)
    r.raise_for_status()
    js = r.json()
    if js.get("IsErroredOnProcessing"):
        raise RuntimeError(js.get("ErrorMessage") or "OCR error")
    parsed = js.get("ParsedResults", [{}])[0].get("ParsedText", "")
    return parsed

def read_pdf_text(file_bytes: bytes) -> str:
    with io.BytesIO(file_bytes) as fp:
        text = extract_text(fp)
    return text or ""

# ---------------------- PDF LAYOUT ----------------------

def draw_dashed_guides(c, x, y, w, h):
    c.setStrokeColor(colors.lightgrey)
    c.setDash(6, 6)
    c.rect(x, y, w, h, stroke=1, fill=0)
    c.setDash()  # solid again

def wrap_text(text: str, font: str, size: float, max_width: float) -> List[str]:
    words = text.split()
    lines = []
    cur = ""
    for w in words:
        test = (cur + " " + w).strip()
        if stringWidth(test, font, size) <= max_width:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines

def create_cards_pdf(df: pd.DataFrame,
                     duplex_mode: str = "Long-edge (mirrored back)",
                     back_offset_x_mm: float = 0.0,
                     back_offset_y_mm: float = 0.0,
                     footer_text: str = "",
                     show_corner: bool = False) -> bytes:
    PAGE_W, PAGE_H = letter  # portrait
    MARGIN = 18  # points
    COLS, ROWS = 2, 4  # 8 cards (2 columns x 4 rows)
    card_w = (PAGE_W - 2*MARGIN) / COLS
    card_h = (PAGE_H - 2*MARGIN) / ROWS

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)

    # Prepare list of items
    records = df.to_dict("records")

    # ---- FRONT PAGES ----
    for i in range(0, len(records), COLS * ROWS):
        slice_rows = records[i:i + COLS * ROWS]
        # draw grid of cards (front: term)
        for idx, rec in enumerate(slice_rows):
            r = idx // COLS
            col = idx % COLS
            x = MARGIN + col * card_w
            y = PAGE_H - MARGIN - (r + 1) * card_h
            draw_dashed_guides(c, x, y, card_w, card_h)

            # term
            term = str(rec.get("Front of Flash Card (term)", "")).strip()
            c.setFont("Helvetica-Bold", 18)
            tw = stringWidth(term, "Helvetica-Bold", 18)
            c.drawCentredString(x + card_w/2, y + card_h/2 + 10, term[:120])

            # footer
            if footer_text:
                c.setFont("Helvetica", 8)
                c.setFillColor(colors.grey)
                c.drawRightString(x + card_w - 6, y + 6, footer_text)
                c.setFillColor(colors.black)

            # tiny corner marker (front)
            if show_corner:
                c.circle(x + 6, y + 6, 1.5, stroke=1, fill=1)

        c.showPage()

        # ---- BACK PAGE for same slice: definitions ----
        # Compute mirrored or normal mapping
        if duplex_mode == "Long-edge (mirrored back)":
            def map_idx(j):
                r = j // COLS
                col = j % COLS
                col_b = (COLS - 1) - col  # mirror horizontally
                return r * COLS + col_b
        else:
            def map_idx(j):  # no mirroring
                return j

        # draw defs
        for idx, rec in enumerate(slice_rows):
            mapped = map_idx(idx)
            r = mapped // COLS
            col = mapped % COLS
            x = MARGIN + col * card_w + mm_to_points(back_offset_x_mm)
            y = PAGE_H - MARGIN - (r + 1) * card_h + mm_to_points(back_offset_y_mm)

            draw_dashed_guides(c, x, y, card_w, card_h)

            definition = str(rec.get("Back of Flash Card (definition)", "")).strip()
            # wrap definition
            c.setFont("Helvetica", 11)
            max_w = card_w - 14
            lines = wrap_text(definition, "Helvetica", 11, max_w)
            top = y + card_h - 20
            for li, line in enumerate(lines[:12]):
                c.drawString(x + 7, top - li * 14, line)

            if footer_text:
                c.setFont("Helvetica", 8)
                c.setFillColor(colors.grey)
                c.drawRightString(x + card_w - 6, y + 6, footer_text)
                c.setFillColor(colors.black)

            if show_corner:
                c.circle(x + 6, y + 6, 1.5, stroke=1, fill=1)

        c.showPage()

    c.save()
    return buf.getvalue()

# ---------------------- UI ----------------------

def header():
    st.title(APP_TITLE)

def step_upload():
    st.subheader("1) Upload or paste your list")
    tabs = st.tabs(["Paste text", "Upload screenshot/PDF", "Spreadsheet / Paste table"])

    # Paste text
    with tabs[0]:
        raw_text = st.text_area("Your list", value=st.session_state.get("raw_text", ""),
                                placeholder="Paste terms + definitions here (e.g., '1. term – definition').",
                                height=220, key="raw_text")
        if st.button("Next: Review and edit", key="go_from_paste"):
            st.session_state["stage"] = "review"

    # Upload screenshot/PDF
    with tabs[1]:
        up = st.file_uploader("Upload image or PDF", type=["png","jpg","jpeg","pdf"])
        st.caption("We'll auto-choose the best extraction for you.")
        with st.expander("Advanced extraction options"):
            ocr_key = st.text_input("OCR.space API key (optional)",
                                    value=st.session_state.get("ocr_key",""),
                                    type="password", key="ocr_key")

        if up is not None:
            data = up.read()
            text = ""
            if up.type == "application/pdf" or up.name.lower().endswith(".pdf"):
                try:
                    text = read_pdf_text(data)
                except Exception as e:
                    st.error(f"PDF text extraction failed: {e}")
            else:
                if ocr_key:
                    try:
                        text = ocrspace_image(data, ocr_key)
                    except Exception as e:
                        st.error(f"OCR failed: {e}")
                else:
                    st.info("Image uploaded. Add an OCR.space API key (in Advanced) to extract text automatically, "
                            "or paste your list in the 'Paste text' tab.")
            if text:
                st.session_state["raw_text"] = text
                st.success("Text extracted! Switch to **Paste text** tab to review or click below.")
                if st.button("Use extracted text and continue", key="go_from_extract"):
                    st.session_state["stage"] = "review"

    # Spreadsheet / paste table
    with tabs[2]:
        mode = st.radio("Choose input method", ["Upload CSV/XLSX", "Paste table"], horizontal=True)
        if mode == "Upload CSV/XLSX":
            f = st.file_uploader("Upload a CSV or Excel file with two columns: term, definition",
                                 type=["csv","xlsx"], key="sheet_up")
            if f is not None:
                try:
                    if f.name.lower().endswith(".csv"):
                        df = pd.read_csv(f)
                    else:
                        df = pd.read_excel(f)
                    st.dataframe(df.head())
                    # normalize columns
                    cols = [c.strip().lower() for c in df.columns.tolist()]
                    if len(cols) >= 2:
                        df2 = pd.DataFrame({
                            "Front of Flash Card (term)": df.iloc[:,0].astype(str).fillna(""),
                            "Back of Flash Card (definition)": df.iloc[:,1].astype(str).fillna("")
                        })
                        st.session_state["cards_df"] = df2
                        if st.button("Next: Review and edit", key="go_from_sheet"):
                            st.session_state["stage"] = "review"
                    else:
                        st.warning("Need at least two columns (term, definition).")
                except Exception as e:
                    st.error(f"Could not read file: {e}")
        else:
            st.caption("Paste a 2‑column table (TERM | DEFINITION). One row per card.")
            pasted = st.text_area("Paste table here", height=160, key="pasted_table")
            if st.button("Parse table", key="parse_table"):
                rows = []
                for line in pasted.splitlines():
                    parts = [p.strip() for p in re.split(r'\t+|\s{2,}|\|', line) if p.strip()]
                    if len(parts) >= 2:
                        rows.append((parts[0], " ".join(parts[1:])))
                if rows:
                    df2 = pd.DataFrame(rows, columns=["Front of Flash Card (term)",
                                                      "Back of Flash Card (definition)"])
                    st.session_state["cards_df"] = df2
                    st.session_state["stage"] = "review"
                else:
                    st.warning("No valid rows found (need 2+ columns per line).")

def step_review():
    st.subheader("2) Review and edit")
    # Determine source df
    df_cards = st.session_state.get("cards_df")
    if df_cards is None:
        raw = st.session_state.get("raw_text","").strip()
        if raw:
            df_cards = parse_text_to_df(raw)
        else:
            df_cards = pd.DataFrame({"Front of Flash Card (term)": [], "Back of Flash Card (definition)": []})
    st.dataframe(df_cards, use_container_width=True, hide_index=True)
    st.caption("Click a cell to edit. Add/remove rows if needed via the context menu (⋯) in the table toolbar.")
    st.session_state["cards_df"] = df_cards

def step_download():
    st.subheader("3) Download PDF")

    with st.expander("Print alignment", expanded=True):
        duplex_mode = st.selectbox("Duplex mode",
                                   ["Long-edge (mirrored back)", "Long-edge (not mirrored)"],
                                   index=0, key="duplex_mode")
        colx, coly = st.columns(2)
        back_offset_x = colx.number_input("Back page offset X (mm)", value=0.00, step=0.10, key="offset_x")
        back_offset_y = coly.number_input("Back page offset Y (mm)", value=0.00, step=0.10, key="offset_y")
        show_corner = st.checkbox("Show tiny corner marker", value=False, key="corner_mark")

    st.markdown("### Card footer (subject • lesson)")
    enable_footer = st.checkbox("Include footer text on cards",
                                value=st.session_state.get("include_footer", True),
                                key="include_footer")
    col1, col2 = st.columns(2)
    subject = col1.text_input("Subject", value=st.session_state.get("footer_subject",""),
                              key="footer_subject", disabled=not enable_footer)
    lesson = col2.text_input("Lesson", value=st.session_state.get("footer_lesson",""),
                             key="footer_lesson", disabled=not enable_footer)
    template = st.text_input("Footer template",
                             value=st.session_state.get("footer_template","{subject} • {lesson}"),
                             key="footer_template", disabled=not enable_footer)
    footer_text = ""
    if enable_footer:
        footer_text = template.replace("{subject}", subject).replace("{lesson}", lesson)

    if st.button("Generate PDF", type="primary"):
        df = st.session_state.get("cards_df")
        if df is None:
            raw = st.session_state.get("raw_text","").strip()
            if raw:
                df = parse_text_to_df(raw)
            else:
                st.warning("Please provide some cards first.")
                return
        pdf_bytes = create_cards_pdf(
            df,
            duplex_mode=duplex_mode,
            back_offset_x_mm=float(back_offset_x),
            back_offset_y_mm=float(back_offset_y),
            footer_text=footer_text,
            show_corner=show_corner
        )
        st.success("PDF generated!")
        st.download_button("Download PDF", data=pdf_bytes, file_name="flashdecky_cards.pdf",
                           mime="application/pdf")

def main():
    inject_css()
    header()
    stage = st.session_state.get("stage","upload")
    if stage == "upload":
        step_upload()
    if stage in ("upload","review"):
        # Show review if user already parsed via sheet tab
        if stage == "review" or st.session_state.get("cards_df") is not None or st.session_state.get("raw_text"):
            step_review()
    if st.session_state.get("cards_df") is not None or st.session_state.get("raw_text"):
        step_download()

if __name__ == "__main__":
    main()
