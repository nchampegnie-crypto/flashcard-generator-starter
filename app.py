
import io, textwrap
from typing import List, Tuple, Optional
import streamlit as st
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.pdfbase.pdfmetrics import stringWidth

# Optional deps
try:
    import pdfplumber
except Exception:
    pdfplumber = None

import requests

# ---------------- Minimal visual (optional): initials badge only ----------------
def icon_badge(c, cx, cy, txt="A", scale=1.0):
    r = 16*scale
    c.setFillColor(colors.lightgrey); c.circle(cx, cy, r, stroke=0, fill=1)
    c.setFillColor(colors.black); c.setFont("Helvetica-Bold", 14*scale)
    c.drawCentredString(cx, cy-5*scale, txt[:2].upper())

# ---------------- Layout constants ----------------
PAGE = letter
COLS, ROWS = 2, 4
CARD_W, CARD_H = PAGE[0]/COLS, PAGE[1]/ROWS
CHUNK = COLS * ROWS

def draw_cut_grid(c):
    c.setLineWidth(0.5); c.setDash(3,3); c.setStrokeColor(colors.grey)
    for i in range(1, COLS): c.line(i*CARD_W, 0, i*CARD_W, PAGE[1])
    for j in range(1, ROWS): c.line(0, j*CARD_H, PAGE[0], j*CARD_H)
    c.setDash()

def compose_marker(idx:int, subject:Optional[str], lesson:Optional[str]) -> str:
    parts = []
    if subject: parts.append(str(subject).strip())
    if lesson: parts.append(f"L{str(lesson).strip()}")
    parts.append(f"#{idx+1}")
    return " ".join(parts)

def draw_index(c, idx, xc, yc, subject: Optional[str], lesson: Optional[str], show_marker: bool):
    if not show_marker:
        return
    c.setFont("Helvetica", 7); c.setFillColor(colors.grey)
    tag = compose_marker(idx, subject, lesson)
    c.drawRightString(xc + CARD_W/2 - 6, yc - CARD_H/2 + 8, tag)

def wrap(text, max_w, fnt="Helvetica", size=11):
    words = text.split(); lines=[]; cur=""
    for w in words:
        t=(cur+" "+w).strip()
        if stringWidth(t, fnt, size) <= max_w:
            cur=t
        else:
            if cur: lines.append(cur)
            cur=w
    if cur: lines.append(cur)
    return lines

# ---------------- PDF builders ----------------
def layout_front(c, batch, start_index, visuals_mode="None", show_marker=True,
                 subject=None, lesson=None, show_subtext=False, subtext_tmpl=""):
    for i, item in enumerate(batch):
        idx = start_index + i
        col = i % COLS; row = (i // COLS) % ROWS
        xc = col*CARD_W + CARD_W/2
        yc = PAGE[1] - (row*CARD_H + CARD_H/2)
        term, definition, _ = item

        # Visuals (optional): None (default) or Initials badge
        if visuals_mode == "Initials badge":
            icon_badge(c, xc, yc+12, term[:2], 1.0)

        # Term text
        c.setFont("Helvetica-Bold", 13); c.setFillColor(colors.black)
        c.drawCentredString(xc, yc-18, term)

        # Optional subtext under the term
        if show_subtext and (subtext_tmpl.strip() or subject or lesson):
            sub = (subtext_tmpl or "{subject} • Lesson {lesson}").format(
                subject=subject or "", lesson=lesson or "", index=idx+1
            ).strip(" •")
            c.setFont("Helvetica", 9); c.setFillColor(colors.grey)
            c.drawCentredString(xc, yc-32, sub)

        # Marker in corner
        draw_index(c, idx, xc, yc, subject, lesson, show_marker)

    draw_cut_grid(c)

def layout_back(c, batch, start_index, long_edge=True, offset_mm=(0,0),
                spelling_mode=False, show_marker=True,
                subject=None, lesson=None, show_subtext_on_back=False, subtext_tmpl=""):
    # offsets (mm -> pt)
    ox = offset_mm[0] * 2.83465; oy = offset_mm[1] * 2.83465
    c.saveState(); c.translate(ox, oy)
    rotate180 = not long_edge
    if rotate180:
        c.translate(PAGE[0], PAGE[1]); c.rotate(180)

    for i, item in enumerate(batch):
        term, definition, _ = item
        col = i % COLS; row = (i // COLS) % ROWS
        if long_edge: col = (COLS-1) - col  # mirror columns
        xc = col*CARD_W + CARD_W/2
        yc = PAGE[1] - (row*CARD_H + CARD_H/2)

        if spelling_mode or not definition:
            # three writing baselines
            c.setStrokeColor(colors.black)
            for j in range(3):
                y = yc - 6 + j*12
                c.line(xc - CARD_W/2 + 10, y, xc + CARD_W/2 - 10, y)
        else:
            lines = wrap(definition, CARD_W-20, "Helvetica", 11)
            c.setFont("Helvetica", 11); c.setFillColor(colors.black)
            y_text = yc + (len(lines)*6)
            for line in lines:
                c.drawCentredString(xc, y_text, line); y_text -= 14

        # Optional subtext on back
        if show_subtext_on_back and (subtext_tmpl.strip() or subject or lesson):
            sub = (subtext_tmpl or "{subject} • Lesson {lesson}").format(
                subject=subject or "", lesson=lesson or "", index=start_index + i + 1
            ).strip(" •")
            c.setFont("Helvetica", 8); c.setFillColor(colors.grey)
            c.drawCentredString(xc, yc - CARD_H/2 + 16, sub)

        # Corner marker
        draw_index(c, start_index + i, xc, yc, subject, lesson, show_marker)

    draw_cut_grid(c); c.restoreState()

def build_pdf(pairs, title="Flashcards", long_edge=True, offset_mm=(0,0),
              show_marker=True, spelling_mode=False,
              sample_n=None, only_first_sheet=False, visuals_mode="None",
              subject=None, lesson=None, show_subtext=False, subtext_tmpl="",
              show_subtext_on_back=False) -> bytes:
    if sample_n: pairs = pairs[:sample_n]
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=PAGE)
    start = 0; sheet = 1
    while start < len(pairs):
        batch = pairs[start:start+CHUNK]
        # FRONT
        c.setFont("Helvetica", 8); c.setFillColor(colors.grey)
        c.drawString(20, PAGE[1]-12, f"Sheet {sheet} FRONT ({'Long-edge' if long_edge else 'Short-edge'})")
        layout_front(c, batch, start, visuals_mode=visuals_mode,
                     show_marker=show_marker, subject=subject, lesson=lesson,
                     show_subtext=show_subtext, subtext_tmpl=subtext_tmpl)
        c.showPage()
        # BACK
        c.setFont("Helvetica", 8); c.setFillColor(colors.grey)
        c.drawString(20, PAGE[1]-12, f"Sheet {sheet} BACK")
        layout_back(c, batch, start, long_edge, offset_mm, spelling_mode,
                    show_marker=show_marker, subject=subject, lesson=lesson,
                    show_subtext_on_back=show_subtext_on_back, subtext_tmpl=subtext_tmpl)
        c.showPage()
        if only_first_sheet: break
        start += CHUNK; sheet += 1
    c.save()
    return buf.getvalue()

# ---------------- Parsing ----------------
def parse_text_to_pairs(txt: str, mode: str):
    pairs=[]
    for raw in txt.strip().splitlines():
        line = raw.strip().strip("•-—").strip()
        if not line: continue
        if mode=="terms":
            if "—" in line: term, definition = line.split("—",1)
            elif " - " in line: term, definition = line.split(" - ",1)
            elif "-" in line and len(line.split("-",1)[0].split())<=3:
                term, definition = line.split("-",1)
            else:
                term, definition = line, ""
            pairs.append((term.strip(), definition.strip(), None))
        else:
            pairs.append((line, "", None))
    return pairs

# ---------------- OCR helpers ----------------
OCR_SPACE_ENDPOINT = "https://api.ocr.space/parse/image"

def ocr_space_extract(file_bytes: bytes, is_pdf=False, api_key: Optional[str]=None) -> Optional[str]:
    key = api_key or "helloworld"  # demo key
    files = {"file": ("upload.pdf" if is_pdf else "upload.png", file_bytes)}
    data = {
        "language": "eng",
        "isOverlayRequired": "false",
        "OCREngine": "2",
        "scale": "true",
        "detectOrientation": "true"
    }
    try:
        resp = requests.post(OCR_SPACE_ENDPOINT, files=files, data=data, headers={"apikey": key}, timeout=30)
        resp.raise_for_status()
        js = resp.json()
        if js.get("IsErroredOnProcessing"):
            return None
        results = js.get("ParsedResults") or []
        texts = [r.get("ParsedText","") for r in results if r]
        out = "\n".join(texts).strip()
        return out or None
    except Exception:
        return None

def pdf_text_extract(file_bytes: bytes) -> Optional[str]:
    if not pdfplumber:
        return None
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            chunks = []
            for page in pdf.pages:
                t = page.extract_text() or ""
                if t.strip():
                    chunks.append(t)
            final = "\n".join(chunks).strip()
            return final or None
    except Exception:
        return None

# ---------------- UI ----------------
st.set_page_config(page_title="8-Up Flashcard PDF Generator", page_icon="🧠", layout="centered")
st.title("8-Up Flashcard PDF Generator")

with st.sidebar:
    st.header("Options")
    mode = st.radio("Input type", ["terms (term — definition)", "spelling (words only)"])
    duplex = st.radio("Duplex mode", ["Long-edge (mirror backs)", "Short-edge (rotate backs)"])
    long_edge = duplex.startswith("Long")
    offx = st.number_input("Offset X (mm)", value=0.0, step=0.5, help="Positive = shift backs RIGHT")
    offy = st.number_input("Offset Y (mm)", value=0.0, step=0.5, help="Positive = shift backs UP")
    show_marker = st.checkbox("Show corner marker", value=True, help="Shows subject/lesson/index in the card corner")
    st.markdown("---")
    st.subheader("Subject / Lesson")
    subject = st.text_input("Subject (optional)", value="", placeholder="e.g., Science or ELA")
    lesson = st.text_input("Lesson (optional)", value="", placeholder="e.g., Unit 2, Lesson 4")
    show_subtext = st.checkbox("Show subtext under term (FRONT)", value=True)
    subtext_tmpl = st.text_input("Subtext template", value="{subject} • Lesson {lesson}", help="Use {subject}, {lesson}, {index}")
    show_subtext_on_back = st.checkbox("Also show subtext on BACK", value=False)
    st.markdown("---")
    st.caption("OCR (for screenshots/PDF scans)")
    ocr_engine = st.radio("OCR method", ["OCR.space (recommended)", "PDF text only"], index=0)
    ocr_api_key = st.text_input("OCR.space API key (optional)", type="password", help="Leave blank to use demo key")
    st.markdown("---")
    visuals_mode = st.selectbox("Front visuals", ["None", "Initials badge"], index=0)

st.write("Choose **Paste text** or **Upload screenshot/PDF**. Edit the extracted text if needed, then generate.")

tab1, tab2 = st.tabs(["Paste text", "Upload screenshot/PDF"])

with tab1:
    default_example = "Observe — to use your senses to learn about things.\nMeasure — to find the size or amount of something.\nInvestigate — plan and do a test to answer a question."
    text_input_area = st.text_area("Your list:", value=default_example, height=220, key="manual_text")

with tab2:
    up = st.file_uploader("Upload image or PDF (screenshot, photo, or PDF)", type=["png", "jpg", "jpeg", "pdf"])
    extracted = ""
    if up is not None:
        file_bytes = up.read()
        if up.type == "application/pdf" or up.name.lower().endswith(".pdf"):
            if ocr_engine.startswith("PDF text only"):
                extracted = pdf_text_extract(file_bytes) or ""
            else:
                extracted = ocr_space_extract(file_bytes, is_pdf=True, api_key=ocr_api_key) or ""
        else:
            # image
            if ocr_engine.startswith("OCR.space"):
                extracted = ocr_space_extract(file_bytes, is_pdf=False, api_key=ocr_api_key) or ""
            else:
                extracted = ""  # no local OCR in this minimal build
        if not extracted:
            st.warning("I couldn't read text from that file. Try a clearer photo, or switch OCR method.")
        st.text_area("Extracted text (you can edit before generating):", value=extracted, height=220, key="extracted_text")

colA, colB = st.columns(2)
with colA:
    title = st.text_input("Title for the PDF", value="Study Cards")
with colB:
    filename_hint = "LongEdge_Mirrored" if long_edge else "ShortEdge_Rotated"
    st.text_input("Filename hint", value=filename_hint, disabled=True)

if st.button("Generate PDF", type="primary"):
    # decide which text to parse
    src_text = st.session_state.get("extracted_text") or st.session_state.get("manual_text") or ""
    pairs = parse_text_to_pairs(src_text, "terms" if mode.startswith("terms") else "spelling")
    if not pairs:
        st.error("I couldn’t find any items. Enter or extract at least one line.")
    else:
        pdf_bytes = build_pdf(
            pairs=pairs, title=title, long_edge=long_edge,
            offset_mm=(offx, offy), show_marker=show_marker,
            spelling_mode=(mode.startswith("spelling")),
            sample_n=3 if False else None,  # keep full unless you add paywall
            only_first_sheet=False,
            visuals_mode=visuals_mode,
            subject=subject.strip() or None,
            lesson=lesson.strip() or None,
            show_subtext=show_subtext, subtext_tmpl=subtext_tmpl,
            show_subtext_on_back=show_subtext_on_back
        )
        st.success("PDF ready!")
        st.download_button(
            "Download cards PDF",
            data=pdf_bytes,
            file_name=f"{title.replace(' ','_')}_{filename_hint}.pdf",
            mime="application/pdf",
        )

st.markdown("— Duplex-ready (mirror backs for long-edge). Use offsets if your printer drifts.")
