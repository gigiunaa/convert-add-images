import os
import json
import zipfile
import uuid
import urllib.parse
import base64
import requests
from flask import Flask, request, jsonify
from bs4 import BeautifulSoup, Tag, NavigableString
import logging
import time
#heki
logging.basicConfig(level=logging.INFO)

PIXELDRAIN_API_KEY = "bff3af9e-ce55-4abc-8bf0-9fca8337da57"
UPLOAD_DIR = "bff3af9e-ce55-4abc-8bf0-9fca8337da57"
app = Flask(__name__)


def generate_id():
    return str(uuid.uuid4())[:8]


def empty_paragraph():
    return {"type": "PARAGRAPH", "id": generate_id(), "nodes": [], "style": {}}


def format_decorations(is_bold=False, is_link=False, link_url=None, is_underline=False):
    dec = []

    # Add bold if requested
    if is_bold or is_link:  # Make links always bold
        dec.append({"type": "BOLD", "fontWeightValue": 700})

    # Add color (different for links)
    if is_link:
        dec.append({
            "type": "COLOR",
            "colorData": {"foreground": "#3A11AE", "background": "transparent"}
        })
    else:
        dec.append({
            "type": "COLOR",
            "colorData": {"foreground": "rgb(0, 0, 0)", "background": "transparent"}
        })

    # Add link
    if is_link and link_url:
        dec.append({
            "type": "LINK",
            "linkData": {
                "link": {
                    "url": link_url,
                    "target": "BLANK",
                    "rel": {"noreferrer": True}
                }
            }
        })

    # Add underline
    if is_underline:
        dec.append({"type": "UNDERLINE"})

    return dec


def build_text_node(text, bold=False, link=None, underline=False, extra_decorations=None):
    decorations = format_decorations(bold, bool(link), link, underline)
    if extra_decorations:
        decorations.extend(extra_decorations)
    return {
        "type": "TEXT",
        "id": "",
        "textData": {
            "text": text,
            "decorations": decorations
        }
    }


def wrap_paragraph_nodes(nodes):
    return {"type": "PARAGRAPH", "id": generate_id(), "nodes": nodes, "style": {}}


def wrap_heading(text, level=2):
    decorations = []
    if level == 3:
        decorations.append({
            "type": "FONT_SIZE",
            "fontSizeData": {
                "unit": "PX",
                "value": 22
            }
        })
    return {
        "type": "HEADING",
        "id": generate_id(),
        "nodes": [build_text_node(text, bold=True, extra_decorations=decorations)],
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
                "nodes": [
                    {
                        "type": "PARAGRAPH",
                        "id": generate_id(),
                        "nodes": item,
                        "style": {
                            "paddingTop": "0px",
                            "paddingBottom": "0px"
                        },
                        "paragraphData": {
                            "textStyle": {
                                "lineHeight": "2"
                            }
                        }
                    }
                ]
            } for item in items
        ]
    }


def wrap_table(table_data):
    num_rows = len(table_data)
    num_cols = max(len(row) for row in table_data) if table_data else 0
    highlight_style = {
        "verticalAlignment": "TOP",
        "backgroundColor": "#CAB8FF"
    }

    table_node = {
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
                        "nodes": [
                            wrap_paragraph_nodes([
                                build_text_node(
                                    node["textData"]["text"],
                                    extra_decorations=[
                                        {
                                            "type": "FONT_SIZE",
                                            "fontSizeData": {"unit": "PX", "value": 16}
                                        }
                                    ] if r_idx > 0 and c_idx > 0 else None
                                )
                                for node in cell
                                if node["type"] == "TEXT"
                            ])
                        ],
                        "tableCellData": {
                            "cellStyle": highlight_style if r_idx == 0 or c_idx == 0 else {}
                        }
                    }
                    for c_idx, cell in enumerate(row)
                ]
            }
            for r_idx, row in enumerate(table_data)
        ],
        "tableData": {
            "dimensions": {
                "colsWidthRatio": [754] * num_cols,
                "rowsHeight": [47] * num_rows,
                "colsMinWidth": [120] * num_cols
            }
        }
    }

    return table_node


def wrap_image(url, alt=""):
    return {"type": "IMAGE", "id": generate_id(),
            "imageData": {"containerData": {"width": {"size": "CONTENT"}, "alignment": "CENTER", "textWrap": True},
                          "image": {"src": {"url": url}, "metadata": {"altText": alt}}}}


def upload_to_pixeldrain(img_src, root_dir, max_retries=3):
    img_filename = os.path.normpath(img_src)

    for dirpath, _, filenames in os.walk(root_dir):
        if os.path.basename(img_filename) in filenames:
            full_path = os.path.join(dirpath, os.path.basename(img_filename))
            logging.info(f"📁 Found image: {full_path}")
            headers = {
                "Authorization": "Basic " + base64.b64encode(f":{PIXELDRAIN_API_KEY}".encode()).decode()
            }

            for attempt in range(1, max_retries + 1):
                try:
                    with open(full_path, "rb") as f:
                        files = {'file': (os.path.basename(full_path), f)}
                        start = time.time()
                        response = requests.post("https://pixeldrain.com/api/file", headers=headers, files=files)
                        duration = time.time() - start

                    if 200 <= response.status_code < 300:
                        file_id = response.json()["id"]
                        logging.info(f"✅ Uploaded {img_filename} (Attempt {attempt}) in {duration:.2f}s")
                        return f"https://pixeldrain.com/api/file/{file_id}"
                    else:
                        logging.warning(
                            f"⚠️ Upload failed for {img_filename} - Attempt {attempt} - Status {response.status_code}")
                except Exception as e:
                    logging.error(f"❌ Upload error for {img_filename} - Attempt {attempt} - Error: {e}")

            logging.error(f"❌ All upload attempts failed for: {img_filename}")
            return None

    logging.warning(f"❌ Image not found: {img_src}")
    return None


def extract_parts(tag, bold_class, image_dir):
    parts = []
    for item in tag.children:
        if isinstance(item, NavigableString):
            txt = str(item)
            if txt.strip():
                is_bold = item.parent.name == "span" and bold_class and bold_class in item.parent.get("class", [])
                parts.append(build_text_node(txt, bold=is_bold))
        elif isinstance(item, Tag):
            if item.name == "br": continue
            if item.name == "img" and item.get("src"):
                url = upload_to_pixeldrain(item["src"], image_dir)
                if url:
                    parts.append(wrap_image(url, item.get("alt", "")))
            elif item.name == "a" and item.get("href"):
                href = item["href"]
                if "google.com/url?q=" in href:
                    href = urllib.parse.unquote(href.split("q=")[1].split("&")[0])
                else:
                    href = urllib.parse.unquote(href)
                is_bold = any(child.name == "span" and bold_class and bold_class in child.get("class", []) for child in
                              item.descendants if isinstance(child, Tag))
                parts.append(build_text_node(item.get_text(), bold=is_bold, link=href, underline=True))
            else:
                parts.extend(extract_parts(item, bold_class, image_dir))
    return parts


def apply_spacing(nodes, block_type):
    before = {"H2": 2, "H3": 1, "H4": 1, "ORDERED_LIST": 1, "BULLETED_LIST": 1, "PARAGRAPH": 1, "IMAGE": 1}
    after = {"H2": 1, "H3": 1, "H4": 1, "ORDERED_LIST": 1, "BULLETED_LIST": 1, "PARAGRAPH": 1, "IMAGE": 1, "TABLE": 2}
    return before.get(block_type, 0), after.get(block_type, 0)


def count_trailing_empty_paragraphs(nodes):
    cnt = 0
    for n in reversed(nodes):
        if n["type"] == "PARAGRAPH" and not n["nodes"]:
            cnt += 1
        else:
            break
    return cnt


def ensure_spacing(nodes, required):
    current = count_trailing_empty_paragraphs(nodes)
    while current < required:
        nodes.append(empty_paragraph());
        current += 1
    while current > required:
        nodes.pop();
        current -= 1


def html_to_ricos(html_path, image_dir):
    with open(html_path, "r", encoding="utf‑8") as f:
        soup = BeautifulSoup(f, "html.parser")
    body = soup.body or soup
    nodes = [];
    bold_class = None
    style_tag = soup.find("style")
    if style_tag and style_tag.string:
        for ln in style_tag.string.split("}"):
            if "font-weight:700" in ln:
                cls = ln.split("{")[0].strip()
                if cls.startswith("."): bold_class = cls[1:]; break

    def add_node(node, block_type, prev_type=None):
        b, a = apply_spacing(nodes, block_type)
        if block_type == "H2" and prev_type == "IMAGE": b = 1
        ensure_spacing(nodes, b)
        nodes.append(node)
        needed = a - count_trailing_empty_paragraphs(nodes)
        for _ in range(max(0, needed)): nodes.append(empty_paragraph())
        return block_type

    prev = None
    for elem in body.find_all(recursive=False):
        tag = elem.name
        if tag == "img" and elem.get("src"):
            url = upload_to_pixeldrain(elem["src"], UPLOAD_DIR)
            if url: prev = add_node(wrap_image(url, elem.get("alt", "")), "IMAGE", prev)
        elif tag in ["h2", "h3", "h4"]:
            level = int(tag[1])
            for im in elem.find_all("img"):
                u = upload_to_pixeldrain(im["src"], UPLOAD_DIR)
                if u: prev = add_node(wrap_image(u, im.get("alt", "")), "IMAGE", prev)
            txt = elem.get_text(strip=True)
            if txt: prev = add_node(wrap_heading(txt, level), f"H{level}", prev)
        elif tag == "p":
            imgs = elem.find_all("img", recursive=False)
            if imgs:
                for im in imgs:
                    u = upload_to_pixeldrain(im["src"], UPLOAD_DIR)
                    if u: prev = add_node(wrap_image(u, im.get("alt", "")), "IMAGE", prev)
            else:
                parts = extract_parts(elem, bold_class, UPLOAD_DIR)
                if parts: prev = add_node(wrap_paragraph_nodes(parts), "PARAGRAPH", prev)
        elif tag in ["ul", "ol"]:
            items = [extract_parts(li, bold_class, UPLOAD_DIR) for li in elem.find_all("li", recursive=False)]
            items = [i for i in items if i]
            if items:
                tp = "ORDERED_LIST" if tag == "ol" else "BULLETED_LIST"
                prev = add_node(wrap_list(items, ordered=(tag == "ol")), tp, prev)

        elif tag == "table":
            table = [
                [extract_parts(td, bold_class, UPLOAD_DIR) for td in tr.find_all(["td", "th"])]
                for tr in elem.find_all("tr")
            ]
            if table:
                table_node = wrap_table(table)
                prev = add_node(table_node, "TABLE", prev)

    return {"nodes": nodes}


@app.route("/convert-zipped", methods=["POST"])
def convert_zipped():
    # Clear existing uploads
    if os.path.exists(UPLOAD_DIR):
        import shutil

        for fn in os.listdir(UPLOAD_DIR):
            path = os.path.join(UPLOAD_DIR, fn)
            if os.path.isfile(path):
                os.remove(path)
            elif os.path.isdir(path):
                shutil.rmtree(path)

    else:
        os.makedirs(UPLOAD_DIR)

    z = request.files.get("zip")
    if not z or not z.filename.lower().endswith(".zip"):
        return jsonify({"error": "Missing .zip file"}), 400

    zip_path = os.path.join(UPLOAD_DIR, "upload.zip")
    z.save(zip_path)
    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(UPLOAD_DIR)

    html_path = None
    for root, _, files in os.walk(UPLOAD_DIR):
        for file in files:
            if file.lower().endswith(".html"):
                html_path = os.path.join(root, file)
                break
        if html_path:
            break

    if not html_path:
        return jsonify({"error": "No HTML file found in ZIP"}), 400

    result = html_to_ricos(html_path, UPLOAD_DIR)
    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
