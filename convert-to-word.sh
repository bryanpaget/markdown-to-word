#!/usr/bin/env bash
set -euo pipefail

# === CONFIGURATION ===
DEFAULT_TITLE="[Untitled Document]"        # Default title for the DOCX file
DEFAULT_MD_FILE="docs/sample.md"          # Default Markdown file path
DEFAULT_OUTPUT_FILE="output/sample.docx"  # Default output file path
DEFAULT_REFERENCE_DOC="template/ssc-template-v2.7.dotx"  # Default reference template
DEFAULT_CLASSIFICATION="Unclassified | Non classifie"  # Default classification text

# Resolve the repository and script directories so relative paths work from any working directory.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"

# Allow overriding defaults with environment variables or CLI arguments.
TITLE="${1:-${TITLE:-$DEFAULT_TITLE}}"                # First argument, environment var, or default title
MARKDOWN_FILE="${2:-${MARKDOWN_FILE:-$DEFAULT_MD_FILE}}"      # Second argument, env var, or default Markdown file
OUTPUT_FILE="${3:-${OUTPUT_FILE:-$DEFAULT_OUTPUT_FILE}}"    # Third argument, env var, or default output DOCX file
REFERENCE_DOC="${4:-${REFERENCE_DOC:-$DEFAULT_REFERENCE_DOC}}" # Fourth argument, env var, or default reference template
CLASSIFICATION="${5:-${CLASSIFICATION:-$DEFAULT_CLASSIFICATION}}" # Fifth argument, env var, or default classification

# Read number_sections from GitHub Actions input (environment)
INPUT_NUMBER_SECTIONS="${INPUT_NUMBER_SECTIONS:-false}"
NUMBER_SECTIONS_FLAG=""
if [[ "$INPUT_NUMBER_SECTIONS" == "true" || "$INPUT_NUMBER_SECTIONS" == "1" || "$INPUT_NUMBER_SECTIONS" == "yes" ]]; then
    NUMBER_SECTIONS_FLAG="--number-sections"
fi

# === FUNCTIONS ===
usage() {
    echo "Usage: $0 [title] [markdown_file] [output_file] [reference_doc] [classification]"
    echo "  title: Title to set in the DOCX metadata (default: '$DEFAULT_TITLE')."
    echo "  markdown_file: Path to the Markdown file (default: '$DEFAULT_MD_FILE')."
    echo "  output_file: Path to the output DOCX file (default: '$DEFAULT_OUTPUT_FILE')."
    echo "  reference_doc: Path to the DOCX reference template (default: '$DEFAULT_REFERENCE_DOC')."
    echo "  classification: Classification text for the header (default: '$DEFAULT_CLASSIFICATION')."
    echo "  (Section numbering is controlled by the INPUT_NUMBER_SECTIONS environment variable.)"
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

# === CONVERT TO WORD ===
echo "🔄 Converting '$MARKDOWN_FILE' to '$OUTPUT_FILE' using template '$REFERENCE_DOC' with title '$TITLE'..."
pandoc "$MARKDOWN_FILE" --metadata=title="$TITLE" \
    --lua-filter="$REPO_ROOT/filters/pagebreak.lua" \
    --lua-filter="$REPO_ROOT/filters/toc.lua" \
    --lua-filter="$REPO_ROOT/filters/mermaid.lua" \
    $NUMBER_SECTIONS_FLAG \
    -o "$OUTPUT_FILE" \
    --reference-doc="$REFERENCE_DOC"

python3 "$REPO_ROOT/scripts/update_header.py" "$OUTPUT_FILE" "$TITLE" "$CLASSIFICATION"
python3 "$REPO_ROOT/scripts/update_tables.py" "$OUTPUT_FILE"

echo "✅ Conversion successful: $OUTPUT_FILE"
