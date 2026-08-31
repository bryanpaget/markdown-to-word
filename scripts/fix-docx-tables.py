#!/usr/bin/env python3
"""Post-process a .docx produced by pandoc + SSC template before LibreOffice converts it.

Four fixes are applied:

1. TABLE WIDTH — Pandoc emits tables with a fixed tblW of 5000 twips (~3.5in) and a
   fixed layout.  When rendered by LibreOffice/Word, wide tables get crushed into
   single-character columns.  This rewrites every <w:tbl> to:
     - tblW  type="pct"  w="5000"   (5000 pct == 100% of the page)
     - tblLayout type="autofit"     (columns size to their content)

2. HEADING2 STYLE — The SSC template's Heading2 style has keepLines + outlineLvl
   which triggers a LibreOffice bug causing content to wrap character-by-character.
   This removes those two properties from the Heading2 pPr.

3. MISSING STYLES — Pandoc emits styles (Compact, Table, Title, Subtitle) that the
   SSC template doesn't define.  LibreOffice falls back to plain-paragraph rendering
   for undefined styles, breaking table grid display.  This injects the missing
   style definitions.

4. CLASSIFICATION TEXT BOX — The template's header contains a sensitivity-label text
   box (e.g. "Unclassified | Non classifié") that is only ~1.2 cm wide.  Word renders
   the text as overflow; LibreOffice clips to the box and wraps every 2 characters.
   This widens every text box whose description contains "classif" (case-insensitive)
   to CLASSIFICATION_BOX_EMU wide so the text fits on one line without overflow.

5. TITLE PAGE HEADING INDENT — Heading1 paragraphs on the title page are given a
   right indent so they don't overlap the decorative leaf graphic in the header.

Usage:
    python3 fix-docx-tables.py <file.docx> [<file2.docx> ...]
"""
import sys
import zipfile
import os
from xml.etree import ElementTree as ET

# ---------------------------------------------------------------------------
# Namespace constants
# ---------------------------------------------------------------------------
W_NS   = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A_NS   = "http://schemas.openxmlformats.org/drawingml/2006/main"
WP_NS  = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
PIC_NS = "http://schemas.openxmlformats.org/drawingml/2006/picture"
A14_NS = "http://schemas.microsoft.com/office/drawing/2010/main"

W   = "{%s}" % W_NS
A   = "{%s}" % A_NS
WP  = "{%s}" % WP_NS

# Register all namespaces so ET.tostring() preserves prefixes instead of
# inventing ns0/ns1/… which breaks the OOXML zip.
_NS_MAP = {
    "wpc":      "http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas",
    "cx":       "http://schemas.microsoft.com/office/drawing/2014/chartex",
    "mc":       "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "aink":     "http://schemas.microsoft.com/office/drawing/2016/ink",
    "am3d":     "http://schemas.microsoft.com/office/drawing/2017/model3d",
    "o":        "urn:schemas-microsoft-com:office:office",
    "oel":      "http://schemas.microsoft.com/office/2019/extlst",
    "r":        "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "m":        "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "v":        "urn:schemas-microsoft-com:vml",
    "wp14":     "http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing",
    "wp":       WP_NS,
    "w10":      "urn:schemas-microsoft-com:office:word",
    "w":        W_NS,
    "w14":      "http://schemas.microsoft.com/office/word/2010/wordml",
    "w15":      "http://schemas.microsoft.com/office/word/2012/wordml",
    "w16cex":   "http://schemas.microsoft.com/office/word/2018/wordml/cex",
    "w16cid":   "http://schemas.microsoft.com/office/word/2016/wordml/cid",
    "w16":      "http://schemas.microsoft.com/office/word/2018/wordml",
    "w16se":    "http://schemas.microsoft.com/office/word/2015/wordml/symex",
    "wpg":      "http://schemas.microsoft.com/office/word/2010/wordprocessingGroup",
    "wpi":      "http://schemas.microsoft.com/office/word/2010/wordprocessingInk",
    "wne":      "http://schemas.microsoft.com/office/word/2006/wordml",
    "wps":      "http://schemas.microsoft.com/office/word/2010/wordprocessingShape",
    "a":        A_NS,
    "a14":      A14_NS,
    "pic":      PIC_NS,
    "adec":     "http://schemas.microsoft.com/office/drawing/2017/decorative",
    "asvg":     "http://schemas.microsoft.com/office/drawing/2016/SVG/main",
    "aclsh":    "http://schemas.microsoft.com/office/drawing/2020/classificationShape",
}
for prefix, uri in _NS_MAP.items():
    ET.register_namespace(prefix, uri)

# ---------------------------------------------------------------------------
# Tuneable parameters
# ---------------------------------------------------------------------------
# Table width
PAGE_PCT   = "5000"   # 5000 pct = 100% of page width
GRID_TWIPS = 9000     # seed column grid (~full usable width in twips)

# Classification text box: widen to this many EMU (1 EMU = 1/914400 inch).
# 1 800 000 EMU ≈ 5 cm — enough for "Unclassified | Non classifié" at 11pt.
CLASSIFICATION_BOX_EMU = "1800000"


# ---------------------------------------------------------------------------
# Fix 1: table widths and style
# ---------------------------------------------------------------------------
# Pandoc emits tblStyle="Table" but the SSC template only defines "TableNormal".
# LibreOffice can't resolve "Table" and falls back to rendering each cell as a
# plain paragraph (no grid visible).  Rewrite to the style that actually exists.
TBLSTYLE_REMAP = {"Table": "TableNormal"}

def _make_border(tag: str, val: str = "single", sz: str = "4", space: str = "0", color: str = "auto") -> ET.Element:
    el = ET.Element(W + tag)
    el.set(W + "val", val)
    el.set(W + "sz", sz)
    el.set(W + "space", space)
    el.set(W + "color", color)
    return el


def fix_table(tbl: ET.Element) -> None:
    tblPr = tbl.find(W + "tblPr")
    if tblPr is None:
        tblPr = ET.SubElement(tbl, W + "tblPr")

    # Remap missing table styles so LibreOffice renders the grid correctly.
    tblStyle = tblPr.find(W + "tblStyle")
    if tblStyle is not None:
        current = tblStyle.get(W + "val", "")
        if current in TBLSTYLE_REMAP:
            tblStyle.set(W + "val", TBLSTYLE_REMAP[current])

    tblW = tblPr.find(W + "tblW")
    if tblW is None:
        tblW = ET.SubElement(tblPr, W + "tblW")
    tblW.set(W + "type", "pct")
    tblW.set(W + "w", PAGE_PCT)

    tblLayout = tblPr.find(W + "tblLayout")
    if tblLayout is None:
        tblLayout = ET.SubElement(tblPr, W + "tblLayout")
    tblLayout.set(W + "type", "autofit")

    # Ensure visible borders. pandoc doesn't emit tblBorders and the SSC
    # template's TableNormal has none either, so LibreOffice renders the grid
    # with invisible hairline borders.  Write them explicitly on every table.
    tblBorders = tblPr.find(W + "tblBorders")
    if tblBorders is None:
        tblBorders = ET.SubElement(tblPr, W + "tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        existing = tblBorders.find(W + side)
        if existing is None:
            tblBorders.append(_make_border(side))

    tblGrid = tbl.find(W + "tblGrid")
    if tblGrid is not None:
        cols = tblGrid.findall(W + "gridCol")
        if cols:
            per = GRID_TWIPS // len(cols)
            for c in cols:
                c.set(W + "w", str(per))


# ---------------------------------------------------------------------------
# Fix 2: Heading2 keepLines / outlineLvl
# ---------------------------------------------------------------------------
def fix_heading2_styles(styles_root: ET.Element) -> None:
    """Remove keepLines and outlineLvl from Heading2 to avoid LibreOffice wrap bug."""
    for st in styles_root.iter(W + "style"):
        if st.get(W + "styleId") == "Heading2":
            pPr = st.find(W + "pPr")
            if pPr is not None:
                for child in list(pPr):
                    if child.tag in (W + "keepLines", W + "outlineLvl"):
                        pPr.remove(child)


# ---------------------------------------------------------------------------
# Fix 3 (styles): inject missing styles pandoc emits but the template lacks
# ---------------------------------------------------------------------------
def fix_missing_styles(styles_root: ET.Element) -> list:
    """Inject styles that pandoc emits but the SSC template doesn't define.

    Missing styles cause LibreOffice to fall back to plain-paragraph rendering,
    which breaks table grid display entirely.

    Currently injects:
      - Compact  (paragraph style used in every table cell by pandoc)
      - Table    (table style alias → TableNormal, so tblStyle lookups resolve)
    """
    existing = {st.get(W + "styleId") for st in styles_root.iter(W + "style")}
    injected = []

    # Compact: a simple no-spacing paragraph style for table cells.
    if "Compact" not in existing:
        st = ET.SubElement(styles_root, W + "style")
        st.set(W + "type", "paragraph")
        st.set(W + "styleId", "Compact")
        ET.SubElement(st, W + "name").set(W + "val", "Compact")
        based = ET.SubElement(st, W + "basedOn")
        based.set(W + "val", "Normal")
        pPr = ET.SubElement(st, W + "pPr")
        spacing = ET.SubElement(pPr, W + "spacing")
        spacing.set(W + "after", "0")
        spacing.set(W + "line", "240")
        spacing.set(W + "lineRule", "auto")
        injected.append("Compact")

    # Table: a table style alias so pandoc's tblStyle="Table" resolves.
    if "Table" not in existing and "TableNormal" in existing:
        st = ET.SubElement(styles_root, W + "style")
        st.set(W + "type", "table")
        st.set(W + "styleId", "Table")
        ET.SubElement(st, W + "name").set(W + "val", "Table")
        based = ET.SubElement(st, W + "basedOn")
        based.set(W + "val", "TableNormal")
        injected.append("Table")

    # Title and Subtitle styles: set right indent so both wrap before reaching
    # the decorative leaf graphic (~7.76 cm from the right text edge).
    # 3600 twips = 6.35 cm — clears the graphic while keeping enough width
    # for the title to wrap in 2-3 lines rather than one word per line.
    # NOTE: Heading1 is NOT included here — it's used throughout the document.
    # The title-page Heading1 is fixed per-paragraph in fix_titlepage_headings().
    for st in styles_root.iter(W + "style"):
        if st.get(W + "styleId") in ("Title", "Subtitle"):
            pPr = st.find(W + "pPr")
            if pPr is None:
                pPr = ET.SubElement(st, W + "pPr")
            ind = pPr.find(W + "ind")
            if ind is None:
                ind = ET.SubElement(pPr, W + "ind")
            ind.set(W + "right", "3600")

    return injected


# ---------------------------------------------------------------------------
# Fix 3: widen classification text boxes in headers
# ---------------------------------------------------------------------------
# Classification text box font size in half-points. 16 = 8pt fits comfortably
# on one line even in the narrower page-margin column without overflowing.
CLASSIFICATION_FONT_SZ = "16"

def fix_classification_textboxes(root: ET.Element) -> int:
    """Widen every text box whose docPr description mentions 'classif', and
    set a small explicit font size so the text doesn't overflow the header line.

    LibreOffice honours the box dimensions literally and wraps inside a ~1 cm
    box, producing character-by-character stacking.  Widening the box to
    CLASSIFICATION_BOX_EMU lets the text sit on one line.  Setting an explicit
    font size prevents the inherited 12pt default from overflowing the right
    margin in the rendered PDF.
    """
    fixed = 0
    for anchor in root.iter(WP + "anchor"):
        docPr = anchor.find(WP + "docPr")
        if docPr is None:
            continue
        descr = (docPr.get("descr") or "").lower()
        name  = (docPr.get("name")  or "").lower()
        if "classif" not in descr and "classif" not in name and "sensitivity" not in name:
            continue
        # Found a classification shape — fix its extent.
        extent = anchor.find(WP + "extent")
        if extent is not None:
            extent.set("cx", CLASSIFICATION_BOX_EMU)
            fixed += 1
        # Also fix the inner xfrm extent so the shape geometry matches.
        for xfrm in anchor.iter(A + "xfrm"):
            ext = xfrm.find(A + "ext")
            if ext is not None:
                ext.set("cx", CLASSIFICATION_BOX_EMU)
        # Set explicit small font size on every run inside the text box so the
        # text doesn't overflow the header at the inherited 12pt default.
        for rPr in anchor.iter(W + "rPr"):
            for tag in (W + "sz", W + "szCs"):
                el = rPr.find(tag)
                if el is None:
                    el = ET.SubElement(rPr, tag)
                el.set(W + "val", CLASSIFICATION_FONT_SZ)
    return fixed


# ---------------------------------------------------------------------------
# Fix 5: indent Heading1 paragraphs on the title page only
# ---------------------------------------------------------------------------
# The leaf graphic in header3 (first-page header) extends ~7.76 cm from the
# right text edge.  Any Heading1 on the title page that is wide enough will
# run into it.  We apply a right indent only to Heading1 paragraphs that
# appear before the first explicit page break (lastRenderedPageBreak or a
# w:br type="page"), which is where the title-page content ends.
TITLEPAGE_IND_RIGHT = "3600"   # twips — same as Title/Subtitle styles

def fix_titlepage_headings(doc_root: ET.Element) -> int:
    """Add right indent to Heading1 paragraphs on the first page only."""
    fixed = 0
    for p in doc_root.iter(W + "p"):
        # Check for a page break inside this paragraph — stop after it.
        for br in p.iter(W + "br"):
            if br.get(W + "type") in ("page", "column"):
                return fixed

        pPr = p.find(W + "pPr")
        if pPr is None:
            continue
        pStyle = pPr.find(W + "pStyle")
        if pStyle is None or pStyle.get(W + "val") != "Heading1":
            continue

        ind = pPr.find(W + "ind")
        if ind is None:
            ind = ET.SubElement(pPr, W + "ind")
        # Only set if not already wider than our value.
        current = int(ind.get(W + "right", "0") or "0")
        if current < int(TITLEPAGE_IND_RIGHT):
            ind.set(W + "right", TITLEPAGE_IND_RIGHT)
            fixed += 1

    return fixed


def fix_doc(path: str) -> dict:
    tmp = path + ".tmp"
    counts = {"tables": 0, "classif_boxes": 0, "styles": False, "injected": []}

    with zipfile.ZipFile(path) as zin:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
            for name in zin.namelist():
                data = zin.read(name)

                if name == "word/styles.xml":
                    root = ET.fromstring(data)
                    fix_heading2_styles(root)
                    counts["injected"] = fix_missing_styles(root)
                    counts["styles"] = True
                    data = ET.tostring(root, xml_declaration=True, encoding="UTF-8")

                elif name.startswith("word/header") and name.endswith(".xml"):
                    root = ET.fromstring(data)
                    counts["classif_boxes"] += fix_classification_textboxes(root)
                    data = ET.tostring(root, xml_declaration=True, encoding="UTF-8")

                elif (
                    name.startswith("word/")
                    and name.endswith(".xml")
                    and b"<w:tbl>" in data
                ):
                    root = ET.fromstring(data)
                    for tbl in root.iter(W + "tbl"):
                        fix_table(tbl)
                        counts["tables"] += 1
                    data = ET.tostring(root, xml_declaration=True, encoding="UTF-8")

                zout.writestr(name, data)

    os.replace(tmp, path)
    return counts


def main() -> None:
    if len(sys.argv) < 2:
        print(
            "usage: fix-docx-tables.py <file.docx> [<file2.docx> ...]",
            file=sys.stderr,
        )
        sys.exit(1)
    for path in sys.argv[1:]:
        c = fix_doc(path)
        injected_str = (f", injected styles: {c['injected']}") if c["injected"] else ""
        print(
            f"{path}: {c['tables']} table(s), "
            f"{c['classif_boxes']} classification box(es) widened"
            f"{injected_str}"
        )


if __name__ == "__main__":
    main()
