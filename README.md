# Markdown to Word Converter

This repository provides a script and GitHub Action to convert a Markdown file to a Word document (`.docx`) using Pandoc.

## Usage

Convert a Markdown file to Word locally:

```bash
./convert-to-word.sh "My Document Title" docs/sample.md output/sample.docx template/ssc-template-v2.7.dotx
```

You can also override defaults with environment variables:

```bash
TITLE="My Document" MARKDOWN_FILE="docs/sample.md" OUTPUT_FILE="output/sample.docx" REFERENCE_DOC="template/ssc-template-v2.7.dotx" ./convert-to-word.sh
```

## Requirements

- `pandoc`
- `python3`
- Python package `python-docx`
- `@mermaid-js/mermaid-cli` (`mmdc`)

## Notes

- The script resolves relative paths from the repository root.
- Output directories are created automatically.
- The DOCX reference template is configured for standard US Letter size (8.5" x 11").
- The title is written to both DOCX metadata and the header, replacing the "[Enter Document Title]" placeholder in the template.

## GitHub Action

This repository also includes a composite GitHub Action. To use it from a workflow:

```yaml
name: Markdown to Word
on:
  workflow_dispatch:

jobs:
  convert:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Repository
        uses: actions/checkout@v4

      - name: Convert Markdown to Word
        uses: gccloudone/markdown-to-word@main
        with:
          default_title: "[Untitled Document]"
          markdown_file: "${{ runner.temp }}/combined.md"
          output_file: "output/markdown-to-word.docx"
          reference_doc: "template/ssc-template-v2.7.dotx"
        env:
          PDF_FILE: ""
```

> Important: This composite action does not perform its own repository checkout. The calling workflow must check out the repository before invoking the action.

The action installs dependencies from `requirements.txt` and then runs `convert-to-word.sh` with the provided inputs.
