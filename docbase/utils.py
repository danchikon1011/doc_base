from __future__ import annotations

import html
import mimetypes
import re
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple
from xml.etree import ElementTree as ET
from zipfile import ZipFile

try:  # pragma: no cover - optional dependency
    from docx import Document as DocxDocument
except Exception:  # pragma: no cover - gracefully handled later
    DocxDocument = None
    DocxParagraph = None
    WD_ALIGN_PARAGRAPH = None
else:  # pragma: no cover - optional dependency
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.text.paragraph import Paragraph as DocxParagraph

try:  # pragma: no cover - optional dependency
    from pptx import Presentation
except Exception:  # pragma: no cover
    Presentation = None

try:  # pragma: no cover - optional dependency
    from openpyxl import Workbook, load_workbook
except Exception:  # pragma: no cover
    Workbook = None
    load_workbook = None

try:  # pragma: no cover - optional dependency
    import textract
except Exception:  # pragma: no cover
    textract = None

try:  # pragma: no cover - optional dependency
    from pdfminer.high_level import extract_text as extract_pdf_text
except Exception:  # pragma: no cover
    extract_pdf_text = None

ALLOWED_EXTENSIONS = {
    "txt",
    "md",
    "markdown",
    "doc",
    "docx",
    "pdf",
    "ppt",
    "pptx",
    "xls",
    "xlsx",
    "csv",
    "rtf",
}

EDITABLE_EXTENSIONS = ALLOWED_EXTENSIONS - {"pdf"}


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _extract_with_textract(path: Path) -> Optional[str]:
    if textract is None:
        return None
    try:
        return textract.process(str(path)).decode("utf-8", errors="ignore")
    except Exception:
        return None


def extract_text_from_file(path: Path, extension: str) -> str:
    extension = extension.lower()
    if extension in {"txt", "md", "markdown", "csv"}:
        return read_text_file(path)
    if extension in {"docx"}:
        paragraphs = extract_docx_paragraphs(path)
        if paragraphs:
            return "\n".join(paragraphs)
    if extension == "doc":
        extracted = _extract_with_textract(path)
        if extracted is not None:
            return extracted
    if extension in {"ppt", "pptx"}:
        slides = extract_pptx_slides(path)
        if slides:
            return "\n\n".join(slides)
    if extension in {"xls", "xlsx"}:
        sheets = extract_spreadsheet_sheets(path)
        if sheets:
            flattened: List[str] = []
            for name, rows in sheets:
                flattened.append(f"[{name}]")
                for row in rows:
                    flattened.append("\t".join(cell for cell in row))
            return "\n".join(flattened)
    if extension == "rtf":
        extracted = _extract_with_textract(path)
        if extracted is not None:
            return extracted
        return read_text_file(path)
    if extension == "pdf":
        if extract_pdf_text is not None:
            try:
                text = extract_pdf_text(str(path))
                if text and text.strip():
                    return text
            except Exception:
                pass
        extracted = _extract_with_textract(path)
        if extracted is not None:
            return extracted
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return ""
    extracted = _extract_with_textract(path)
    if extracted is not None:
        return extracted
    return read_text_file(path)


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_content_to_file(content: str, extension: str, destination: Path) -> Optional[Path]:
    extension = extension.lower()
    if extension in {"txt", "md", "markdown", "csv"}:
        destination.write_text(content, encoding="utf-8")
        return destination
    if extension in {"doc", "docx"} and DocxDocument is not None:
        doc = DocxDocument()
        for paragraph in content.splitlines() or [""]:
            doc.add_paragraph(paragraph)
        doc.save(destination)
        return destination
    if extension in {"ppt", "pptx"} and Presentation is not None:
        presentation = Presentation()
        layout = presentation.slide_layouts[1]
        slide = presentation.slides.add_slide(layout)
        if slide.shapes.title:
            slide.shapes.title.text = "Документ"
        placeholder = None
        if len(slide.shapes.placeholders) > 1:
            placeholder = slide.shapes.placeholders[1]
        if placeholder and hasattr(placeholder, "text"):
            placeholder.text = content
        else:
            textbox = slide.shapes.add_textbox(left=0, top=0, width=presentation.slide_width, height=presentation.slide_height)
            textbox.text_frame.text = content
        presentation.save(destination)
        return destination
    if extension in {"xls", "xlsx"} and Workbook is not None:
        workbook = Workbook()
        sheet = workbook.active
        for idx, line in enumerate(content.splitlines(), start=1):
            sheet.cell(row=idx, column=1, value=line)
        workbook.save(destination)
        return destination
    if extension == "rtf":
        destination.write_text(content, encoding="utf-8")
        return destination
    destination.write_text(content, encoding="utf-8")
    return destination


def chunk_text(text: str, max_length: int = 600) -> Iterable[str]:
    words = text.split()
    chunk = []
    count = 0
    for word in words:
        chunk.append(word)
        count += len(word) + 1
        if count >= max_length:
            yield " ".join(chunk)
            chunk = []
            count = 0
    if chunk:
        yield " ".join(chunk)


def detect_mime_type(filename: str) -> str:
    mime_type, _ = mimetypes.guess_type(filename)
    return mime_type or "application/octet-stream"


DOCX_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
PPTX_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
SPREADSHEET_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def _zip_xml(path: Path, member: str) -> Optional[ET.Element]:
    try:
        with ZipFile(path) as archive:
            with archive.open(member) as payload:
                return ET.fromstring(payload.read())
    except KeyError:
        return None
    except Exception:
        return None


def extract_docx_paragraphs(path: Path) -> List[str]:
    paragraphs: List[str] = []
    if DocxDocument is not None:
        try:
            document = DocxDocument(str(path))
            paragraphs = [
                paragraph.text.strip()
                for paragraph in document.paragraphs
                if paragraph.text and paragraph.text.strip()
            ]
        except Exception:
            paragraphs = []
    if paragraphs:
        return paragraphs
    root = _zip_xml(path, "word/document.xml")
    if root is None:
        return []
    extracted: List[str] = []
    for paragraph in root.iter(f"{DOCX_NS}p"):
        texts = [node.text or "" for node in paragraph.iter(f"{DOCX_NS}t")]
        combined = "".join(texts).strip()
        if combined:
            extracted.append(combined)
    return extracted


def extract_pptx_slides(path: Path) -> List[str]:
    slides: List[str] = []
    if Presentation is not None:
        try:
            presentation = Presentation(str(path))
            for slide in presentation.slides:
                texts: List[str] = []
                for shape in slide.shapes:
                    text = getattr(shape, "text", "")
                    if text:
                        snippet = str(text).strip()
                        if snippet:
                            texts.append(snippet)
                combined = "\n".join(texts).strip()
                if combined:
                    slides.append(combined)
        except Exception:
            slides = []
    if slides:
        return slides
    try:
        with ZipFile(path) as archive:
            members = [
                name
                for name in archive.namelist()
                if name.startswith("ppt/slides/slide") and name.endswith(".xml")
            ]
            members.sort(
                key=lambda name: int(name.split("slide")[1].split(".xml")[0])
            )
            extracted: List[str] = []
            for member in members:
                with archive.open(member) as payload:
                    root = ET.fromstring(payload.read())
                texts = [node.text or "" for node in root.iter(f"{PPTX_NS}t")]
                combined = "\n".join(part.strip() for part in texts if (part or "").strip())
                if combined:
                    extracted.append(combined)
            return extracted
    except Exception:
        return []
    return []


def extract_spreadsheet_sheets(path: Path) -> List[Tuple[str, List[List[str]]]]:
    if load_workbook is not None:
        try:
            workbook = load_workbook(filename=str(path), data_only=True)
            sheets: List[Tuple[str, List[List[str]]]] = []
            for sheet in workbook.worksheets:
                rows: List[List[str]] = []
                for row in sheet.iter_rows(values_only=True):
                    cells = ["" if cell is None else str(cell) for cell in row]
                    rows.append(cells)
                sheets.append((sheet.title, rows))
            return sheets
        except Exception:
            pass
    try:
        with ZipFile(path) as archive:
            shared_strings: List[str] = []
            if "xl/sharedStrings.xml" in archive.namelist():
                with archive.open("xl/sharedStrings.xml") as payload:
                    root = ET.fromstring(payload.read())
                for entry in root.iter(f"{SPREADSHEET_NS}si"):
                    parts = [node.text or "" for node in entry.iter(f"{SPREADSHEET_NS}t")]
                    shared_strings.append("".join(parts))

            workbook_root = _zip_xml(path, "xl/workbook.xml")
            if workbook_root is None:
                return []

            relationships: dict[str, str] = {}
            rel_root = _zip_xml(path, "xl/_rels/workbook.xml.rels")
            if rel_root is not None:
                for rel in rel_root.iter(f"{REL_NS}Relationship"):
                    target = rel.attrib.get("Target")
                    if target:
                        relationships[rel.attrib.get("Id")] = target

            sheets: List[Tuple[str, List[List[str]]]] = []
            for sheet in workbook_root.iter(f"{SPREADSHEET_NS}sheet"):
                name = sheet.attrib.get("name", "Лист")
                rel_id = sheet.attrib.get(
                    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
                )
                if not rel_id:
                    continue
                target = relationships.get(rel_id)
                if not target:
                    continue
                member = target if target.startswith("xl/") else f"xl/{target}"
                if member not in archive.namelist():
                    continue
                with archive.open(member) as payload:
                    root = ET.fromstring(payload.read())
                rows: List[List[str]] = []
                for row in root.iter(f"{SPREADSHEET_NS}row"):
                    cells: List[str] = []
                    for cell in row.iter(f"{SPREADSHEET_NS}c"):
                        value = ""
                        cell_type = cell.attrib.get("t")
                        v = cell.find(f"{SPREADSHEET_NS}v")
                        if v is not None and v.text is not None:
                            if cell_type == "s":
                                try:
                                    idx = int(v.text)
                                    value = shared_strings[idx]
                                except (ValueError, IndexError):
                                    value = v.text
                            else:
                                value = v.text
                        elif cell_type == "inlineStr":
                            t = cell.find(f"{SPREADSHEET_NS}t")
                            if t is not None and t.text:
                                value = t.text
                        cells.append(value)
                    rows.append(cells)
                sheets.append((name, rows))
            return sheets
    except Exception:
        return []
    return []


def prepare_preview(extension: Optional[str], file_path: Optional[str], content: str) -> dict:
    ext = (extension or "").lower()
    path = Path(file_path) if file_path else None

    if ext == "pdf" and path and path.exists():
        return {"kind": "pdf"}

    if ext in {"doc", "docx", "rtf", "txt", "md", "markdown"}:
        if path and path.exists() and ext == "docx":
            html_preview = render_docx_html(path)
            if html_preview:
                return {"kind": "docx", "html": html_preview}
        paragraphs: List[str] = []
        if path and path.exists() and ext in {"doc", "docx"}:
            paragraphs = extract_docx_paragraphs(path)
        if not paragraphs and content:
            paragraphs = [line for line in content.splitlines() if line.strip()]
        return {"kind": "paragraphs", "paragraphs": paragraphs or [content]}

    if ext in {"ppt", "pptx"}:
        slides = []
        if path and path.exists():
            slides = build_pptx_preview(path)
        if not slides:
            slide_texts: List[str] = []
            if path and path.exists():
                slide_texts = extract_pptx_slides(path)
            if not slide_texts and content:
                slide_texts = [block.strip() for block in content.split("\n\n") if block.strip()]
            if slide_texts:
                slides = build_pptx_preview_from_text(slide_texts)
        return {"kind": "slides", "slides": slides}

    if ext in {"xls", "xlsx", "csv"}:
        sheets: List[Tuple[str, List[List[str]]]] = []
        if path and path.exists() and ext in {"xls", "xlsx"}:
            sheets = extract_spreadsheet_sheets(path)
        if not sheets and content:
            rows = [line.split("\t") for line in content.splitlines() if line]
            if rows:
                sheets = [("Лист 1", rows)]
        return {
            "kind": "sheets",
            "sheets": [{"name": name, "rows": rows} for name, rows in sheets],
        }

    text = content or ""
    return {"kind": "text", "text": text}


def _docx_run_to_html(run) -> str:
    text = html.escape(getattr(run, "text", "") or "")
    if not text:
        return ""
    text = text.replace("\n", "<br />")
    bold = getattr(run, "bold", None)
    italic = getattr(run, "italic", None)
    underline = getattr(run, "underline", None)
    font = getattr(run, "font", None)
    if font is not None:
        if bold is None:
            bold = getattr(font, "bold", None)
        if italic is None:
            italic = getattr(font, "italic", None)
        if underline is None:
            underline = getattr(font, "underline", None)
    if bold:
        text = f"<strong>{text}</strong>"
    if italic:
        text = f"<em>{text}</em>"
    if underline:
        text = f"<span class=\"docx-underline\">{text}</span>"
    return text


def _docx_list_level(paragraph) -> Optional[int]:
    if paragraph is None or getattr(paragraph, "_p", None) is None:
        return None
    p = paragraph._p
    pPr = getattr(p, "pPr", None)
    if pPr is None:
        return None
    numPr = getattr(pPr, "numPr", None)
    if numPr is None:
        return None
    ilvl = getattr(numPr, "ilvl", None)
    if ilvl is not None and getattr(ilvl, "val", None) is not None:
        try:
            return int(ilvl.val)
        except (TypeError, ValueError):
            return 0
    return 0


def _docx_close_lists(html_parts: List[str], stack: List[int], target: int = 0) -> None:
    while len(stack) > target:
        html_parts.append("</ul>")
        stack.pop()


def _docx_alignment_class(paragraph) -> str:
    if WD_ALIGN_PARAGRAPH is None:
        return ""
    alignment = getattr(paragraph, "alignment", None)
    if alignment is None:
        return ""
    if alignment == WD_ALIGN_PARAGRAPH.CENTER:
        return " docx-align-center"
    if alignment == WD_ALIGN_PARAGRAPH.RIGHT:
        return " docx-align-right"
    if alignment == WD_ALIGN_PARAGRAPH.JUSTIFY:
        return " docx-align-justify"
    return ""


def _docx_heading_level(style_name: str) -> int:
    match = re.search(r"(\d+)", style_name)
    if match:
        try:
            value = int(match.group(1))
            return max(1, min(6, value))
        except ValueError:
            return 2
    return 2


def _docx_render_table(table) -> str:
    rows_html: List[str] = []
    for row in getattr(table, "rows", []):
        cells_html: List[str] = []
        for cell in getattr(row, "cells", []):
            cell_paragraphs: List[str] = []
            for paragraph in getattr(cell, "paragraphs", []):
                paragraph_html = "".join(_docx_run_to_html(run) for run in getattr(paragraph, "runs", []))
                if not paragraph_html:
                    paragraph_html = html.escape(getattr(paragraph, "text", "") or "")
                paragraph_html = paragraph_html.replace("\n", "<br />")
                if paragraph_html:
                    cell_paragraphs.append(paragraph_html)
            cells_html.append("<td>{}</td>".format("<br />".join(cell_paragraphs) or "&nbsp;"))
        if cells_html:
            rows_html.append(f"<tr>{''.join(cells_html)}</tr>")
    if not rows_html:
        return ""
    return f"<table class=\"docx-table\"><tbody>{''.join(rows_html)}</tbody></table>"


def render_docx_html(path: Path) -> str:
    if DocxDocument is None or DocxParagraph is None:
        return ""
    try:
        document = DocxDocument(str(path))
    except Exception:
        return ""

    html_parts: List[str] = []
    list_stack: List[int] = []

    paragraphs: Sequence = getattr(document, "paragraphs", [])
    tables: Sequence = getattr(document, "tables", [])
    tables_iter = iter(tables)
    table_map = {getattr(table, "_tbl", None): table for table in tables}

    body = getattr(document, "element", None)
    body = getattr(body, "body", None)
    if body is None:
        return ""

    for child in body.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "tbl":
            table = table_map.get(child)
            if table is None:
                try:
                    table = next(tables_iter)
                except StopIteration:
                    table = None
            if table is not None:
                _docx_close_lists(html_parts, list_stack, 0)
                table_html = _docx_render_table(table)
                if table_html:
                    html_parts.append(table_html)
            continue
        if tag != "p":
            continue
        paragraph = DocxParagraph(child, document)
        paragraph_html = "".join(_docx_run_to_html(run) for run in paragraph.runs)
        if not paragraph_html:
            paragraph_html = html.escape(paragraph.text or "")
        paragraph_html = paragraph_html.replace("\n", "<br />").strip()
        if not paragraph_html:
            continue
        style = getattr(paragraph, "style", None)
        style_name = (getattr(style, "name", "") or "").lower()
        if style_name.startswith("heading"):
            _docx_close_lists(html_parts, list_stack, 0)
            level = _docx_heading_level(style_name)
            html_parts.append(f"<h{level}>{paragraph_html}</h{level}>")
            continue
        list_level = _docx_list_level(paragraph)
        if list_level is not None:
            while len(list_stack) <= list_level:
                html_parts.append("<ul class=\"docx-list\">")
                list_stack.append(len(list_stack))
            _docx_close_lists(html_parts, list_stack, list_level + 1)
            html_parts.append(f"<li>{paragraph_html or '&nbsp;'}</li>")
            continue
        _docx_close_lists(html_parts, list_stack, 0)
        alignment_class = _docx_alignment_class(paragraph)
        html_parts.append(f"<p class=\"docx-paragraph{alignment_class}\">{paragraph_html}</p>")

    _docx_close_lists(html_parts, list_stack, 0)
    return "".join(html_parts)


def _split_slide_lines(lines: Sequence[str]) -> Tuple[Optional[str], List[str]]:
    cleaned = [line.strip() for line in lines if line.strip()]
    if not cleaned:
        return None, []
    if len(cleaned) == 1:
        return cleaned[0], []
    return cleaned[0], cleaned[1:]


def build_pptx_preview_from_text(slides: Sequence[str]) -> List[dict]:
    rendered: List[dict] = []
    for slide in slides:
        lines = slide.splitlines()
        title, bullet_lines = _split_slide_lines(lines)
        if not bullet_lines and not title:
            continue
        body: List[str] = []
        if bullet_lines:
            body.append("<ul class=\"pptx-list\">")
            body.extend(f"<li>{html.escape(line)}</li>" for line in bullet_lines)
            body.append("</ul>")
        rendered.append({
            "title": title,
            "html": "".join(body) if body else None,
        })
    return rendered


def build_pptx_preview(path: Path) -> List[dict]:
    if Presentation is None:
        return []
    try:
        presentation = Presentation(str(path))
    except Exception:
        return []
    slides_payload: List[dict] = []
    for slide in presentation.slides:
        title_shape = getattr(slide.shapes, "title", None)
        title = ""
        if title_shape is not None:
            title = (getattr(title_shape, "text", "") or "").strip()
        body_parts: List[str] = []
        list_stack: List[int] = []

        def close_lists(level: int = 0) -> None:
            while len(list_stack) > level:
                body_parts.append("</ul>")
                list_stack.pop()

        for shape in slide.shapes:
            if shape == title_shape:
                continue
            text_frame = getattr(shape, "text_frame", None)
            if text_frame is None:
                continue
            for paragraph in text_frame.paragraphs:
                runs = getattr(paragraph, "runs", [])
                paragraph_html = "".join(_docx_run_to_html(run) for run in runs)
                if not paragraph_html:
                    paragraph_html = html.escape(getattr(paragraph, "text", "") or "")
                paragraph_html = paragraph_html.replace("\n", "<br />").strip()
                if not paragraph_html:
                    continue
                level = getattr(paragraph, "level", 0) or 0
                bullet = getattr(paragraph, "_p", None)
                bullet_enabled = False
                if bullet is not None:
                    pPr = getattr(bullet, "pPr", None)
                    if pPr is not None:
                        bullet_enabled = any(
                            child.tag.split("}")[-1].startswith("bu") and child.tag.split("}")[-1] != "buNone"
                            for child in pPr.iterchildren()
                        )
                if bullet_enabled or level > 0:
                    while len(list_stack) <= level:
                        body_parts.append("<ul class=\"pptx-list\">")
                        list_stack.append(len(list_stack))
                    close_lists(level + 1)
                    body_parts.append(f"<li>{paragraph_html}</li>")
                else:
                    close_lists(0)
                    body_parts.append(f"<p>{paragraph_html}</p>")
        close_lists(0)
        content_html = "".join(body_parts)
        slides_payload.append(
            {
                "title": title or None,
                "html": content_html or None,
            }
        )
    return slides_payload
