
import streamlit as st, hashlib, io, time, re, json, pathlib
from typing import Optional, List, Tuple
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.pdfbase.pdfmetrics import stringWidth
import pandas as pd

try:
    import pdfplumber
except Exception:
    pdfplumber = None

import requests

# ---- Branding ----
st.set_page_config(page_title="FlashDecky — study cards from any list", page_icon="assets/icon.png", layout="wide")
st.markdown(pathlib.Path("flashdecky_header.css").read_text(), unsafe_allow_html=True)
col1, col2 = st.columns([1,5])
with col1:
    st.image("assets/icon.png", width=64)
with col2:
    st.image("assets/wordmark.png", width=360)
st.markdown("<hr/>", unsafe_allow_html=True)

# ---- Steps ----
st.session_state.setdefault("step", 1)
st.session_state.setdefault("extracted_text", "")
st.session_state.setdefault("pairs", [])

with st.sidebar:
    st.markdown("### Progress")
    steps = ["1) Upload/Paste", "2) Review & Fix", "3) Download PDF"]
    for i, label in enumerate(steps, start=1):
        st.write(("✅ " if st.session_state.step>i else "➡️ " if st.session_state.step==i else "○ ") + label)

# ---- OCR helpers ----
OCR_SPACE_ENDPOINT = "https://api.ocr.space/parse/image"

def ocr_space_extract(file_bytes: bytes, is_pdf=False, api_key: Optional[str]=None, retries=3, backoff=1.3) -> Optional[str]:
    key = api_key or "helloworld"
    files = {"file": ("upload.pdf" if is_pdf else "upload.png", file_bytes)}
    data = {"language":"eng","isOverlayRequired":"false","OCREngine":"2","scale":"true","detectOrientation":"true"}
    last_err = None
    for attempt in range(retries):
        try:
            resp = requests.post(OCR_SPACE_ENDPOINT, files=files, data=data, headers={"apikey": key}, timeout=30)
            if resp.status_code == 200:
                js = resp.json()
                if not js.get("IsErroredOnProcessing"):
                    texts = [r.get("ParsedText","") for r in (js.get("ParsedResults") or [])]
                    out = "\n".join(texts).strip()
                    if out:
                        return out
            time.sleep(backoff * (attempt + 1))
        except Exception as e:
            last_err = e
            time.sleep(backoff * (attempt + 1))
    return None

def pdf_text_extract(file_bytes: bytes) -> Optional[str]:
    if not pdfplumber:
        return None
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            chunks = []
            for page in pdf.pages:
                t = page.extract_text() or ""
                if t.strip(): chunks.append(t)
            return ("\n".join(chunks)).strip() or None
    except Exception:
        return None

# ---- Parsing ----
SEP_PATTERN = re.compile(
    r"""^\s*(?:\d+[\.\)]\s*)?(?:[•\-]\s*)?(?P<term>.+?)\s*(?:[\-\u2013\u2014:])\s+(?P<def>.+)\s*$""",
    re.VERBOSE
)
def parse_pairs_from_text(txt: str) -> List[Tuple[str,str,Optional[str]]]:
    raw_lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
    pairs: List[Tuple[str,str,Optional[str]]] = []
    last_idx = -1
    for ln in raw_lines:
        m = SEP_PATTERN.match(ln)
        if m:
            term = m.group("term").strip()
            definition = m.group("def").strip()
            pairs.append((term, definition, None))
            last_idx = len(pairs)-1
        else:
            if last_idx >= 0:
                t, d, meta = pairs[last_idx]
                sep = "" if d.endswith(('-', '–', '—')) else " "
                pairs[last_idx] = (t, (d + sep + ln).strip(), meta)
            else:
                pairs.append((ln, "", None)); last_idx = len(pairs)-1
    return pairs

# ---- PDF generation ----
PAGE = letter
COLS, ROWS = 2, 4
CARD_W, CARD_H = PAGE[0]/COLS, PAGE[1]/ROWS
CHUNK = COLS * ROWS

def wrap_lines(text, max_w, fnt="Helvetica", size=11):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        cand = (cur + " " + w).strip()
        from reportlab.pdfbase.pdfmetrics import stringWidth
        if stringWidth(cand, fnt, size) <= max_w:
            cur = cand
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    return lines

def draw_cut_grid(c):
    from reportlab.lib import colors
    c.setLineWidth(0.5); c.setDash(3,3); c.setStrokeColor(colors.grey)
    for i in range(1, COLS): c.line(i*CARD_W, 0, i*CARD_W, PAGE[1])
    for j in range(1, ROWS): c.line(0, j*CARD_H, PAGE[0], j*CARD_H)
    c.setDash()

def compose_marker(idx:int, subject:Optional[str], lesson:Optional[str]) -> str:
    parts = []
    if subject: parts.append(str(subject).strip())
    if lesson: parts.append(str(lesson).strip())
    parts.append(f"#{idx+1}")
    return " ".join(parts)

def draw_index(c, idx, xc, yc, subject: Optional[str], lesson: Optional[str], show_marker: bool):
    from reportlab.lib import colors
    if not show_marker: return
    c.setFont("Helvetica", 7); c.setFillColor(colors.grey)
    tag = compose_marker(idx, subject, lesson)
    c.drawRightString(xc + CARD_W/2 - 6, yc - CARD_H/2 + 8, tag)

def layout_front(c, batch, start_index, show_marker=True, subject=None, lesson=None,
                 show_subtext=False, subtext_tmpl=""):
    for i, item in enumerate(batch):
        idx = start_index + i
        col = i % COLS; row = (i // COLS) % ROWS
        xc = col*CARD_W + CARD_W/2
        yc = PAGE[1] - (row*CARD_H + CARD_H/2)
        term, definition, _ = item
        c.setFont("Helvetica-Bold", 13); c.setFillColorRGB(0,0,0)
        c.drawCentredString(xc, yc-18, term)
        if show_subtext and (subtext_tmpl.strip() or subject or lesson):
            sub = (subtext_tmpl or "{subject} • {lesson}").format(subject=subject or "", lesson=lesson or "", index=idx+1).strip(" •")
            c.setFont("Helvetica", 9); c.setFillColorRGB(.4,.4,.4)
            c.drawCentredString(xc, yc-32, sub)
        draw_index(c, idx, xc, yc, subject, lesson, show_marker)
    draw_cut_grid(c)

def layout_back(c, batch, start_index, long_edge=True, offset_mm=(0,0),
                spelling_mode=False, show_marker=True, subject=None, lesson=None,
                show_subtext_on_back=False, subtext_tmpl=""):
    from reportlab.lib import colors
    ox = offset_mm[0] * 2.83465; oy = offset_mm[1] * 2.83465
    c.saveState(); c.translate(ox, oy)
    rotate180 = not long_edge
    if rotate180:
        c.translate(PAGE[0], PAGE[1]); c.rotate(180)
    for i, item in enumerate(batch):
        term, definition, _ = item
        col = i % COLS; row = (i // COLS) % ROWS
        if long_edge: col = (COLS-1) - col
        xc = col*CARD_W + CARD_W/2
        yc = PAGE[1] - (row*CARD_H + CARD_H/2)
        if spelling_mode or not definition:
            c.setStrokeColorRGB(0,0,0)
            for j in range(3):
                y = yc - 6 + j*12
                c.line(xc - CARD_W/2 + 10, y, xc + CARD_W/2 - 10, y)
        else:
            lines = wrap_lines(definition, CARD_W-24, "Helvetica", 11)
            c.setFont("Helvetica", 11); c.setFillColorRGB(0,0,0)
            start_y = yc + (len(lines)-1)*7
            y = start_y
            for line in lines:
                c.drawCentredString(xc, y, line); y -= 14
        if show_subtext_on_back and (subtext_tmpl.strip() or subject or lesson):
            sub = (subtext_tmpl or "{subject} • {lesson}").format(subject=subject or "", lesson=lesson or "", index=start_index+i+1).strip(" •")
            c.setFont("Helvetica", 8); c.setFillColorRGB(.4,.4,.4)
            c.drawCentredString(xc, yc - CARD_H/2 + 16, sub)
        draw_index(c, start_index + i, xc, yc, subject, lesson, show_marker)
    draw_cut_grid(c); c.restoreState()

def build_pdf(pairs, title="FlashDecky Cards", long_edge=True, offset_mm=(0,0),
              show_marker=True, spelling_mode=False, subject=None, lesson=None,
              show_subtext=False, subtext_tmpl="", show_subtext_on_back=False, watermark=None) -> bytes:
    buf = io.BytesIO(); c = canvas.Canvas(buf, pagesize=PAGE)
    start = 0; sheet = 1
    while start < len(pairs):
        batch = pairs[start:start+CHUNK]
        c.setFont("Helvetica", 8); c.setFillColorRGB(.4,.4,.4)
        c.drawString(20, PAGE[1]-12, f"Sheet {sheet} FRONT ({'Long-edge' if long_edge else 'Short-edge'})")
        layout_front(c, batch, start, show_marker, subject, lesson, show_subtext, subtext_tmpl)
        if watermark: c.drawString(20, 20, watermark)
        c.showPage()
        c.setFont("Helvetica", 8); c.setFillColorRGB(.4,.4,.4)
        c.drawString(20, PAGE[1]-12, f"Sheet {sheet} BACK")
        layout_back(c, batch, start, long_edge, offset_mm, spelling_mode, show_marker, subject, lesson, show_subtext_on_back, subtext_tmpl)
        if watermark: c.drawString(20, 20, watermark)
        c.showPage()
        start += CHUNK; sheet += 1
    c.save(); return buf.getvalue()

# ---- Advanced options ----
with st.expander("Advanced print options", expanded=False):
    c1, c2, c3 = st.columns(3)
    with c1:
        duplex = st.radio("Duplex mode", ["Long-edge (mirror backs)", "Short-edge (rotate backs)"])
        long_edge = duplex.startswith("Long")
    with c2:
        offx = st.number_input("Back alignment X (mm)", value=0.0, step=0.5, help="Shift backs RIGHT")
        offy = st.number_input("Back alignment Y (mm)", value=0.0, step=0.5, help="Shift backs UP")
    with c3:
        show_marker = st.checkbox("Show corner marker", value=True)
    c4, c5 = st.columns(2)
    with c4:
        subject = st.text_input("Subject (optional)", value="", placeholder="e.g., Science or ELA")
        lesson = st.text_input("Lesson (optional)", value="", placeholder="e.g., Unit 2 Lesson 4")
    with c5:
        show_subtext = st.checkbox("Subtext under term (front)", value=False)
        subtext_tmpl = st.text_input("Subtext template", value="{subject} • {lesson}", help="Use {subject}, {lesson}, {index}")
        show_subtext_on_back = st.checkbox("Also show subtext on back", value=False)

# ---- Step 1 ----
if st.session_state.step == 1:
    st.header("1) Upload or paste your list")
    t1, t2 = st.tabs(["Paste text", "Upload screenshot/PDF"])
    with t1:
        default_example = "1. munch - to chew food loudly and\ncompletely\n2) bellowed — to have shouted in a loud\ndeep voice\n3 - rough: when you do something in a way that is not gentle."
        st.text_area("Your list", value=default_example, height=220, key="manual_text")
    with t2:
        up = st.file_uploader("Upload image or PDF (screenshot, photo, or PDF)", type=["png","jpg","jpeg","pdf"])
        ocr_method = st.radio("OCR method", ["OCR.space (recommended)","PDF text only"], index=0, horizontal=True)
        ocr_api_key = st.text_input("OCR.space API key (optional)", type="password")
        if up is not None:
            file_bytes = up.read()
            st.info("Extracting text…")
            if up.type == "application/pdf" or up.name.lower().endswith(".pdf"):
                if ocr_method.startswith("PDF text only"):
                    extracted = pdf_text_extract(file_bytes) or ""
                else:
                    extracted = ocr_space_extract(file_bytes, is_pdf=True, api_key=ocr_api_key) or ""
            else:
                if ocr_method.startswith("OCR.space"):
                    extracted = ocr_space_extract(file_bytes, is_pdf=False, api_key=ocr_api_key) or ""
                else:
                    extracted = ""
            if not extracted:
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Retry OCR"): st.rerun()
                with c2:
                    st.caption("Tip: Try **PDF text only** for exported PDFs or upload a sharper PNG at 150–200% zoom.")
            st.session_state.extracted_text = extracted or st.session_state.get("extracted_text","")
            st.text_area("Extracted text (edit before parsing):", value=st.session_state.extracted_text, height=220, key="extracted_text_box")

    if st.button("Next: Review & fix", type="primary"):
        src = st.session_state.get("extracted_text_box") or st.session_state.get("manual_text") or ""
        st.session_state.pairs = parse_pairs_from_text(src)
        st.session_state.step = 2
        st.rerun()

# ---- Step 2 ----
elif st.session_state.step == 2:
    st.header("2) Review & fix")
    pairs = st.session_state.get("pairs", [])
    if not pairs:
        st.warning("No items parsed yet. Go back and add a list.")
    else:
        df = pd.DataFrame(pairs, columns=["Term","Definition","Lesson"])
        df["Lesson"] = df["Lesson"].fillna("")
        st.caption("Click a cell to edit; add or remove rows as needed.")
        df = st.data_editor(df, num_rows="dynamic", use_container_width=True, key="editor")
        st.session_state.pairs = list(df[["Term","Definition","Lesson"]].itertuples(index=False, name=None))

        st.subheader("Preview (first 8 cards)")
        cols = st.columns(2)
        for i, (term, definition, _) in enumerate(st.session_state.pairs[:8]):
            with cols[i%2]:
                short = (definition[:120] + "…") if len(definition) > 120 else definition
                st.markdown("""
<div class="fd-preview-card">
  <div class="fd-term">{term}</div>
  <div class="fd-def">{short}</div>
</div>
""", unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    if c1.button("⬅ Back"):
        st.session_state.step = 1; st.rerun()
    if c2.button("Next: Generate PDF", type="primary"):
        st.session_state.step = 3; st.rerun()

# ---- Step 3 ----
elif st.session_state.step == 3:
    st.header("3) Download your duplex-ready PDF")
    pairs = st.session_state.get("pairs", [])
    if not pairs:
        st.warning("No items to print. Go back and add a list.")
    else:
        pdf_bytes = build_pdf(
            pairs=pairs, title="FlashDecky Cards",
            long_edge=globals().get("long_edge", True), offset_mm=(globals().get("offx",0.0), globals().get("offy",0.0)),
            show_marker=globals().get("show_marker", True), spelling_mode=False,
            subject=globals().get("subject","") or None, lesson=globals().get("lesson","") or None,
            show_subtext=globals().get("show_subtext", False), subtext_tmpl=globals().get("subtext_tmpl","{subject} • {lesson}"),
            show_subtext_on_back=globals().get("show_subtext_on_back", False),
            watermark=None
        )
        st.success("PDF ready!")
        st.markdown("""
<div class="footer-cta">
  <div style="display:flex;gap:12px;align-items:center;justify-content:flex-end;">
    <span style="opacity:.7">Ready?</span>
  </div>
</div>
""", unsafe_allow_html=True)
        st.download_button("⬇ Download cards PDF", data=pdf_bytes, file_name="FlashDecky_cards.pdf", mime="application/pdf", type="primary")
        c1, c2 = st.columns(2)
        if c1.button("⬅ Back"):
            st.session_state.step = 2; st.rerun()
        if c2.button("Start over"):
            st.session_state.clear(); st.rerun()
