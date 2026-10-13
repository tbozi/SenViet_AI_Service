from contextlib import asynccontextmanager
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config.settings import settings
from routers import chat, ingest
from core.database import fetch_hotel_knowledge
from core.vector_store import vector_store

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Khởi tạo dữ liệu khi khởi động server
    print(f"[*] Khởi động {settings.APP_NAME} v{settings.APP_VERSION}...")
    stats = vector_store.get_stats()
    chroma_count = stats.get("total_vectors_in_chroma", 0)
    pg_count = stats.get("total_vectors_in_postgres", 0)
    print(f"[*] Vector Store hiện có: {chroma_count} vectors (ChromaDB), {pg_count} vectors (PostgreSQL).")
    
    if chroma_count == 0:
        print("[*] Vector Database trống, đang tự động nạp dữ liệu từ PostgreSQL...")
        docs = fetch_hotel_knowledge()
        count = vector_store.index_documents(docs)
        print(f"[+] Đã hoàn tất nạp {count} tài liệu vào Vector Database thành công!")
    
    yield
    print("[*] Dừng dịch vụ AI...")

app = FastAPI(
    title="Hệ thống Trợ lý ảo AI Khách sạn Sen Việt (AI Microservice)",
    description="""
    Microservice phụ trách trí tuệ nhân tạo (AI & Data Science) cho Đồ án Tốt nghiệp Quản lý Chuỗi Khách sạn Sen Việt Luxury.
    
    ## Các công nghệ cốt lõi:
    - **Kiến trúc RAG (Retrieval-Augmented Generation)**: Chống ảo giác và tăng cường độ chính xác dữ liệu thực tế.
    - **Vector Database (ChromaDB)**: Lưu trữ và đánh chỉ mục vector nhúng (Embeddings) bằng thuật toán HNSW Cosine Similarity.
    - **Large Language Model (Google Gemini)**: Xử lý ngôn ngữ tự nhiên và tổng hợp thông tin tư vấn đặt phòng.
    - **Tích hợp linh hoạt**: Hỗ trợ xuất dữ liệu dạng Interactive Card (Đặt phòng, PayOS VietQR, Phiếu giữ phòng tại quầy).
    """,
    version=settings.APP_VERSION,
    lifespan=lifespan
)

# Cấu hình CORS để cả FE Khách hàng (8080), FE Nhân viên (8082) và BE Spring Boot (8081) đều kết nối được
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Đăng ký các router
app.include_router(chat.router)
app.include_router(ingest.router)

@app.post("/ai/chat", response_model=chat.ApiResponse, summary="Gửi tin nhắn chat tới AI (Root /ai/chat)")
async def root_ai_chat(request: chat.ChatRequest):
    return await chat.chat_endpoint(request)

@app.get("/", summary="Trang chủ Dịch vụ AI")
async def root():
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "Online",
        "documentation": "/docs",
        "health": "/api/health"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
