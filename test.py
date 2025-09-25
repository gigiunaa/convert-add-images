import os
import json
import urllib.parse
import uuid
import base64
import requests
from bs4 import BeautifulSoup, Tag, NavigableString

PIXELDRAIN_API_KEY = "bff3af9e-ce55-4abc-8bf0-9fca8337da57"
blog_dir = os.getcwd()

def generate_id():
    return str(uuid.uuid4())[:8]

def empty_paragraph():
    return {
        "type": "PARAGRAPH",
        "id": generate_id(),
        "nodes": [],
        "style": {}
    }

def format_decorations(is_bold=False, is_link=False, link_url=None, is_underline=False):
    decorations = [{
        "type": "COLOR",
        "colorData": {
            "background": "transparent",
            "foreground": "rgb(0, 0, 0)"
        }
    }]
    if is_bold:
        decorations.insert(0, {"type": "BOLD", "fontWeightValue": 700})
    if is_link and link_url:
        decorations.append({
            "type": "LINK",
            "linkData": {
                "link": {
                    "url": link_url,
                    "target": "BLANK"
                }
            }
        })
    if is_underline:
        decorations.append({"type": "UNDERLINE"})
    return decorations

def build_text_node(text, bold=False, link=None, underline=False):
    return {
        "type": "TEXT",
        "id": "",
        "textData": {
            "text": text,
            "decorations": format_decorations(bold, bool(link), link, underline)
        }
    }

def wrap_paragraph_nodes(text_nodes):
    return {
        "type": "PARAGRAPH",
        "id": generate_id(),
        "nodes": text_nodes,
        "style": {}
    }

def wrap_heading(text, level=2):
    return {
        "type": "HEADING",
        "id": generate_id(),
        "nodes": [build_text_node(text, bold=True)],
        "style": {},
        "headingData": {
            "level": level,
            "textStyle": {
                "textAlignment": "AUTO"
            }
        }
    }

def wrap_list(items, ordered=False):
    return {
        "type": "ORDERED_LIST" if ordered else "BULLETED_LIST",
        "id": generate_id(),
        "nodes": [
            {
                "type": "LIST_ITEM",
                "id": generate_id(),
                "nodes": [wrap_paragraph_nodes(item)],
            }
            for item in items
        ]
    }

def wrap_table(table_data):
    return {
        "type": "TABLE",
        "id": generate_id(),
        "nodes": [
            {
                "type": "TABLE_ROW",
                "id": generate_id(),
                "nodes": [
                    {
                        "type": "TABLE_CELL",
                        "id": generate_id(),
                        "nodes": [wrap_paragraph_nodes(cell)],
                        "tableCellData": {}
                    } for cell in row
                ]
            } for row in table_data
        ],
        "tableData": {}
    }

def wrap_image(pixeldrain_url, alt=""):
    return {
        "type": "IMAGE",
        "id": generate_id(),
        "imageData": {
            "containerData": {
                "width": {
                    "size": "CONTENT"
                },
                "alignment": "CENTER",
                "textWrap": True
            },
            "image": {
                "src": {
                    "url": pixeldrain_url
                },
                "metadata": {
                    "altText": alt
                }
            }
        }
    }

def upload_to_pixeldrain(img_src):
    images_dir = os.path.join(blog_dir, "images")
    file_path = os.path.join(images_dir, os.path.basename(img_src))
    if not os.path.exists(file_path):
        print(f"❌ Image not found: {file_path}")
        return None

    print(f"🔁 Uploading {file_path} to Pixeldrain...")
    headers = {
        "Authorization": "Basic " + base64.b64encode(f":{PIXELDRAIN_API_KEY}".encode()).decode()
    }

    with open(file_path, "rb") as f:
        files = {'file': (os.path.basename(file_path), f)}
        try:
            response = requests.post("https://pixeldrain.com/api/file", headers=headers, files=files)
            if 200 <= response.status_code < 300:
                file_id = response.json()["id"]
                direct_url = f"https://pixeldrain.com/api/file/{file_id}"
                print(f"✅ Uploaded: {direct_url}")
                return direct_url
            else:
                print(f"❌ Upload failed: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"❌ Error uploading: {e}")

def extract_parts(tag, bold_class):
    parts = []
    for item in tag.children:
        if isinstance(item, NavigableString):
            text = str(item)
            if text.strip():
                is_bold = False
                if item.parent.name == "span" and bold_class and bold_class in item.parent.get("class", []):
                    is_bold = True
                parts.append(build_text_node(text, bold=is_bold))
        elif isinstance(item, Tag):
            if item.name == "br":
                continue
            elif item.name == "img" and item.get("src"):
                pixeldrain_url = upload_to_pixeldrain(item["src"])
                if pixeldrain_url:
                    parts.append(wrap_image(pixeldrain_url, item.get("alt", "")))
            elif item.name == "a" and item.get("href"):
                raw_href = item["href"]
                if "https://www.google.com/url?q=" in raw_href:
                    raw_href = urllib.parse.unquote(raw_href.split("url?q=")[-1].split("&")[0])
                else:
                    raw_href = urllib.parse.unquote(raw_href)
                is_bold = any(
                    child.name == "span" and bold_class in child.get("class", [])
                    for child in item.descendants if isinstance(child, Tag)
                )
                parts.append(build_text_node(item.get_text(), bold=is_bold, link=raw_href, underline=True))
            else:
                parts.extend(extract_parts(item, bold_class))
    return parts

def apply_spacing(nodes, block_type):
    spacing_before_rules = {
        "H2": 2,
        "H3": 1,
        "H4": 1,
        "ORDERED_LIST": 1,
        "BULLETED_LIST": 1,
        "PARAGRAPH": 1,
        "IMAGE": 1
    }
    spacing_after_rules = {
        "H2": 1,
        "H3": 1,
        "H4": 1,
        "ORDERED_LIST": 1,
        "BULLETED_LIST": 1,
        "PARAGRAPH": 1
    }
    return spacing_before_rules.get(block_type, 0), spacing_after_rules.get(block_type, 0)

def count_trailing_empty_paragraphs(nodes):
    count = 0
    for node in reversed(nodes):
        if node["type"] == "PARAGRAPH" and not node["nodes"]:
            count += 1
        else:
            break
    return count

def ensure_spacing(nodes, required):
    current = count_trailing_empty_paragraphs(nodes)
    if current < required:
        for _ in range(required - current):
            nodes.append(empty_paragraph())
    elif current > required:
        for _ in range(current - required):
            nodes.pop()
    return required  # Now it returns what was ensured

def html_to_ricos():
    html_path = os.path.join(blog_dir, "document.html")
    if not os.path.exists(html_path):
        print("❌ document.html not found in root directory.")
        return

    with open(html_path, "r", encoding="utf-8") as file:
        soup = BeautifulSoup(file.read(), "html.parser")

    body = soup.body if soup.body else soup
    nodes = []
    bold_class = None

    style_tag = soup.find("style")
    if style_tag and style_tag.string:
        for line in style_tag.string.split("}"):
            if 'font-weight:700' in line:
                class_name = line.split("{")[0].strip()
                if class_name.startswith("."):
                    bold_class = class_name[1:]
                    break

    for elem in body.find_all(recursive=False):
        tag = elem.name

        def add_node_with_spacing(node, block_type):
            spacing_before, spacing_after = apply_spacing(nodes, block_type)

            # Remove overlapping empty paragraphs before this block
            ensure_spacing(nodes, spacing_before)

            # Add the actual block
            nodes.append(node)

            # Now handle spacing AFTER — count how many empty lines already at the end
            trailing = count_trailing_empty_paragraphs(nodes)
            needed = spacing_after - trailing
            if needed > 0:
                for _ in range(needed):
                    nodes.append(empty_paragraph())

        if tag == "img" and elem.get("src"):
            pixeldrain_url = upload_to_pixeldrain(elem["src"])
            if pixeldrain_url:
                add_node_with_spacing(wrap_image(pixeldrain_url, elem.get("alt", "")), "PARAGRAPH")

        elif tag in ["h2", "h3", "h4"]:
            level = int(tag[1])
            imgs = elem.find_all("img")
            for img in imgs:
                if img.get("src"):
                    pixeldrain_url = upload_to_pixeldrain(img["src"])
                    if pixeldrain_url:
                        add_node_with_spacing(wrap_image(pixeldrain_url, img.get("alt", "")), "PARAGRAPH")
            text = elem.get_text(strip=True)
            if text:
                add_node_with_spacing(wrap_heading(text, level), f"H{level}")

        elif tag == "p":
            imgs = elem.find_all("img", recursive=False)
            if imgs:
                for img in imgs:
                    if img.get("src"):
                        pixeldrain_url = upload_to_pixeldrain(img["src"])
                        if pixeldrain_url:
                            add_node_with_spacing(wrap_image(pixeldrain_url, img.get("alt", "")), "PARAGRAPH")
            else:
                parts = extract_parts(elem, bold_class)
                if parts:
                    add_node_with_spacing(wrap_paragraph_nodes(parts), "PARAGRAPH")

        elif tag in ["ul", "ol"]:
            is_ordered = tag == "ol"
            list_items = []
            for li in elem.find_all("li", recursive=False):
                content = extract_parts(li, bold_class)
                if content:
                    list_items.append(content)
            if list_items:
                block_type = "ORDERED_LIST" if is_ordered else "BULLETED_LIST"
                add_node_with_spacing(wrap_list(list_items, ordered=is_ordered), block_type)

        elif tag == "table":
            table = []
            for tr in elem.find_all("tr"):
                row = []
                for td in tr.find_all(["td", "th"]):
                    row.append(extract_parts(td, bold_class))
                table.append(row)
            if table:
                add_node_with_spacing(wrap_table(table), "PARAGRAPH")

    return {"nodes": nodes}

if __name__ == "__main__":
    ricos_json = html_to_ricos()
    if ricos_json:
        with open("ricos_output.json", "w", encoding="utf-8") as out_file:
            json.dump(ricos_json, out_file, ensure_ascii=False, indent=2)
        print("✅ Ricos JSON written to ricos_output.json")
