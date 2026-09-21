import io
import json
import os
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

import pymupdf as fitz  # PyMuPDF
import pytesseract
from PIL import Image
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from openai import OpenAI

import chromadb
from langchain_openai import OpenAIEmbeddings

if os.name == "nt":
    tesseract_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.exists(tesseract_path):
        pytesseract.pytesseract.tesseract_cmd = tesseract_path

# ------------------------------------------------------------------------------
# LOAD ENVIRONMENT VARIABLES FROM .ENV
# ------------------------------------------------------------------------------
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "fallback-secret-key-change-me")
AUTH_USERNAME = os.getenv("AUTH_USERNAME")
AUTH_PASSWORD = os.getenv("AUTH_PASSWORD")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "."))
CHROMA_DIR = STORAGE_DIR / "chroma_db"
UPLOAD_DIR = STORAGE_DIR / "uploads"
CHROMA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not found in .env file. Please check your configuration.")
if not AUTH_USERNAME or not AUTH_PASSWORD:
    raise ValueError("AUTH_USERNAME and AUTH_PASSWORD must be set in the environment.")

# Initialize OpenAI Client using the key from .env
client = OpenAI(api_key=OPENAI_API_KEY)

# ------------------------------------------------------------------------------
# CHROMADB & EMBEDDINGS SETUP
# ------------------------------------------------------------------------------
chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))


class LangChainEmbeddingFunction:
    def __init__(self, embeddings: OpenAIEmbeddings):
        self.embeddings = embeddings

    def name(self) -> str:
        return "langchain-text-embedding-3-small"

    def __call__(self, input: list[str]) -> list[list[float]]:
        return self.embeddings.embed_documents(input)


embed_fn = LangChainEmbeddingFunction(
    OpenAIEmbeddings(model="text-embedding-3-small")
)

collection = chroma_client.get_or_create_collection(
    name="doctor_measurements_openai",
    embedding_function=embed_fn
)

# ------------------------------------------------------------------------------
# SECURITY & AUTHENTICATION SETUP
# ------------------------------------------------------------------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

FAKE_USERS_DB = {
    AUTH_USERNAME: {
        "username": AUTH_USERNAME,
        "full_name": "Dr. Tailor Admin",
        "hashed_password": pwd_context.hash(AUTH_PASSWORD),
        "role": "admin"
    }
}

# ------------------------------------------------------------------------------
# SCHEMAS
# ------------------------------------------------------------------------------
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

class User(BaseModel):
    username: str
    full_name: Optional[str] = None
    role: str

class MeasurementInput(BaseModel):
    patient_id: str
    doctor_id: str
    chest: float
    waist: float
    hips: Optional[float] = 0.0
    shoulder: float
    arm_length: Optional[float] = 0.0
    inseam: Optional[float] = 0.0
    notes: Optional[str] = ""

class QueryRequest(BaseModel):
    query_text: str
    n_results: Optional[int] = 5

# ------------------------------------------------------------------------------
# HELPER FUNCTIONS
# ------------------------------------------------------------------------------
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception

    user_dict = FAKE_USERS_DB.get(token_data.username)
    if user_dict is None:
        raise credentials_exception
    return User(**user_dict)

def extract_raw_text(file_bytes: bytes, filename: str) -> str:
    if filename.lower().endswith(".pdf"):
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        text = "".join([page.get_text() for page in doc])
        return text
    else:
        image = Image.open(io.BytesIO(file_bytes))
        return pytesseract.image_to_string(image)

def parse_text_to_json(raw_text: str) -> dict:
    prompt = f"""
    Extract body measurement values from the raw text captured from a doctor logbook.
    Return JSON ONLY with these keys:
    - patient_id (str)
    - doctor_id (str)
    - chest (float, inches)
    - waist (float, inches)
    - hips (float, inches)
    - shoulder (float, inches)
    - arm_length (float, inches)
    - inseam (float, inches)
    - notes (str)

    Raw OCR Text:
    {raw_text}
    """
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)

def save_to_chromadb(data: dict, record_id: str):
    doc_text = (
        f"Patient ID: {data.get('patient_id', 'N/A')}. "
        f"Doctor ID: {data.get('doctor_id', 'N/A')}. "
        f"Chest: {data.get('chest', 0)} in, Waist: {data.get('waist', 0)} in, "
        f"Shoulder: {data.get('shoulder', 0)} in, Hips: {data.get('hips', 0)} in, "
        f"Arm: {data.get('arm_length', 0)} in, Inseam: {data.get('inseam', 0)} in. "
        f"Notes: {data.get('notes', '')}"
    )

    metadata = {
        "patient_id": str(data.get("patient_id", "")),
        "doctor_id": str(data.get("doctor_id", "")),
        "chest": float(data.get("chest", 0.0)),
        "waist": float(data.get("waist", 0.0)),
        "hips": float(data.get("hips", 0.0) or 0.0),
        "shoulder": float(data.get("shoulder", 0.0)),
        "arm_length": float(data.get("arm_length", 0.0) or 0.0),
        "inseam": float(data.get("inseam", 0.0) or 0.0),
        "notes": str(data.get("notes", "")),
        "image_file": str(data.get("image_file", "")),
        "created_at": datetime.utcnow().strftime("%Y-%m-%d")
    }

    collection.add(
        documents=[doc_text],
        metadatas=[metadata],
        ids=[record_id]
    )


def unique_records(records: dict) -> list[dict]:
    unique = {}
    for index, record_id in enumerate(records.get("ids", [])):
        metadata = records.get("metadatas", [])[index] or {}
        document = records.get("documents", [])[index] or ""
        fingerprint = json.dumps(
            {
                "patient_id": metadata.get("patient_id"),
                "doctor_id": metadata.get("doctor_id"),
                "document": document,
            },
            sort_keys=True,
        )
        unique.setdefault(fingerprint, {
            "id": record_id,
            "document": document,
            "metadata": metadata,
        })
    return list(unique.values())


def measurement_from_record(record: dict, field: str) -> float | None:
    value = record["metadata"].get(field)
    if value not in (None, "", 0, 0.0):
        return float(value)
    label = "arm" if field == "arm_length" else field
    match = re.search(rf"{label}:\s*([\d.]+)", record["document"], re.IGNORECASE)
    return float(match.group(1)) if match else None


def normalized_metadata(record: dict) -> dict:
    metadata = dict(record["metadata"])
    for field in ["chest", "waist", "hips", "shoulder", "arm_length", "inseam"]:
        metadata[field] = measurement_from_record(record, field)
    if not metadata.get("notes"):
        metadata["notes"] = record["document"].split("Notes:")[-1].strip()
    return metadata

# ------------------------------------------------------------------------------
# API ENDPOINTS
# ------------------------------------------------------------------------------
app = FastAPI(title="Medical Custom Tailoring RAG Backend", version="1.0.0")

@app.get("/")
async def health_check():
    return {"status": "ok", "service": "medical-tailoring-api"}

@app.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user_dict = FAKE_USERS_DB.get(form_data.username)
    if not user_dict or not verify_password(form_data.password, user_dict["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user_dict["username"]}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/api/v1/measurements/manual")
async def create_manual_measurement(
    record: MeasurementInput, 
    current_user: User = Depends(get_current_user)
):
    record_id = f"REC_{datetime.utcnow().timestamp()}"
    save_to_chromadb(record.dict(), record_id)
    return {"status": "success", "record_id": record_id, "data": record}

@app.post("/api/v1/measurements/upload")
async def upload_document_ocr(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    contents = await file.read()
    raw_text = extract_raw_text(contents, file.filename)
    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="Could not extract readable text from uploaded file.")
    
    parsed_data = parse_text_to_json(raw_text)
    record_id = f"OCR_{datetime.utcnow().timestamp()}"
    extension = Path(file.filename or "upload.bin").suffix.lower() or ".bin"
    stored_file = UPLOAD_DIR / f"{record_id}{extension}"
    stored_file.write_bytes(contents)
    parsed_data["image_file"] = stored_file.name
    save_to_chromadb(parsed_data, record_id)
    
    return {
        "status": "success",
        "record_id": record_id,
        "extracted_raw_text": raw_text,
        "parsed_data": parsed_data
    }


@app.get("/api/v1/measurements/{record_id}/image")
async def get_measurement_image(
    record_id: str,
    current_user: User = Depends(get_current_user)
):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", record_id):
        raise HTTPException(status_code=400, detail="Invalid record ID.")
    matches = list(UPLOAD_DIR.glob(f"{record_id}.*"))
    if not matches:
        raise HTTPException(status_code=404, detail="No uploaded image found for this record.")
    return FileResponse(matches[0])

@app.post("/api/v1/measurements/query")
async def query_rag_measurements(
    request: QueryRequest,
    current_user: User = Depends(get_current_user)
):
    try:
        results = collection.query(
            query_texts=[request.query_text],
            n_results=request.n_results
        )
    except Exception:
        records = collection.get(include=["documents", "metadatas"])
        query_terms = set(request.query_text.lower().split())
        ranked_records = sorted(
            unique_records(records),
            key=lambda record: sum(term in record["document"].lower() for term in query_terms),
            reverse=True,
        )
        ranked_records = [record for record in ranked_records if any(term in record["document"].lower() for term in query_terms)]
        return {
            "query": request.query_text,
            "results": [
                {**record, "metadata": normalized_metadata(record), "distance": None}
                for record in ranked_records[:request.n_results]
            ],
        }

    query_records = unique_records({
        "ids": results.get("ids", [[]])[0],
        "documents": results.get("documents", [[]])[0],
        "metadatas": results.get("metadatas", [[]])[0],
    })
    formatted_results = []
    if query_records:
        for record in query_records:
            formatted_results.append({
                **record,
                "metadata": normalized_metadata(record),
                "distance": None,
            })
            
    return {"query": request.query_text, "results": formatted_results}

@app.get("/api/v1/measurements/analytics")
async def get_measurement_analytics(
    current_user: User = Depends(get_current_user)
):
    records = unique_records(collection.get(include=["documents", "metadatas"]))
    fields = ["chest", "waist", "hips", "shoulder", "arm_length", "inseam"]

    def average(field: str):
        values = [measurement_from_record(record, field) for record in records]
        values = [value for value in values if value is not None]
        return round(sum(values) / len(values), 2) if values else None

    records_by_doctor = {}
    for record in records:
        doctor_id = record["metadata"].get("doctor_id", "Unknown")
        records_by_doctor[doctor_id] = records_by_doctor.get(doctor_id, 0) + 1

    return {
        "total_records": len(records),
        "average_measurements": {field: average(field) for field in fields},
        "records_by_doctor": records_by_doctor,
        "records": [
            {
                "record_id": record["id"],
                "patient_id": record["metadata"].get("patient_id", ""),
                "doctor_id": record["metadata"].get("doctor_id", ""),
                **{field: measurement_from_record(record, field) for field in fields},
                "notes": record["metadata"].get("notes", "") or record["document"].split("Notes:")[-1].strip(),
                "image_file": record["metadata"].get("image_file", ""),
                "created_at": record["metadata"].get("created_at", ""),
            }
            for record in records
        ],
    }