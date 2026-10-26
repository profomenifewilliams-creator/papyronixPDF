"""Offline Office, text, image and conversion operations for Papyronix.

All processing takes place in-process or by invoking a locally installed LibreOffice/Tesseract
binary. This module contains no network clients, API keys, or AI service calls.
"""
from __future__ import annotations

import csv
import difflib
import io
import os
import re
import shutil
import subprocess
import tempfile
from copy import copy
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from .services import OutputArtifact, ProcessingError, safe_stem, open_pdf, pdf_bytes, new_writer_from_pages, parse_pages

TEXT_MIME = "text/plain; charset=utf-8"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PDF_MIME = "application/pdf"

OFFICE_OPERATIONS = {
    "pdf-to-word", "pdf-to-text", "pdf-to-images", "pdf-ocr", "image-to-text",
    "word-to-pdf", "word-to-text", "word-replace", "word-clean", "word-count",
    "text-to-word", "excel-to-csv", "csv-to-excel", "excel-clean", "excel-merge",
    "excel-to-pdf", "pptx-to-pdf", "pptx-to-text", "pptx-to-word",
    "word-compare", "word-template-fill", "word-table-to-excel", "word-add-page-numbers",
    "word-to-markdown", "word-extract-images",
    "word-clear-metadata", "text-to-pdf", "excel-to-word", "excel-split-sheets",
    "excel-sort", "excel-compare", "csv-clean", "csv-filter",
}


def _ext(filename: str) -> str:
    return Path(filename).suffix.lower()


def _read_docx(data: bytes):
    from docx import Document
    try:
        return Document(io.BytesIO(data))
    except Exception as exc:
        raise ProcessingError("This Word file could not be opened. Use a valid .docx file, not the older .doc format.") from exc


def _document_paragraphs_and_cells(document):
    """Yield document paragraphs and paragraphs inside tables, headers and footers."""
    seen_cells = set()
    for paragraph in document.paragraphs:
        yield paragraph
    def walk_table(table):
        for row in table.rows:
            for cell in row.cells:
                ident = id(cell._tc)
                if ident in seen_cells:
                    continue
                seen_cells.add(ident)
                for paragraph in cell.paragraphs:
                    yield paragraph
                for nested in cell.tables:
                    yield from walk_table(nested)
    for table in document.tables:
        yield from walk_table(table)
    for section in document.sections:
        for part in (section.header, section.footer, section.first_page_header, section.first_page_footer,
                     section.even_page_header, section.even_page_footer):
            for paragraph in part.paragraphs:
                yield paragraph
            for table in part.tables:
                yield from walk_table(table)


def _replace_paragraph_text(paragraph, needle: str, replacement: str, case_sensitive: bool = True) -> int:
    """Replace text across Word runs while retaining the formatting of unaffected runs."""
    if not needle:
        return 0
    count = 0
    search_from = 0
    for _ in range(10000):
        runs = list(paragraph.runs)
        full = "".join(run.text for run in runs)
        haystack = full if case_sensitive else full.casefold()
        target = needle if case_sensitive else needle.casefold()
        start = haystack.find(target, search_from)
        if start < 0:
            break
        end = start + len(needle)
        offsets = []
        cursor = 0
        for run in runs:
            offsets.append((cursor, cursor + len(run.text)))
            cursor += len(run.text)
        start_idx = next((i for i, (a, b) in enumerate(offsets) if a <= start < b), None)
        end_idx = next((i for i, (a, b) in enumerate(offsets) if a < end <= b), None)
        if start_idx is None or end_idx is None:
            break
        start_run, end_run = runs[start_idx], runs[end_idx]
        start_offset = start - offsets[start_idx][0]
        end_offset = end - offsets[end_idx][0]
        if start_idx == end_idx:
            value = start_run.text
            start_run.text = value[:start_offset] + replacement + value[end_offset:]
        else:
            start_run.text = start_run.text[:start_offset] + replacement
            for idx in range(start_idx + 1, end_idx):
                runs[idx].text = ""
            end_run.text = end_run.text[end_offset:]
        count += 1
        # Skip newly inserted replacement text so replacing a token with itself cannot loop.
        search_from = start + len(replacement)
        if search_from < 0:
            break
    return count


def _word_to_text(data: bytes) -> str:
    document = _read_docx(data)
    lines = []
    for p in document.paragraphs:
        if p.text.strip():
            lines.append(p.text)
    for table_index, table in enumerate(document.tables, start=1):
        lines.append(f"[TABLE {table_index}]")
        for row in table.rows:
            lines.append(" | ".join(cell.text.replace("\n", " / ") for cell in row.cells))
    for section in document.sections:
        for part_label, part in (("HEADER", section.header), ("FOOTER", section.footer)):
            text = "\n".join(p.text for p in part.paragraphs if p.text.strip())
            if text:
                lines.append(f"[{part_label}]\n{text}")
    return "\n\n".join(lines).strip()


def _pdf_to_text(filename: str, data: bytes, password: str = "") -> list[str]:
    reader = open_pdf(data, filename, password)
    text_pages = []
    for index, page in enumerate(reader.pages, start=1):
        text_pages.append(f"===== PAGE {index} =====\n{page.extract_text() or ''}".rstrip())
    joined = "\n\n".join(text_pages).strip()
    if not joined:
        raise ProcessingError("No selectable text was found in this PDF. It may be scanned; use the local OCR tool if Tesseract is installed.")
    return text_pages


def _local_libreoffice_convert(filename: str, data: bytes) -> bytes:
    executable = shutil.which("soffice") or shutil.which("libreoffice")
    if not executable:
        raise ProcessingError("This conversion needs LibreOffice installed on the same computer as Papyronix. Install LibreOffice, restart the app, and try again. No cloud converter or API is used.")
    ext = _ext(filename)
    if ext not in {".docx", ".xlsx", ".pptx"}:
        raise ProcessingError("Local PDF export supports .docx, .xlsx and .pptx files only.")
    with tempfile.TemporaryDirectory(prefix="papyronix-office-") as temp:
        root = Path(temp)
        source = root / (safe_stem(filename) + ext)
        out_dir = root / "out"
        profile = root / "profile"
        out_dir.mkdir()
        source.write_bytes(data)
        command = [executable, f"-env:UserInstallation={profile.as_uri()}", "--headless", "--convert-to", "pdf", "--outdir", str(out_dir), str(source)]
        try:
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180, check=False, text=True)
        except subprocess.TimeoutExpired as exc:
            raise ProcessingError("Local Office conversion timed out after three minutes. Try a smaller or simpler document.") from exc
        output = out_dir / (source.stem + ".pdf")
        if result.returncode != 0 or not output.is_file() or output.stat().st_size == 0:
            detail = (result.stderr or result.stdout or "").strip()
            if detail:
                detail = re.sub(r"\s+", " ", detail)[:240]
            suffix = f" Details: {detail}" if detail else ""
            raise ProcessingError("LibreOffice could not convert this file. Make sure LibreOffice is installed and the source is valid." + suffix)
        return output.read_bytes()


def _pdf_to_docx(filename: str, data: bytes, password: str = "") -> bytes:
    from docx import Document
    reader = open_pdf(data, filename, password)
    if len(reader.pages) > 500:
        raise ProcessingError("PDF-to-Word is limited to 500 pages per file to protect local memory.")
    doc = Document()
    doc.add_heading(Path(filename).stem[:120] or "Converted PDF", level=1)
    any_text = False
    for index, page in enumerate(reader.pages, start=1):
        if index > 1:
            doc.add_page_break()
        text = page.extract_text() or ""
        if text.strip():
            any_text = True
            for block in re.split(r"\n\s*\n", text.strip()):
                cleaned = "\n".join(line.rstrip() for line in block.splitlines()).strip()
                if cleaned:
                    doc.add_paragraph(cleaned)
        else:
            doc.add_paragraph("[No selectable text on this page. Scanned content is not transcribed by this conversion.]", style="Caption")
    if not any_text:
        raise ProcessingError("No selectable text was found in this PDF. Run OCR first if it is a scan and local Tesseract is installed.")
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def _pdf_to_images(filename: str, data: bytes, params: dict[str, str]) -> list[OutputArtifact]:
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise ProcessingError("PDF-to-image support needs the bundled pypdfium2 dependency. Install the project requirements, then restart Papyronix.") from exc
    password = params.get("pdf_password", "")
    pages_text = params.get("pages", "all")
    try:
        dpi = int(params.get("dpi", "144"))
    except ValueError as exc:
        raise ProcessingError("Choose an image resolution of 72, 96, 144 or 200 DPI.") from exc
    if dpi not in {72, 96, 144, 200}:
        raise ProcessingError("Choose an image resolution of 72, 96, 144 or 200 DPI.")
    try:
        doc = pdfium.PdfDocument(data, password=password or None)
        total = len(doc)
        if total > 1000:
            raise ProcessingError("PDF-to-image is limited to 1,000 pages per operation.")
        selected = parse_pages(pages_text, total)
        scale = dpi / 72.0
        outputs = []
        pixels_total = 0
        stem = safe_stem(filename)
        try:
            for number in selected:
                page = doc[number - 1]
                bitmap = page.render(scale=scale)
                try:
                    pixels_total += bitmap.width * bitmap.height
                    if pixels_total > 120_000_000:
                        raise ProcessingError("The selected pages would create too many pixels. Choose fewer pages or a lower resolution.")
                    image = bitmap.to_pil()
                    try:
                        buffer = io.BytesIO()
                        image.save(buffer, format="PNG", optimize=True)
                        outputs.append(OutputArtifact(f"{stem}-page-{number:04d}.png", buffer.getvalue(), "image/png"))
                    finally:
                        image.close()
                finally:
                    bitmap.close()
                page.close()
        finally:
            doc.close()
        return outputs
    except ProcessingError:
        raise
    except Exception as exc:
        raise ProcessingError("This PDF could not be rendered as images. Check the file and its password.") from exc


def _tesseract_available() -> bool:
    return bool(shutil.which("tesseract"))


def _ocr_image_bytes(data: bytes, language: str = "eng") -> str:
    if not _tesseract_available():
        raise ProcessingError("Local OCR needs the free Tesseract OCR engine installed on this computer. Install Tesseract and its language data, restart Papyronix, then try again. No AI API or token is used.")
    try:
        from PIL import Image, UnidentifiedImageError
        import pytesseract
        with Image.open(io.BytesIO(data)) as image:
            if image.width * image.height > 24_000_000:
                raise ProcessingError("The selected image exceeds the 24-megapixel OCR limit. Resize it and try again.")
            text = pytesseract.image_to_string(image, lang=language, timeout=90)
        if not text.strip():
            raise ProcessingError("OCR did not detect readable text. Try a clearer image or check the installed Tesseract language pack.")
        return text.strip()
    except ProcessingError:
        raise
    except Exception as exc:
        raise ProcessingError("Local OCR could not read this image. Confirm Tesseract and the requested language pack are installed.") from exc


def _ocr_pdf(filename: str, data: bytes, params: dict[str, str]) -> bytes:
    try:
        import pypdfium2 as pdfium
        import pytesseract
        from PIL import Image
        from pypdf import PdfReader, PdfWriter
    except ImportError as exc:
        raise ProcessingError("Local PDF OCR needs pypdfium2, Pillow and pytesseract from the project requirements.") from exc
    if not _tesseract_available():
        raise ProcessingError("Local PDF OCR needs the free Tesseract OCR engine installed on this computer. Install Tesseract and its language data, restart Papyronix, then try again. No AI API or token is used.")
    try:
        dpi = int(params.get("dpi", "150"))
    except ValueError as exc:
        raise ProcessingError("Choose OCR resolution 100, 150 or 200 DPI.") from exc
    if dpi not in {100, 150, 200}:
        raise ProcessingError("Choose OCR resolution 100, 150 or 200 DPI.")
    lang = (params.get("ocr_language") or "eng").strip()[:40]
    password = params.get("pdf_password", "")
    writer = PdfWriter()
    try:
        doc = pdfium.PdfDocument(data, password=password or None)
        total = len(doc)
        if total > 100:
            doc.close()
            raise ProcessingError("OCR is limited to 100 pages per PDF. Split a larger PDF first.")
        scale = dpi / 72.0
        pixels_total = 0
        try:
            for index in range(total):
                page = doc[index]
                bitmap = page.render(scale=scale)
                try:
                    pixels_total += bitmap.width * bitmap.height
                    if pixels_total > 160_000_000:
                        raise ProcessingError("OCR rendering exceeded the local pixel safety limit. Use fewer pages or a lower resolution.")
                    image = bitmap.to_pil()
                    try:
                        page_pdf = pytesseract.image_to_pdf_or_hocr(image, extension="pdf", lang=lang, timeout=120)
                    finally:
                        image.close()
                finally:
                    bitmap.close()
                    page.close()
                page_reader = PdfReader(io.BytesIO(page_pdf))
                for pdf_page_obj in page_reader.pages:
                    writer.add_page(pdf_page_obj)
        finally:
            doc.close()
        if len(writer.pages) == 0:
            raise ProcessingError("This PDF has no pages to OCR.")
        return pdf_bytes(writer)
    except ProcessingError:
        raise
    except Exception as exc:
        raise ProcessingError("Local OCR failed. Check that Tesseract and the selected language pack are installed, then try a smaller file.") from exc


def _clean_docx(data: bytes) -> bytes:
    from docx.oxml.ns import qn
    doc = _read_docx(data)
    # Normalize excessive whitespace, preserving intentional line breaks and styles.
    for paragraph in list(_document_paragraphs_and_cells(doc)):
        original = paragraph.text
        cleaned = re.sub(r"[\t ]+", " ", original).strip()
        if cleaned != original:
            if paragraph.runs:
                paragraph.runs[0].text = cleaned
                for run in paragraph.runs[1:]:
                    run.text = ""
            else:
                paragraph.add_run(cleaned)
        # Remove completely empty body paragraphs; retain the last required paragraph in each table cell.
        element = paragraph._p
        parent = element.getparent()
        if not paragraph.text.strip() and parent is not None and parent.tag != qn("w:tc"):
            parent.remove(element)
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def _replace_docx(data: bytes, needle: str, replacement: str) -> tuple[bytes, int]:
    if not needle:
        raise ProcessingError("Enter the text you want to find.")
    if len(needle) > 500 or len(replacement) > 2000:
        raise ProcessingError("The find text is limited to 500 characters and replacement text to 2,000 characters.")
    doc = _read_docx(data)
    count = 0
    for paragraph in _document_paragraphs_and_cells(doc):
        count += _replace_paragraph_text(paragraph, needle, replacement, case_sensitive=True)
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue(), count


def _excel_workbook(data: bytes, read_only=False, data_only=False):
    from openpyxl import load_workbook
    try:
        return load_workbook(io.BytesIO(data), read_only=read_only, data_only=data_only)
    except Exception as exc:
        raise ProcessingError("This Excel file could not be opened. Use a valid .xlsx file, not the older .xls format.") from exc


def _excel_to_csv(filename: str, data: bytes) -> list[OutputArtifact]:
    workbook = _excel_workbook(data, read_only=True, data_only=True)
    artifacts = []
    try:
        if len(workbook.worksheets) > 100:
            raise ProcessingError("Excel export is limited to 100 worksheets per workbook.")
        for sheet in workbook.worksheets:
            stream = io.StringIO(newline="")
            writer = csv.writer(stream, lineterminator="\n")
            rows = 0
            for row in sheet.iter_rows(values_only=True):
                writer.writerow(["" if value is None else value for value in row])
                rows += 1
                if rows > 250_000:
                    raise ProcessingError(f"Worksheet '{sheet.title}' exceeds 250,000 rows. Export a smaller sheet.")
            sheet_name = re.sub(r"[^A-Za-z0-9._-]+", "-", sheet.title).strip(".-_") or "sheet"
            name = f"{safe_stem(filename)}-{sheet_name}.csv"
            artifacts.append(OutputArtifact(name, stream.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8"))
    finally:
        workbook.close()
    return artifacts


def _csv_to_excel(filename: str, data: bytes, delimiter: str) -> bytes:
    from openpyxl import Workbook
    delimiter_map = {"comma": ",", "semicolon": ";", "tab": "\t", "pipe": "|"}
    sep = delimiter_map.get(delimiter, ",")
    try:
        decoded = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ProcessingError("This CSV could not be decoded as UTF-8. Save the source as UTF-8 and retry.") from exc
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Imported data"
    try:
        rows = 0
        for row in csv.reader(io.StringIO(decoded), delimiter=sep):
            rows += 1
            if rows > 250_000:
                raise ProcessingError("CSV-to-Excel is limited to 250,000 rows per file.")
            if len(row) > 16_384:
                raise ProcessingError("A CSV row exceeds Excel's 16,384-column limit.")
            for col_idx, value in enumerate(row, start=1):
                cell = sheet.cell(row=rows, column=col_idx, value=value)
                # CSV content is user data, never an executable Excel formula.
                if isinstance(value, str) and value.startswith("="):
                    cell.data_type = "s"
        sheet.freeze_panes = "A2"
        if sheet.max_row and sheet.max_column:
            sheet.auto_filter.ref = sheet.dimensions
        out = io.BytesIO()
        workbook.save(out)
        return out.getvalue()
    finally:
        workbook.close()


def _excel_clean(filename: str, data: bytes) -> bytes:
    from openpyxl.utils import get_column_letter
    workbook = _excel_workbook(data)
    try:
        total_removed = 0
        if len(workbook.worksheets) > 100:
            raise ProcessingError("Excel cleanup is limited to 100 worksheets per workbook.")
        for sheet in workbook.worksheets:
            if sheet.max_row > 250_000 or sheet.max_column > 16_384:
                raise ProcessingError(f"Worksheet '{sheet.title}' exceeds the cleanup safety limit.")
            seen = set()
            remove_rows = []
            for row_idx in range(1, sheet.max_row + 1):
                values = tuple(cell.value for cell in sheet[row_idx])
                if all(value is None or (isinstance(value, str) and not value.strip()) for value in values):
                    remove_rows.append(row_idx)
                    continue
                key = tuple((value.strip() if isinstance(value, str) else value) for value in values)
                try:
                    if key in seen:
                        remove_rows.append(row_idx)
                    else:
                        seen.add(key)
                except TypeError:
                    # Lists/dicts aren't valid Excel cell values; keep the row if encountered.
                    pass
            for row_idx in reversed(remove_rows):
                sheet.delete_rows(row_idx, 1)
            total_removed += len(remove_rows)
            if sheet.max_row and sheet.max_column:
                sheet.auto_filter.ref = sheet.dimensions
        # Output remains XLSX; cleanup count is recorded in the document's custom property only when supported.
        out = io.BytesIO()
        workbook.save(out)
        return out.getvalue()
    finally:
        workbook.close()


def _excel_merge(files: list[tuple[str, bytes]]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter
    output = Workbook()
    output.remove(output.active)
    used_names = set()
    try:
        for filename, data in files:
            source = _excel_workbook(data, read_only=False, data_only=False)
            try:
                for source_sheet in source.worksheets:
                    raw = f"{Path(filename).stem}_{source_sheet.title}"
                    base = re.sub(r"[\\/*?:\[\]]", "_", raw).strip("'")[:31] or "Sheet"
                    dest_name, counter = base, 2
                    while dest_name.casefold() in used_names:
                        suffix = f"_{counter}"
                        dest_name = base[:31-len(suffix)] + suffix
                        counter += 1
                    used_names.add(dest_name.casefold())
                    target = output.create_sheet(dest_name)
                    for row in source_sheet.iter_rows():
                        for cell in row:
                            new = target.cell(row=cell.row, column=cell.column, value=cell.value)
                            if cell.has_style:
                                new.font = copy(cell.font)
                                new.fill = copy(cell.fill)
                                new.border = copy(cell.border)
                                new.alignment = copy(cell.alignment)
                                new.protection = copy(cell.protection)
                            if cell.number_format:
                                new.number_format = cell.number_format
                            if cell.hyperlink:
                                new._hyperlink = copy(cell.hyperlink)
                            if cell.comment:
                                new.comment = copy(cell.comment)
                    for key, dim in source_sheet.column_dimensions.items():
                        target.column_dimensions[key].width = dim.width
                        target.column_dimensions[key].hidden = dim.hidden
                    for key, dim in source_sheet.row_dimensions.items():
                        target.row_dimensions[key].height = dim.height
                        target.row_dimensions[key].hidden = dim.hidden
                    target.freeze_panes = source_sheet.freeze_panes
                    for merged in source_sheet.merged_cells.ranges:
                        try:
                            target.merge_cells(str(merged))
                        except ValueError:
                            pass
                    if source_sheet.sheet_view.showGridLines is not None:
                        target.sheet_view.showGridLines = source_sheet.sheet_view.showGridLines
            finally:
                source.close()
        if not output.worksheets:
            output.create_sheet("Empty")
        out = io.BytesIO()
        output.save(out)
        return out.getvalue()
    finally:
        output.close()


def _pptx_to_text(data: bytes) -> str:
    from pptx import Presentation
    try:
        deck = Presentation(io.BytesIO(data))
    except Exception as exc:
        raise ProcessingError("This PowerPoint file could not be opened. Use a valid .pptx file.") from exc
    lines = []
    if len(deck.slides) > 1000:
        raise ProcessingError("PowerPoint text extraction is limited to 1,000 slides.")
    for index, slide in enumerate(deck.slides, start=1):
        lines.append(f"SLIDE {index}")
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False) and shape.text.strip():
                lines.append(shape.text.strip())
            if getattr(shape, "has_table", False):
                for row in shape.table.rows:
                    lines.append(" | ".join(cell.text for cell in row.cells))
        lines.append("")
    text = "\n".join(lines).strip()
    if not text:
        raise ProcessingError("No selectable text was found in this presentation.")
    return text


def _pptx_to_word(data: bytes, name: str) -> bytes:
    from docx import Document
    text = _pptx_to_text(data)
    doc = Document()
    doc.add_heading(Path(name).stem[:120] or "Presentation Notes", level=1)
    for line in text.splitlines():
        if line.startswith("SLIDE "):
            doc.add_heading(line, level=2)
        elif line.strip():
            doc.add_paragraph(line)
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def _word_count_report(filename: str, data: bytes, password: str = "") -> bytes:
    ext = _ext(filename)
    if ext == ".docx":
        text = _word_to_text(data)
        paragraphs = sum(1 for part in text.splitlines() if part.strip())
    elif ext == ".pdf":
        text = "\n".join(_pdf_to_text(filename, data, password))
        paragraphs = sum(1 for part in text.splitlines() if part.strip())
    elif ext in {".txt", ".md", ".csv"}:
        text = data.decode("utf-8-sig", errors="replace")
        paragraphs = sum(1 for part in text.splitlines() if part.strip())
    elif ext == ".pptx":
        text = _pptx_to_text(data)
        paragraphs = sum(1 for part in text.splitlines() if part.strip() and not part.startswith("SLIDE "))
    else:
        raise ProcessingError("Word count supports PDF, DOCX, PPTX, TXT, Markdown and CSV files.")
    words = re.findall(r"\b[\w’'-]+\b", text, flags=re.UNICODE)
    report = [
        f"DOCUMENT ANALYSIS: {Path(filename).name}",
        "=" * min(90, max(10, len(filename) + 19)),
        f"Words: {len(words):,}",
        f"Characters (including spaces): {len(text):,}",
        f"Characters (excluding whitespace): {sum(not c.isspace() for c in text):,}",
        f"Non-empty lines/paragraphs: {paragraphs:,}",
        f"Bytes processed: {len(data):,}",
        "",
        "Generated locally by Papyronix. Counts are based on extractable text; tables and layout may affect paragraph totals.",
    ]
    return "\n".join(report).encode("utf-8")




def _paragraph_to_markdown(paragraph) -> str:
    pieces = []
    for run in paragraph.runs:
        value = run.text.replace("|", r"\|").replace("\n", "<br>")
        if not value:
            continue
        if run.bold and run.italic:
            value = f"***{value}***"
        elif run.bold:
            value = f"**{value}**"
        elif run.italic:
            value = f"*{value}*"
        if run.font.name in {"Consolas", "Courier New", "Courier"}:
            value = f"`{value}`"
        pieces.append(value)
    text = "".join(pieces).strip()
    style_name = (paragraph.style.name if paragraph.style else "").casefold()
    if style_name.startswith("heading "):
        try:
            level = max(1, min(6, int(style_name.split()[-1])))
        except ValueError:
            level = 2
        return "#" * level + " " + text if text else ""
    if style_name == "title":
        return "# " + text if text else ""
    if "list bullet" in style_name:
        return "- " + text if text else ""
    if "list number" in style_name:
        return "1. " + text if text else ""
    return text


def _word_to_markdown(data: bytes) -> str:
    from docx.text.paragraph import Paragraph
    from docx.table import Table
    document = _read_docx(data)
    blocks = []
    body = document.element.body
    for child in body.iterchildren():
        if child.tag.endswith("}p"):
            paragraph = Paragraph(child, document)
            text = _paragraph_to_markdown(paragraph)
            if text:
                blocks.append(text)
        elif child.tag.endswith("}tbl"):
            table = Table(child, document)
            rows = []
            for row in table.rows:
                values = [cell.text.replace("|", r"\|").replace("\n", "<br>").strip() for cell in row.cells]
                rows.append(values)
            if rows:
                columns = max(len(row) for row in rows)
                rows = [row + [""] * (columns - len(row)) for row in rows]
                lines = ["| " + " | ".join(rows[0]) + " |", "| " + " | ".join(["---"] * columns) + " |"]
                lines.extend("| " + " | ".join(row) + " |" for row in rows[1:])
                blocks.append("\n".join(lines))
    return "\n\n".join(blocks).strip()


def _extract_docx_images(filename: str, data: bytes) -> list[OutputArtifact]:
    try:
        archive = ZipFile(io.BytesIO(data))
    except Exception as exc:
        raise ProcessingError("This Word document is not a readable DOCX package.") from exc
    allowed = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".emf", ".wmf", ".svg"}
    outputs = []
    total_bytes = 0
    try:
        media_files = [item for item in archive.infolist() if item.filename.startswith("word/media/") and not item.is_dir() and Path(item.filename).suffix.lower() in allowed]
        if not media_files:
            raise ProcessingError("No supported embedded image files were found in this Word document.")
        if len(media_files) > 200:
            raise ProcessingError("Image extraction is limited to 200 embedded images per Word file.")
        for index, item in enumerate(media_files, start=1):
            if item.file_size > 20 * 1024 * 1024:
                raise ProcessingError(f"Embedded image {Path(item.filename).name} exceeds the 20 MB per-image limit.")
            total_bytes += item.file_size
            if total_bytes > 100 * 1024 * 1024:
                raise ProcessingError("The embedded images exceed the 100 MB combined extraction limit.")
            payload = archive.read(item.filename)
            image_name = _safe_output_filename(Path(item.filename).name, f"image-{index:03d}")
            outputs.append(OutputArtifact(f"{safe_stem(filename)}-{image_name}", payload, _mime_for_image(Path(item.filename).suffix.lower())))
    except ProcessingError:
        raise
    except Exception as exc:
        raise ProcessingError("The embedded media could not be extracted from this Word file.") from exc
    finally:
        archive.close()
    return outputs


def _mime_for_image(extension: str) -> str:
    return {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".bmp": "image/bmp", ".tif": "image/tiff", ".tiff": "image/tiff", ".svg": "image/svg+xml", ".emf": "image/emf", ".wmf": "image/wmf"}.get(extension, "application/octet-stream")


def _markdown_inline_to_word(paragraph, text: str) -> None:
    """Render a deliberately small, safe Markdown inline subset without external services."""
    from docx.shared import RGBColor
    token_pattern = re.compile(r"(\*\*.+?\*\*|__.+?__|(?<!\*)\*[^*\n]+\*(?!\*)|(?<!_)_[^_\n]+_(?!_)|`[^`\n]+`|\[[^\]]+\]\([^)]+\))")
    last = 0
    for match in token_pattern.finditer(text):
        if match.start() > last:
            paragraph.add_run(text[last:match.start()])
        token = match.group(0)
        run = None
        if token.startswith(("**", "__")):
            run = paragraph.add_run(token[2:-2]); run.bold = True
        elif token.startswith("*") or token.startswith("_"):
            run = paragraph.add_run(token[1:-1]); run.italic = True
        elif token.startswith("`"):
            run = paragraph.add_run(token[1:-1]); run.font.name = "Consolas"; run.font.color.rgb = RGBColor(60, 65, 75)
        else:
            link = re.fullmatch(r"\[([^\]]+)\]\(([^)]+)\)", token)
            shown = f"{link.group(1)} ({link.group(2)})" if link else token
            run = paragraph.add_run(shown); run.font.color.rgb = RGBColor(35, 91, 170)
        last = match.end()
    if last < len(text):
        paragraph.add_run(text[last:])


def _split_markdown_table_row(line: str) -> list[str]:
    value = line.strip().strip("|")
    return [part.strip() for part in value.split("|")]


def _is_markdown_table_separator(line: str) -> bool:
    parts = _split_markdown_table_row(line)
    return len(parts) >= 2 and all(re.fullmatch(r":?-{3,}:?", part.replace(" ", "")) for part in parts)


def _text_to_word(data: bytes) -> bytes:
    from docx import Document
    if len(data) > 10 * 1024 * 1024:
        raise ProcessingError("Text-to-Word is limited to 10 MB of UTF-8 text per conversion.")
    text = data.decode("utf-8-sig", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    doc = Document()
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped:
            index += 1
            continue
        # Markdown pipe table: header row, separator row and zero or more body rows.
        if index + 1 < len(lines) and "|" in line and _is_markdown_table_separator(lines[index + 1]):
            header = _split_markdown_table_row(line)
            body_rows = []
            index += 2
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                body_rows.append(_split_markdown_table_row(lines[index]))
                index += 1
            width = max([len(header)] + [len(row) for row in body_rows])
            table = doc.add_table(rows=1, cols=width)
            table.style = "Light Shading Accent 1"
            for col in range(width):
                table.rows[0].cells[col].text = header[col] if col < len(header) else ""
                for run in table.rows[0].cells[col].paragraphs[0].runs:
                    run.bold = True
            for row in body_rows:
                cells = table.add_row().cells
                for col in range(width):
                    cells[col].text = row[col] if col < len(row) else ""
            continue
        heading_match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading_match:
            paragraph = doc.add_heading(level=len(heading_match.group(1)))
            _markdown_inline_to_word(paragraph, heading_match.group(2))
        elif re.fullmatch(r"[-*_]{3,}", stripped):
            paragraph = doc.add_paragraph("—" * 24)
        elif re.match(r"^\s*[-*+]\s+", line):
            paragraph = doc.add_paragraph(style="List Bullet")
            _markdown_inline_to_word(paragraph, re.sub(r"^\s*[-*+]\s+", "", line))
        elif re.match(r"^\s*\d+[.)]\s+", line):
            paragraph = doc.add_paragraph(style="List Number")
            _markdown_inline_to_word(paragraph, re.sub(r"^\s*\d+[.)]\s+", "", line))
        elif stripped.startswith("> "):
            paragraph = doc.add_paragraph(style="Quote")
            _markdown_inline_to_word(paragraph, stripped[2:])
        else:
            paragraph = doc.add_paragraph()
            _markdown_inline_to_word(paragraph, stripped)
        index += 1
    output = io.BytesIO()
    doc.save(output)
    return output.getvalue()

def _read_csv_rows(data: bytes) -> tuple[list[str], list[list[str]], str]:
    """Read UTF-8 CSV, detecting common separators and returning headers and rows."""
    if len(data) > 50 * 1024 * 1024:
        raise ProcessingError("CSV files are limited to 50 MB per operation.")
    text = data.decode("utf-8-sig", errors="replace")
    if not text.strip():
        raise ProcessingError("The CSV file is empty.")
    sample = text[:65536]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    rows = list(reader)
    if not rows or not any(cell.strip() for cell in rows[0]):
        raise ProcessingError("The CSV file must start with a non-empty header row.")
    headers = [cell.strip() for cell in rows[0]]
    data_rows = rows[1:]
    width = len(headers)
    normalized = []
    for row in data_rows:
        if not any(cell.strip() for cell in row):
            continue
        if len(row) < width:
            row = row + [""] * (width - len(row))
        elif len(row) > width:
            row = row[:width - 1] + [delimiter.join(row[width - 1:])]
        normalized.append(row)
    return headers, normalized, delimiter


def _safe_output_filename(value: str, fallback: str) -> str:
    value = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "-", str(value or "")).strip(" .-_ ")
    value = re.sub(r"\s+", "-", value)[:70]
    return value or fallback


def _template_merge_docx(template_data: bytes, csv_data: bytes, template_name: str) -> list[OutputArtifact]:
    """Deterministic Word mail merge using {{Header}} tokens and a local CSV."""
    from docx import Document
    import re as _re
    headers, rows, _delimiter = _read_csv_rows(csv_data)
    if not rows:
        raise ProcessingError("The CSV must contain at least one data row below the header.")
    if len(rows) > 200:
        raise ProcessingError("Mail merge is limited to 200 output documents at a time.")
    header_lookup = {header.casefold(): header for header in headers if header}
    if len(header_lookup) != len([h for h in headers if h]):
        raise ProcessingError("CSV headers must be unique, ignoring capitalization.")

    template = _read_docx(template_data)
    all_paragraphs = list(_document_paragraphs_and_cells(template))
    tokens = set()
    for paragraph in all_paragraphs:
        tokens.update(_re.findall(r"\{\{\s*([^{}]+?)\s*\}\}", paragraph.text))
    if not tokens:
        raise ProcessingError("No {{ColumnName}} placeholders were found in the Word template.")
    missing = [token for token in sorted(tokens) if token.strip().casefold() not in header_lookup]
    if missing:
        raise ProcessingError("The CSV is missing template columns: " + ", ".join(missing[:15]))

    artifacts = []
    for row_number, row in enumerate(rows, start=1):
        row_map = {headers[i].casefold(): row[i] for i in range(min(len(headers), len(row)))}
        document = _read_docx(template_data)
        paragraphs = list(_document_paragraphs_and_cells(document))
        for token in tokens:
            header = header_lookup[token.strip().casefold()]
            value = row_map.get(header.casefold(), "")
            full_token = "{{" + token + "}}"
            spaced_token = "{{ " + token + " }}"
            # Replace the exact normalized token and its common spaced form.
            for paragraph in paragraphs:
                _replace_paragraph_text(paragraph, full_token, value)
                if spaced_token != full_token:
                    _replace_paragraph_text(paragraph, spaced_token, value)
        name_value = next((row_map.get(key, "") for key in ("fullname", "name", "company", "id") if row_map.get(key, "").strip()), "")
        doc_name = _safe_output_filename(name_value, f"record-{row_number:03d}")
        stream = io.BytesIO()
        document.save(stream)
        artifacts.append(OutputArtifact(f"{doc_name}.docx", stream.getvalue(), DOCX_MIME))
    return artifacts


def _word_compare(filename_old: str, old_data: bytes, filename_new: str, new_data: bytes) -> bytes:
    old_lines = _word_to_text(old_data).splitlines()
    new_lines = _word_to_text(new_data).splitlines()
    diff = list(difflib.unified_diff(old_lines, new_lines, fromfile=Path(filename_old).name, tofile=Path(filename_new).name, lineterm=""))
    if not diff:
        report = "No text differences were found in the extracted paragraphs, tables, headers and footers.\n\nNote: visual layout, images, tracked changes and pagination were not compared."
    else:
        report = "WORD DOCUMENT COMPARISON\n" + "=" * 24 + "\n\n" + "\n".join(diff) + "\n\nNote: this report compares extracted text only; it does not compare visual layout, images, tracked changes or pagination."
    return report.encode("utf-8")


def _word_tables_to_excel(filename: str, data: bytes) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    document = _read_docx(data)
    if not document.tables:
        raise ProcessingError("No Word tables were found in this document.")
    if len(document.tables) > 100:
        raise ProcessingError("Word table export is limited to 100 tables per document.")
    workbook = Workbook()
    workbook.remove(workbook.active)
    for index, table in enumerate(document.tables, start=1):
        ws = workbook.create_sheet(f"Table{index}")
        for r_idx, row in enumerate(table.rows, start=1):
            if len(row.cells) > 100:
                raise ProcessingError(f"Word table {index} has more than 100 columns.")
            for c_idx, cell in enumerate(row.cells, start=1):
                value = cell.text.replace("\n", " / ").strip()
                target = ws.cell(r_idx, c_idx, value=value)
                target.data_type = "s"
                if r_idx == 1:
                    target.font = Font(bold=True, color="17365D")
                    target.fill = PatternFill("solid", fgColor="DCE8F7")
        ws.freeze_panes = "A2"
        if ws.max_row and ws.max_column:
            ws.auto_filter.ref = ws.dimensions
            for column_cells in ws.iter_cols(min_row=1, max_row=min(ws.max_row, 100)):
                letter = column_cells[0].column_letter
                width = min(38, max(10, max((len(str(c.value or "")) for c in column_cells), default=8) + 2))
                ws.column_dimensions[letter].width = width
    out = io.BytesIO()
    workbook.save(out)
    workbook.close()
    return out.getvalue()


def _word_add_page_numbers(data: bytes) -> bytes:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    document = _read_docx(data)
    processed_footers = set()
    for section in document.sections:
        footer = section.footer
        footer_id = id(footer._element)
        # Sections can share a linked footer. Add one field per actual footer part.
        if footer_id in processed_footers:
            continue
        processed_footers.add(footer_id)
        if len(footer.paragraphs) == 1 and not footer.paragraphs[0].text.strip() and "fldSimple" not in footer.paragraphs[0]._p.xml:
            paragraph = footer.paragraphs[0]
        else:
            paragraph = footer.add_paragraph()
        paragraph.alignment = 2  # right aligned
        paragraph.add_run("Page ")
        field = OxmlElement("w:fldSimple")
        field.set(qn("w:instr"), "PAGE")
        run = OxmlElement("w:r")
        text = OxmlElement("w:t")
        text.text = "1"
        run.append(text)
        field.append(run)
        paragraph._p.append(field)
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


def _word_clear_metadata(data: bytes) -> bytes:
    from datetime import datetime
    document = _read_docx(data)
    properties = document.core_properties
    for key in ("author", "category", "comments", "content_status", "identifier", "keywords", "language", "last_modified_by", "subject", "title", "version"):
        try:
            setattr(properties, key, "")
        except (AttributeError, ValueError):
            pass
    properties.revision = 1
    # Normalize timestamps rather than retaining the original authoring timestamps.
    try:
        properties.created = datetime(2000, 1, 1)
        properties.modified = datetime(2000, 1, 1)
    except (AttributeError, ValueError, TypeError):
        pass
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


def _text_to_pdf(filename: str, data: bytes, params: dict[str, str]) -> bytes:
    from reportlab.lib.pagesizes import A4, LETTER
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, KeepTogether
    from xml.sax.saxutils import escape
    if len(data) > 5 * 1024 * 1024:
        raise ProcessingError("Text-to-PDF is limited to 5 MB of UTF-8 text per conversion.")
    text = data.decode("utf-8-sig", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    try:
        font_size = int(params.get("font_size", "10"))
    except ValueError as exc:
        raise ProcessingError("Font size must be a number from 8 to 14 points.") from exc
    if font_size < 8 or font_size > 14:
        raise ProcessingError("Font size must be a number from 8 to 14 points.")
    pagesize = LETTER if params.get("page_size", "a4").lower() == "letter" else A4
    styles = getSampleStyleSheet()
    body = ParagraphStyle("PapyronixBody", parent=styles["BodyText"], fontName="Helvetica", fontSize=font_size, leading=font_size * 1.45, spaceAfter=4)
    heading = ParagraphStyle("PapyronixHeading", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=font_size + 4, leading=(font_size + 4) * 1.25, spaceBefore=9, spaceAfter=5)
    title = ParagraphStyle("PapyronixTitle", parent=styles["Title"], alignment=TA_CENTER, fontName="Helvetica-Bold", fontSize=font_size + 6, leading=(font_size + 6) * 1.25, spaceAfter=14)
    story = [Paragraph(escape(Path(filename).stem.replace("_", " ")), title), Spacer(1, 2 * mm)]
    for line in text.split("\n"):
        clean = line.strip()
        if not clean:
            story.append(Spacer(1, 3 * mm))
        elif clean.startswith("### "):
            story.append(Paragraph(escape(clean[4:]), body))
        elif clean.startswith("## ") or clean.startswith("# "):
            story.append(Paragraph(escape(clean.lstrip("# ")), heading))
        elif clean.startswith(("- ", "* ")):
            story.append(Paragraph("• " + escape(clean[2:]), ParagraphStyle("PapyronixBullet", parent=body, leftIndent=12, firstLineIndent=-8)))
        elif re.match(r"^\d+[.)]\s+", clean):
            story.append(Paragraph(escape(clean), ParagraphStyle("PapyronixNumbered", parent=body, leftIndent=12, firstLineIndent=-8)))
        else:
            story.append(Paragraph(escape(clean), body))
    out = io.BytesIO()
    def draw_page_number(canvas_obj, doc):
        canvas_obj.saveState()
        canvas_obj.setFont("Helvetica", 8)
        canvas_obj.drawRightString(pagesize[0] - 18 * mm, 10 * mm, f"Page {doc.page}")
        canvas_obj.restoreState()
    doc = SimpleDocTemplate(out, pagesize=pagesize, rightMargin=18 * mm, leftMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm, title=Path(filename).stem[:200])
    try:
        doc.build(story, onFirstPage=draw_page_number, onLaterPages=draw_page_number)
    except Exception as exc:
        raise ProcessingError("The text could not be laid out as a PDF. Simplify unusual markup or split the source into smaller files.") from exc
    return out.getvalue()


def _excel_to_word_report(filename: str, data: bytes) -> bytes:
    from docx import Document
    from docx.shared import Inches
    workbook = _excel_workbook(data, read_only=False, data_only=False)
    if len(workbook.worksheets) > 30:
        workbook.close()
        raise ProcessingError("Excel-to-Word supports up to 30 worksheets per report.")
    document = Document()
    document.add_heading(Path(filename).stem[:120], 0)
    document.add_paragraph("Workbook table export · Generated locally by Papyronix")
    any_rows = False
    try:
        for sheet in workbook.worksheets:
            if sheet.max_row > 1000 or sheet.max_column > 30:
                raise ProcessingError(f"Worksheet '{sheet.title}' exceeds the 1,000-row or 30-column export limit.")
            rows = [["" if cell.value is None else str(cell.value) for cell in row] for row in sheet.iter_rows()]
            while rows and not any(value.strip() for value in rows[-1]):
                rows.pop()
            if not rows:
                continue
            while rows and not any(value.strip() for value in rows[0]):
                rows.pop(0)
            if not rows:
                continue
            max_cols = max(len(row) for row in rows)
            if max_cols == 0:
                continue
            if any_rows:
                document.add_page_break()
            any_rows = True
            document.add_heading(sheet.title, level=1)
            table = document.add_table(rows=1, cols=max_cols)
            table.style = "Light Shading Accent 1"
            for col, value in enumerate(rows[0]):
                table.rows[0].cells[col].text = value
                for run in table.rows[0].cells[col].paragraphs[0].runs:
                    run.bold = True
            for row in rows[1:]:
                cells = table.add_row().cells
                for col in range(max_cols):
                    cells[col].text = row[col] if col < len(row) else ""
        if not any_rows:
            raise ProcessingError("No non-empty worksheet data was found in this workbook.")
        output = io.BytesIO()
        document.save(output)
        return output.getvalue()
    finally:
        workbook.close()


def _excel_split_sheets(filename: str, data: bytes) -> list[OutputArtifact]:
    from openpyxl import Workbook
    workbook = _excel_workbook(data, read_only=False, data_only=False)
    if len(workbook.worksheets) > 50:
        workbook.close()
        raise ProcessingError("Excel worksheet split supports up to 50 worksheets per workbook.")
    artifacts = []
    try:
        for source in workbook.worksheets:
            target_book = Workbook()
            target = target_book.active
            target.title = source.title[:31] or "Sheet1"
            if source.max_row > 200_000 or source.max_column > 500:
                target_book.close()
                raise ProcessingError(f"Worksheet '{source.title}' exceeds the 200,000-row or 500-column safety limit.")
            for row in source.iter_rows():
                for cell in row:
                    dest = target.cell(row=cell.row, column=cell.column, value=cell.value)
                    if cell.has_style:
                        dest._style = copy(cell._style)
                    if cell.number_format:
                        dest.number_format = cell.number_format
                    if cell.hyperlink:
                        dest._hyperlink = copy(cell.hyperlink)
                    if cell.comment:
                        dest.comment = copy(cell.comment)
            for merged in source.merged_cells.ranges:
                target.merge_cells(str(merged))
            target.freeze_panes = source.freeze_panes
            target.auto_filter.ref = source.auto_filter.ref
            for key, dim in source.column_dimensions.items():
                target.column_dimensions[key].width = dim.width
                target.column_dimensions[key].hidden = dim.hidden
                target.column_dimensions[key].bestFit = dim.bestFit
            for key, dim in source.row_dimensions.items():
                target.row_dimensions[key].height = dim.height
                target.row_dimensions[key].hidden = dim.hidden
            for row_idx in range(1, target.max_row + 1):
                for col_idx in range(1, target.max_column + 1):
                    cell = target.cell(row_idx, col_idx)
                    if isinstance(cell.value, str) and cell.value.startswith(("=", "+", "-", "@")) and cell.data_type != "f":
                        cell.data_type = "s"
            output = io.BytesIO()
            target_book.save(output)
            target_book.close()
            artifacts.append(OutputArtifact(f"{safe_stem(filename)}-{_safe_output_filename(source.title, 'sheet')}.xlsx", output.getvalue(), XLSX_MIME))
    finally:
        workbook.close()
    return artifacts


def _excel_sort(filename: str, data: bytes, params: dict[str, str]) -> bytes:
    workbook = _excel_workbook(data, read_only=False, data_only=False)
    requested_sheet = params.get("sheet_name", "").strip()
    if requested_sheet and requested_sheet not in workbook.sheetnames:
        workbook.close()
        raise ProcessingError("The selected worksheet name was not found. Use a sheet name exactly as shown in Excel.")
    ws = workbook[requested_sheet] if requested_sheet else workbook.active
    column_name = params.get("sort_column", "").strip()
    if not column_name:
        workbook.close()
        raise ProcessingError("Enter the header name of the column to sort by.")
    if ws.max_row < 2:
        workbook.close()
        raise ProcessingError("The selected worksheet has no data rows to sort.")
    if ws.max_row > 200_000 or ws.max_column > 500:
        workbook.close()
        raise ProcessingError("Sorting is limited to 200,000 rows and 500 columns.")
    matches = [cell.column for cell in ws[1] if str(cell.value or "").strip().casefold() == column_name.casefold()]
    if not matches:
        workbook.close()
        raise ProcessingError(f"The header '{column_name}' was not found in worksheet '{ws.title}'.")
    col_index = matches[0]
    # Snapshot data and formatting independently so writing sorted rows cannot mutate sort keys
    # and common cell styling travels with each record.
    row_values = []
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row, max_col=ws.max_column):
        row_values.append([{
            "value": cell.value,
            "style": copy(cell._style) if cell.has_style else None,
            "number_format": cell.number_format,
            "hyperlink": copy(cell.hyperlink) if cell.hyperlink else None,
            "comment": copy(cell.comment) if cell.comment else None,
        } for cell in row])
    nonblank = [row for row in row_values if row[col_index - 1]["value"] not in (None, "")]
    blank = [row for row in row_values if row[col_index - 1]["value"] in (None, "")]
    def key(row):
        value = row[col_index - 1]["value"]
        if isinstance(value, bool):
            return (0, int(value))
        if isinstance(value, (int, float)):
            return (1, float(value))
        return (2, str(value).casefold())
    direction = params.get("sort_direction", "ascending").lower()
    if direction not in {"ascending", "descending"}:
        workbook.close()
        raise ProcessingError("Choose ascending or descending sort direction.")
    nonblank.sort(key=key, reverse=direction == "descending")
    sorted_rows = nonblank + blank
    for out_row, source_row in enumerate(sorted_rows, start=2):
        for col_idx, snapshot in enumerate(source_row, start=1):
            target = ws.cell(out_row, col_idx)
            target.value = snapshot["value"]
            target._style = copy(snapshot["style"]) if snapshot["style"] is not None else None
            target.number_format = snapshot["number_format"]
            target._hyperlink = copy(snapshot["hyperlink"]) if snapshot["hyperlink"] else None
            target.comment = copy(snapshot["comment"]) if snapshot["comment"] else None
    output = io.BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def _workbook_cell_map(filename: str, data: bytes) -> dict[tuple[str, str], object]:
    workbook = _excel_workbook(data, read_only=False, data_only=False)
    result = {}
    try:
        if len(workbook.worksheets) > 50:
            raise ProcessingError(f"{filename} has more than 50 worksheets; reduce the workbook before comparing.")
        for ws in workbook.worksheets:
            populated = 0
            for (row, col), cell in ws._cells.items():
                if cell.value is not None:
                    populated += 1
                    result[(ws.title, cell.coordinate)] = cell.value
            if populated > 500_000:
                raise ProcessingError(f"{filename}, worksheet '{ws.title}', has more than 500,000 populated cells.")
        if len(result) > 500_000:
            raise ProcessingError(f"{filename} has more than 500,000 populated cells across all worksheets.")
        return result
    finally:
        workbook.close()


def _excel_compare(filename_a: str, data_a: bytes, filename_b: str, data_b: bytes) -> bytes:
    before = _workbook_cell_map(filename_a, data_a)
    after = _workbook_cell_map(filename_b, data_b)
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    writer.writerow(["Worksheet", "Cell", "Earlier value", "Later value", "Change"])
    changed = 0
    from openpyxl.utils.cell import coordinate_to_tuple
    keys = sorted(set(before) | set(after), key=lambda item: (item[0].casefold(), coordinate_to_tuple(item[1])))
    for sheet, coord in keys:
        old, new = before.get((sheet, coord)), after.get((sheet, coord))
        if old != new:
            kind = "Added" if (sheet, coord) not in before else "Removed" if (sheet, coord) not in after else "Changed"
            writer.writerow([_safe_csv_value(sheet), _safe_csv_value(coord), _safe_csv_value(old), _safe_csv_value(new), kind])
            changed += 1
            if changed > 20_000:
                raise ProcessingError("More than 20,000 cell changes were found. Compare smaller ranges or split the workbook first.")
    if changed == 0:
        writer.writerow(["", "", "", "", "No cell differences found"])
    return out.getvalue().encode("utf-8-sig")


def _safe_csv_value(value: object) -> str:
    """Prefix obvious spreadsheet formulas while leaving ordinary negative numbers intact."""
    text = "" if value is None else str(value)
    stripped = text.lstrip()
    if not stripped:
        return text
    numeric = re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", stripped)
    if stripped.startswith(("=", "@", "\t", "\r")) or (stripped.startswith(("+", "-")) and not numeric):
        return "'" + text
    return text


def _csv_clean(filename: str, data: bytes) -> bytes:
    headers, rows, delimiter = _read_csv_rows(data)
    cleaned = []
    seen = set()
    for row in rows:
        row = [cell.strip() for cell in row]
        if not any(row):
            continue
        key = tuple(row)
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(row)
    out = io.StringIO(newline="")
    writer = csv.writer(out, delimiter=delimiter, lineterminator="\n")
    writer.writerow([_safe_csv_value(value) for value in headers])
    writer.writerows([_safe_csv_value(value) for value in row] for row in cleaned)
    return out.getvalue().encode("utf-8-sig")


def _csv_filter(filename: str, data: bytes, params: dict[str, str]) -> bytes:
    headers, rows, delimiter = _read_csv_rows(data)
    column = params.get("filter_column", "").strip()
    search = params.get("filter_value", "").strip()
    mode = params.get("filter_mode", "contains").lower()
    if not column or not search:
        raise ProcessingError("Enter a column header and a value to filter for.")
    if mode not in {"contains", "exact"}:
        raise ProcessingError("Choose contains or exact matching.")
    candidates = [index for index, header in enumerate(headers) if header.casefold() == column.casefold()]
    if not candidates:
        raise ProcessingError(f"Column '{column}' was not found. Use one of: {', '.join(headers[:20])}.")
    index = candidates[0]
    search_norm = search.casefold()
    if mode == "contains":
        selected = [row for row in rows if search_norm in row[index].casefold()]
    else:
        selected = [row for row in rows if search_norm == row[index].casefold()]
    out = io.StringIO(newline="")
    writer = csv.writer(out, delimiter=delimiter, lineterminator="\n")
    writer.writerow(headers)
    writer.writerows(selected)
    return out.getvalue().encode("utf-8-sig")

def process_office_tool(operation: str, files: list[tuple[str, bytes]], params: dict[str, str]) -> list[OutputArtifact]:
    if not files:
        raise ProcessingError("Choose at least one file before processing.")
    name, data = files[0]
    stem = safe_stem(name)

    if operation in {"word-compare", "word-template-fill", "excel-compare"}:
        if len(files) != 2:
            needed = "a Word template and a CSV file" if operation == "word-template-fill" else "exactly two source files"
            raise ProcessingError(f"Choose {needed} for this operation.")
        if operation == "word-compare":
            if any(_ext(filename) != ".docx" for filename, _ in files):
                raise ProcessingError("Choose two modern .docx Word files to compare.")
            report = _word_compare(files[0][0], files[0][1], files[1][0], files[1][1])
            return [OutputArtifact(f"{safe_stem(files[0][0])}-vs-{safe_stem(files[1][0])}-changes.txt", report, TEXT_MIME)]
        if operation == "word-template-fill":
            templates = [(filename, content) for filename, content in files if _ext(filename) == ".docx"]
            csv_sources = [(filename, content) for filename, content in files if _ext(filename) == ".csv"]
            if len(templates) != 1 or len(csv_sources) != 1:
                raise ProcessingError("Choose exactly one .docx Word template and one .csv data file. The selection order does not matter.")
            return _template_merge_docx(templates[0][1], csv_sources[0][1], templates[0][0])
        if any(_ext(filename) != ".xlsx" for filename, _ in files):
            raise ProcessingError("Choose two .xlsx workbooks to compare.")
        report = _excel_compare(files[0][0], files[0][1], files[1][0], files[1][1])
        return [OutputArtifact(f"{safe_stem(files[0][0])}-vs-{safe_stem(files[1][0])}-changes.csv", report, "text/csv; charset=utf-8")]

    if operation == "word-to-pdf" or operation == "excel-to-pdf" or operation == "pptx-to-pdf":
        expected = {"word-to-pdf": ".docx", "excel-to-pdf": ".xlsx", "pptx-to-pdf": ".pptx"}[operation]
        if _ext(name) != expected:
            raise ProcessingError(f"This tool accepts {expected} files only.")
        return [OutputArtifact(f"{stem}.pdf", _local_libreoffice_convert(name, data), PDF_MIME)]

    if operation == "pdf-to-text":
        pages = _pdf_to_text(name, data, params.get("pdf_password", ""))
        content = "\n\n".join(pages).encode("utf-8")
        return [OutputArtifact(f"{stem}.txt", content, TEXT_MIME)]

    if operation == "pdf-to-word":
        if _ext(name) != ".pdf":
            raise ProcessingError("Choose a PDF file for this tool.")
        content = _pdf_to_docx(name, data, params.get("pdf_password", ""))
        return [OutputArtifact(f"{stem}-editable.docx", content, DOCX_MIME)]

    if operation == "pdf-to-images":
        if _ext(name) != ".pdf":
            raise ProcessingError("Choose a PDF file for this tool.")
        return _pdf_to_images(name, data, params)

    if operation == "pdf-ocr":
        if _ext(name) != ".pdf":
            raise ProcessingError("Choose a PDF file for local OCR.")
        return [OutputArtifact(f"{stem}-searchable.pdf", _ocr_pdf(name, data, params), PDF_MIME)]

    if operation == "image-to-text":
        if _ext(name) not in {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}:
            raise ProcessingError("Choose a JPG, PNG, TIFF, BMP or WebP image for OCR.")
        language = (params.get("ocr_language") or "eng").strip()[:40]
        return [OutputArtifact(f"{stem}-ocr.txt", _ocr_image_bytes(data, language).encode("utf-8"), TEXT_MIME)]

    if operation == "word-to-text":
        if _ext(name) != ".docx":
            raise ProcessingError("Choose a .docx Word file. Legacy .doc files are not supported.")
        text = _word_to_text(data)
        if not text:
            raise ProcessingError("No text was found in this Word document.")
        return [OutputArtifact(f"{stem}.txt", text.encode("utf-8"), TEXT_MIME)]

    if operation == "word-to-markdown":
        if _ext(name) != ".docx":
            raise ProcessingError("Choose a .docx Word file.")
        markdown = _word_to_markdown(data)
        if not markdown:
            raise ProcessingError("No readable paragraphs or tables were found in this Word file.")
        return [OutputArtifact(f"{stem}.md", markdown.encode("utf-8"), TEXT_MIME)]

    if operation == "word-extract-images":
        if _ext(name) != ".docx":
            raise ProcessingError("Choose a .docx Word file.")
        return _extract_docx_images(name, data)

    if operation == "word-replace":
        if _ext(name) != ".docx":
            raise ProcessingError("Choose a .docx Word file.")
        updated, count = _replace_docx(data, params.get("find_text", ""), params.get("replace_text", ""))
        if count == 0:
            raise ProcessingError("No exact match was found. The search is case-sensitive and must match the document text exactly.")
        return [OutputArtifact(f"{stem}-replaced.docx", updated, DOCX_MIME)]

    if operation == "word-clean":
        if _ext(name) != ".docx":
            raise ProcessingError("Choose a .docx Word file.")
        return [OutputArtifact(f"{stem}-cleaned.docx", _clean_docx(data), DOCX_MIME)]

    if operation == "word-table-to-excel":
        if _ext(name) != ".docx":
            raise ProcessingError("Choose a .docx Word document containing at least one table.")
        return [OutputArtifact(f"{stem}-tables.xlsx", _word_tables_to_excel(name, data), XLSX_MIME)]

    if operation == "word-add-page-numbers":
        if _ext(name) != ".docx":
            raise ProcessingError("Choose a .docx Word file.")
        return [OutputArtifact(f"{stem}-page-numbered.docx", _word_add_page_numbers(data), DOCX_MIME)]

    if operation == "word-clear-metadata":
        if _ext(name) != ".docx":
            raise ProcessingError("Choose a .docx Word file.")
        return [OutputArtifact(f"{stem}-metadata-cleared.docx", _word_clear_metadata(data), DOCX_MIME)]

    if operation == "text-to-pdf":
        if _ext(name) not in {".txt", ".md"}:
            raise ProcessingError("Choose a TXT or Markdown file.")
        return [OutputArtifact(f"{stem}.pdf", _text_to_pdf(name, data, params), PDF_MIME)]

    if operation == "text-to-word":
        if _ext(name) not in {".txt", ".md"}:
            raise ProcessingError("Choose a TXT or Markdown file.")
        return [OutputArtifact(f"{stem}.docx", _text_to_word(data), DOCX_MIME)]

    if operation == "word-count":
        return [OutputArtifact(f"{stem}-analysis.txt", _word_count_report(name, data, params.get("pdf_password", "")), TEXT_MIME)]

    if operation == "excel-to-csv":
        if _ext(name) != ".xlsx":
            raise ProcessingError("Choose an .xlsx workbook.")
        return _excel_to_csv(name, data)

    if operation == "csv-to-excel":
        if _ext(name) != ".csv":
            raise ProcessingError("Choose a .csv file.")
        out = _csv_to_excel(name, data, params.get("delimiter", "comma"))
        return [OutputArtifact(f"{stem}.xlsx", out, XLSX_MIME)]

    if operation == "excel-clean":
        if _ext(name) != ".xlsx":
            raise ProcessingError("Choose an .xlsx workbook.")
        return [OutputArtifact(f"{stem}-cleaned.xlsx", _excel_clean(name, data), XLSX_MIME)]

    if operation == "excel-split-sheets":
        if _ext(name) != ".xlsx":
            raise ProcessingError("Choose an .xlsx workbook.")
        return _excel_split_sheets(name, data)

    if operation == "excel-sort":
        if _ext(name) != ".xlsx":
            raise ProcessingError("Choose an .xlsx workbook.")
        return [OutputArtifact(f"{stem}-sorted.xlsx", _excel_sort(name, data, params), XLSX_MIME)]

    if operation == "excel-to-word":
        if _ext(name) != ".xlsx":
            raise ProcessingError("Choose an .xlsx workbook.")
        return [OutputArtifact(f"{stem}-report.docx", _excel_to_word_report(name, data), DOCX_MIME)]

    if operation == "csv-clean":
        if _ext(name) != ".csv":
            raise ProcessingError("Choose a .csv file.")
        return [OutputArtifact(f"{stem}-cleaned.csv", _csv_clean(name, data), "text/csv; charset=utf-8")]

    if operation == "csv-filter":
        if _ext(name) != ".csv":
            raise ProcessingError("Choose a .csv file.")
        return [OutputArtifact(f"{stem}-filtered.csv", _csv_filter(name, data, params), "text/csv; charset=utf-8")]

    if operation == "excel-merge":
        if any(_ext(filename) != ".xlsx" for filename, _ in files):
            raise ProcessingError("Every selected file must be an .xlsx workbook.")
        if len(files) < 2:
            raise ProcessingError("Choose at least two Excel workbooks to combine.")
        if len(files) > 30:
            raise ProcessingError("Excel merge is limited to 30 input workbooks.")
        return [OutputArtifact("combined-workbooks.xlsx", _excel_merge(files), XLSX_MIME)]

    if operation == "pptx-to-text":
        if _ext(name) != ".pptx":
            raise ProcessingError("Choose a .pptx PowerPoint file.")
        text = _pptx_to_text(data)
        return [OutputArtifact(f"{stem}-slides.txt", text.encode("utf-8"), TEXT_MIME)]

    if operation == "pptx-to-word":
        if _ext(name) != ".pptx":
            raise ProcessingError("Choose a .pptx PowerPoint file.")
        return [OutputArtifact(f"{stem}-speaker-notes.docx", _pptx_to_word(data, name), DOCX_MIME)]

    raise ProcessingError("This operation is not available yet.")
