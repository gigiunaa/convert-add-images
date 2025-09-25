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

# === CONFIG ===
logging.basicConfig(level=logging.INFO)
PIXELDRAIN_API_KEY = "bff3af9e-ce55-4abc-8bf0-9fca8337da57"
UPLOAD_DIR = "bff3af9e-ce55-4abc-8bf0-9fca8337da57"

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
    if is_link and link_url:
        dec.append({
            "type": "LINK",
            "linkData": {
                "link": {"url": link_url, "target": "BLANK", "rel": {"noreferrer": True}}
            }
        })
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
        "textData": {"text": text, "decorations": decorations}
    }

def wrap_paragraph_nodes(nodes):
    return {"type": "PARAGRAPH", "id": generate_id(), "nodes": nodes, "style": {}}

def wrap_heading(text, level=2):
    decorations = []
    if level == 3:
        decorations.append({
            "type": "FONT_SIZE",
            "fontSizeData": {"unit": "PX", "value": 22}
        })
    return {
        "type": "HEADING",
        "id": generate_id(),
        "nodes": [build_text_node(text, bold=True, extra_decorations=decorations)],
        "style": {},
        "headingData": {"level": level, "textStyle": {"textAlignment": "AUTO"}}
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
                        "style": {"paddingTop": "0px", "paddingBottom": "0px"},
                        "paragraphData": {"textStyle": {"lineHeight": "2"}}
                    }
                ]
            }
            for item in items
        ]
    }

def wrap_table(table_data):
    num_rows = len(table_data)
    num_cols = max(len(row) for row in table_data) if table_data else 0
    highlight_style = {"verticalAlignment": "TOP", "backgroundColor": "#CAB8FF"}
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
                                        {"type": "FONT_SIZE", "fontSizeData": {"unit": "PX", "value": 16}}
                                    ] if r_idx > 0 and c_idx > 0 else None
                                )
                                for node in cell if node["type"] == "TEXT"
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
    return {
        "type": "IMAGE",
        "id": generate_id(),
        "imageData": {
            "containerData": {"width": {"size": "CONTENT"}, "alignment": "CENTER", "textWrap": True},
            "image": {"src": {"url": url}, "metadata": {"altText": alt}}
        }
    }

# ========= HTTP endpoint =========

@app.route("/convert-html", methods=["POST"])
def convert_html():
    content_type = request.headers.get("Content-Type", "")
    try:
        if "application/json" in content_type:
            payload = request.get_json(silent=True) or {}
            html_string = payload.get("html")
        else:
            html_string = request.form.get("html")

        if not html_string or not str(html_string).strip():
            return jsonify({"error": "Missing 'html' field with HTML content"}), 400

        # TODO: აქ შეგიძლია დაამატო html_string → ricos კონვერტაცია

        return jsonify({"nodes": [{"type": "PARAGRAPH", "id": generate_id()}]})

    except Exception as e:
        logging.exception("Error converting HTML")
        return jsonify({"error": "Failed to convert HTML", "details": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
