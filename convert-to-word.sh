#!/usr/bin/env bash
set -euo pipefail

# ============================================================
#  Markdown → DOCX (+ optional PDF via LaTeX)
#  Fixes: argument collision, PDF generation, path resolution
# ============================================================

# --- Config defaults ---
DEFAULT_TITLE="[Untitled Document]"
DEFAULT_MD_FILE="docs/sample.md"
DEFAULT_OUTPUT_FILE="output/sample.docx"
DEFAULT_REFERENCE_DOC="template/ssc-template-v2.7.dotx"
DEFAULT_CLASSIFICATION="Unclassified | Non classifie"
DEFAULT_PDF_FILE=""                       # empty = skip PDF
DEFAULT_LATEX_TEMPLATE="template/latex-template.tex"

# --- Resolve repo root ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"

# --- Allow overrides from environment or CLI arguments ---
# Positional: 1=title, 2=markdown, 3=output, 4=reference, 5=classification
# PDF file is NOT a positional argument – use env var PDF_FILE only.
TITLE="${1:-${TITLE:-$DEFAULT_TITLE}}"
MARKDOWN_FILE="${2:-${MARKDOWN_FILE:-$DEFAULT_MD_FILE}}"
OUTPUT_FILE="${3:-${OUTPUT_FILE:-$DEFAULT_OUTPUT_FILE}}"
REFERENCE_DOC="${4:-${REFERENCE_DOC:-$DEFAULT_REFERENCE_DOC}}"
CLASSIFICATION="${5:-${CLASSIFICATION:-$DEFAULT_CLASSIFICATION}}"
PDF_FILE="${PDF_FILE:-$DEFAULT_PDF_FILE}"   # <-- fixed: no $6, only env

# --- Helper ---
usage() {
    cat <<EOF
Usage: $0 [title] [markdown_file] [output_file] [reference_doc] [classification]

  title           : Document title (default: '$DEFAULT_TITLE')
  markdown_file   : Path to Markdown file (default: '$DEFAULT_MD_FILE')
  output_file     : Path to output DOCX (default: '$DEFAULT_OUTPUT_FILE')
  reference_doc   : Path to Word template (default: '$DEFAULT_REFERENCE_DOC')
  classification  : Classification text (default: '$DEFAULT_CLASSIFICATION')

To generate a PDF, set the environment variable PDF_FILE before running.
Example: PDF_FILE=output/sample.pdf ./convert.sh ...
EOF
    exit 1
}

[[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && usage

# --- Dependencies ---
command -v pandoc >/dev/null 2>&1 || { echo "❌ pandoc not found"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "❌ python3 not found"; exit 1; }
python3 -c 'import docx' >/dev/null 2>&1 || { echo "❌ python-docx missing"; exit 1; }
command -v mmdc >/dev/null 2>&1 || { echo "⚠️  mmdc (Mermaid) not found – diagrams may not render"; }

# --- Resolve absolute paths ---
WORKSPACE_ROOT="${GITHUB_WORKSPACE:-$PWD}"
[[ "$MARKDOWN_FILE" != /* ]] && MARKDOWN_FILE="$WORKSPACE_ROOT/$MARKDOWN_FILE"
[[ "$OUTPUT_FILE" != /* ]] && OUTPUT_FILE="$WORKSPACE_ROOT/$OUTPUT_FILE"
[[ "$REFERENCE_DOC" != /* ]] && REFERENCE_DOC="$REPO_ROOT/$REFERENCE_DOC"
[[ -n "$PDF_FILE" && "$PDF_FILE" != /* ]] && PDF_FILE="$WORKSPACE_ROOT/$PDF_FILE"

# --- Check files ---
[[ -f "$MARKDOWN_FILE" ]] || { echo "❌ Markdown file not found: $MARKDOWN_FILE"; exit 1; }
[[ -f "$REFERENCE_DOC" ]] || { echo "❌ Reference template not found: $REFERENCE_DOC"; exit 1; }

mkdir -p "$(dirname "$OUTPUT_FILE")"
[[ -n "$PDF_FILE" ]] && mkdir -p "$(dirname "$PDF_FILE")"

# --- 1. Convert to DOCX ---
echo "🔄 Converting to DOCX: $OUTPUT_FILE"
pandoc "$MARKDOWN_FILE" \
    --metadata=title:"$TITLE" \
    --lua-filter="$REPO_ROOT/filters/pagebreak.lua" \
    --lua-filter="$REPO_ROOT/filters/toc.lua" \
    --lua-filter="$REPO_ROOT/filters/mermaid.lua" \
    -o "$OUTPUT_FILE" \
    --reference-doc="$REFERENCE_DOC"

# Post-processing
python3 "$REPO_ROOT/scripts/update_header.py" "$OUTPUT_FILE" "$TITLE" "$CLASSIFICATION"
python3 "$REPO_ROOT/scripts/update_tables.py" "$OUTPUT_FILE"
EXIT_CODE=$?

# --- 2. (Optional) Generate PDF via LaTeX ---
if [[ -n "$PDF_FILE" ]]; then
    echo "🔄 Generating PDF: $PDF_FILE"
    LATEX_TEMPLATE="$REPO_ROOT/$DEFAULT_LATEX_TEMPLATE"
    
    # Use pandoc's built-in PDF engine (handles multiple passes)
    if command -v xelatex >/dev/null 2>&1; then
        ENGINE="xelatex"
    elif command -v pdflatex >/dev/null 2>&1; then
        ENGINE="pdflatex"
    else
        echo "⚠️  No LaTeX engine found – skipping PDF"
        PDF_FILE=""
    fi
    
    if [[ -n "$PDF_FILE" ]]; then
        if ! pandoc "$MARKDOWN_FILE" \
            --metadata=title:"$TITLE" \
            --lua-filter="$REPO_ROOT/filters/pagebreak.lua" \
            --lua-filter="$REPO_ROOT/filters/toc.lua" \
            --lua-filter="$REPO_ROOT/filters/mermaid.lua" \
            -o "$PDF_FILE" \
            --pdf-engine="$ENGINE" \
            --template="$LATEX_TEMPLATE"; then
            echo "❌ PDF generation failed"
            exit 1
        fi
        echo "✅ PDF generated: $PDF_FILE"
    fi
fi

# --- Finish ---
if [[ $EXIT_CODE -eq 0 ]]; then
    echo "✅ Conversion successful: $OUTPUT_FILE"
else
    echo "❌ Conversion failed (post‑processing error)"
    exit $EXIT_CODE
fi
