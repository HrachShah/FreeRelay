import xml.etree.ElementTree as ET
import zipfile

z = zipfile.ZipFile("FreeRelay_v3_MAX.zip")
content = z.read("word/document.xml").decode("utf-8")

root = ET.fromstring(content)

text_parts = []
for t in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"):
    if t.text:
        text_parts.append(t.text)

result = "".join(text_parts)

# Find Section 18 - Public Leaderboard
start = result.find("18.")
if start != -1:
    with open("section_18.txt", "w", encoding="utf-8") as f:
        f.write("=== Section 18: Public Leaderboard ===\n\n")
        f.write(result[start : start + 10000])
    print("Section 18 written to section_18.txt")
