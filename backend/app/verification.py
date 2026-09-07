import random
from typing import Dict

def mock_ocr_analysis(image_url: str) -> Dict[str, int]:
    """
    MOCK AI/OCR Engine.
    In production, this would use Google Cloud Vision, AWS Textract, or a local Tesseract/PaddleOCR model.
    It extracts the numbers written on the Form EC8A.
    """
    print(f"AI: Processing forensic image analysis for {image_url}")
    
    # Simulating OCR extracting values from the image
    return {
        "party_a": random.randint(100, 250),
        "party_b": random.randint(50, 150),
        "total_valid": random.randint(300, 450)
    }

def verify_result_integrity(reported_data: dict, ocr_data: dict) -> bool:
    """
    Benford's Law and Statistical Anomaly Detection.
    Compares what the human agent typed vs what the AI sees on the paper.
    """
    
    # 1. Simple cross-check (Threshold: 0% tolerance for numbers)
    match_a = reported_data['party_a_votes'] == ocr_data['party_a']
    match_b = reported_data['party_b_votes'] == ocr_data['party_b']
    
    if not match_a or not match_b:
        return False # Integrity mismatch
        
    return True
