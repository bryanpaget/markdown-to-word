#!/usr/bin/env bash
set -euo pipefail

# === CONFIGURATION ===
DEFAULT_TITLE="[Untitled Document]"        # Default title for the DOCX file
DEFAULT_MD_FILE="docs/sample.md"          # Default Markdown file path
DEFAULT_OUTPUT_FILE="output/sample.docx"  # Default output file path
DEFAULT_REFERENCE_DOC="template/ssc-template-v2.7.dotx"  # Default reference template
DEFAULT_CLASSIFICATION="Unclassified | Non classifie"  # Default classification text
DEFAULT_PDF_FILE=""                       # Default PDF file (empty = no PDF generation)
DEFAULT_LATEX_TEMPLATE="template/latex-template.tex"  # Default LaTeX template

# Resolve the repository and script directories so relative paths work from any working directory.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR" && pwd)"

# Allow overriding defaults with environment variables or CLI arguments.
TITLE="${1:-${TITLE:-$DEFAULT_TITLE}}"                # First argument, environment var, or default title
MARKDOWN_FILE="${2:-${MARKDOWN_FILE:-$DEFAULT_MD_FILE}}"      # Second argument, env var, or default Markdown file
OUTPUT_FILE="${3:-${OUTPUT_FILE:-$DEFAULT_OUTPUT_FILE}}"    # Third argument, env var, or default output DOCX file
REFERENCE_DOC="${4:-${REFERENCE_DOC:-$DEFAULT_REFERENCE_DOC}}" # Fourth argument, env var, or default reference template
CLASSIFICATION="${5:-${CLASSIFICATION:-$DEFAULT_CLASSIFICATION}}" # Fifth argument, env var, or default classification
PDF_FILE="${6:-${PDF_FILE:-$DEFAULT_PDF_FILE}}"              # Sixth argument, env var, or default PDF file (empty = skip)

# === FUNCTIONS ===
usage() {
    echo "Usage: $0 [title] [markdown_file] [output_file] [reference_doc] [classification] [pdf_file]"
    echo "  title: Title to set in the DOCX metadata (default: '$DEFAULT_TITLE')."
    echo "  markdown_file: Path to the Markdown file (default: '$DEFAULT_MD_FILE')."
    echo "  output_file: Path to the output DOCX file (default: '$DEFAULT_OUTPUT_FILE')."
    echo "  reference_doc: Path to the DOCX reference template (default: '$DEFAULT_REFERENCE_DOC')."
    echo "  classification: Classification text for the header (default: '$DEFAULT_CLASSIFICATION')."
    echo "  pdf_file: Path to the output PDF file (optional)."
    exit 1
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
fi

# === CHECK DEPENDENCIES ===
if ! command -v pandoc >/dev/null 2>&1; then
    echo "❌ Error: 'pandoc' is not installed. Please install it and try again."
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "❌ Error: 'python3' is not installed. Please install it and try again."
    exit 1
fi

if ! python3 -c 'import docx' >/dev/null 2>&1; then
    echo "❌ Error: Python package 'python-docx' is not installed. Install it with 'pip3 install -r requirements.txt'."
    exit 1
fi

if ! command -v mmdc >/dev/null 2>&1; then
    echo "❌ Error: 'mmdc' (Mermaid CLI) is not installed. Please install @mermaid-js/mermaid-cli and try again."
    exit 1
fi

# Check for LaTeX dependencies if PDF generation is requested
if [[ -n "$PDF_FILE" ]]; then
    if ! command -v pdflatex >/dev/null 2>&1 && ! command -v xelatex >/dev/null 2>&1; then
        echo "⚠️  Warning: Neither 'pdflatex' nor 'xelatex' found. PDF generation will be skipped."
        PDF_FILE=""
    fi
fi

# === RESOLVE PATHS ===
WORKSPACE_ROOT="${GITHUB_WORKSPACE:-$PWD}"

if [[ "$MARKDOWN_FILE" != /* ]]; then
    MARKDOWN_FILE="$WORKSPACE_ROOT/$MARKDOWN_FILE"
fi
if [[ "$OUTPUT_FILE" != /* ]]; then
    OUTPUT_FILE="$WORKSPACE_ROOT/$OUTPUT_FILE"
fi
if [[ "$REFERENCE_DOC" != /* ]]; then
    REFERENCE_DOC="$REPO_ROOT/$REFERENCE_DOC"
fi
if [[ "$PDF_FILE" != /* && -n "$PDF_FILE" ]]; then
    PDF_FILE="$WORKSPACE_ROOT/$PDF_FILE"
fi
# === CHECK FILES ===
if [[ ! -f "$MARKDOWN_FILE" ]]; then
    echo "❌ Error: Markdown file '$MARKDOWN_FILE' not found."
    exit 1
fi

if [[ ! -f "$REFERENCE_DOC" ]]; then
    echo "❌ Error: Reference DOCX template '$REFERENCE_DOC' not found."
    exit 1
fi

mkdir -p "$(dirname "$OUTPUT_FILE")"
if [[ -n "$PDF_FILE" ]]; then
    mkdir -p "$(dirname "$PDF_FILE")"
fi

# === CONVERT TO WORD ===
echo "🔄 Converting '$MARKDOWN_FILE' to '$OUTPUT_FILE' using template '$REFERENCE_DOC' with title '$TITLE'..."
pandoc "$MARKDOWN_FILE" --metadata=title:"$TITLE" \
                        --lua-filter="$REPO_ROOT/filters/pagebreak.lua" \
                        --lua-filter="$REPO_ROOT/filters/toc.lua" \
                        --lua-filter="$REPO_ROOT/filters/mermaid.lua" \
                        -o "$OUTPUT_FILE" \
                        --reference-doc="$REFERENCE_DOC"

# Run any additional processing scripts (if needed):
python3 "$REPO_ROOT/scripts/update_header.py" "$OUTPUT_FILE" "$TITLE" "$CLASSIFICATION"
python3 "$REPO_ROOT/scripts/update_tables.py" "$OUTPUT_FILE"
EXIT_CODE=$?

# === CONVERT TO PDF (optional) ===
if [[ -n "$PDF_FILE" ]]; then
    echo "🔄 Generating PDF '$PDF_FILE' with LaTeX template and smaller margins..."
    LATEX_TEMPLATE="$REPO_ROOT/$DEFAULT_LATEX_TEMPLATE"
    TEMP_TEX="${PDF_FILE%.pdf}.tex"
    pandoc "$MARKDOWN_FILE" --metadata=title:"$TITLE" \
                            --lua-filter="$REPO_ROOT/filters/pagebreak.lua" \
                            --lua-filter="$REPO_ROOT/filters/toc.lua" \
                            --lua-filter="$REPO_ROOT/filters/mermaid.lua" \
                            -o "$TEMP_TEX" \
                            --template="$LATEX_TEMPLATE"
    if command -v xelatex >/dev/null 2>&1; then
        xelatex -interaction nonstopmode "$TEMP_TEX" || true
        xelatex -interaction nonstopmode "$TEMP_TEX" || true
    else
        pdflatex -interaction nonstopmode "$TEMP_TEX" || true
        pdflatex -interaction nonstopmode "$TEMP_TEX" || true
    fi
    if [[ -f "${TEMP_TEX%.tex}.pdf" ]]; then
        mv "${TEMP_TEX%.tex}.pdf" "$PDF_FILE"
        echo "✅ PDF generated: $PDF_FILE"
    else
        echo "⚠️  Warning: PDF generation failed."
    fi
    rm -f "$TEMP_TEX" "${TEMP_TEX%.tex}.aux" "${TEMP_TEX%.tex}.log" "${TEMP_TEX%.tex}.out" "${TEMP_TEX%.tex}.toc"
fi

if [[ $EXIT_CODE -eq 0 ]]; then
    echo "✅ Conversion successful: $OUTPUT_FILE"
else
    echo "❌ Conversion failed."
    exit $EXIT_CODE
fi
