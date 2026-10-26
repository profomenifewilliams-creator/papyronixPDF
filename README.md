# Papyronix AI — independent, local-first Django Document Studio

Papyronix is a self-managed document-processing application built with Python, Django, HTML/CSS, locally bundled Bootstrap and prefixed Tailwind utilities. Run it on your own computer or host it on infrastructure you control. It is **not built on Floot**, does not require a hosted app builder, and does not make AI API calls or require AI tokens.

The processing engine uses conventional file-format libraries. A few optional capabilities invoke **locally installed** LibreOffice or Tesseract programs; they process the document on the same computer/server, rather than sending it to a conversion API.

## Capabilities

The Document Studio now exposes **45 processing tools**, in addition to the template-based Document Builder. The processing pipeline is deterministic file-format software; it does not use an AI model, API token, hosted AI provider or third-party document API.

### PDF tools
- Merge PDFs in selected order; split by ranges, fixed-size batches or one page per output.
- Extract, remove and reorder pages; rotate selected pages.
- Add a text watermark or page numbering.
- Re-save a PDF and compress eligible page-content streams. This does not downsample images or guarantee a smaller file.
- Add password encryption or remove encryption when the current password is known.
- Convert JPG/PNG images to PDF.
- Extract selectable PDF text to TXT or an editable Word document.
- Render PDF pages to PNG at selectable DPI, and select individual pages for export.
- Create searchable PDFs from scans using local Tesseract OCR (requires Tesseract installed).

### Word and document tools
- Convert DOCX to PDF using local LibreOffice.
- Extract text, tables and common headers/footers from DOCX, export common Word structure to Markdown, or extract embedded image assets.
- Find and replace text across Word paragraphs, tables, headers and footers.
- Compare two Word versions with a local change report.
- Run deterministic mail merge: fill `{{ColumnName}}` placeholders in a DOCX template using CSV rows, creating up to 200 separate Word files in one run.
- Export all top-level Word tables to a formatted Excel workbook.
- Add dynamic page-number fields to Word section footers.
- Clear common author/title/core document metadata in a copy; this does not scrub all comments, revisions or hidden data.
- Normalize excess spaces and remove empty body paragraphs from DOCX.
- Convert TXT/Markdown files into editable DOCX or paginated PDF. DOCX creation interprets basic Markdown headings, emphasis, lists, quotes and simple tables locally.
- Build a word/character/line count report for PDF, DOCX, PPTX, TXT, Markdown and CSV files.
- Convert PDF selectable text to DOCX, with important limitations: it makes the text editable but does not recreate the PDF's exact page design, columns, fonts, or embedded images. Scanned PDFs must be OCRed first.

### Spreadsheet tools
- Export all worksheets of an XLSX workbook to CSV (multiple sheets are returned in a ZIP).
- Import CSV into XLSX and freeze the first row and enable filters. Values are kept as text to preserve identifiers/leading zeros and CSV cells starting with `=` are not imported as formulas.
- Remove completely blank rows and exact duplicate rows across all worksheets.
- Clean CSV records by trimming whitespace and removing blank/duplicate rows, or filter CSV rows by a named column. CSV cleaning/filtering prefixes obvious formula-like strings with an apostrophe to reduce spreadsheet formula-injection risk.
- Sort an XLSX worksheet by a column header in ascending/descending order.
- Compare two XLSX workbooks cell by cell and export a change report, including added and removed values.
- Split each worksheet into its own XLSX file or combine sheets from multiple workbooks. Split output preserves cell values/formulas and basic formatting; charts, macros, pivots and external links are not guaranteed to transfer.
- Convert XLSX workbook sheets into editable Word tables or PDF using local LibreOffice.

### PowerPoint tools
- Export PPTX to PDF using local LibreOffice.
- Extract slide titles/text boxes and table values to TXT.
- Create a Word outline from presentation headings and text. This is an editable outline, not an exact slide-layout reproduction.

### Template-based Document Builder (no generative AI)

The separate **Document Builder** creates editable DOCX files from structured forms for business letters, project/business reports, meeting minutes, CVs/resumes, invoices and project proposals. It automatically applies headings, section order, tables, bullet lists, page numbers and consistent typography. Invoice line amounts and totals are calculated locally from the quantity and unit price fields. Choose Word output or PDF output through local LibreOffice.

The builder formats the information you supply; it does not invent facts, write text using a language model, require AI tokens, or send your content to a generation service. It is intended to remove the repetitive work of setting up common documents, not to replace subject-matter review or provide legal, medical, accounting or other professional advice.

### Local OCR and privacy
- Extract text from supported image files using local Tesseract OCR.
- OCR PDF pages into a searchable PDF using local rendering and Tesseract.
- The app's optional document assistant performs local lexical retrieval over extracted text. It is not a generative AI model and does not make AI API calls.
- Files sent to a processing tool are handled by the Django server running the app. Processing uploads are not saved by default; logged-in users' explicit library uploads are retained in the configured local media directory. Processing history stores metadata, not the file payload.

## Local-only programs needed for some features

The ordinary PDF, Word text replacement, spreadsheet and PowerPoint text tools use Python packages installed from `requirements.txt` and work without an AI API or a running network service.

- **Office-to-PDF:** install LibreOffice locally and make sure `soffice` (or `libreoffice`) can be found on `PATH`. This is needed for Word-to-PDF, Excel-to-PDF and PowerPoint-to-PDF. The converter runs headlessly with a temporary local profile.
- **OCR:** install the Tesseract OCR engine and the language data you intend to use. Make sure `tesseract` is on `PATH`. English uses language code `eng`; other codes work only when their language data is installed. `pytesseract` is a Python wrapper, not the OCR executable itself.

The application checks for these local programs and displays a clear error if one is absent. No cloud conversion or OCR service is called. Docker builds install LibreOffice and the English Tesseract language package in the container image.

## Requirements

- Python 3.12 or 3.13 recommended.
- Internet access once to install Python packages from `requirements.txt`. Ordinary processing can then run offline.
- Optional Node.js/npm only if you want to rebuild Tailwind CSS. The local stylesheet is included.
- Optional LibreOffice and Tesseract as described above for their specific features.

The project pins Django **6.1.2** in `requirements.txt` (the release selected for this project as of October 26, 2026). Check the official Django release and security page before a public production deployment: <https://www.djangoproject.com/download/>.

## Windows setup

1. Extract the project folder to a location such as `C:\Projects\papyronix_ai`.
2. Install Python and make sure `py` works in Command Prompt.
3. To enable Office-to-PDF and OCR, install LibreOffice and Tesseract separately and ensure their command-line executables are available on `PATH`.
4. Double-click `run_windows.bat`, or open a terminal in the project directory and run:

   ```powershell
   py -m venv .venv
   .venv\Scripts\activate
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   copy .env.example .env
   python manage.py migrate
   python manage.py check
   python manage.py runserver 127.0.0.1:8000
   ```

5. Open <http://127.0.0.1:8000>.
6. Create an account to use the document library, retrieval assistant and activity history. Use `python manage.py createsuperuser` for the Django admin account.

## macOS/Linux setup

```bash
./run_local.sh
```

Or run the setup commands inside the script manually. For Office-to-PDF or OCR, install LibreOffice and Tesseract using your operating system's package manager and confirm their command-line tools are on `PATH`.

## Optional Docker setup

Docker builds a local image that includes the Python dependencies, LibreOffice and Tesseract with English language data. The SQLite database and media files persist in `./data/`.

```bash
docker compose up --build
```

Open <http://127.0.0.1:8000>. Stop with `Ctrl+C` or `docker compose down`. Change `DJANGO_SECRET_KEY` and configure hosts/security settings before exposing the service publicly. Adding further Tesseract language packs requires installing their package inside the image.

## Data handling and limits

- Processing files are sent to the Django server running the app. When running locally, that is your own machine. When hosted elsewhere, files are processed by that server, so publish an accurate privacy notice.
- Explicit document library uploads are retained under the configured `media/` directory and indexed in SQLite. Back up both the database and media directory; document content should not be treated as automatically backed up.
- Default processing upload limit: 100 MiB combined (`PAPYRONIX_MAX_UPLOAD_BYTES`). The private library has a 25 MiB per-file limit.
- OCR is limited to 100 pages per PDF in one job. PDF image export is limited to 1,000 pages and applies pixel safety limits. Word/PDF text extraction is limited to 500 pages for PDF-to-Word.
- Conversion results may vary when source files contain uncommon fonts, embedded objects, advanced Excel features or layout-specific formatting. Keep the source file and review the exported result before relying on it.
- The PDF-to-Word converter extracts selectable text; it is not equivalent to a commercial layout-reconstruction converter.

## Tailwind rebuild (optional)

The application already includes local prefixed Tailwind utility CSS. To rebuild it from source:

```bash
npm install
npm run build:css
```

## Configuration for self-managed hosting

Copy `.env.example` to `.env` and set a strong `DJANGO_SECRET_KEY`. For a public deployment, set `DJANGO_DEBUG=False`, configure exact `DJANGO_ALLOWED_HOSTS`, serve over HTTPS, configure secure cookies/CSRF and HSTS, back up the database/media folder, run `collectstatic`, and use `requirements-deploy.txt` with Gunicorn or another suitable production server. Do not expose Django's development server to the public internet. Review quotas, upload sizes, concurrency, malware scanning and rate limits before accepting files from the wider public.

## Run checks

```bash
python manage.py check
python manage.py test
```

The source test suite covers the PDF engine and local document conversions. It does not replace a production security, browser-compatibility or load test. `python diagnose_local.py` checks which optional native programs are available on the current machine.

## Current limitations

Papyronix is an independent document-processing workspace, not a bit-for-bit replacement for the full Microsoft Office authoring applications. It does not yet implement PDF electronic signatures, irreversible/redaction-safe PDF redaction, PDF form editing, complex PDF layout reconstruction, XLSX pivot-table preservation, legacy `.doc`/`.xls`/`.ppt` files, cloud storage integrations or billing. Its document builder and mail merge are deterministic template systems, not generative AI. OCR quality depends on scan quality and installed Tesseract language data.

## Project layout

- `config/` — Django settings, URLs and WSGI/ASGI configuration.
- `workspace/services.py` — PDF engine and shared tool registry.
- `workspace/office_services.py` — offline Office, conversion, text and OCR logic.
- `workspace/document_builder.py` — structured Word document templates with local formatting and invoice arithmetic.
- `workspace/views.py` — pages, uploads, downloads, library, search and history.
- `workspace/tests.py` — PDF and document-engine unit tests.
- `templates/` — responsive HTML templates.
- `static/` — local CSS, JavaScript, Bootstrap and Tailwind assets.
- `diagnose_local.py` — optional native-engine and Python dependency readiness check.
- `media/` — local private document storage created at runtime.

## Deploy on Render (production configuration included)

The repository includes `render.yaml` and a production-ready Docker configuration for Render. The Blueprint uses PostgreSQL for account/history metadata and a persistent disk at `/var/data` for the local document library; LibreOffice and Tesseract are installed in the container for local conversions and OCR. It also configures the `/health/` endpoint, HTTPS proxy handling, CSRF trust for the Render hostname, and a generated Django secret.

**This production configuration is not a free-tier setup.** Render free web services cannot attach persistent disks, and free PostgreSQL databases expire after 30 days. The Blueprint deliberately selects paid resources so user files and the database do not silently disappear. Review the charges in Render before applying it. See Render's current guidance at <https://render.com/docs/deploy-django>, <https://render.com/docs/disks>, and <https://render.com/docs/free>.

To deploy: push this project to a Git repository accessible to Render, open the Render Dashboard, create a new Blueprint, select that repository and approve the services. After the deploy reaches Live, visit `/health/`, then create a superuser from Render Shell with `python manage.py createsuperuser`. The container's startup command runs migrations.

Set `DJANGO_CSRF_TRUSTED_ORIGINS` if you later add a custom domain. Do not make `media/` public: it stores private user library documents. Use a tested backup plan for both the PostgreSQL database and uploaded files.
