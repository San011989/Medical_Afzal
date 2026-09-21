# Medical Custom Tailoring Portal

A FastAPI and Streamlit application for storing body measurements, processing OCR/PDF/image uploads, searching measurement records with ChromaDB, viewing analytics, and downloading filtered dashboard data.

## Features

- Authentication with JWT tokens.
- Manual measurement entry.
- OCR processing for PDF, PNG, JPG, and JPEG files.
- ChromaDB persistence and semantic record search.
- Duplicate record suppression in search and analytics views.
- Analytics for chest, waist, hips, shoulder, arm length, and inseam.
- Doctor name/ID filtering in Analytics.
- CSV and JSON downloads for filtered analytics data.
- Uploaded diagram/image storage and display from search results or Analytics.

## Project Structure

```text
app.py                 Streamlit frontend
main.py                FastAPI backend
auth.py                Authentication helpers
database.py            Legacy database helper
ocr_service.py         OCR helper functions
requirements.txt       Python dependencies
test_ocr_endpoint.py   OCR API test script
chroma_db/             Persistent ChromaDB data
uploads/               Stored uploaded images, created automatically
```

## Requirements

- Python 3.10 or newer.
- An OpenAI API key for embeddings and OCR-to-JSON parsing.
- Tesseract OCR for image text extraction.
- Windows users can install Tesseract from:
  `https://github.com/UB-Mannheim/tesseract/wiki`

The backend checks this Windows path automatically:

```text
C:\Program Files\Tesseract-OCR\tesseract.exe
```

## Setup

Create and activate a virtual environment, then install dependencies:

```powershell
uv venv
.\.venv\Scripts\Activate.ps1
uv pip install -r requirements.txt
```

Alternatively:

```powershell
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```env
OPENAI_API_KEY=your_openai_api_key
JWT_SECRET_KEY=replace_with_a_long_random_secret
```

`OPENAI_API_KEY` is required. `JWT_SECRET_KEY` is optional, but should be set in non-development environments.

## Run the Application

Start the FastAPI backend in one terminal:

```powershell
uv run uvicorn main:app --reload --port 8000
```

Start the Streamlit frontend in another terminal:

```powershell
uv run streamlit run app.py
```

Open the Streamlit URL shown in the terminal, normally:

```text
http://localhost:8501
```

The FastAPI documentation is available at:

```text
http://127.0.0.1:8000/docs
```

## Login

Default development account:

```text
Username: admin@medical.com
Password: admin123
```

Change the authentication implementation before deploying this application publicly.

## API Endpoints

All measurement endpoints require a bearer token obtained from `/token`.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/token` | Authenticate and receive a JWT token |
| `POST` | `/api/v1/measurements/manual` | Save manual measurements |
| `POST` | `/api/v1/measurements/upload` | OCR an uploaded document/image and save the record |
| `POST` | `/api/v1/measurements/query` | Search measurement records |
| `GET` | `/api/v1/measurements/analytics` | Return analytics and normalized records |
| `GET` | `/api/v1/measurements/{record_id}/image` | Retrieve a stored uploaded image |

## Data Storage

- ChromaDB data is stored in `chroma_db/`.
- Uploaded files are stored in `uploads/` and linked to their record IDs.
- The active Chroma collection is `doctor_measurements_openai`.
- Existing records created before image storage was added do not have linked images.

## OCR and Body Diagrams

Uploaded images are displayed in the upload screen and stored after processing. OCR extracts readable labels and numbers, but the application does not automatically measure body distances from the shape of a drawn body diagram. Diagram display and text extraction are supported separately.

## Testing

Run a syntax check:

```powershell
python -m py_compile app.py main.py
```

The OCR endpoint test requires the backend to be running:

```powershell
python test_ocr_endpoint.py
```

## Notes

- Start the FastAPI backend before using the Streamlit frontend.
- If semantic embeddings are unavailable, search falls back to matching terms in stored documents.
- Do not commit `.env`, API keys, or sensitive uploaded files to source control.
