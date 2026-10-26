# Papyronix local build verification report

## Checks completed in this packaging environment

- Python syntax compilation passed for the project source files.
- **51 unit tests passed** when run directly with Python's `unittest` runner: page-range validation; PDF merge/split/extract/remove/reorder/rotate/watermark/page-number/optimization/password/image conversion; PDF-to-text/Word/image conversion; Word text replacement, cleanup, comparison, CSV mail merge, Word-to-Markdown, embedded-image extraction, Markdown-to-Word formatting, table export, page-number fields and metadata cleanup; text-to-PDF; CSV cleaning/filtering; XLSX sorting/splitting/comparison and XLSX-to-Word export; PowerPoint text export; ZIP packaging; and document-template generation with validation and invoice arithmetic checks.
- The earlier manual smoke-test script passed 23 direct engine checks, including template-based document generation, locally installed LibreOffice conversions for DOCX/XLSX/PPTX and Tesseract OCR. In this expansion pass, 7 additional integration smoke checks passed for the 45-tool registry, local Office-to-PDF conversions, Tesseract image OCR, mail-merge ZIP packaging and extractable text-to-PDF output. These checks exercise local processing functions, not the full Django request/render stack.
- The app now exposes **45 file-processing tools** plus a separate template-based Document Builder for six common document types. The added workflows include Word mail merge from CSV, Word-version comparison, Word-to-Markdown export, embedded-image extraction, Markdown-to-Word formatting, Word-table export, dynamic Word page numbers, metadata cleanup, text-to-PDF, workbook-to-Word export, worksheet splitting, spreadsheet sorting/comparison, and CSV cleaning/filtering. The updated Python package requirements include pypdfium2 for local PDF rendering and pytesseract as a wrapper for an installed Tesseract binary. No AI API client or token dependency was added. The new Office processing features use the Python libraries already present in the dependency list.
- Local Bootstrap assets and Tailwind utility CSS remain bundled in the project.

## Checks not completed in this environment

The packaging environment does not have Django installed, and the earlier package-install attempt could not reach the package index. Therefore **Django `manage.py check`, database migrations, Django view/template rendering, and Django's test command have not been executed here**. The underlying direct unit tests ran, but they do not prove the complete website's request/view integration.

After installing dependencies on your computer, run the following from the project directory:

```bash
python manage.py migrate
python manage.py check
python manage.py test
python diagnose_local.py
```

The Office-to-PDF and OCR features require the local `soffice`/`libreoffice` and `tesseract` command-line programs respectively. The optional Docker build includes these binaries; native installations must install them separately.

This is not a claim of a full production security, accessibility, browser-compatibility or load test. Review output files before using them as official, legal, financial or publication-ready documents.

## Render deployment preparation (October 27, 2026)

- Added `render.yaml` for the Render Blueprint, with a Docker web service in Frankfurt, PostgreSQL, a persistent 1 GB media/data disk, generated Django secret, HTTPS-aware security settings, and `/health/` health checks.
- Updated Django settings to read `DATABASE_URL`, use Render's service hostname in `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`, trust Render's HTTPS proxy header, and fail fast if a non-debug deployment has no secret key.
- Updated the Docker image to collect static files at build time, run migrations on startup, bind to Render's `PORT`, and retain local LibreOffice/Tesseract engines.
- `render.yaml` parsed successfully as YAML; Python `compileall` passed for the source code; source scan found no AI API endpoints/CDN dependencies in templates or static files.
- The local package installer cannot reach PyPI from this environment, so the added `dj-database-url` and `psycopg[binary]` packages could not be installed here. `docker` is also unavailable in this environment. Thus, an image build, real Django `manage.py check`, migrations against PostgreSQL, and hosted health check remain unverified.
- **Deployment status: NOT YET DEPLOYED.** This connected Render account requires an explicit workspace selection before resource changes. The only returned workspace is `My Workspace`. A new Git repository is also needed as Render's deploy source; the available GitHub connection can access existing repositories but does not expose repository creation. No existing repository was repurposed and no Render resources were created without the required confirmation/source repository.

The Render Blueprint intentionally selects paid resources because Render free web services cannot attach a persistent disk and free PostgreSQL databases expire after 30 days. Review charges in Render before applying the Blueprint.


## Repackaging note (October 27, 2026)

- Added `START_HERE.txt` with beginner-friendly install and run steps.
- Updated Render Blueprint plan identifiers to the current documented IDs (`256mb` for PostgreSQL and `0.5c-512mb` for the web service).
- Re-ran the pure Python document engine test suite during repackaging: 51 tests passed.
- Re-ran Python syntax compilation and ZIP/YAML integrity checks. The Django request/runtime integration remains unverified in this environment.
