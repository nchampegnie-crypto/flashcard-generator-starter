
import io, os, re, requests
from typing import List, Tuple
import streamlit as st
import pandas as pd
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.colors import black, HexColor

st.set_page_config(page_title="FlashDecky", page_icon="⚡", layout="wide")
with open("flashdecky_header.css","r") as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

c1, c2 = st.columns([1,6])
with c1: st.image("assets/icon.png", width=56)
with c2: st.image("assets/wordmark.png", use_column_width=False)
st.markdown("---")

with st.sidebar:
    st.header("Progress")
    st.markdown("1) Upload/Paste  \n2) Review and edit  \n3) Download PDF")

LIST_START_RE = re.compile(r"(?mi)^\s*(?:\d+[\.\)]\s+|[-*•]\s+)")
HEADWORD_START_RE = re.compile(r"(?:(?<=^)|(?<=\n)|(?<=\)))\s*([A-Za-z][A-Za-z'’\-]+)(?=\s+(?:\(|\d+\.))")

def split_blocks(text: str) -> List[str]:
    text = text.replace("\r\n","\n")
    starts = [m.start() for m in LIST_START_RE.finditer(text)]
    if starts:
        blocks = []
        for i, s in enumerate(starts):
            e = starts[i+1] if i+1 < len(starts) else len(text)
            blocks.append(text[s:e].strip())
        return blocks
    mlist = list(HEADWORD_START_RE.finditer(text))
    if mlist:
        idxs = [m.start(1) for m in mlist]
        blocks = []
        for i, s in enumerate(idxs):
            e = idxs[i+1] if i+1 < len(idxs) else len(text)
            blocks.append(text[s:e].strip())
        return blocks
    return [blk.strip() for blk in re.split(r"\n\s*\n+", text) if blk.strip()]

def parse_term_def(block: str) -> Tuple[str,str]:
    cleaned = " ".join([ln.strip() for ln in block.splitlines() if ln.strip()])
    m = re.match(r"^(?P<term>.+?)\s*(?:-|—|–|:)\s+(?P<def>.+)$", cleaned)
    if m:
        return m.group("term").strip(), m.group("def").strip()
    m2 = re.match(r"^\s*(?P<term>[A-Za-z][A-Za-z'’\-]+)\s+(?P<def>.+)$", cleaned, flags=re.S)
    if m2:
        return m2.group("term").strip(), m2.group("def").strip()
    parts = cleaned.split(None, 1)
    if len(parts)==2:
        return parts[0].strip(), parts[1].strip()
    return cleaned.strip(), ""

def parse_pairs_from_text(text: str) -> List[Tuple[str,str]]:
    blocks = split_blocks(text)
    return [parse_term_def(b) for b in blocks]

def ocr_space_image(image_bytes: bytes, is_pdf=False, key=None) -> str:
    key = key or os.environ.get("OCR_SPACE_API_KEY") or "helloworld"
    url = "https://api.ocr.space/parse/image"
    files = {"filename": ("upload.pdf" if is_pdf else "upload.png", image_bytes)}
    data = {"apikey": key, "OCREngine": 2, "scale": True, "isTable": False, "language": "eng"}
    if is_pdf: data["filetype"] = "PDF"
    try:
        r = requests.post(url, files=files, data=data, timeout=60)
        j = r.json()
        if j.get("IsErroredOnProcessing"): return ""
        return " ".join([p.get("ParsedText","") for p in j.get("ParsedResults",[])]).strip()
    except Exception:
        return ""

def extract_pdf_text_native(pdf_bytes: bytes) -> str:
    try:
        from pdfminer.high_level import extract_text
        return extract_text(io.BytesIO(pdf_bytes)) or ""
    except Exception:
        return ""

def auto_extract(file_bytes: bytes, filename: str, api_key=None) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        txt = extract_pdf_text_native(file_bytes)
        if len(txt.strip()) >= 10: return txt
        return ocr_space_image(file_bytes, is_pdf=True, key=api_key)
    else:
        return ocr_space_image(file_bytes, is_pdf=False, key=api_key)

def build_pdf(pairs, subject, lesson, footer_tmpl, duplex_mode="long-edge (mirrored back)",
              back_offset_x_mm=0.0, back_offset_y_mm=0.0, show_corner_marker=False):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    from reportlab.lib.colors import black, HexColor
    W, H = letter
    cols, rows = 2, 4
    card_w, card_h = W/cols, H/rows
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    def guides():
        c.setStrokeColor(HexColor("#D1D5DB"))
        c.setLineWidth(0.5); c.setDash(3,3)
        c.line(card_w, 0, card_w, H)
        for y in [card_h, 2*card_h, 3*card_h]: c.line(0, y, W, y)
        c.setDash()
    def footer_text(idx):
        s = (footer_tmpl or "").replace("{subject}", subject or "").replace("{lesson}", lesson or "").replace("{index}", str(idx+1))
        return s.strip()
    for start in range(0, len(pairs), 8):
        batch = pairs[start:start+8]
        guides()
        for i, (term, _) in enumerate(batch):
            col, row = i % cols, i // cols
            x0, y0 = col*card_w, H - (row+1)*card_h
            c.setFont("Helvetica-Bold", 22); c.setFillColor(black)
            c.drawCentredString(x0+card_w/2, y0+card_h/2 + 6, term)
            if footer_tmpl:
                c.setFont("Helvetica", 9); c.setFillColor(HexColor("#6B7280"))
                c.drawRightString(x0+card_w-10, y0+8, footer_text(start+i))
            if show_corner_marker:
                c.setFillColor(HexColor("#9CA3AF")); c.circle(x0+8, y0+8, 2, fill=1, stroke=0)
        c.showPage()
    offx = back_offset_x_mm * 72.0/25.4
    offy = back_offset_y_mm * 72.0/25.4
    for start in range(0, len(pairs), 8):
        batch = pairs[start:start+8]
        guides()
        if duplex_mode.lower().startswith("short"):
            c.translate(W, H); c.rotate(180)
        for i, (_, definition) in enumerate(batch):
            if "mirrored" in duplex_mode.lower():
                row, col = i // 2, i % 2
                col = 1 - col
                j = row*2 + col
            else:
                j = i
            col, row = j % 2, j // 2
            x0, y0 = col*card_w + offx, H - (row+1)*card_h + offy
            c.setFillColor(black); c.setFont("Helvetica", 14)
            from textwrap import wrap
            y = y0 + card_h/2 + 10
            for line in wrap(definition, 60):
                c.drawCentredString(x0+card_w/2, y, line); y -= 16
            if footer_tmpl:
                c.setFont("Helvetica", 9); c.setFillColor(HexColor("#6B7280"))
                c.drawRightString(x0+card_w-10, y0+8, footer_text(start+i))
            if show_corner_marker:
                c.setFillColor(HexColor("#9CA3AF")); c.circle(x0+8, y0+8, 2, fill=1, stroke=0)
        c.showPage()
    c.save()
    return buf.getvalue()

st.session_state.setdefault("extracted_text","")
st.session_state.setdefault("manual_text","")
st.session_state.setdefault("pairs", [])
st.session_state.setdefault("sheet_df", pd.DataFrame(columns=["Term","Definition"]))
st.session_state.setdefault("step", 1)

st.header("1) Upload or paste your list")
t1, t2 = st.tabs(["Paste text", "Upload screenshot/PDF"])

with t1:
    default_example = ("abhor (v.) to hate, detest (Because he always wound up kicking himself in the head when he tried to play soccer, Oswald began to abhor the sport.)\n"
                       "abide 1. (v.) to put up with (Though he did not agree with the decision, Chuck decided to abide by it.) 2. (v.) to remain (Despite the beating they've taken from the weather throughout the millennia, the mountains abide.)")
    st.session_state.manual_text = st.text_area("Your list", value=st.session_state.get("manual_text") or default_example, height=200)

with t2:
    up = st.file_uploader("Upload image or PDF", type=["png","jpg","jpeg","pdf"])
    st.caption("We’ll auto-choose the best extraction for you.")
    extracted = st.session_state.get("extracted_text","")
    if up is not None:
        file_bytes = up.read()
        with st.spinner("Extracting text…"):
            extracted = auto_extract(file_bytes, up.name, api_key=None)
        if not extracted.strip():
            st.warning("I couldn't read text from that file. Try a clearer image or paste the text instead.")
    st.session_state.extracted_text = extracted or st.session_state.get("extracted_text","")
    st.text_area("Extracted text (you can edit before parsing):", value=st.session_state.extracted_text, height=180, key="extracted_text_box")

if st.button("Next: Review and edit", type="primary"):
    src = st.session_state.get("extracted_text_box") or st.session_state.get("manual_text") or ""
    st.session_state.pairs = parse_pairs_from_text(src)
    st.session_state.step = 2
    st.rerun()

if st.session_state.get("step",1) >= 2:
    st.header("2) Review and edit")
    pairs = st.session_state.get("pairs", [])
    df = pd.DataFrame(pairs, columns=["Term","Definition"]).fillna("")
    cfg2 = {
        "Term": st.column_config.TextColumn(label="Front of Flash Card (term)"),
        "Definition": st.column_config.TextColumn(label="Back of Flash Card (definition)"),
    }
    st.caption("Click a cell to edit. Add/remove rows if needed.")
    df = st.data_editor(df, num_rows="dynamic", use_container_width=True, column_config=cfg2, key="editor_simple")
    st.session_state.pairs = [(str(r["Term"]).strip(), str(r["Definition"]).strip()) for _, r in df.iterrows()]

    st.markdown("---")
    st.header("3) Download PDF")
    with st.expander("Print alignment"):
        duplex_mode = st.selectbox("Duplex mode", ["Long-edge (mirrored back)","Short-edge (rotate back)","Long-edge (no mirror)"], index=0)
        bxo = st.number_input("Back page offset X (mm)", value=0.0, step=0.5)
        byo = st.number_input("Back page offset Y (mm)", value=0.0, step=0.5)
        corner_marker = st.checkbox("Show tiny corner marker", value=False)

    st.subheader("Card footer (subject • lesson)")
    include_footer = st.checkbox("Include footer text on cards", value=True, key="footer_include")
    subject = st.text_input("Subject", value=st.session_state.get("footer_subject",""))
    lesson  = st.text_input("Lesson",  value=st.session_state.get("footer_lesson",""))
    templ   = st.text_input("Footer template", value=st.session_state.get("footer_template","{subject} • {lesson}"))
    st.session_state["footer_subject"] = subject
    st.session_state["footer_lesson"] = lesson
    st.session_state["footer_template"] = templ

    if st.button("Generate PDF", type="primary"):
        pairs = st.session_state.get("pairs", [])
        if not pairs:
            st.warning("Please add at least one term.")
        else:
            with st.spinner("Rendering PDF…"):
                pdf_bytes = build_pdf(
                    pairs=pairs,
                    subject=subject if include_footer else "",
                    lesson=lesson if include_footer else "",
                    footer_tmpl=templ if include_footer else "",
                    duplex_mode=duplex_mode.lower(),
                    back_offset_x_mm=bxo,
                    back_offset_y_mm=byo,
                    show_corner_marker=corner_marker,
                )
            st.success("Done!")
            st.download_button("Download flashcards (PDF)", data=pdf_bytes, file_name="flashdecky_cards.pdf", mime="application/pdf")
