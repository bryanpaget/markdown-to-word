import sys
import os
import zipfile
import re
import tempfile

def update_header(docx_path, title_text, classification=None):
    # Ensure the docx_path is an absolute path
    docx_path = os.path.abspath(docx_path)

    # Check if the file exists
    if not os.path.exists(docx_path):
        raise FileNotFoundError(f"Error: Cannot find DOCX file at '{docx_path}'")
    
    # Default classification if not provided
    if classification is None:
        classification = "Unclassified | Non classifie"

    # We'll modify the docx file directly by working with the zip archive
    # This gives us access to all headers, not just the ones python-docx exposes
    import shutil
    temp_docx = docx_path + '.tmp'
    
    # Make a copy to work on
    shutil.copy2(docx_path, temp_docx)
    
    with zipfile.ZipFile(temp_docx, 'r') as z:
        # Create a temporary directory to extract and modify files
        with tempfile.TemporaryDirectory() as tmpdir:
            # Extract all files
            z.extractall(tmpdir)
            
            # Get the metadata title (this is what was previously set)
            core_xml_path = os.path.join(tmpdir, 'docProps/core.xml')
            metadata_title = None
            if os.path.exists(core_xml_path):
                with open(core_xml_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                match = re.search(r'<dc:title>([^<]*)</dc:title>', content)
                if match:
                    metadata_title = match.group(1)
            
            # Only replace the placeholder and the old metadata title
            # Don't replace other header content like "Unclassified | Non classifié"
            # The template has the placeholder split across elements: "[Enter ", "Document Title", "]"
            placeholders = ["[Enter Document Title]", "[Enter ", "Document Title", "]"]
            if metadata_title and metadata_title.strip():
                placeholders.append(metadata_title)
            
            # Remove duplicates while preserving order
            seen = set()
            placeholders = [p for p in placeholders if p and p.strip() and not (p in seen or seen.add(p))]
            
            # Update core.xml for metadata
            if os.path.exists(core_xml_path):
                with open(core_xml_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                # Replace title in core.xml
                content = re.sub(
                    r'<dc:title>([^<]*)</dc:title>',
                    f'<dc:title>{title_text}</dc:title>',
                    content
                )
                with open(core_xml_path, 'w', encoding='utf-8') as f:
                    f.write(content)
            
            # Update all header XML files
            for name in z.namelist():
                if 'header' in name.lower() and name.endswith('.xml'):
                    filepath = os.path.join(tmpdir, name)
                    if os.path.exists(filepath):
                        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                            content = f.read()
                        
                        # First handle the split placeholder case: "[Enter ", "Document Title", "]"
                        # The template has: <w:t>[Enter </w:t>...<w:t>Document Title</w:t>...<w:t>]</w:t>
                        # Match the entire sequence and replace with a single element containing the title
                        split_pattern = r'\[Enter [\s\S]*?Document Title[\s\S]*?\]'
                        split_replacement = f'<w:r><w:t>{title_text}</w:t></w:r>'
                        content = re.sub(split_pattern, split_replacement, content, count=1)
                        
                        # Also handle the non-split placeholder
                        for placeholder in placeholders:
                            # Skip the split parts if we already handled them
                            if placeholder in ["[Enter ", "Document Title", "]"]:
                                continue
                            # Escape special regex characters in placeholder
                            escaped = re.escape(placeholder)
                            # Replace in <w:t> elements
                            content = re.sub(
                                rf'(<w:t[^>]*>){escaped}(</w:t>)',
                                rf'\1{title_text}\2',
                                content
                            )
                        
                        # Replace classification text in all <w:t> elements
                        # This handles "Unclassified | Non classifie" being in the headers
                        # Escape the classification text for regex
                        escaped_classification = re.escape(classification)
                        escaped_default = re.escape("Unclassified | Non classifie")
                        # Replace the default classification text with the custom one
                        content = re.sub(
                            rf'(<w:t[^>]*>){escaped_default}(</w:t>)',
                            rf'\1{classification}\2',
                            content
                        )
                        
                        with open(filepath, 'w', encoding='utf-8') as f:
                            f.write(content)
            
            # Write all files to the final docx
            with zipfile.ZipFile(docx_path, 'w') as out_z:
                for name in z.namelist():
                    filepath = os.path.join(tmpdir, name)
                    if os.path.exists(filepath):
                        out_z.write(filepath, name)
    
    # Remove temp file
    if os.path.exists(temp_docx):
        os.remove(temp_docx)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 update_header.py <docx_path> <title_text> [classification]")
        sys.exit(1)

    docx_path = sys.argv[1]
    title_text = sys.argv[2]
    classification = sys.argv[3] if len(sys.argv) > 3 else None

    update_header(docx_path, title_text, classification)
