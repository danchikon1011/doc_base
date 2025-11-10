from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Iterable, Optional

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
    if extension in {"docx"} and DocxDocument is not None:
        document = DocxDocument(str(path))
        return "\n".join(paragraph.text for paragraph in document.paragraphs)
    if extension == "doc":
        extracted = _extract_with_textract(path)
        if extracted is not None:
            return extracted
    if extension in {"ppt", "pptx"} and Presentation is not None:
        presentation = Presentation(str(path))
        texts = []
        for slide in presentation.slides:
            for shape in slide.shapes:
                if hasattr(shape, "text"):
                    texts.append(shape.text)
        return "\n".join(texts)
    if extension in {"xls", "xlsx"} and load_workbook is not None:
        workbook = load_workbook(filename=str(path), data_only=True)
        texts = []
        for sheet in workbook.worksheets:
            for row in sheet.iter_rows(values_only=True):
                row_text = [str(cell) for cell in row if cell is not None]
                if row_text:
                    texts.append("\t".join(row_text))
        return "\n".join(texts)
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
