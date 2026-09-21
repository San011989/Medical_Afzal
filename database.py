# database.py
import chromadb
from chromadb.utils import embedding_functions

chroma_client = chromadb.PersistentClient(path="./chroma_db")
embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")

collection = chroma_client.get_or_create_collection(
    name="doctor_measurements",
    embedding_function=embed_fn
)

def save_measurement_record(record_id: str, measurement_data: dict):
    # Narrative document representation for vector semantic search
    doc_text = (
        f"Doctor ID: {measurement_data.get('doctor_id')}. "
        f"Chest: {measurement_data.get('chest')}in, Waist: {measurement_data.get('waist')}in, "
        f"Shoulder: {measurement_data.get('shoulder')}in. "
        f"Notes: {measurement_data.get('notes', '')}"
    )
    
    # Metadata filtering allows strict numerical range queries
    metadata = {
        "doctor_id": str(measurement_data.get("doctor_id")),
        "chest": float(measurement_data.get("chest", 0)),
        "waist": float(measurement_data.get("waist", 0)),
        "shoulder": float(measurement_data.get("shoulder", 0)),
        "created_at": str(datetime.utcnow().date())
    }
    
    collection.add(
        documents=[doc_text],
        metadatas=[metadata],
        ids=[record_id]
    )