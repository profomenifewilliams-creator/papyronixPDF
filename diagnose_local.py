"""Report which local Papyronix engines are available; never contacts a remote service."""
from __future__ import annotations

import importlib.util
import shutil
import sys

PYTHON_MODULES = {
    "Django": "django",
    "pypdf": "pypdf",
    "Pillow": "PIL",
    "python-docx": "docx",
    "openpyxl": "openpyxl",
    "python-pptx": "pptx",
    "pypdfium2 (PDF rendering)": "pypdfium2",
    "pytesseract (OCR wrapper)": "pytesseract",
}


def main() -> int:
    print("Papyronix local engine diagnostics")
    print("No network requests or AI API calls are made by this script.\n")
    print(f"Python: {sys.version.split()[0]}")
    missing = []
    for label, module_name in PYTHON_MODULES.items():
        installed = importlib.util.find_spec(module_name) is not None
        print(f"{'OK      ' if installed else 'MISSING '} Python package: {label}")
        if not installed:
            missing.append(label)
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    tesseract = shutil.which("tesseract")
    print(f"{'OK      ' if soffice else 'OPTIONAL'} Local Office renderer: {soffice or 'not found (Office-to-PDF tools will show a setup message)'}")
    print(f"{'OK      ' if tesseract else 'OPTIONAL'} Local OCR engine: {tesseract or 'not found (OCR tools will show a setup message)'}")
    print("\nNo API keys or tokens are required for these engines.")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
