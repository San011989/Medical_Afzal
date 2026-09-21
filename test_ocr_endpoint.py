import io
import os
import requests
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

load_dotenv()

# ------------------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------------------
BASE_URL = "http://127.0.0.1:8000"
LOGIN_URL = f"{BASE_URL}/token"
UPLOAD_URL = f"{BASE_URL}/api/v1/measurements/upload"

USERNAME = os.getenv("AUTH_USERNAME")
PASSWORD = os.getenv("AUTH_PASSWORD")

# ------------------------------------------------------------------------------
# HELPER: CREATE A SAMPLE IMAGE IN MEMORY
# ------------------------------------------------------------------------------
def create_sample_measurement_image() -> bytes:
    """Generates a simple image containing dummy body measurement text in memory."""
    img = Image.new("RGB", (500, 300), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    # Text to mimic handwritten or printed doctor logbook measurements
    text_content = (
        "DOCTOR LOGBOOK RECORD\n"
        "Patient ID: P-9921\n"
        "Doctor ID: DOC-104\n"
        "Chest: 42.5 in\n"
        "Waist: 34.0 in\n"
        "Shoulder: 18.5 in\n"
        "Hips: 38.0 in\n"
        "Notes: Broad shoulder adjustment needed."
    )
    
    draw.text((20, 20), text_content, fill=(0, 0, 0))
    
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format="PNG")
    img_byte_arr.seek(0)
    return img_byte_arr.getvalue()

# ------------------------------------------------------------------------------
# MAIN EXECUTION FLOW
# ------------------------------------------------------------------------------
def main():
    session = requests.Session()

    # Step 1: Authenticate and retrieve JWT Token
    print("1. Attempting login...")
    login_data = {
        "username": USERNAME,
        "password": PASSWORD
    }
    
    try:
        response = session.post(LOGIN_URL, data=login_data)
        response.raise_for_status()
        token_info = response.json()
        access_token = token_info.get("access_token")
        print("   [SUCCESS] Logged in successfully!")
        print(f"   Token: {access_token[:20]}...\n")
    except requests.exceptions.RequestException as e:
        print(f"   [ERROR] Login failed: {e}")
        if response is not None and response.text:
            print(f"   Details: {response.text}")
        return

    # Step 2: Set Authorization Header
    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    # Step 3: Generate and upload image to OCR endpoint
    print("2. Generating sample image and uploading to OCR endpoint...")
    image_bytes = create_sample_measurement_image()
    
    files = {
        "file": ("test_measurement.png", image_bytes, "image/png")
    }

    try:
        upload_response = session.post(UPLOAD_URL, headers=headers, files=files)
        upload_response.raise_for_status()
        
        result = upload_response.json()
        print("   [SUCCESS] OCR processing and ChromaDB storage complete!\n")
        print("--- Response Details ---")
        print(f"Record ID          : {result.get('record_id')}")
        print(f"Extracted Raw Text :\n{result.get('extracted_raw_text')}")
        print(f"Parsed JSON Data   :\n{result.get('parsed_data')}")
        
    except requests.exceptions.RequestException as e:
        print(f"   [ERROR] Upload failed: {e}")
        if upload_response is not None and upload_response.text:
            print(f"   Details: {upload_response.text}")

if __name__ == "__main__":
    main()