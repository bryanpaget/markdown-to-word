import sys
import os
from docx import Document

def update_header(docx_path, title_text):
    # Ensure the docx_path is an absolute path
    docx_path = os.path.abspath(docx_path)

    # Check if the file exists
    if not os.path.exists(docx_path):
        raise FileNotFoundError(f"Error: Cannot find DOCX file at '{docx_path}'")

    # Load the document
    doc = Document(docx_path)

    # Update the document title metadata only.
    # Avoid injecting the title into the header, because the reference
    # template includes a header style with a horizontal border line.
    doc.core_properties.title = title_text

    # Save the updated document
    doc.save(docx_path)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 update_header.py <docx_path> <title_text>")
        sys.exit(1)

    update_header(sys.argv[1], sys.argv[2])
