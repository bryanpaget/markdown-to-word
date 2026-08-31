#!/usr/bin/env python3
"""Style code blocks in a pandoc-generated DOCX.

Pandoc emits code as paragraphs styled ``Source Code`` whose runs use syntax
highlight token character styles (``FunctionTok``, ``KeywordTok``, ...) that all
chain to a ``VerbatimChar`` character style. In a freshly generated document
those styles carry no font or size, so code renders in the body font (Aptos,
proportional) at body size.

This script post-processes ``word/styles.xml`` so code renders in a monospace
font (Consolas; substituted by DejaVu Sans Mono / Courier New when absent), at a
smaller size, on a light grey shaded background.

Usage: style-docx-code.py <docx_path>
"""

import os
import re
import shutil
import sys
import tempfile
import zipfile

CODE_FONT = "Consolas"
CODE_SIZE_HALF_PTS = "18"  # 9pt
SHADE_FILL = "F2F2F2"  # light grey

STYLES_XML = "word/styles.xml"


def build_source_code_style(full_match):
    """Return the rebuilt SourceCode paragraph style element (font, size, shading).

    ``full_match`` is the regex match over the entire ``<w:style ...>...</w:style>``
    element. The opening tag (including any attribute order) and all child
    elements except ``w:pPr`` are preserved; ``w:pPr`` is rebuilt with word wrap
    off and light grey shading.
    """
    full = full_match.group(0)
    open_tag_end = full.find(">")
    open_tag = full[: open_tag_end + 1]
    body = full[open_tag_end + 1: -len("</w:style>")]

    ppr = (
        "<w:pPr>"
        "<w:wordWrap w:val=\"off\" />"
        "<w:shd w:val=\"clear\" w:color=\"auto\" w:fill=\"%s\" />"
        "</w:pPr>"
    ) % SHADE_FILL
    rpr = (
        "<w:rPr>"
        "<w:rFonts w:ascii=\"%s\" w:hAnsi=\"%s\" w:eastAsia=\"%s\" w:cs=\"%s\" />"
        "<w:sz w:val=\"%s\" /><w:szCs w:val=\"%s\" />"
        "</w:rPr>"
    ) % (CODE_FONT, CODE_FONT, CODE_FONT, CODE_FONT, CODE_SIZE_HALF_PTS, CODE_SIZE_HALF_PTS)

    name = ""
    m = re.search(r"<w:name\s+[^>]*/>", body)
    if m:
        name = m.group(0)

    return open_tag + name + rpr + ppr + "</w:style>"


VERBATIM_CHAR_STYLE = (
    '<w:style w:type="character" w:styleId="VerbatimChar">'
    '<w:name w:val="VerbatimChar" />'
    '<w:basedOn w:val="DefaultParagraphFont" />'
    '<w:rPr>'
    '<w:rFonts w:ascii="%s" w:hAnsi="%s" w:eastAsia="%s" w:cs="%s" />'
    '<w:sz w:val="%s" /><w:szCs w:val="%s" />'
    '</w:rPr>'
    '</w:style>'
) % (CODE_FONT, CODE_FONT, CODE_FONT, CODE_FONT, CODE_SIZE_HALF_PTS, CODE_SIZE_HALF_PTS)


def process(styles_path, styles_xml):
    with open(styles_xml, "r", encoding="utf-8") as fh:
        content = fh.read()

    changed = False

    m = re.search(r'<w:style\s+[^>]*w:styleId="SourceCode"[^>]*>.*?</w:style>', content, re.S)
    if m:
        new_style = build_source_code_style(m)
        if new_style != m.group(0):
            content = content[:m.start()] + new_style + content[m.end():]
            changed = True

    if 'w:styleId="VerbatimChar"' not in content:
        content = content.replace("</w:styles>", VERBATIM_CHAR_STYLE + "</w:styles>")
        changed = True

    if changed:
        with open(styles_xml, "w", encoding="utf-8") as fh:
            fh.write(content)
    return changed


def main():
    if len(sys.argv) != 2:
        print("Usage: style-docx-code.py <docx_path>", file=sys.stderr)
        sys.exit(1)

    docx_path = os.path.abspath(sys.argv[1])
    if not os.path.exists(docx_path):
        print("Error: file not found: %s" % docx_path, file=sys.stderr)
        sys.exit(1)

    tmp = docx_path + ".tmp"
    shutil.copy2(docx_path, tmp)

    try:
        with zipfile.ZipFile(tmp, "r") as zin:
            with tempfile.TemporaryDirectory() as tmpdir:
                zin.extractall(tmpdir)
                styles_xml = os.path.join(tmpdir, STYLES_XML)
                changed = process(STYLES_XML, styles_xml)
                if changed:
                    with zipfile.ZipFile(docx_path, "w") as zout:
                        for name in zin.namelist():
                            p = os.path.join(tmpdir, name)
                            if os.path.exists(p):
                                zout.write(p, name)
        if changed:
            print("Updated code styles in %s" % docx_path)
        else:
            print("No changes needed for %s" % docx_path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


if __name__ == "__main__":
    main()
