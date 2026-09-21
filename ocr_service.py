# ocr_service.py
import fitz  # PyMuPDF
from PIL import Image
import pytesseract
import json

def extract_text_from_file(file_bytes: bytes, filename: str) -> str:
    """Extract raw text from PDF or Image formats."""
    if filename.endswith(".pdf"):
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text()
        return text
    else:
        image = Image.open(io.BytesIO(file_bytes))
        return pytesseract.image_to_string(image)

def parse_measurements_with_llm(raw_text: str, client) -> dict:
    """Passes OCR raw text to LLM to standardize measurement key-values."""
    prompt = f"""
    Extract body measurement values from the following text captured from a doctor logbook.
    Return JSON ONLY matching these keys: doctor_id, patient_id, chest, waist, hips, shoulder, arm_length, inseam, notes.
    Text:
    {raw_text}
    """
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)