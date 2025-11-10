from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Iterable, List, Optional, Tuple
from xml.etree import ElementTree as ET
from zipfile import ZipFile

try:  # pragma: no cover - optional dependency
    from docx import Document as DocxDocument
except Exception:  # pragma: no cover - gracefully handled later
    DocxDocument = None

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
    if extension == "pdf" and extract_pdf_text is not None:
        return extract_pdf_text(str(path))
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
        paragraphs: List[str] = []
        if path and path.exists() and ext in {"doc", "docx"}:
            paragraphs = extract_docx_paragraphs(path)
        if not paragraphs and content:
            paragraphs = [line for line in content.splitlines() if line.strip()]
        return {"kind": "paragraphs", "paragraphs": paragraphs or [content]}

    if ext in {"ppt", "pptx"}:
        slides: List[str] = []
        if path and path.exists():
            slides = extract_pptx_slides(path)
        if not slides and content:
            slides = [block.strip() for block in content.split("\n\n") if block.strip()]
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
