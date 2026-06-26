import sys
import os
import zipfile
import re
import tempfile

def update_header(docx_path, title_text):
    # Ensure the docx_path is an absolute path
    docx_path = os.path.abspath(docx_path)

    # Check if the file exists
    if not os.path.exists(docx_path):
        raise FileNotFoundError(f"Error: Cannot find DOCX file at '{docx_path}'")

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
            
            # First, collect all current titles from headers
            # This allows us to find what needs to be replaced
            header_titles = set()
            for name in z.namelist():
                if 'header' in name.lower() and name.endswith('.xml'):
                    filepath = os.path.join(tmpdir, name)
                    if os.path.exists(filepath):
                        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                            content = f.read()
                        texts = re.findall(r'<w:t[^>]*>([^<]+)</w:t>', content)
                        header_titles.update(texts)
            
            # Also get the metadata title
            core_xml_path = os.path.join(tmpdir, 'docProps/core.xml')
            metadata_title = None
            if os.path.exists(core_xml_path):
                with open(core_xml_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                match = re.search(r'<dc:title>([^<]*)</dc:title>', content)
                if match:
                    metadata_title = match.group(1)
                    header_titles.add(metadata_title)
            
            # Text to replace in headers: placeholder, metadata title, and any header titles
            placeholders = ["[Enter Document Title]"]
            if metadata_title:
                placeholders.append(metadata_title)
            placeholders.extend(header_titles)
            
            # Remove empty strings and duplicates while preserving order
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
                        
                        # Replace in text elements
                        for placeholder in placeholders:
                            # Escape special regex characters in placeholder
                            escaped = re.escape(placeholder)
                            # Replace in <w:t> elements
                            content = re.sub(
                                rf'(<w:t[^>]*>){escaped}(</w:t>)',
                                rf'\1{title_text}\2',
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
    if len(sys.argv) != 3:
        print("Usage: python3 update_header.py <docx_path> <title_text>")
        sys.exit(1)

    update_header(sys.argv[1], sys.argv[2])
