#!/usr/bin/env bash
set -euo pipefail

# === CONFIGURATION ===
DEFAULT_TITLE="[Untitled Document]"        # Default title for the DOCX file
DEFAULT_MD_FILE="docs/sample.md"          # Default Markdown file path
DEFAULT_OUTPUT_FILE="output/sample.docx"  # Default output file path
DEFAULT_REFERENCE_DOC="template/ssc-template-v2.7.dotx"  # SSC Word template
DEFAULT_CLASSIFICATION="Unclassified | Non classifie"  # Bilingual classification text

# Resolve the repository and script directories so relative paths work from any working directory.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"

# Allow overriding defaults with environment variables or CLI arguments.
TITLE="${1:-${TITLE:-$DEFAULT_TITLE}}"                # First argument, environment var, or default title
MARKDOWN_FILE="${2:-${MARKDOWN_FILE:-$DEFAULT_MD_FILE}}"      # Second argument, env var, or default Markdown file
OUTPUT_FILE="${3:-${OUTPUT_FILE:-$DEFAULT_OUTPUT_FILE}}"    # Third argument, env var, or default output DOCX file
REFERENCE_DOC="${4:-${REFERENCE_DOC:-$DEFAULT_REFERENCE_DOC}}" # Fourth argument, env var, or default reference template
CLASSIFICATION="${5:-${CLASSIFICATION:-$DEFAULT_CLASSIFICATION}}" # Fifth argument, env var, or default classification

# Mermaid filter flag, resolved after path resolution below. Default empty.
MERMAID_FLAG=""

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
    echo "  reference_doc: Path to the SSC Word template (default: '$DEFAULT_REFERENCE_DOC')."
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

# Mermaid is optional: the filter is only applied when the source actually
# contains mermaid code blocks (or MERMAID is forced to true). This avoids a
# hard dependency on @mermaid-js/mermaid-cli for documents without diagrams.
# Valid values: auto (detect), true (force on), false (force off).
MERMAID="${MERMAID:-${INPUT_MERMAID:-auto}}"
MERMAID_FLAG=""
case "$MERMAID" in
    true|1|yes) MERMAID_FLAG="--lua-filter=$REPO_ROOT/filters/mermaid.lua" ;;
    false|0|no) MERMAID_FLAG="" ;;
    auto)
        if grep -qE '^```[[:space:]]*mermaid' "$MARKDOWN_FILE" 2>/dev/null; then
            MERMAID_FLAG="--lua-filter=$REPO_ROOT/filters/mermaid.lua"
        fi
        ;;
esac

if [[ -n "$MERMAID_FLAG" ]] && ! command -v mmdc >/dev/null 2>&1; then
    echo "❌ Error: 'mmdc' (Mermaid CLI) is not installed. Please install @mermaid-js/mermaid-cli and try again."
    exit 1
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
# Only override the title if the caller explicitly provided one (not the default placeholder),
# and the caller hasn't asked to keep the template cover title.
USE_TEMPLATE_TITLE="${INPUT_USE_TEMPLATE_TITLE:-true}"
TITLE_FLAG=""
if [[ "$USE_TEMPLATE_TITLE" != "true" && "$TITLE" != "$DEFAULT_TITLE" ]]; then
    TITLE_FLAG="--metadata=title=$TITLE"
fi

echo "🔄 Converting '$MARKDOWN_FILE' to '$OUTPUT_FILE' using template '$REFERENCE_DOC'..."
pandoc "$MARKDOWN_FILE" ${TITLE_FLAG:+"$TITLE_FLAG"} \
    --lua-filter="$REPO_ROOT/filters/pagebreak.lua" \
    --lua-filter="$REPO_ROOT/filters/toc.lua" \
    ${MERMAID_FLAG:+"$MERMAID_FLAG"} \
    $NUMBER_SECTIONS_FLAG \
    --resource-path="$(dirname "$MARKDOWN_FILE")" \
    -o "$OUTPUT_FILE" \
    --reference-doc="$REFERENCE_DOC"

# Use frontmatter title for header if available, fall back to provided title
HEADER_TITLE="$TITLE"
if [[ -z "$TITLE_FLAG" ]]; then
    # Extract title from frontmatter
    FRONTMATTER_TITLE=$(awk '/^---$/{n++} n==1 && /^title:/{gsub(/^title: *"?/,""); gsub(/"$/,""); print; exit}' "$MARKDOWN_FILE")
    if [[ -n "$FRONTMATTER_TITLE" ]]; then
        HEADER_TITLE="$FRONTMATTER_TITLE"
    fi
fi

python3 "$REPO_ROOT/scripts/update_header.py" "$OUTPUT_FILE" "$HEADER_TITLE" "$CLASSIFICATION"
python3 "$REPO_ROOT/scripts/update_tables.py" "$OUTPUT_FILE"

echo "✅ Conversion successful: $OUTPUT_FILE"
