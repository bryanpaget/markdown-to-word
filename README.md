# Markdown to Word &middot; SSC GitHub Action

Converts Government of Canada Markdown documentation into professionally formatted
Word documents (`.docx`) using the [SSC template](template/ssc-template-v2.7.dotx).

> **Website**: [bryanpaget.github.io/markdown-to-word](https://bryanpaget.github.io/markdown-to-word)

## Usage

Convert a Markdown file to Word locally:

```bash
./convert-to-word.sh "My Document Title" docs/sample.md output/sample.docx template/ssc-template-v2.7.dotx
```

With environment variables:

```bash
TITLE="My Document" MARKDOWN_FILE="docs/sample.md" OUTPUT_FILE="output/sample.docx" REFERENCE_DOC="template/ssc-template-v2.7.dotx" ./convert-to-word.sh
```

## Requirements

- `pandoc` (3.0+)
- `python3` + `python-docx`
- `@mermaid-js/mermaid-cli` (`mmdc`)

## How It Works

1. **Pandoc** converts Markdown to DOCX using the SSC template
2. **Lua filters** handle page breaks, table of contents, and Mermaid diagrams
3. **Python scripts** post-process the DOCX (header, classification, table fonts)

## GitHub Action

```yaml
- name: Convert Markdown to Word
  uses: bryanpaget/markdown-to-word@main
  with:
    default_title: "Incident Response Plan"
    markdown_file: "docs/incident-response.md"
    output_file:   "output/incident-response.docx"
```

| Input | Required | Default | Description |
|---|---|---|---|
| `default_title` | yes | &mdash; | Title for the Word document |
| `markdown_file` | yes | &mdash; | Path to the Markdown file |
| `output_file` | no | `output/output.docx` | Output DOCX path |
| `reference_doc` | no | `template/ssc-template-v2.7.dotx` | SSC template |
| `classification` | no | `Unclassified \| Non classifi&eacute;` | Document classification |
| `number_sections` | no | `false` | Numbered headings |

> The action installs all dependencies automatically. Make sure to check out the repository before invoking.

## Notes

- Uses the official **SSC template** (`ssc-template-v2.7.dotx`) with cover page, headers, and classification.
- Place `:::{#toc}:::` in your Markdown for a Word TOC field.
- Mermaid diagrams (` ```mermaid `) are rendered as embedded images.
