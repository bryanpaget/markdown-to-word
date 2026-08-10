# Markdown to Word &middot; SSC GitHub Action

[![SSC Template](https://img.shields.io/badge/SSC-Template%20v2.7-d52b1e?style=flat-square&labelColor=1a1f2e)](template/ssc-template-v2.7.dotx)
[![Government of Canada](https://img.shields.io/badge/Gov't%20of%20Canada-Compatible-1a2840?style=flat-square&labelColor=0f1419)](docs/index.html)

Converts Government of Canada Markdown documentation into professionally formatted
Word documents (`.docx`) using the official [Shared Services Canada (SSC) template](template/ssc-template-v2.7.dotx).

> **Website**: [bryanpaget.github.io/markdown-to-word](https://bryanpaget.github.io/markdown-to-word)

## SSC Template

This action is purpose-built for the SSC documentation workflow. The reference template (`template/ssc-template-v2.7.dotx`) provides:

- **Cover page** — title, subtitle, date, version, and classification banner
- **Headers & footers** — document title and bilingual classification on every page
- **GC-compliant fonts** — Carlito (Calibri substitute), Liberation Serif for headings
- **Classification handling** — set `UNCLASSIFIED`, `Protected A`, `Protected B`, or `CONFIDENTIAL` via the `classification` input
- **Bilingual support** — default classification is `Unclassified | Non classifi&eacute;`

## Usage

```bash
./convert-to-word.sh "Incident Response Plan" docs/incident-response.md output/incident-response.docx
```

With environment variables:

```bash
TITLE="Incident Response Plan" \
MARKDOWN_FILE="docs/incident-response.md" \
OUTPUT_FILE="output/incident-response.docx" \
./convert-to-word.sh
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
| `reference_doc` | no | `template/ssc-template-v2.7.dotx` | SSC Word template (`.dotx`) |
| `classification` | no | `Unclassified \| Non classifi&eacute;` | Bilingual classification in header |
| `number_sections` | no | `false` | Numbered headings (`1.`, `1.1`, etc.) |

> The action installs all dependencies automatically. Make sure to check out the repository before invoking.

## Notes

- Uses the official **SSC template** (`ssc-template-v2.7.dotx`) with cover page, headers, and classification.
- Place `:::{#toc}:::` in your Markdown for a static table of contents with hyperlink entries.
- Mermaid diagrams (```` ```mermaid ````) are rendered as embedded images.
- Classification is written to the document header and document properties — suitable for GC document handling.
