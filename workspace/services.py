"""Local PDF processing engine. No remote services or API keys are used."""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import re
import zipfile
from typing import Iterable

from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

MAX_PAGE_COUNT = 5000

@dataclass
class OutputArtifact:
    name: str
    content: bytes
    content_type: str = "application/pdf"

TOOLS = [
    # PDF operations
    {"slug": "merge", "name": "Merge PDFs", "group": "Organize PDFs", "family": "pdf", "description": "Combine several PDF files in the order you choose.", "icon": "merge", "multi": True, "accept": ".pdf", "hint": "Select at least two PDFs. Use the up/down ordering controls before processing."},
    {"slug": "split", "name": "Split PDF", "group": "Organize PDFs", "family": "pdf", "description": "Separate a PDF into custom page ranges, equal batches, or one page per file.", "icon": "split", "multi": False, "accept": ".pdf", "hint": "For custom ranges, use comma-separated groups such as 1-3,4-6,7-9."},
    {"slug": "extract", "name": "Extract pages", "group": "Organize PDFs", "family": "pdf", "description": "Create a new PDF containing only the pages you need.", "icon": "extract", "multi": False, "accept": ".pdf", "hint": "Example: 1,3-5,8 creates a PDF containing pages 1, 3, 4, 5 and 8."},
    {"slug": "rotate", "name": "Rotate pages", "group": "Organize PDFs", "family": "pdf", "description": "Correct the orientation of selected pages.", "icon": "rotate", "multi": False, "accept": ".pdf", "hint": "Choose all pages or a list such as 2,4-6, then select a rotation angle."},
    {"slug": "remove", "name": "Remove pages", "group": "Organize PDFs", "family": "pdf", "description": "Remove unwanted pages and export a clean copy.", "icon": "remove", "multi": False, "accept": ".pdf", "hint": "Enter pages to remove, for example 2,5-7. At least one page must remain."},
    {"slug": "reorder", "name": "Reorder pages", "group": "Organize PDFs", "family": "pdf", "description": "Define a new page order using page numbers and ranges.", "icon": "reorder", "multi": False, "accept": ".pdf", "hint": "Enter every page exactly once, for example 3,1,2,4-6."},
    {"slug": "watermark", "name": "Add watermark", "group": "Polish PDFs", "family": "pdf", "description": "Apply a subtle text watermark across every page.", "icon": "watermark", "multi": False, "accept": ".pdf", "hint": "Use a short phrase such as DRAFT or CONFIDENTIAL."},
    {"slug": "page-numbers", "name": "Page numbers", "group": "Polish PDFs", "family": "pdf", "description": "Add page numbering to a new copy of the PDF.", "icon": "numbers", "multi": False, "accept": ".pdf", "hint": "Choose the first number. Page labels are added at the bottom-right of each page."},
    {"slug": "optimize", "name": "Optimize PDF streams", "group": "Polish PDFs", "family": "pdf", "description": "Re-save a PDF and compress eligible page content streams.", "icon": "optimize", "multi": False, "accept": ".pdf", "hint": "This is a structural optimization, not image downsampling; a smaller output is not guaranteed."},
    {"slug": "images-to-pdf", "name": "Images to PDF", "group": "PDF Conversion", "family": "pdf", "description": "Combine JPG and PNG images into a multi-page PDF.", "icon": "images", "multi": True, "accept": ".jpg,.jpeg,.png", "hint": "Select JPG or PNG images in the order you want them to appear."},
    {"slug": "pdf-to-word", "name": "PDF to editable Word", "group": "PDF Conversion", "family": "pdf", "description": "Extract selectable PDF text into an editable DOCX file.", "icon": "word", "multi": False, "accept": ".pdf", "hint": "Text is made editable, but the original page layout, columns and embedded images may not be preserved."},
    {"slug": "pdf-to-text", "name": "PDF to text", "group": "PDF Conversion", "family": "pdf", "description": "Extract selectable text from every PDF page into a TXT file.", "icon": "text", "multi": False, "accept": ".pdf", "hint": "Scanned PDFs need OCR before their text can be extracted."},
    {"slug": "pdf-to-images", "name": "PDF to images", "group": "PDF Conversion", "family": "pdf", "description": "Export selected PDF pages as high-quality PNG images.", "icon": "images", "multi": False, "accept": ".pdf", "hint": "Choose page numbers and output resolution. Many pages are packaged as a ZIP download."},
    {"slug": "pdf-ocr", "name": "OCR scanned PDF", "group": "Text & OCR", "family": "pdf", "description": "Create a searchable PDF from page scans using local Tesseract OCR.", "icon": "ocr", "multi": False, "accept": ".pdf", "hint": "Requires the free Tesseract OCR program installed locally. No AI API or token is used."},
    {"slug": "protect", "name": "Password-protect PDF", "group": "PDF Security", "family": "pdf", "description": "Encrypt a PDF with a password you choose.", "icon": "protect", "multi": False, "accept": ".pdf", "hint": "Use a strong, unique password and store it safely. This cannot recover a forgotten password."},
    {"slug": "unlock", "name": "Unlock PDF", "group": "PDF Security", "family": "pdf", "description": "Remove encryption from a PDF when you know its current password.", "icon": "unlock", "multi": False, "accept": ".pdf", "hint": "You must supply the correct current password. This tool does not bypass PDF security."},
    # Word and everyday document operations
    {"slug": "word-to-pdf", "name": "Word to PDF", "group": "Word & Documents", "family": "office", "description": "Convert DOCX documents to PDF using locally installed LibreOffice.", "icon": "pdf", "multi": False, "accept": ".docx", "hint": "Requires LibreOffice installed on this computer. Layout is rendered locally and no file is sent to a converter API."},
    {"slug": "word-to-text", "name": "Word to text", "group": "Word & Documents", "family": "office", "description": "Extract readable paragraphs, table contents, headers and footers from DOCX.", "icon": "text", "multi": False, "accept": ".docx", "hint": "Accepts modern .docx files. The older binary .doc format is not supported."},
    {"slug": "word-to-markdown", "name": "Word to Markdown", "group": "Word & Documents", "family": "office", "description": "Export Word headings, lists, paragraphs and tables as an editable Markdown file.", "icon": "text", "multi": False, "accept": ".docx", "hint": "Exports common paragraph and table structure. Page layout, floating objects and advanced formatting are not represented in Markdown."},
    {"slug": "word-extract-images", "name": "Extract images from Word", "group": "Word & Documents", "family": "office", "description": "Extract embedded image files from a DOCX and download them directly or as a ZIP.", "icon": "images", "multi": False, "accept": ".docx", "hint": "Extracts media assets embedded in the DOCX package; it does not extract WordArt, charts or vector content that is stored as editable drawing instructions."},
    {"slug": "word-replace", "name": "Find and replace in Word", "group": "Word & Documents", "family": "office", "description": "Replace repeated terms in a Word file without rewriting it with an AI model.", "icon": "replace", "multi": False, "accept": ".docx", "hint": "Matching is exact and case-sensitive. Run formatting is retained as far as Word's text-run structure allows."},
    {"slug": "word-clean", "name": "Clean Word document", "group": "Word & Documents", "family": "office", "description": "Normalize excess whitespace and remove empty body paragraphs in DOCX files.", "icon": "clean", "multi": False, "accept": ".docx", "hint": "Always review the cleaned output, especially if the original used blank lines for intentional spacing."},
    {"slug": "text-to-word", "name": "Text to Word", "group": "Word & Documents", "family": "office", "description": "Turn a plain-text or Markdown file into an editable DOCX document.", "icon": "word", "multi": False, "accept": ".txt,.md", "hint": "Basic Markdown headings, emphasis, bullets, numbered lists, quotes and simple pipe tables are converted to formatted Word elements. Hyperlinks are written as label plus URL text; images and complex Markdown extensions are not imported."},
    {"slug": "word-count", "name": "Document word counter", "group": "Word & Documents", "family": "office", "description": "Count words, characters and non-empty lines in common document formats.", "icon": "count", "multi": False, "accept": ".pdf,.docx,.pptx,.txt,.md,.csv", "hint": "Counts are based on extractable text; image-only scans need OCR first."},
    {"slug": "word-compare", "name": "Compare Word versions", "group": "Word & Documents", "family": "office", "description": "Generate a local line-by-line change report for two DOCX versions.", "icon": "compare", "multi": True, "accept": ".docx", "hint": "Select the older version first and the newer version second. The report compares extracted paragraphs and table text, not tracked changes or page layout."},
    {"slug": "word-template-fill", "name": "Word mail merge from CSV", "group": "Word & Documents", "family": "office", "description": "Fill {{Column}} placeholders in a Word template using rows from a CSV, producing one DOCX per person or record.", "icon": "template", "multi": True, "accept": ".docx,.csv", "hint": "Select one DOCX template and one CSV file. Use placeholders matching CSV column headers, such as {{FullName}}. Up to 200 outputs per run."},
    {"slug": "word-table-to-excel", "name": "Extract Word tables to Excel", "group": "Word & Documents", "family": "office", "description": "Export each table in a Word document to a separate formatted Excel worksheet.", "icon": "excel", "multi": False, "accept": ".docx", "hint": "Exports table cell values and basic headings. Images, merged-cell layout and advanced Word table styling are not recreated."},
    {"slug": "word-add-page-numbers", "name": "Add Word page numbers", "group": "Word & Documents", "family": "office", "description": "Insert a dynamic page number field into each section footer of a DOCX.", "icon": "numbers", "multi": False, "accept": ".docx", "hint": "Word or LibreOffice updates the page-number fields when it opens or renders the document."},
    {"slug": "word-clear-metadata", "name": "Clear Word document properties", "group": "Word & Documents", "family": "office", "description": "Clear common author, title and document-property metadata from a DOCX copy.", "icon": "clean", "multi": False, "accept": ".docx", "hint": "Clears common core properties only. It does not remove comments, tracked changes, embedded files or every possible metadata field."},
    {"slug": "text-to-pdf", "name": "Text or Markdown to PDF", "group": "PDF Conversion", "family": "office", "description": "Create a paginated PDF from TXT or Markdown with local Python libraries.", "icon": "pdf", "multi": False, "accept": ".txt,.md", "hint": "Basic headings and lists are formatted. Complex Markdown, embedded images and advanced page-layout rules are not interpreted."},
    {"slug": "excel-to-word", "name": "Excel workbook to Word report", "group": "Spreadsheets", "family": "office", "description": "Build a Word report containing readable tables from an Excel workbook's worksheets.", "icon": "word", "multi": False, "accept": ".xlsx", "hint": "Exports cell values into Word tables. Charts, pivot-table layout, formulas as calculated results and Excel-specific formatting are not recreated."},
    # Spreadsheet operations
    {"slug": "excel-to-csv", "name": "Excel to CSV", "group": "Spreadsheets", "family": "office", "description": "Export workbook sheets to CSV, packaged as a ZIP when there are multiple sheets.", "icon": "csv", "multi": False, "accept": ".xlsx", "hint": "Cell values are exported; formulas are not calculated by this engine. Cached results are used where present."},
    {"slug": "csv-to-excel", "name": "CSV to Excel", "group": "Spreadsheets", "family": "office", "description": "Import CSV data into a formatted XLSX workbook with frozen headers and filters.", "icon": "excel", "multi": False, "accept": ".csv", "hint": "Choose the delimiter that matches your CSV file."},
    {"slug": "csv-clean", "name": "Clean CSV data", "group": "Spreadsheets", "family": "office", "description": "Trim whitespace and remove blank or duplicate rows from a CSV file.", "icon": "clean", "multi": False, "accept": ".csv", "hint": "The first row is kept as the header. Duplicate data rows are removed using their cleaned cell values."},
    {"slug": "csv-filter", "name": "Filter CSV rows", "group": "Spreadsheets", "family": "office", "description": "Keep rows whose selected column contains or exactly matches a value.", "icon": "filter", "multi": False, "accept": ".csv", "hint": "The first row is the header. Matching is case-insensitive. Choose the column name exactly as it appears in the CSV."},
    {"slug": "excel-clean", "name": "Clean Excel data", "group": "Spreadsheets", "family": "office", "description": "Remove completely blank rows and exact duplicate rows from every worksheet.", "icon": "clean", "multi": False, "accept": ".xlsx", "hint": "This removes duplicate rows based on all cell values. Review the output before replacing any source workbook."},
    {"slug": "excel-split-sheets", "name": "Split Excel worksheets", "group": "Spreadsheets", "family": "office", "description": "Export each worksheet from one workbook as its own XLSX file in a ZIP.", "icon": "split", "multi": False, "accept": ".xlsx", "hint": "Values, formulas, basic cell styles, merged ranges, widths and frozen panes are copied. Charts, macros, pivot tables and external links are not copied."},
    {"slug": "excel-sort", "name": "Sort Excel rows by column", "group": "Spreadsheets", "family": "office", "description": "Sort worksheet rows by a header name in ascending or descending order.", "icon": "sort", "multi": False, "accept": ".xlsx", "hint": "Choose a header exactly as it appears in the first row. Blank values remain at the bottom. Review formulas after sorting because formula references may need adjustment."},
    {"slug": "excel-compare", "name": "Compare Excel workbooks", "group": "Spreadsheets", "family": "office", "description": "Create a cell-by-cell change report for two XLSX workbooks.", "icon": "compare", "multi": True, "accept": ".xlsx", "hint": "Select the earlier workbook first and the newer workbook second. Formulas are compared as formulas, not recalculated results."},
    {"slug": "excel-merge", "name": "Combine Excel workbooks", "group": "Spreadsheets", "family": "office", "description": "Combine sheets from multiple workbooks into a single XLSX file.", "icon": "merge", "multi": True, "accept": ".xlsx", "hint": "Each source worksheet becomes a separate sheet. Cell values and basic styles are copied; external links and pivots are not merged."},
    {"slug": "excel-to-pdf", "name": "Excel to PDF", "group": "Spreadsheets", "family": "office", "description": "Export an XLSX workbook to PDF using locally installed LibreOffice.", "icon": "pdf", "multi": False, "accept": ".xlsx", "hint": "Requires LibreOffice installed locally. Check print areas, page scaling and orientation in Excel before converting."},
    # Presentation operations
    {"slug": "pptx-to-pdf", "name": "PowerPoint to PDF", "group": "Presentations", "family": "office", "description": "Export a PPTX presentation to PDF with the local LibreOffice engine.", "icon": "pdf", "multi": False, "accept": ".pptx", "hint": "Requires LibreOffice installed on this computer. Some Microsoft-specific fonts and animations may render differently."},
    {"slug": "pptx-to-text", "name": "PowerPoint to text", "group": "Presentations", "family": "office", "description": "Extract slide headings, text boxes and table contents into a text file.", "icon": "text", "multi": False, "accept": ".pptx", "hint": "Text inside pictures, diagrams or screenshots is not extracted unless you use OCR separately."},
    {"slug": "pptx-to-word", "name": "PowerPoint to Word notes", "group": "Presentations", "family": "office", "description": "Create an editable Word outline from slide text and slide headings.", "icon": "word", "multi": False, "accept": ".pptx", "hint": "This creates a text outline, not a screenshot-perfect reproduction of the slides."},
    # Offline text/OCR
    {"slug": "image-to-text", "name": "Image to text (OCR)", "group": "Text & OCR", "family": "office", "description": "Extract text from scanned images with the free Tesseract OCR engine installed locally.", "icon": "ocr", "multi": False, "accept": ".jpg,.jpeg,.png,.tif,.tiff,.bmp,.webp", "hint": "Requires Tesseract and the selected language data installed on this computer. No AI API or token is used."},
]
TOOL_MAP = {tool["slug"]: tool for tool in TOOLS}

class ProcessingError(ValueError):
    """A safe, user-facing processing validation error."""

def safe_stem(filename: str) -> str:
    stem = re.sub(r"\.[^.]+$", "", filename or "document")
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip(".-_")
    return (stem[:70] or "document")

def validate_pdf(data: bytes, filename: str) -> None:
    if not data:
        raise ProcessingError(f"{filename}: the selected file is empty.")
    if b"%PDF-" not in data[:1024]:
        raise ProcessingError(f"{filename}: this file does not appear to be a valid PDF.")

def open_pdf(data: bytes, filename: str, password: str = "") -> PdfReader:
    validate_pdf(data, filename)
    try:
        reader = PdfReader(BytesIO(data), strict=False)
        if reader.is_encrypted:
            if not password:
                raise ProcessingError(f"{filename} is password-protected. Enter its current password to continue.")
            try:
                result = reader.decrypt(password)
            except Exception as exc:
                raise ProcessingError(f"The password for {filename} could not unlock this PDF.") from exc
            if not result:
                raise ProcessingError(f"The password for {filename} is incorrect.")
        if len(reader.pages) > MAX_PAGE_COUNT:
            raise ProcessingError(f"{filename} exceeds the {MAX_PAGE_COUNT:,}-page processing limit.")
        if len(reader.pages) == 0:
            raise ProcessingError(f"{filename} does not contain any readable pages.")
        return reader
    except ProcessingError:
        raise
    except Exception as exc:
        raise ProcessingError(f"{filename} could not be read. It may be damaged or use an unsupported PDF feature.") from exc

def pdf_bytes(writer: PdfWriter) -> bytes:
    stream = BytesIO()
    try:
        writer.write(stream)
    except Exception as exc:
        raise ProcessingError("The document could not be exported. Try another PDF or check whether it uses unsupported encryption.") from exc
    return stream.getvalue()

def parse_pages(spec: str, total: int) -> list[int]:
    """Parse 1-based pages and ranges: '1,3-5,8'."""
    value = (spec or "").strip().lower()
    if value in {"", "all", "*"}:
        return list(range(1, total + 1))
    result: list[int] = []
    for token in value.split(","):
        token = token.strip()
        match = re.fullmatch(r"(\d+)(?:\s*-\s*(\d+))?", token)
        if not match:
            raise ProcessingError(f"'{token}' is not a valid page number or range. Use a format such as 1,3-5,8.")
        start = int(match.group(1))
        end = int(match.group(2) or start)
        if start < 1 or end < 1 or start > total or end > total:
            raise ProcessingError(f"Page {max(start, end)} is outside the document, which has {total} pages.")
        step = 1 if start <= end else -1
        result.extend(range(start, end + step, step))
    if not result:
        raise ProcessingError("Enter at least one page number or range.")
    if len(set(result)) != len(result):
        raise ProcessingError("The page selection contains duplicate pages. Remove repeated page numbers and try again.")
    return result

def parse_groups(spec: str, total: int) -> list[list[int]]:
    value = (spec or "").strip()
    if not value:
        raise ProcessingError("Enter the page ranges to split, such as 1-3,4-6.")
    groups = [parse_pages(token, total) for token in value.split(",") if token.strip()]
    if not groups:
        raise ProcessingError("Enter at least one valid page range to split.")
    return groups

def new_writer_from_pages(reader: PdfReader, pages: Iterable[int]) -> PdfWriter:
    writer = PdfWriter()
    for number in pages:
        writer.add_page(reader.pages[number - 1])
    return writer

def _watermark_page(page, text: str):
    from pypdf import PdfReader as _PdfReader
    width = float(page.mediabox.width)
    height = float(page.mediabox.height)
    overlay_bytes = BytesIO()
    sheet = canvas.Canvas(overlay_bytes, pagesize=(width, height), pageCompression=1)
    sheet.saveState()
    sheet.translate(width / 2, height / 2)
    sheet.rotate(35)
    sheet.setFillColorRGB(0.67, 0.70, 0.75)
    font_size = max(16, min(36, width / max(len(text), 10)))
    sheet.setFont("Helvetica-Bold", font_size)
    sheet.drawCentredString(0, 0, text[:100])
    sheet.restoreState()
    sheet.save()
    overlay_bytes.seek(0)
    overlay_reader = _PdfReader(overlay_bytes)
    page.merge_page(overlay_reader.pages[0])

def process_tool(operation: str, files: list[tuple[str, bytes]], params: dict[str, str]) -> list[OutputArtifact]:
    if operation not in TOOL_MAP:
        raise ProcessingError("Choose a supported PDF tool.")
    if not files:
        raise ProcessingError("Choose at least one file before processing.")
    if not TOOL_MAP[operation].get("multi", False) and len(files) != 1:
        raise ProcessingError("This tool accepts one source file at a time.")
    stem = safe_stem(files[0][0])
    password = params.get("pdf_password", "")

    if operation == "images-to-pdf":
        if len(files) > 40:
            raise ProcessingError("Choose no more than 40 images per conversion.")
        images = []
        total_pixels = 0
        try:
            for name, data in files:
                if not re.search(r"\.(jpe?g|png)$", name, re.I):
                    raise ProcessingError(f"{name}: only JPG and PNG images are accepted.")
                with Image.open(BytesIO(data)) as image:
                    image.verify()
                with Image.open(BytesIO(data)) as image:
                    pixels = image.width * image.height
                    total_pixels += pixels
                    if pixels > 15_000_000:
                        raise ProcessingError(f"{name}: image dimensions exceed the 15-megapixel per-image limit.")
                    if total_pixels > 50_000_000:
                        raise ProcessingError("The selected images exceed the combined image-pixel limit. Convert fewer or smaller images at a time.")
                    images.append(image.convert("RGB"))
            if not images:
                raise ProcessingError("Choose at least one JPG or PNG image.")
            out = BytesIO()
            images[0].save(out, format="PDF", save_all=True, append_images=images[1:], resolution=150.0)
            return [OutputArtifact("images-converted.pdf", out.getvalue())]
        except ProcessingError:
            raise
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
            raise ProcessingError("One of the images could not be decoded safely. Use valid, reasonably sized JPG or PNG files.") from exc
        finally:
            for image in images:
                image.close()

    # Non-PDF document operations are isolated in a local-only module to keep the PDF engine focused.
    from .office_services import OFFICE_OPERATIONS, process_office_tool
    if operation in OFFICE_OPERATIONS:
        return process_office_tool(operation, files, params)

    if operation == "merge":
        if len(files) < 2:
            raise ProcessingError("Choose at least two PDFs to merge.")
        if len(files) > 30:
            raise ProcessingError("Merge is limited to 30 source files per operation.")
        writer = PdfWriter()
        combined_pages = 0
        for name, data in files:
            reader = open_pdf(data, name, password)
            combined_pages += len(reader.pages)
            if combined_pages > 10_000:
                raise ProcessingError("Merging these files would exceed the 10,000-page combined limit.")
            for page in reader.pages:
                writer.add_page(page)
        return [OutputArtifact("merged-document.pdf", pdf_bytes(writer))]

    filename, data = files[0]
    reader = open_pdf(data, filename, password)
    total = len(reader.pages)

    if operation == "split":
        mode = params.get("split_mode", "ranges")
        if mode == "each":
            groups = [[page] for page in range(1, total + 1)]
        elif mode == "fixed":
            try:
                size = int(params.get("pages_per_file", "5"))
            except ValueError as exc:
                raise ProcessingError("Pages per file must be a whole number.") from exc
            if size < 1 or size > 10_000:
                raise ProcessingError("Pages per file must be a whole number from 1 to 10,000.")
            groups = [list(range(start, min(start + size, total + 1))) for start in range(1, total + 1, size)]
        else:
            groups = parse_groups(params.get("ranges", ""), total)
        if len(groups) > 1000:
            raise ProcessingError("This split would create more than 1,000 output files. Choose larger ranges or batches.")
        artifacts = []
        for index, group in enumerate(groups, start=1):
            writer = new_writer_from_pages(reader, group)
            artifacts.append(OutputArtifact(f"{stem}-part-{index:02d}.pdf", pdf_bytes(writer)))
        return artifacts

    if operation == "extract":
        pages = parse_pages(params.get("pages", ""), total)
        return [OutputArtifact(f"{stem}-extracted.pdf", pdf_bytes(new_writer_from_pages(reader, pages)))]

    if operation == "remove":
        removed = set(parse_pages(params.get("pages", ""), total))
        remaining = [number for number in range(1, total + 1) if number not in removed]
        if not remaining:
            raise ProcessingError("You cannot remove every page. Keep at least one page in the output.")
        return [OutputArtifact(f"{stem}-pages-removed.pdf", pdf_bytes(new_writer_from_pages(reader, remaining)))]

    if operation == "reorder":
        pages = parse_pages(params.get("order", ""), total)
        if len(pages) != total or set(pages) != set(range(1, total + 1)):
            raise ProcessingError(f"The new order must include all {total} pages exactly once.")
        return [OutputArtifact(f"{stem}-reordered.pdf", pdf_bytes(new_writer_from_pages(reader, pages)))]

    if operation == "rotate":
        try:
            angle = int(params.get("angle", "90"))
        except ValueError as exc:
            raise ProcessingError("Choose a rotation of 90, 180, or 270 degrees.") from exc
        if angle not in {90, 180, 270}:
            raise ProcessingError("Choose a rotation of 90, 180, or 270 degrees.")
        pages = set(parse_pages(params.get("pages", "all"), total))
        writer = PdfWriter()
        for index, page in enumerate(reader.pages, start=1):
            if index in pages:
                page.rotate(angle)
            writer.add_page(page)
        return [OutputArtifact(f"{stem}-rotated.pdf", pdf_bytes(writer))]

    if operation == "watermark":
        text = (params.get("watermark", "") or "").strip()
        if not text or len(text) > 100:
            raise ProcessingError("Enter watermark text between 1 and 100 characters.")
        writer = PdfWriter()
        for page in reader.pages:
            _watermark_page(page, text)
            writer.add_page(page)
        return [OutputArtifact(f"{stem}-watermarked.pdf", pdf_bytes(writer))]

    if operation == "page-numbers":
        try:
            start = int(params.get("start_number", "1"))
        except ValueError as exc:
            raise ProcessingError("The starting page number must be a whole number.") from exc
        if not 0 <= start <= 999999:
            raise ProcessingError("The starting number must be between 0 and 999999.")
        writer = PdfWriter()
        for index, page in enumerate(reader.pages):
            width, height = float(page.mediabox.width), float(page.mediabox.height)
            overlay = BytesIO()
            sheet = canvas.Canvas(overlay, pagesize=(width, height), pageCompression=1)
            sheet.setFillColorRGB(0.25, 0.31, 0.40)
            sheet.setFont("Helvetica", 9)
            sheet.drawRightString(width - 28, 18, str(start + index))
            sheet.save()
            overlay.seek(0)
            page.merge_page(PdfReader(overlay).pages[0])
            writer.add_page(page)
        return [OutputArtifact(f"{stem}-numbered.pdf", pdf_bytes(writer))]

    if operation == "optimize":
        writer = PdfWriter()
        for page in reader.pages:
            try:
                page.compress_content_streams()
            except Exception:
                # Some unusual streams cannot be rewritten; copying can still work.
                pass
            writer.add_page(page)
        return [OutputArtifact(f"{stem}-optimized.pdf", pdf_bytes(writer))]

    if operation == "protect":
        user_password = params.get("new_password", "")
        confirm = params.get("confirm_password", "")
        if len(user_password) < 8:
            raise ProcessingError("Use a password with at least 8 characters.")
        if user_password != confirm:
            raise ProcessingError("The new password and confirmation do not match.")
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        writer.encrypt(user_password=user_password, owner_password=(params.get("owner_password") or user_password))
        return [OutputArtifact(f"{stem}-protected.pdf", pdf_bytes(writer))]

    if operation == "unlock":
        # open_pdf already checks and decrypts using the supplied current password.
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        return [OutputArtifact(f"{stem}-unlocked.pdf", pdf_bytes(writer))]

    raise ProcessingError("This operation is not available yet.")

def outputs_as_zip(artifacts: list[OutputArtifact]) -> bytes:
    stream = BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        used: set[str] = set()
        for artifact in artifacts:
            filename = artifact.name
            if filename in used:
                path = Path(filename)
                root, ext = path.stem, path.suffix
                counter = 2
                while f"{root}-{counter}{ext}" in used:
                    counter += 1
                filename = f"{root}-{counter}{ext}"
            used.add(filename)
            archive.writestr(filename, artifact.content)
    return stream.getvalue()
