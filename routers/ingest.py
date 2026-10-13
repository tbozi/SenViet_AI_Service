from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any
from core.database import fetch_hotel_knowledge
from core.vector_store import vector_store

router = APIRouter(prefix="/api", tags=["Data Ingestion & Monitoring"])

class IngestResponse(BaseModel):
    code: int = 1000
    message: str
    total_indexed: int
    vector_stats: Dict[str, Any]

class HealthResponse(BaseModel):
    status: str
    service: str
    vector_store: Dict[str, Any]

@router.post("/ingest", response_model=IngestResponse, summary="Đồng bộ dữ liệu từ PostgreSQL sang Vector Database")
async def trigger_ingestion():
    """
    Kích hoạt pipeline nạp dữ liệu:
    1. Đọc dữ liệu khách sạn, phòng, chính sách, dịch vụ từ PostgreSQL
    2. Vector hóa và lưu trữ vào ChromaDB với thuật toán Cosine HNSW
    """
    try:
        documents = fetch_hotel_knowledge()
        count = vector_store.index_documents(documents)
        stats = vector_store.get_stats()
        return IngestResponse(
            code=1000,
            message="Đồng bộ dữ liệu vào Vector Database thành công!",
            total_indexed=count,
            vector_stats=stats
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi đồng bộ dữ liệu: {str(e)}")

@router.get("/health", response_model=HealthResponse, summary="Kiểm tra trạng thái dịch vụ AI & Vector Database")
async def health_check():
    """Endpoint giám sát sức khỏe dịch vụ và số lượng vector embeddings đã lưu"""
    stats = vector_store.get_stats()
    return HealthResponse(
        status="healthy",
        service="SenViet Hotel AI Microservice (FastAPI + ChromaDB)",
        vector_store=stats
    )
