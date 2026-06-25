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
- The title is written to DOCX metadata only, not into the header, to avoid horizontal header border lines from the template.

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
      - uses: actions/checkout@v3
      - uses: gccloudone/markdown-to-word@main
        with:
          default_title: "My Document"
          markdown_file: "docs/sample.md"
          output_file: "output/sample.docx"
          reference_doc: "template/ssc-template-v2.7.dotx"
```

The action installs dependencies from `requirements.txt` and then runs `convert-to-word.sh` with the provided inputs.
