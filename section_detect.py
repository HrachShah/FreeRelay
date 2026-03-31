import zipfile
import xml.etree.ElementTree as ET
import re

z = zipfile.ZipFile("FreeRelay_v3_MAX.zip")
content = z.read("word/document.xml").decode("utf-8")

root = ET.fromstring(content)

text_parts = []
for t in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"):
    if t.text:
        text_parts.append(t.text)

result = "".join(text_parts)

# Find the table of contents section (first ~2000 chars have "SectionTopic")
toc_start = result.find("SectionTopic")
if toc_start != -1:
    toc = result[toc_start : toc_start + 3000]
    # Find all entries in TOC
    entries = re.findall(r"(\d+)[–-](\d+)([A-Z][^0-9]*)", toc)
    print("=== Table of Contents ===")
    for start, end, title in entries:
        print(f"{start}-{end}: {title.strip()[:80]}")
