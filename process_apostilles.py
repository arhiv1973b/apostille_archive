#!/usr/bin/env python3
"""
Автоматическая обработка PDF-документов из реестра апостилей
- Скачивание/использование существующих PDF
- Разделение на страницы
- Конвертация в изображения
- OCR (Tesseract: русский + румынский)
- Вычисление SHA256
- Формирование JSON-отчёта
"""

import os
import sys
import json
import hashlib
import subprocess
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

try:
    from PyPDF2 import PdfReader, PdfWriter
except ImportError:
    print("Installing PyPDF2...")
    subprocess.run([sys.executable, "-m", "pip", "install", "PyPDF2"], check=True)
    from PyPDF2 import PdfReader, PdfWriter

try:
    from pdf2image import convert_from_path
except ImportError:
    print("Installing pdf2image...")
    subprocess.run([sys.executable, "-m", "pip", "install", "pdf2image"], check=True)
    from pdf2image import convert_from_path

try:
    import pytesseract
except ImportError:
    print("Installing pytesseract...")
    subprocess.run([sys.executable, "-m", "pip", "install", "pytesseract"], check=True)
    import pytesseract

from PIL import Image, ImageEnhance, ImageFilter


BASE_DIR = Path(r"C:\apostille_archive")
REGISTRY_PDF = Path(
    r"C:\Users\arhiv\OneDrive\Документы\ViberDownloads\apostille_registry_working.signed.pdf"
)

EXISTING_PDFS = [
    Path(r"C:\Users\arhiv\11_verification_results"),
    Path(r"C:\Users\arhiv\11_audited_apostilles"),
    Path(r"C:\Users\arhiv\02_analysis\final_apostille_demo\downloaded_apostilles"),
]

LANGUAGES = "rus+ron"
DPI = 300


def extract_ids_from_registry(registry_pdf: Path) -> List[str]:
    """Извлечение ID апостилей из реестра PDF"""
    print(f"[*] Extracting IDs from registry: {registry_pdf}")

    result = subprocess.run(
        ["pdftotext", str(registry_pdf), "-"],
        capture_output=True,
        text=True,
        check=True,
    )

    text = result.stdout

    id_pattern = re.compile(r"([A-Z0-9]{12,})")
    found_ids = id_pattern.findall(text)

    unique_ids = []
    seen = set()
    for id_val in found_ids:
        if id_val not in seen and len(id_val) >= 10:
            seen.add(id_val)
            unique_ids.append(id_val)

    print(f"    Found {len(unique_ids)} unique IDs")
    return unique_ids


def find_existing_pdf(apostille_id: str) -> Optional[Path]:
    """Поиск существующего PDF по ID"""
    for base_dir in EXISTING_PDFS:
        if not base_dir.exists():
            continue
        for pdf_file in base_dir.glob("*.pdf"):
            if apostille_id.lower() in pdf_file.name.lower():
                return pdf_file
    return None


def compute_sha256(file_path: Path) -> str:
    """Вычисление SHA256 хеша файла"""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def split_pdf(pdf_path: Path, output_dir: Path) -> List[Path]:
    """Разделение PDF на отдельные страницы"""
    output_dir.mkdir(parents=True, exist_ok=True)

    reader = PdfReader(str(pdf_path))
    base_name = pdf_path.stem

    output_files = []
    for i, page in enumerate(reader.pages, 1):
        writer = PdfWriter()
        writer.add_page(page)

        output_file = output_dir / f"{base_name}_page_{i:03d}.pdf"
        with open(output_file, "wb") as f:
            writer.write(f)

        output_files.append(output_file)

    return output_files


def convert_pdf_to_images(
    pdf_path: Path, output_dir: Path, dpi: int = DPI
) -> List[Path]:
    """Конвертация PDF страниц в изображения"""
    output_dir.mkdir(parents=True, exist_ok=True)

    base_name = pdf_path.stem

    try:
        images = convert_from_path(
            str(pdf_path), dpi=dpi, fmt="png", first_page=1, last_page=1
        )
    except Exception as e:
        print(f"    [!] PDF conversion failed: {e}")
        return []

    if not images:
        print(f"    [!] No images generated from {pdf_path}")
        return []

    output_files = []
    for i, image in enumerate(images, 1):
        output_file = output_dir / f"{base_name}.png"
        image.save(str(output_file), "PNG")
        output_files.append(output_file)

    return output_files


def preprocess_image(image_path: Path) -> Path:
    """Предобработка изображения для улучшения OCR"""
    try:
        img = Image.open(image_path)

        if img.mode != "L":
            img = img.convert("L")

        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.5)

        output_path = image_path.parent / f"{image_path.stem}_processed.png"
        img.save(str(output_path), "PNG")

        return output_path
    except Exception as e:
        print(f"    [!] Preprocess error: {e}")
        return image_path


def run_ocr(image_path: Path, languages: str = LANGUAGES) -> str:
    """Запуск OCR на изображении"""
    processed_path = preprocess_image(image_path)

    try:
        text = pytesseract.image_to_string(
            str(processed_path), lang=languages, config="--psm 6"
        )
    except Exception as e:
        print(f"    [!] OCR Error: {e}")
        text = ""

    if str(processed_path) != str(image_path):
        try:
            processed_path.unlink()
        except:
            pass

    return text.strip()


def process_apostille(apostille_id: str, pdf_path: Path, base_dir: Path) -> Dict:
    """Обработка одного апостиля"""
    print(f"[*] Processing: {apostille_id}")

    result = {
        "apostille_id": apostille_id,
        "source_pdf": str(pdf_path),
        "processing_date": datetime.now().isoformat(),
        "pages": [],
        "full_text": "",
        "sha256": {},
    }

    pdf_dir = base_dir / apostille_id
    pages_dir = pdf_dir / "pages"
    images_dir = pdf_dir / "images"
    ocr_dir = pdf_dir / "ocr_texts"

    pdf_dir.mkdir(parents=True, exist_ok=True)

    result["sha256"]["pdf"] = compute_sha256(pdf_path)

    page_pdfs = split_pdf(pdf_path, pages_dir)

    for page_pdf in page_pdfs:
        page_num = int(re.search(r"_page_(\d+)\.pdf$", page_pdf.name).group(1))

        if page_num == 1:
            continue

        page_result = {
            "page_number": page_num,
            "pdf_file": str(page_pdf),
            "sha256": compute_sha256(page_pdf),
        }

        images = convert_pdf_to_images(page_pdf, images_dir)

        if not images:
            print(f"    [!] No images from page {page_num}")
            continue

        for img in images:
            ocr_file = ocr_dir / f"{img.stem}.txt"
            ocr_dir.mkdir(parents=True, exist_ok=True)

            text = run_ocr(img)

            with open(ocr_file, "w", encoding="utf-8") as f:
                f.write(text)

            page_result["ocr_file"] = str(ocr_file)
            page_result["text_length"] = len(text)

            if result["full_text"]:
                result["full_text"] += "\n\n"
            result["full_text"] += text

        result["pages"].append(page_result)

    return result


def generate_report(results: List[Dict], output_file: Path):
    """Генерация JSON-отчёта"""
    report = {
        "generated_at": datetime.now().isoformat(),
        "total_documents": len(results),
        "documents": results,
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n[+] Report saved to: {output_file}")


def main():
    print("=" * 60)
    print("Apostille Registry PDF Processing Pipeline")
    print("=" * 60)

    BASE_DIR.mkdir(parents=True, exist_ok=True)

    if not REGISTRY_PDF.exists():
        print(f"[!] Registry PDF not found: {REGISTRY_PDF}")
        print("[*] Scanning existing directories for PDFs...")

        all_pdfs = []
        for base_dir in EXISTING_PDFS:
            if base_dir.exists():
                all_pdfs.extend(list(base_dir.glob("*.pdf")))

        print(f"    Found {len(all_pdfs)} existing PDFs")

        results = []
        for pdf_path in all_pdfs[:10]:
            try:
                apostille_id = pdf_path.stem.replace("apostille_", "").split("_")[0]

                pdf_dir = BASE_DIR / apostille_id
                result = process_apostille(apostille_id, pdf_path, BASE_DIR)
                results.append(result)
            except Exception as e:
                print(f"    [!] Error processing {pdf_path}: {e}")

        if results:
            generate_report(results, BASE_DIR / "report.json")
        return

    apostille_ids = extract_ids_from_registry(REGISTRY_PDF)

    results = []
    processed = 0
    skipped = 0

    for apostille_id in apostille_ids:
        pdf_path = find_existing_pdf(apostille_id)

        if not pdf_path:
            print(f"[?] PDF not found for: {apostille_id}")
            skipped += 1
            continue

        try:
            result = process_apostille(apostille_id, pdf_path, BASE_DIR)
            results.append(result)
            processed += 1

            print(f"    ✓ Processed: {apostille_id} ({len(result['pages'])} pages OCR)")

        except Exception as e:
            print(f"    [!] Error: {e}")
            skipped += 1

    print(f"\n{'=' * 60}")
    print(f"Processing complete: {processed} processed, {skipped} skipped")
    print(f"{'=' * 60}")

    if results:
        generate_report(results, BASE_DIR / "report.json")


if __name__ == "__main__":
    main()
