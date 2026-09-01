#!/usr/bin/env python3
"""Assemble the Aurora Security Narratives book markdown.

Produces a single markdown file (default output/books/aurora-security-narratives.md)
containing, in order:

1.  YAML frontmatter + TOC placeholder (consumed by the markdown-to-word filters).
2.  README.md (the SCTM) as the first section.
3.  Every security control narrative in azure/*.md, in SCTM order.
4.  Appendix A - evidence documents (AUR-SEC-* local copies). (optional)
5.  Appendix B - incident reports (AUR-INC-*). (optional)
6.  Only items 1-3 are built by default; see INCLUDE_APPENDICES.

While assembling, local references are resolved and rewritten:
- Images (png/svg) -> repo-root-relative paths so pandoc embeds them.
- YAML/terraform/config evidence (.yaml/.yml/.tf/.txt/.json/.d2) -> content is
  injected into the book as a fenced code block beneath the link.
- Markdown evidence/incident links -> internal anchors into the appendices.
- README SCTM links to controls -> internal anchors (#ac-2 etc.).

Links that cannot be resolved are left unchanged (never fabricated).

Appendices (evidence documents and incident reports) are excluded by default and
enabled with INCLUDE_APPENDICES=1. When embedded, each appendix file's own YAML
frontmatter is stripped so it cannot override the book metadata (pandoc merges
multiple metadata blocks, later ones winning).
"""

import os
import re
import sys
import urllib.parse
from datetime import date

# The security-narratives repo root. When these helpers are run from a cloned
# markdown-to-word/scripts/ directory, the caller (export.sh) sets
# NARRATIVES_ROOT so paths resolve against the narratives repo, not this clone.
REPO_ROOT = os.environ.get("NARRATIVES_ROOT") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
AZURE_DIR = os.path.join(REPO_ROOT, "azure")
README_PATH = os.path.join(REPO_ROOT, "README.md")

DEFAULT_TITLE = "Aurora Security Narratives"
DEFAULT_AUTHOR = "Shared Services Canada"
DEFAULT_VERSION = "v1.0.0"
DEFAULT_CLASSIFICATION = "UNCLASSIFIED"

INJECT_EXTS = {".yaml", ".yml", ".tf", ".txt", ".json", ".d2"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg"}
LANGS = {".yaml": "yaml", ".yml": "yaml", ".tf": "hcl", ".txt": "text", ".json": "json", ".d2": "d2"}

TITLE = os.environ.get("COMBINED_TITLE", DEFAULT_TITLE)
AUTHOR = os.environ.get("AUTHOR", DEFAULT_AUTHOR)
VERSION = os.environ.get("VERSION", DEFAULT_VERSION)
CLASSIFICATION = os.environ.get("CLASSIFICATION", DEFAULT_CLASSIFICATION)
EFFECTIVE_DATE = os.environ.get("EFFECTIVE_DATE", date.today().isoformat())
OUTPUT = os.environ.get("BOOK_OUTPUT", os.path.join("output", "books", "aurora-security-narratives.md"))

# Appendices (markdown evidence docs + incident reports) are included by default so
# that every evidence artifact linked from a control is pulled into the book. Set
# INCLUDE_APPENDICES=0 (or false/no/off) to exclude them.
_APPENDIX_FLAG = os.environ.get("INCLUDE_APPENDICES", "").strip().lower()
if _APPENDIX_FLAG in ("0", "false", "no", "off"):
    INCLUDE_APPENDICES = False
else:
    INCLUDE_APPENDICES = True

INCIDENTS_DIR = os.path.join(AZURE_DIR, "incidents")
EVIDENCE_DIR = os.path.join(AZURE_DIR, "evidence")

# Human-friendly titles for evidence docs whose filename stem is not presentable.
EVIDENCE_TITLE_OVERRIDES = {
    "aurora_ssp_draft.md": "Aurora System Security Plan",
}

WARNINGS = []


def warn(msg):
    WARNINGS.append(msg)
    print(msg, file=sys.stderr)


# ---------------------------------------------------------------------------
# Pandoc-style auto identifiers (used for internal cross-references)
# ---------------------------------------------------------------------------
def pandoc_anchor(text):
    """Replicate pandoc's auto_identifier algorithm for ASCII heading text."""
    s = text.replace(" ", "-").replace("\n", "-")
    s = re.sub(r"[^A-Za-z0-9_.\-]", "", s)
    s = s.lower()
    m = re.search(r"[a-z]", s)
    if m:
        s = s[m.start():]
    else:
        s = "section"
    return s


# ---------------------------------------------------------------------------
# SCTM order (authoritative ordering from README)
# ---------------------------------------------------------------------------
def sctm_control_files():
    order = []
    if not os.path.exists(README_PATH):
        return order
    in_sctm = False
    with open(README_PATH, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("## SCTM"):
                in_sctm = True
                continue
            if in_sctm and line.startswith("## "):
                break
            if in_sctm:
                m = re.search(r"\]\((azure/[\w()-]+\.md)\)", line)
                if m and "docs/" not in m.group(1):
                    order.append(m.group(1))
    return order


# ---------------------------------------------------------------------------
# Appendix inventory
# ---------------------------------------------------------------------------
def _evidence_title(path):
    """Presentable appendix title for an evidence markdown file."""
    base = os.path.basename(path)
    return EVIDENCE_TITLE_OVERRIDES.get(base, os.path.splitext(base)[0])


def discover_evidence_docs():
    """Discover every markdown evidence doc under azure/evidence/.

    Returns a list of (title, abs_path) sorted by control-folder then filename so
    the appendix order is stable. This replaces the previous hardcoded manifest so
    that new evidence is picked up automatically and nothing is silently orphaned.
    """
    items = []
    if not os.path.isdir(EVIDENCE_DIR):
        return items
    for md_path in sorted(
        (os.path.join(root, name)
         for root, _dirs, files in os.walk(EVIDENCE_DIR)
         for name in files
         if name.lower().endswith(".md")),
        key=lambda p: os.path.relpath(p, EVIDENCE_DIR).lower(),
    ):
        items.append((_evidence_title(md_path), md_path))
    return items


def discover_incident_reports():
    """Discover every incident report under azure/incidents/."""
    items = []
    if not os.path.isdir(INCIDENTS_DIR):
        return items
    for name in sorted(os.listdir(INCIDENTS_DIR)):
        if name.lower().endswith(".md"):
            path = os.path.join(INCIDENTS_DIR, name)
            items.append((os.path.splitext(name)[0], path))
    return items


APPENDIX_A = discover_evidence_docs()
APPENDIX_B = discover_incident_reports()


def build_md_anchors():
    """Map repo-root-relative appendix file path -> heading anchor."""
    if not INCLUDE_APPENDICES:
        return {}
    anchors = {}
    for title, path in APPENDIX_A + APPENDIX_B:
        rel = os.path.relpath(path, REPO_ROOT)
        anchors[rel] = pandoc_anchor(title)
    return anchors


MD_ANCHORS = build_md_anchors()

MD_ANCHORS_BY_BASENAME = {os.path.basename(k): v for k, v in MD_ANCHORS.items()}

CONTROL_ANCHORS = {}


def control_anchor(rel):
    if rel in CONTROL_ANCHORS:
        return CONTROL_ANCHORS[rel]
    abs_path = os.path.join(REPO_ROOT, rel)
    if not os.path.exists(abs_path):
        return None
    with open(abs_path, encoding="utf-8") as fh:
        head = fh.read(200)
    m = re.search(r"^#\s+(.+)$", head, flags=re.MULTILINE)
    anchor = pandoc_anchor(m.group(1).strip()) if m else None
    CONTROL_ANCHORS[rel] = anchor
    return anchor


# ---------------------------------------------------------------------------
# Link transformation
# ---------------------------------------------------------------------------
class LinkInfo(object):
    __slots__ = ("label", "target", "img")

    def __init__(self, label, target, img):
        self.label = label
        self.target = target
        self.img = img


def split_links(text):
    """Split text into alternating literal chunks and LinkInfo objects.

    Handles nested parentheses in targets (e.g. evidence/CM-2(3)/config.yaml).
    """
    chunks = []
    i = 0
    n = len(text)
    while i < n:
        m = re.compile(r"!?\[").search(text, i)
        if not m:
            chunks.append(text[i:])
            break
        if m.start() > i:
            chunks.append(text[i:m.start()])
        pos = m.end()
        img = text[m.start()] == "!"
        close = text.find("](", pos)
        if close == -1:
            chunks.append(text[m.start():])
            i = m.start() + 1
            continue
        label = text[pos:close]
        i = close + 2
        depth = 0
        j = i
        while j < n:
            c = text[j]
            if c == "(":
                depth += 1
            elif c == ")":
                if depth == 0:
                    break
                depth -= 1
            j += 1
        if j >= n:
            # unterminated link - treat as plain text
            chunks.append(text[m.start():])
            i = m.start() + 1
            continue
        target = text[i:j]
        chunks.append(LinkInfo(label, target, img))
        i = j + 1
    return chunks


def is_external(target):
    return target.startswith(("http://", "https://", "mailto:", "data:", "#")) or target.startswith("../")


# Azure DevOps web URL for a file in THIS repo, e.g.
#   https://dev.azure.com/SSC-Aurora/Aurora/_git/security-narratives?path=/azure/evidence/AC-3/x.yaml&version=GBmain
# We recognise these so evidence linked by its DevOps URL is still inlined into
# the book (the file physically lives in the repo / SA folder).
_DEVOPS_PATH_RE = re.compile(
    r"https://dev\.azure\.com/SSC-Aurora/Aurora/_git/security-narratives\?[^\s]*?path=/([^&#\s]+)")


def devops_repo_relpath(target):
    """If target is a DevOps web URL pointing at a file in this repo, return the
    repo-root-relative path to that file (if it exists), else None."""
    m = _DEVOPS_PATH_RE.search(target)
    if not m:
        return None
    rel = urllib.parse.unquote(m.group(1)).lstrip("/")
    rel = re.sub(r"/{2,}", "/", rel)
    abs_path = os.path.normpath(os.path.join(REPO_ROOT, rel))
    if not abs_path.startswith(os.path.normpath(REPO_ROOT)):
        return None
    if not os.path.exists(abs_path):
        return None
    return os.path.relpath(abs_path, REPO_ROOT)


def resolve_local(base_dir, target):
    """Resolve a local relative target against base_dir. Returns (rel_root_path, abs_path) or None."""
    t = urllib.parse.unquote(target).strip()
    t = re.sub(r"/{2,}", "/", t)
    if t.startswith("./"):
        t = t[2:]
    if t.startswith("azure/"):
        p = os.path.normpath(os.path.join(REPO_ROOT, t))
    else:
        p = os.path.normpath(os.path.join(base_dir, t))
    if not os.path.exists(p):
        # some links omit the evidence/ prefix
        alt = os.path.normpath(os.path.join(AZURE_DIR, "evidence", t))
        if os.path.exists(alt):
            p = alt
        else:
            return None
    rel = os.path.relpath(p, REPO_ROOT)
    if rel.startswith(".."):
        return None
    return rel, p


INCIDENT_LINK_RE = re.compile(r"https://dev\.azure\.com/SSC-Aurora/Aurora/_git/security-narratives[^)]*path=/azure/incidents/([A-Z0-9_.\-% ]+\.md)")


def rewrite_incident_url(target):
    m = INCIDENT_LINK_RE.search(target)
    if not m:
        return None
    fname = urllib.parse.unquote(m.group(1))
    rel = os.path.join("azure", "incidents", fname)
    anchor = MD_ANCHORS.get(rel)
    if anchor:
        return "#" + anchor
    return None


def transform(text, base_dir, rel_source, inject=True):
    """Rewrite links in markdown text. Returns (new_text, injected_blocks).

    injected_blocks is a list of (label, rel_path) for config files whose content
    should be injected beneath the link.
    """
    chunks = split_links(text)
    out = []
    injections = []
    for chunk in chunks:
        if isinstance(chunk, str):
            # reference-style definitions
            m = re.match(r"^\[([^\]]+)\]:\s+(\S+)(.*)$", chunk)
            if m:
                target = m.group(2)
                anchor = rewrite_incident_url(target)
                if anchor:
                    out.append("[%s]: %s%s" % (m.group(1), anchor, m.group(3)))
                    continue
                out.append(chunk)
                continue
            out.append(chunk)
            continue
        link = chunk
        target = link.target
        if is_external(target):
            anchor = rewrite_incident_url(target)
            if anchor:
                out.append("[%s](%s)" % (link.label, anchor))
                continue
            # Keep the (clickable) link, but if it is a DevOps URL pointing at an
            # inject-able evidence file in this repo, also inline the file content
            # so the evidence is physically present in the book.
            out.append("[%s](%s)" % (link.label, target))
            if inject and not link.img:
                dev_rel = devops_repo_relpath(target)
                if dev_rel and os.path.splitext(dev_rel)[1].lower() in INJECT_EXTS:
                    injections.append((link.label, dev_rel))
            continue
        resolved = resolve_local(base_dir, target)
        if resolved is None:
            base_name = os.path.basename(urllib.parse.unquote(target))
            anchor = MD_ANCHORS_BY_BASENAME.get(base_name)
            if anchor:
                out.append("[%s](#%s)" % (link.label, anchor))
            else:
                warn("  ! unresolved link: %s -> %s" % (rel_source, target))
                out.append("[%s](%s)" % (link.label, target))
            continue
        rel, _abs = resolved
        ext = os.path.splitext(rel)[1].lower()
        if ext == ".md":
            anchor = MD_ANCHORS.get(rel) or control_anchor(rel)
            if not anchor:
                anchor = MD_ANCHORS_BY_BASENAME.get(os.path.basename(rel))
            if anchor:
                out.append("[%s](#%s)" % (link.label, anchor))
            elif INCLUDE_APPENDICES:
                warn("  ! appendix anchor missing for: %s" % rel)
                out.append("[%s](%s)" % (link.label, rel))
            else:
                out.append("[%s](%s)" % (link.label, rel))
        elif link.img or ext in IMAGE_EXTS:
            out.append("![%s](%s)" % (link.label, rel))
        else:
            out.append("[%s](%s)" % (link.label, rel))
        if inject and ext in INJECT_EXTS:
            injections.append((link.label, rel))
    return "".join(out), injections


def read_file(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def strip_frontmatter(text):
    """Remove a leading YAML frontmatter block (--- ... ---).

    Embedded evidence/incident files carry their own frontmatter which, if left
    in, would override the book metadata (pandoc merges multiple metadata blocks
    with later ones taking precedence).
    """
    if text.startswith("\ufeff"):
        text = text[1:]
    if not text.startswith("---"):
        return text
    lines = text.split("\n")
    if len(lines) < 3:
        return text
    for i in range(2, len(lines)):
        if lines[i].strip() in ("---", "..."):
            return "\n".join(lines[i + 1:]).lstrip("\n")
    return text


def demote_headings(text):
    return re.sub(r"^(#+)\s", lambda m: "#" * (min(len(m.group(1)) + 1, 6)) + " ", text, flags=re.MULTILINE)


def render_control(rel_path):
    abs_path = os.path.join(REPO_ROOT, rel_path)
    text = read_file(abs_path)
    new_text, injections = transform(text, AZURE_DIR, rel_path, inject=True)
    parts = [new_text.rstrip()]
    for label, rel in injections:
        abs_ev = os.path.join(REPO_ROOT, rel)
        content = read_file(abs_ev)
        ext = os.path.splitext(rel)[1].lower()
        lang = LANGS.get(ext, "text")
        parts.append("")
        parts.append("**File: %s**" % rel)
        parts.append("")
        parts.append("```%s" % lang)
        parts.append(content.rstrip())
        parts.append("```")
    return "\n\n".join(parts)


def render_control_for_readme(rel_path):
    """Resolve a control reference from the README to an internal anchor."""
    abs_path = os.path.join(REPO_ROOT, rel_path)
    if not os.path.exists(abs_path):
        return rel_path
    with open(abs_path, encoding="utf-8") as fh:
        head = fh.read(200)
    m = re.search(r"^#\s+(.+)$", head, flags=re.MULTILINE)
    if m:
        return "#" + pandoc_anchor(m.group(1).strip())
    return rel_path


def render_readme():
    text = read_file(README_PATH)
    chunks = split_links(text)
    out = []
    for chunk in chunks:
        if isinstance(chunk, str):
            out.append(chunk)
            continue
        link = chunk
        target = link.target
        if target.startswith("azure/") and target.endswith(".md") and "docs/" not in target:
            anchor = render_control_for_readme(target)
            if anchor.startswith("#"):
                out.append("[%s](%s)" % (link.label, anchor))
            else:
                out.append("[%s](%s)" % (link.label, target))
        else:
            out.append("[%s](%s)" % (link.label, target))
    return "".join(out)


def render_appendix(title, items):
    parts = ["# " + title]
    for item_title, path in items:
        if not os.path.exists(path):
            warn("  ! appendix file missing: %s" % path)
            continue
        rel = os.path.relpath(path, REPO_ROOT)
        text = strip_frontmatter(read_file(path))
        new_text, injections = transform(text, os.path.dirname(path), rel, inject=True)
        body = [new_text.rstrip()]
        for _label, inj_rel in injections:
            abs_ev = os.path.join(REPO_ROOT, inj_rel)
            content = read_file(abs_ev)
            ext = os.path.splitext(inj_rel)[1].lower()
            lang = LANGS.get(ext, "text")
            body.append("")
            body.append("**File: %s**" % inj_rel)
            body.append("")
            body.append("```%s" % lang)
            body.append(content.rstrip())
            body.append("```")
        parts.append("\n\\newpage\n\n## " + item_title)
        parts.append(demote_headings("\n\n".join(body)))
    return "\n\n".join(parts)


def frontmatter():
    return """---
title: "%s"
author: "%s"
date: "%s"
version: "%s"
classification: "%s"
---

\\newpage

::: {#toc}
:::

\\newpage
""" % (TITLE, AUTHOR, EFFECTIVE_DATE, VERSION, CLASSIFICATION)


def main():
    controls = sctm_control_files()
    if not controls:
        print("Error: could not extract control list from README SCTM", file=sys.stderr)
        sys.exit(1)

    missing = [c for c in controls if not os.path.exists(os.path.join(REPO_ROOT, c))]
    if missing:
        warn("  ! SCTM controls missing files: %s" % ", ".join(missing))

    sections = [frontmatter().rstrip()]

    sections.append("# README\n\n" + render_readme().rstrip())

    for rel in controls:
        abs_path = os.path.join(REPO_ROOT, rel)
        if not os.path.exists(abs_path):
            continue
        sections.append("\\newpage\n\n" + render_control(rel))

    if INCLUDE_APPENDICES:
        sections.append(render_appendix("Appendix A - Evidence Documents", APPENDIX_A))
        sections.append(render_appendix("Appendix B - Incident Reports", APPENDIX_B))

    book = "\n\n".join(sections) + "\n"

    out_abs = os.path.join(REPO_ROOT, OUTPUT)
    os.makedirs(os.path.dirname(out_abs), exist_ok=True)
    with open(out_abs, "w", encoding="utf-8") as fh:
        fh.write(book)

    n_ctrl = len([c for c in controls if os.path.exists(os.path.join(REPO_ROOT, c))])
    extra = " (appendices included)" if INCLUDE_APPENDICES else " (appendices excluded)"
    print("Wrote %s (%d controls%s)" % (out_abs, n_ctrl, extra))
    if WARNINGS:
        print("Warnings (%d):" % len(WARNINGS))
        for w in WARNINGS:
            print(w)


if __name__ == "__main__":
    main()
