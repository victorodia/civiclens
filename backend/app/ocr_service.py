import asyncio
import io
import logging
import os
import re
import shutil
from typing import Dict

import pytesseract
from PIL import Image, ImageEnhance, ImageOps

# Resolve the Tesseract binary portably:
#   1. TESSERACT_CMD env override (explicit wins)
#   2. whatever is on PATH (Linux container: /usr/bin/tesseract)
#   3. well-known Windows install location (dev machines)
# The old code hardcoded the Windows path, so on the server every OCR call
# crashed into the error branch and "AI verification" silently did nothing.
_tess = (
    os.environ.get("TESSERACT_CMD")
    or shutil.which("tesseract")
    or r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)
pytesseract.pytesseract.tesseract_cmd = _tess

logger = logging.getLogger(__name__)


async def extract_votes_from_image(image_bytes: bytes) -> Dict[str, any]:
    """
    Extracts vote tallies for Party A, B, and C from a Form EC8A image scan.
    Uses Tesseract OCR with specific pre-processing for handwritten numbers.
    Runs in a thread: OCR is CPU-heavy and must not block the event loop.
    """
    return await asyncio.to_thread(_extract_votes_sync, image_bytes)


def _extract_votes_sync(image_bytes: bytes) -> Dict[str, any]:
    try:
        # Load image from bytes
        img = Image.open(io.BytesIO(image_bytes))

        # Cap resolution before anything else: Tesseract gains nothing on form
        # scans beyond ~1600px, and full-size phone photos (12MP+) are what
        # OOM-killed a worker on this 1GB VM.
        img.thumbnail((1600, 1600), Image.LANCZOS)

        # 1. PRE-PROCESSING FOR OCR
        # Convert to grayscale
        img = ImageOps.grayscale(img)

        # Increase contrast to make handwritten marks pop
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2.5)

        # 2. OCR CONFIGURATION
        # --psm 11: Sparse text. Finds as much text as possible in no particular order.
        # --oem 3: Default, based on what is available.
        # -c tessedit_char_whitelist=0123456789: Restrict output to digits only.
        custom_config = r"--oem 3 --psm 11 -c tessedit_char_whitelist=0123456789"

        # Execute OCR and get structured data including confidence
        data = pytesseract.image_to_data(img, config=custom_config, output_type=pytesseract.Output.DICT)

        # Filter findings
        found_numbers = []
        confidences = []

        for i in range(len(data["text"])):
            text = data["text"][i].strip()
            try:
                conf = float(data["conf"][i])
            except (ValueError, TypeError):
                continue

            # Only consider numbers with a minimum confidence
            if text.isdigit() and conf > 30:
                found_numbers.append(int(text))
                confidences.append(conf)

        # 3. HEURISTIC MAPPING (MVP Version)
        # In a production app, we would use template matching to find exact coordinates
        # for Party A, Party B, and Party C boxes.
        # For now, we take the top 3 high-confidence numbers found.

        results = {
            "party_a": found_numbers[0] if len(found_numbers) > 0 else 0,
            "party_b": found_numbers[1] if len(found_numbers) > 1 else 0,
            "party_c": found_numbers[2] if len(found_numbers) > 2 else 0,
            "total_extracted": len(found_numbers),
            "avg_confidence": round(sum(confidences) / len(confidences), 2) if confidences else 0.0,
            "status": "success" if len(found_numbers) >= 2 else "partial_failure",
        }

        logger.info(f"[OCR] Analysis Complete: {results}")
        return results

    except Exception as e:
        logger.error(f"[OCR] Analysis Failed: {str(e)}")
        return {
            "party_a": 0,
            "party_b": 0,
            "party_c": 0,
            "avg_confidence": 0.0,
            "status": "error",
            "error": str(e),
        }
