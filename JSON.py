import os
import json
import uuid
from urllib.parse import urlparse, urljoin
from flask import Flask, request, jsonify
from bs4 import BeautifulSoup, Tag, NavigableString
import logging

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

# ========= Helpers =========

def generate_id():
    return str(uuid.uuid4())[:8]

def empty_paragraph():
    return {"type": "PARAGRAPH", "id": generate_id(), "nodes": [], "style": {}}

def format_decorations(is_bold=False, is_link=False, link_url=None, is_underline=False):
    dec = []
    if is_bold or is_link:
        dec.append({"type": "BOLD", "fontWeightValue": 700})
    dec.append({
        "type": "COLOR",
        "colorData": {"foreground": "#3A11AE" if is_link else "rgb(0, 0, 0)", "background": "transparent"}
    })
    if is_link and link_url:
        dec.append({
            "type": "LINK",
            "linkData": {"link": {"url": link_url, "target": "BLANK", "rel": {"noreferrer": True}}}
        })
    if is_underline:
        dec.append({"type": "UNDERLINE"})
    return dec

def build_text_node(text, bold=False, link=None, underline=False, extra_decorations=None):
    decorations = format_decorations(bold, bool(link), link, underline)
    if extra_decorations:
        decorations.extend(extra_decorations)
    return {"type": "TEXT", "id": "", "textData": {"text": text, "decorations": decorations}}

def wrap_paragraph_nodes(nodes):
    return {"type": "PARAGRAPH", "id": generate_id(), "nodes": nodes, "style": {}}

def wrap_heading(text, level=2):
    return {
        "type": "HEADING",
        "id": generate_id(),
        "nodes": [build_text_node(text, bold=True)],
        "style": {},
        "headingData": {"level": level, "textStyle": {"textAlignment": "AUTO"}}
    }

def wrap_list(items, ordered=False):
    return {
        "type": "ORDERED_LIST" if ordered else "BULLETED_LIST",
        "id": generate_id(),
        "nodes": [{
            "type": "LIST_ITEM",
            "id": generate_id(),
            "nodes": [{
                "type": "PARAGRAPH",
                "id": generate_id(),
                "nodes": item,
                "style": {"paddingTop": "0px", "paddingBottom": "0px"},
                "paragraphData": {"textStyle": {"lineHeight": "2"}}
            }]
        } for item in items]
    }

def wrap_image(url, alt=""):
    return {
        "type": "IMAGE",
        "id": generate_id(),
        "imageData": {
            "containerData": {"width": {"size": "CONTENT"}, "alignment": "CENTER", "textWrap": True},
            "image": {"src": {"url": url}, "metadata": {"altText": alt}}
        }
    }

# ========= URL resolution =========

def is_absolute_url(u: str) -> bool:
    try:
        p = urlparse(u)
        return bool(p.scheme) and bool(p.netloc)
    except Exception:
        return False

def resolve_image_src(src: str, base_url: str | None, image_url_map: dict | None, images_fifo: list | None):
    if not src:
        return None
    if image_url_map:
        if src in image_url_map:
            return image_url_map[src]
        base = os.path.basename(src)
        if base in image_url_map:
            return image_url_map[base]
    if images_fifo is not None and len(images_fifo) > 0:
        return images_fifo.pop(0)
    if is_absolute_url(src):
        return src
    if base_url:
        return urljoin(base_url, src)
    return src

# ========= HTML → Ricos =========

def extract_parts(tag, base_url, image_url_map, images_fifo):
    parts = []
    for item in tag.children:
        if isinstance(item, NavigableString):
            txt = str(item).strip()
            if txt:
                parts.append(build_text_node(txt))
        elif isinstance(item, Tag):
            if item.name == "img" and item.get("src"):
                resolved = resolve_image_src(item["src"], base_url, image_url_map, images_fifo)
                if resolved:
                    parts.append(wrap_image(resolved, item.get("alt", "")))
            elif item.name == "a" and item.get("href"):
                href = item["href"]
                parts.append(build_text_node(item.get_text(), link=href, underline=True))
            else:
                parts.extend(extract_parts(item, base_url, image_url_map, images_fifo))
    return parts

def html_string_to_ricos(html_string: str, base_url=None, image_url_map=None, images_fifo=None):
    soup = BeautifulSoup(html_string, "html.parser")
    body = soup.body or soup
    nodes = []
    for elem in body.find_all(recursive=False):
        tag = elem.name
        if tag in ["h1", "h2", "h3", "h4"]:
            txt = elem.get_text(strip=True)
            if txt:
                nodes.append(wrap_heading(txt, int(tag[1])))
        elif tag == "p":
            imgs = elem.find_all("img", recursive=False)
            if imgs:
                for im in imgs:
                    resolved = resolve_image_src(im["src"], base_url, image_url_map, images_fifo)
                    if resolved:
                        nodes.append(wrap_image(resolved, im.get("alt", "")))
            else:
                parts = extract_parts(elem, base_url, image_url_map, images_fifo)
                if parts:
                    nodes.append(wrap_paragraph_nodes(parts))
        elif tag in ["ul", "ol"]:
            items = [extract_parts(li, base_url, image_url_map, images_fifo)
                     for li in elem.find_all("li", recursive=False)]
            if items:
                nodes.append(wrap_list(items, ordered=(tag == "ol")))
        elif tag == "img" and elem.get("src"):
            resolved = resolve_image_src(elem["src"], base_url, image_url_map, images_fifo)
            if resolved:
                nodes.append(wrap_image(resolved, elem.get("alt", "")))
    return {"nodes": nodes}

# ========= Flask endpoint =========

@app.route("/convert-files", methods=["POST"])
def convert_files():
    try:
        payload = request.get_json(silent=True) or {}
        files = payload.get("files", [])

        if not files:
            return jsonify({"error": "Missing 'files' array"}), 400

        results = []
        for f in files:
            filename = f.get("filename")
            html_string = f.get("html")
            if not html_string:
                continue

            ricos = html_string_to_ricos(html_string)
            results.append({
                "filename": filename,
                "ricos": ricos
            })

        return jsonify({"results": results})
    except Exception as e:
        logging.exception("Error in /convert-files")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
