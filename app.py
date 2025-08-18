
import io, os, re, textwrap, requests
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
    st.markdown("1) Upload/Paste\n\n2) Review and edit\n\n3) Download PDF")

def parse_pairs_from_text(text: str) -> List[Tuple[str,str]]:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    pairs = []
    for ln in lines:
        ln = re.sub(r"^\s*\d+[\.\)]\s*", "", ln)
        m = re.split(r"\s(?:-|—|–|:)\s", ln, maxsplit=1)
        if len(m)==2:
            term, definition = m[0].strip(), m[1].strip()
        else:
            parts = ln.split(None, 1)
            term = parts[0].strip()
            definition = parts[1].strip() if len(parts)>1 else ""
        pairs.append((term, definition))
    return pairs

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
        s = footer_tmpl.replace("{subject}", subject or "").replace("{lesson}", lesson or "").replace("{index}", str(idx+1))
        return s.strip()

    # Front
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

    # Back
    offx = back_offset_x_mm * 72.0/25.4
    offy = back_offset_y_mm * 72.0/25.4
    for start in range(0, len(pairs), 8):
        batch = pairs[start:start+8]
        guides()
        if duplex_mode.lower().startswith("short"):
            c.translate(W, H); c.rotate(180)
        for i, (_, definition) in enumerate(batch):
            # mirrored col for long edge
            if "mirrored" in duplex_mode.lower():
                row, col = i // cols, i % cols
                col = (cols-1) - col
                j = row*cols + col
            else:
                j = i
            col, row = j % cols, j // cols
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

# ---- State ----
st.session_state.setdefault("extracted_text","")
st.session_state.setdefault("manual_text","")
st.session_state.setdefault("pairs", [])
st.session_state.setdefault("sheet_df", pd.DataFrame(columns=["Term","Definition"]))
st.session_state.setdefault("step", 1)

st.header("1) Upload or paste your list")
t1, t2, t3 = st.tabs(["Paste text", "Upload screenshot/PDF", "Paste from sheet (grid)"])

with t1:
    default_example = ("1. munch - to chew food loudly and\n"
                       "completely\n"
                       "2) bellowed — to have shouted in a loud\n"
                       "deep voice")
    st.session_state.manual_text = st.text_area("Your list", value=st.session_state.get("manual_text") or default_example, height=260)

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
    st.text_area("Extracted text (you can edit before parsing):", value=st.session_state.extracted_text, height=220, key="extracted_text_box")

with t3:
    st.caption("Option A: Copy two columns (Term, Definition) from Excel/Sheets and paste into the grid. "
               "Option B: Upload a CSV/Excel and map columns.")
    cfg = {
        "Term": st.column_config.TextColumn(label="Front of Flash Card (term)"),
        "Definition": st.column_config.TextColumn(label="Back of Flash Card (definition)"),
    }
    if st.session_state.sheet_df.empty:
        st.session_state.sheet_df = pd.DataFrame([{"Term":"","Definition":""}])
    grid_df = st.data_editor(st.session_state.sheet_df, num_rows="dynamic", use_container_width=True,
                             column_config=cfg, key="grid_paste_editor")
    st.session_state.sheet_df = grid_df
    st.markdown("---")
    up2 = st.file_uploader("Upload CSV or Excel", type=["csv","xlsx","xls"], key="grid_uploader")
    if up2 is not None:
        ext = up2.name.lower().split(".")[-1]
        has_header = st.checkbox("First row contains headers", value=True, key="grid_has_header")
        if ext=="csv":
            df_raw = pd.read_csv(up2, header=0 if has_header else None)
        else:
            xls = pd.ExcelFile(up2)
            sheet_name = st.selectbox("Sheet", xls.sheet_names, key="grid_sheet_select")
            df_raw = pd.read_excel(up2, sheet_name=sheet_name, header=0 if has_header else None, engine="openpyxl")
        if not has_header:
            df_raw.columns = [f"Column {i+1}" for i in range(df_raw.shape[1])]
        cols = list(df_raw.columns)
        if cols:
            term_col = st.selectbox("Which column is the Term (front)?", cols, index=0, key="grid_term_col")
            def_col  = st.selectbox("Which column is the Definition (back)?", cols, index=1 if len(cols)>1 else 0, key="grid_def_col")
            df_map = df_raw[[term_col, def_col]].rename(columns={term_col:"Term", def_col:"Definition"})
            df_map["Term"] = df_map["Term"].astype(str).str.strip()
            df_map["Definition"] = df_map["Definition"].astype(str).str.strip()
            st.dataframe(df_map.head(8), use_container_width=True)
            c1,c2 = st.columns(2)
            if c1.button("Load into grid (replace)", key="grid_load_replace"):
                st.session_state.sheet_df = df_map.copy(); st.success("Loaded into grid."); st.rerun()
            if c2.button("Append to grid", key="grid_load_append"):
                st.session_state.sheet_df = pd.concat([st.session_state.sheet_df, df_map], ignore_index=True); st.success("Appended."); st.rerun()

# Next
if st.button("Next: Review and edit", type="primary"):
    df = st.session_state.sheet_df.copy()
    if not df.empty:
        df["Term"] = df["Term"].astype(str).str.strip()
        df["Definition"] = df["Definition"].astype(str).str.strip()
        df_valid = df[(df["Term"]!="") | (df["Definition"]!="")]
    else:
        df_valid = pd.DataFrame(columns=["Term","Definition"])
    if len(df_valid):
        st.session_state.pairs = list(df_valid.itertuples(index=False, name=None))
    else:
        src = st.session_state.get("extracted_text_box") or st.session_state.get("manual_text") or ""
        st.session_state.pairs = parse_pairs_from_text(src)
    st.session_state.step = 2
    st.rerun()

# Step 2 & 3
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
    with st.expander("Card footer (subject • lesson)"):
        enable_footer = st.checkbox("Add footer text on cards", value=True, key="footer_enable")
        subject = st.text_input("Subject", value="", key="footer_subject", disabled=not enable_footer)
        lesson  = st.text_input("Lesson",  value="", key="footer_lesson",  disabled=not enable_footer)
        templ   = st.text_input("Footer template", value="{subject} • {lesson}", key="footer_template", disabled=not enable_footer)
    if st.button("Generate PDF", type="primary"):
        pairs = st.session_state.get("pairs", [])
        if not pairs:
            st.warning("Please add at least one term.")
        else:
            with st.spinner("Rendering PDF…"):
                pdf_bytes = build_pdf(
                    pairs=pairs,
                    subject=subject if enable_footer else "",
                    lesson=lesson if enable_footer else "",
                    footer_tmpl=templ if enable_footer else "",
                    duplex_mode=duplex_mode.lower(),
                    back_offset_x_mm=bxo,
                    back_offset_y_mm=byo,
                    show_corner_marker=corner_marker,
                )
            st.success("Done!")
            st.download_button("Download flashcards (PDF)", data=pdf_bytes, file_name="flashdecky_cards.pdf", mime="application/pdf")
