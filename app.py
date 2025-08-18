
import streamlit as st, io, re, time
from typing import Optional, List, Tuple
from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.lib import colors
import pandas as pd
import requests

# Optional PDF text extractor
try:
    import pdfplumber
except Exception:
    pdfplumber = None

# ---------- Robust asset loading ----------
APP_DIR = Path(__file__).parent
ASSETS = APP_DIR / "assets"

def safe_image(path: Path, width=None):
    if path.exists():
        st.image(str(path), width=width)
    else:
        st.markdown(f"<div style='color:#B91C1C;font-weight:600'>Missing asset: {path.as_posix()}</div>", unsafe_allow_html=True)

st.set_page_config(page_title="FlashDecky — study cards from any list",
                   page_icon=str(ASSETS / "icon.png"),
                   layout="wide")

css_path = APP_DIR / "flashdecky_header.css"
if css_path.exists():
    st.markdown(f"<style>{css_path.read_text()}</style>", unsafe_allow_html=True)

# Header (extra space div avoids clipping on some themes)
st.markdown('<div class="fd-header-space"></div>', unsafe_allow_html=True)
c1, c2 = st.columns([1,5])
with c1: safe_image(ASSETS / "icon.png", width=64)
with c2: safe_image(ASSETS / "wordmark.png", width=360)
st.markdown("<hr/>", unsafe_allow_html=True)

# ---------- Steps ----------
st.session_state.setdefault("step", 1)
st.session_state.setdefault("pairs", [])
st.session_state.setdefault("extracted_text", "")

with st.sidebar:
    st.markdown("### Progress")
    steps = ["1) Upload/Paste", "2) Review and edit", "3) Download PDF"]
    for i, label in enumerate(steps, start=1):
        st.write(("✅ " if st.session_state.step>i else "➡️ " if st.session_state.step==i else "○ ") + label)

# ---------- Extraction helpers ----------
OCR_SPACE_ENDPOINT = "https://api.ocr.space/parse/image"

def ocr_space_extract(file_bytes: bytes, is_pdf=False, api_key: Optional[str]=None, retries=3, backoff=1.3) -> Optional[str]:
    key = api_key or "helloworld"
    files = {"file": ("upload.pdf" if is_pdf else "upload.png", file_bytes)}
    data = {"language":"eng","isOverlayRequired":"false","OCREngine":"2","scale":"true","detectOrientation":"true"}
    for attempt in range(retries):
        try:
            r = requests.post(OCR_SPACE_ENDPOINT, files=files, data=data, headers={"apikey": key}, timeout=30)
            if r.status_code == 200:
                js = r.json()
                if not js.get("IsErroredOnProcessing"):
                    texts = [p.get("ParsedText","") for p in (js.get("ParsedResults") or [])]
                    out = "\n".join(texts).strip()
                    if out: return out
            time.sleep(backoff * (attempt + 1))
        except Exception:
            time.sleep(backoff * (attempt + 1))
    return None

def pdf_text_extract(file_bytes: bytes) -> Optional[str]:
    if not pdfplumber: return None
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            chunks = []
            for p in pdf.pages:
                t = p.extract_text() or ""
                if t.strip(): chunks.append(t)
            return ("\n".join(chunks)).strip() or None
    except Exception:
        return None

def auto_extract(file_bytes: bytes, filename: str, api_key: Optional[str]) -> str:
    is_pdf = filename.lower().endswith(".pdf")
    if is_pdf:
        txt = pdf_text_extract(file_bytes) or ""
        if len(txt.strip()) >= 20:
            return txt
        return ocr_space_extract(file_bytes, is_pdf=True, api_key=api_key) or ""
    else:
        return ocr_space_extract(file_bytes, is_pdf=False, api_key=api_key) or ""

# ---------- Parsing ----------
SEP_PATTERN = re.compile(
    r'^\s*(?:\d+[\.\)]\s*)?(?:[•\-]\s*)?(?P<term>.+?)\s*(?:[\-\u2013\u2014:])\s+(?P<def>.+)\s*$'
)
def parse_pairs_from_text(txt: str) -> List[Tuple[str,str]]:
    raw_lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
    pairs: List[Tuple[str,str]] = []
    last_idx = -1
    for ln in raw_lines:
        m = SEP_PATTERN.match(ln)
        if m:
            term = m.group("term").strip()
            definition = m.group("def").strip()
            pairs.append((term, definition))
            last_idx = len(pairs)-1
        else:
            if last_idx >= 0:
                t, d = pairs[last_idx]
                sep = "" if d.endswith(('-', '–', '—')) else " "
                pairs[last_idx] = (t, (d + sep + ln).strip())
            else:
                pairs.append((ln, "")); last_idx = len(pairs)-1
    return pairs

# ---------- PDF generation ----------
PAGE = letter
COLS, ROWS = 2, 4
CARD_W, CARD_H = PAGE[0]/COLS, PAGE[1]/ROWS
CHUNK = COLS * ROWS

def wrap_lines(text, max_w, fnt="Helvetica", size=11):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        cand = (cur + " " + w).strip()
        if stringWidth(cand, fnt, size) <= max_w: cur = cand
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    return lines

def draw_cut_grid(c):
    c.setLineWidth(0.5); c.setDash(3,3); c.setStrokeColor(colors.grey)
    for i in range(1, COLS): c.line(i*CARD_W, 0, i*CARD_W, PAGE[1])
    for j in range(1, ROWS): c.line(0, j*CARD_H, PAGE[0], j*CARD_H)
    c.setDash()

def draw_index(c, idx, xc, yc, show_marker: bool):
    if not show_marker: return
    c.setFont("Helvetica", 7); c.setFillColor(colors.grey)
    c.drawRightString(xc + CARD_W/2 - 6, yc - CARD_H/2 + 8, f"#{idx+1}")

def draw_footer(c, text, x_right, y_bottom):
    if not text: return
    c.setFont("Helvetica", 8); c.setFillColor(colors.grey)
    c.drawRightString(x_right - 6, y_bottom + 6, text)

def make_footer_text(template: str, subject: str, lesson: str) -> str:
    try:
        return template.format(subject=subject.strip(), lesson=lesson.strip()).strip()
    except Exception:
        return f"{subject.strip()} • {lesson.strip()}".strip(" •")

def layout_front(c, batch, start_index, show_marker=False, footer_text=None):
    for i, item in enumerate(batch):
        idx = start_index + i
        col = i % COLS; row = (i // COLS) % ROWS
        left = col*CARD_W; bottom = PAGE[1] - (row+1)*CARD_H
        xc = left + CARD_W/2
        yc = bottom + CARD_H/2
        term, definition = item
        c.setFont("Helvetica-Bold", 13); c.setFillColor(colors.black)
        c.drawCentredString(xc, yc-18, term)
        if footer_text:
            draw_footer(c, footer_text, left + CARD_W, bottom)
        draw_index(c, idx, xc, yc, show_marker)
    draw_cut_grid(c)

def layout_back(c, batch, start_index, long_edge=True, offset_mm=(0,0), spelling_mode=False, show_marker=False, footer_text=None):
    ox = offset_mm[0] * 2.83465; oy = offset_mm[1] * 2.83465
    c.saveState(); c.translate(ox, oy)
    rotate180 = not long_edge
    if rotate180:
        c.translate(PAGE[0], PAGE[1]); c.rotate(180)

    for i, item in enumerate(batch):
        term, definition = item
        col = i % COLS; row = (i // COLS) % ROWS
        if long_edge: col = (COLS-1) - col
        left = col*CARD_W; bottom = PAGE[1] - (row+1)*CARD_H
        xc = left + CARD_W/2
        yc = bottom + CARD_H/2

        if spelling_mode or not definition:
            c.setStrokeColor(colors.black)
            for j in range(3):
                y = yc - 6 + j*12
                c.line(xc - CARD_W/2 + 10, y, xc + CARD_W/2 - 10, y)
        else:
            lines = wrap_lines(definition, CARD_W-24, "Helvetica", 11)
            c.setFont("Helvetica", 11); c.setFillColor(colors.black)
            start_y = yc + (len(lines)-1)*7
            y = start_y
            for line in lines:
                c.drawCentredString(xc, y, line); y -= 14

        if footer_text:
            draw_footer(c, footer_text, left + CARD_W, bottom)

        draw_index(c, start_index + i, xc, yc, show_marker)

    draw_cut_grid(c); c.restoreState()

def build_pdf(pairs, *, long_edge=True, offset_mm=(0,0), show_marker=False, spelling_mode=False, footer_text=None) -> bytes:
    buf = io.BytesIO(); c = canvas.Canvas(buf, pagesize=PAGE)
    start = 0; sheet = 1
    while start < len(pairs):
        batch = pairs[start:start+CHUNK]
        c.setFont("Helvetica", 8); c.setFillColor(colors.grey)
        c.drawString(20, PAGE[1]-12, f"Sheet {sheet} FRONT ({'Long-edge' if long_edge else 'Short-edge'})")
        layout_front(c, batch, start, show_marker=show_marker, footer_text=footer_text)
        c.showPage()

        c.setFont("Helvetica", 8); c.setFillColor(colors.grey)
        c.drawString(20, PAGE[1]-12, f"Sheet {sheet} BACK")
        layout_back(c, batch, start, long_edge, offset_mm, spelling_mode, show_marker, footer_text)
        c.showPage()

        start += CHUNK; sheet += 1
    c.save(); return buf.getvalue()

# ---------- UI controls (restored minimal set) ----------
with st.expander("Print alignment", expanded=False):
    c1, c2, c3 = st.columns(3)
    with c1:
        duplex = st.radio("Duplex mode", ["Long-edge (mirror backs)", "Short-edge (rotate backs)"])
        long_edge = duplex.startswith("Long")
    with c2:
        offx = st.number_input("Back alignment X (mm)", value=0.0, step=0.5, help="Shift backs RIGHT")
        offy = st.number_input("Back alignment Y (mm)", value=0.0, step=0.5, help="Shift backs UP")
    with c3:
        show_marker = st.checkbox("Show corner marker", value=False)

with st.expander("Card footer (subject • lesson)", expanded=False):
    enable_footer = st.checkbox("Add footer text on cards", value=True)
    subject = st.text_input("Subject", value="")
    lesson = st.text_input("Lesson", value="")
    templ = st.text_input("Footer template", value="{subject} • {lesson}")
    footer_text = make_footer_text(templ, subject, lesson) if enable_footer else None

# ---------- Step 1: Upload or paste ----------
if st.session_state.step == 1:
    st.header("1) Upload or paste your list")
    t1, t2 = st.tabs(["Paste text", "Upload screenshot/PDF"])

    with t1:
        default_example = "1. munch - to chew food loudly and\ncompletely\n2) bellowed — to have shouted in a loud\ndeep voice\n3 - rough: when you do something in a way that is not gentle."
        st.text_area("Your list", value=default_example, height=220, key="manual_text")

    with t2:
        up = st.file_uploader("Upload image or PDF", type=["png","jpg","jpeg","pdf"])
        st.caption("We’ll auto-choose the best extraction for you.")
        with st.expander("Advanced extraction options", expanded=False):
            ocr_api_key = st.text_input("OCR.space API key (optional)", type="password", help="Use your key to avoid demo limits.")

        if up is not None:
            file_bytes = up.read()
            with st.spinner("Extracting text…"):
                extracted = auto_extract(file_bytes, up.name, ocr_api_key)
            if not extracted.strip():
                st.warning("I couldn't read text from that file. Try a clearer image or paste the text instead.")
            st.session_state.extracted_text = extracted or st.session_state.get("extracted_text","")
            st.text_area("Extracted text (you can edit before parsing):", value=st.session_state.extracted_text, height=220, key="extracted_text_box")

    if st.button("Next: Review and edit", type="primary"):
        src = st.session_state.get("extracted_text_box") or st.session_state.get("manual_text") or ""
        st.session_state.pairs = parse_pairs_from_text(src)
        st.session_state.step = 2
        st.rerun()

# ---------- Step 2: Review and edit ----------
elif st.session_state.step == 2:
    st.header("2) Review and edit")
    pairs = st.session_state.get("pairs", [])
    if not pairs:
        st.warning("No items parsed yet. Go back and add a list.")
    else:
        df = pd.DataFrame(pairs, columns=["Term","Definition"]).fillna("")
        df["Term"] = df["Term"].astype(str)
        df["Definition"] = df["Definition"].astype(str)

        st.caption("Click a cell to edit. Add/remove rows if needed.")
        df = st.data_editor(df, num_rows="dynamic", use_container_width=True, key="editor_simple")
        st.session_state.pairs = [(str(r.Term).strip(), str(r.Definition).strip()) for r in df.itertuples(index=False)]

    c1, c2 = st.columns(2)
    if c1.button("⬅ Back"):
        st.session_state.step = 1; st.rerun()
    if c2.button("Next: Generate PDF", type="primary"):
        st.session_state.step = 3; st.rerun()

# ---------- Step 3: Download ----------
elif st.session_state.step == 3:
    st.header("3) Download your duplex-ready PDF")
    pairs = [(str(t or ""), str(d or "")) for t, d in st.session_state.get("pairs", [])]
    if not pairs:
        st.warning("No items to print. Go back and add a list.")
    else:
        pdf_bytes = build_pdf(
            pairs=pairs,
            long_edge=long_edge,
            offset_mm=(offx, offy),
            show_marker=show_marker,
            spelling_mode=False,
            footer_text=footer_text
        )
        st.success("PDF ready!")
        st.download_button("⬇ Download cards PDF", data=pdf_bytes, file_name="FlashDecky_cards.pdf", mime="application/pdf", type="primary")

        c1, c2 = st.columns(2)
        if c1.button("⬅ Back"):
            st.session_state.step = 2; st.rerun()
        if c2.button("Start over"):
            st.session_state.clear(); st.rerun()
