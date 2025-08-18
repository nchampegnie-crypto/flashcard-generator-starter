
import io, textwrap
from typing import List, Tuple, Optional
import streamlit as st
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.pdfbase.pdfmetrics import stringWidth

# --------------------- ICONS (vector, print-safe) ---------------------
def icon_badge(c, cx, cy, txt="A", scale=1.0):
    r = 16*scale
    c.setFillColor(colors.lightblue); c.circle(cx, cy, r, stroke=0, fill=1)
    c.setFillColor(colors.darkblue); c.setFont("Helvetica-Bold", 14*scale)
    c.drawCentredString(cx, cy-5*scale, txt[:2].upper())

def icon_eyes(c, cx, cy, scale=1.0):
    c.setFillColor(colors.white); c.setStrokeColor(colors.black)
    w=18*scale; h=12*scale
    c.ellipse(cx-w-2, cy-h/2, cx-2, cy+h/2, stroke=1, fill=1)
    c.ellipse(cx+2, cy-h/2, cx+w+2, cy+h/2, stroke=1, fill=1)
    c.setFillColor(colors.darkblue)
    c.circle(cx-w/2-2, cy, 4*scale, stroke=0, fill=1)
    c.circle(cx+w/2+2, cy, 4*scale, stroke=0, fill=1)

def icon_ruler(c, cx, cy, scale=1.0):
    w=60*scale; h=12*scale
    c.setFillColor(colors.goldenrod); c.setStrokeColor(colors.saddlebrown)
    c.rect(cx-w/2, cy-h/2, w, h, stroke=1, fill=1)
    for i in range(13):
        x = cx - w/2 + i*w/12.0
        tick = 6*scale if i%2==0 else 3*scale
        c.line(x, cy+h/2, x, cy+h/2 - tick)

def icon_lightbulb(c, cx, cy, scale=1.0):
    c.setFillColor(colors.yellow); c.setStrokeColor(colors.orange)
    c.circle(cx, cy+10*scale, 14*scale, stroke=1, fill=1)
    c.setFillColor(colors.orange); c.rect(cx-8*scale, cy-8*scale, 16*scale, 10*scale, stroke=0, fill=1)

def icon_magnifier(c, cx, cy, scale=1.0):
    r=14*scale
    c.setFillColor(colors.lightblue); c.setStrokeColor(colors.darkblue)
    c.circle(cx, cy, r, stroke=1, fill=1)
    c.line(cx+r*0.7, cy-r*0.7, cx+r*2.0, cy-r*2.0)

ICON_MAP = {
    "observe": icon_eyes,
    "measure": icon_ruler,
    "infer": icon_lightbulb,
    "investigate": icon_magnifier,
}

def pick_icon(term):
    key = term.lower()
    for k, fn in ICON_MAP.items():
        if k in key:
            return fn
    return lambda c, x, y, s=1.0: icon_badge(c, x, y, txt=term[:2], scale=s)

# --------------------- LAYOUT CONSTANTS ---------------------
PAGE = letter
COLS, ROWS = 2, 4
CARD_W, CARD_H = PAGE[0]/COLS, PAGE[1]/ROWS
CHUNK = COLS * ROWS

def draw_cut_grid(c):
    c.setLineWidth(0.5); c.setDash(3,3); c.setStrokeColor(colors.grey)
    for i in range(1, COLS): c.line(i*CARD_W, 0, i*CARD_W, PAGE[1])
    for j in range(1, ROWS): c.line(0, j*CARD_H, PAGE[0], j*CARD_H)
    c.setDash()

def draw_index(c, idx, xc, yc, lesson: Optional[str]):
    c.setFont("Helvetica", 7); c.setFillColor(colors.grey)
    tag = f"L{lesson}-#{idx+1}" if lesson else f"#{idx+1}"
    c.drawRightString(xc + CARD_W/2 - 6, yc - CARD_H/2 + 8, tag)

def wrap(text, max_w, fnt="Helvetica", size=11):
    words = text.split(); lines=[]; cur=""
    for w in words:
        t=(cur+" "+w).strip()
        if stringWidth(t, fnt, size) <= max_w:
            cur=t
        else:
            lines.append(cur); cur=w
    if cur: lines.append(cur)
    return lines

# --------------------- PDF BUILDERS ---------------------
def layout_front(c, batch, start_index, spelling_mode=False, include_lessons=True):
    for i, item in enumerate(batch):
        idx = start_index + i
        col = i % COLS; row = (i // COLS) % ROWS
        xc = col*CARD_W + CARD_W/2
        yc = PAGE[1] - (row*CARD_H + CARD_H/2)
        term, definition, lesson = item
        pick_icon(term)(c, xc, yc+10, 1.0)
        c.setFont("Helvetica-Bold", 13); c.setFillColor(colors.black)
        c.drawCentredString(xc, yc-25, term)
        draw_index(c, idx, xc, yc, lesson if include_lessons else None)
    draw_cut_grid(c)

def layout_back(c, batch, start_index, long_edge=True, offset_mm=(0,0),
                spelling_mode=False, include_lessons=True):
    ox = offset_mm[0] * 2.83465; oy = offset_mm[1] * 2.83465  # mm -> pt
    c.saveState(); c.translate(ox, oy)
    rotate180 = not long_edge
    if rotate180:
        c.translate(PAGE[0], PAGE[1]); c.rotate(180)
    for i, item in enumerate(batch):
        term, definition, lesson = item
        col = i % COLS; row = (i // COLS) % ROWS
        if long_edge: col = (COLS-1) - col
        xc = col*CARD_W + CARD_W/2
        yc = PAGE[1] - (row*CARD_H + CARD_H/2)
        if spelling_mode or not definition:
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
        idx = start_index + i
        draw_index(c, idx, xc, yc, lesson if include_lessons else None)
    draw_cut_grid(c); c.restoreState()

def build_pdf(pairs, title="Flashcards", long_edge=True, offset_mm=(0,0),
              include_lessons=True, spelling_mode=False,
              sample_n=None, only_first_sheet=False) -> bytes:
    if sample_n:
        pairs = pairs[:sample_n]
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=PAGE)
    start = 0; sheet = 1
    while start < len(pairs):
        batch = pairs[start:start+CHUNK]
        c.setFont("Helvetica", 8); c.setFillColor(colors.grey)
        c.drawString(20, PAGE[1]-12, f"Sheet {sheet} FRONT ({'Long-edge' if long_edge else 'Short-edge'})")
        layout_front(c, batch, start, spelling_mode, include_lessons); c.showPage()
        c.setFont("Helvetica", 8); c.setFillColor(colors.grey)
        c.drawString(20, PAGE[1]-12, f"Sheet {sheet} BACK")
        layout_back(c, batch, start, long_edge, offset_mm, spelling_mode, include_lessons); c.showPage()
        if only_first_sheet: break
        start += CHUNK; sheet += 1
    c.save()
    return buf.getvalue()

# --------------------- PARSING ---------------------
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

# --------------------- STREAMLIT UI ---------------------
st.set_page_config(page_title="8-Up Flashcard PDF Generator", page_icon="🧠", layout="centered")
st.title("8-Up Flashcard PDF Generator")

with st.sidebar:
    st.header("Options")
    mode = st.radio("Input type", ["terms (term — definition)", "spelling (words only)"])
    duplex = st.radio("Duplex mode", ["Long-edge (mirror backs)", "Short-edge (rotate backs)"])
    long_edge = duplex.startswith("Long")
    offx = st.number_input("Offset X (mm)", value=0.0, step=0.5, help="Positive = shift backs RIGHT")
    offy = st.number_input("Offset Y (mm)", value=0.0, step=0.5, help="Positive = shift backs UP")
    include_lessons = st.checkbox("Show L{lesson}-# markers", value=True)
    sample = st.checkbox("Sample (first 3 cards only)", value=False)
    first_sheet = st.checkbox("Generate only first sheet", value=False)

st.write("Paste your list below. For **terms mode**, use `term — definition` (em dash) or `term - definition` per line. For **spelling mode**, enter one word per line.")

default_example = "Observe — to use your senses to learn about things.\nMeasure — to find the size or amount of something.\nInfer — to use what you know to answer a question."
text = st.text_area("Your list:", value=default_example, height=180)

colA, colB = st.columns(2)
with colA:
    title = st.text_input("Title for the PDF", value="Study Cards")
with colB:
    filename_hint = "LongEdge_Mirrored" if long_edge else "ShortEdge_Rotated"
    st.text_input("Filename hint", value=filename_hint, disabled=True)

if st.button("Generate PDF", type="primary"):
    pairs = parse_text_to_pairs(text, "terms" if mode.startswith("terms") else "spelling")
    if not pairs:
        st.error("I couldn’t find any items. Enter at least one line.")
    else:
        pdf_bytes = build_pdf(
            pairs=pairs, title=title, long_edge=long_edge,
            offset_mm=(offx, offy), include_lessons=include_lessons,
            spelling_mode=(mode.startswith("spelling")),
            sample_n=3 if sample else None,
            only_first_sheet=first_sheet
        )
        st.success("PDF ready!")
        st.download_button(
            "Download cards PDF",
            data=pdf_bytes,
            file_name=f"{title.replace(' ','_')}_{filename_hint}.pdf",
            mime="application/pdf",
        )

st.markdown("— Made for parents & teachers. 8-up, perfectly aligned, duplex-ready.")
