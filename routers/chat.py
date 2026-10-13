import uuid
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from core.rag_engine import rag_engine
from core.context import current_session_id

router = APIRouter(prefix="/api", tags=["AI Chatbot"])

class ChatMessage(BaseModel):
    role: str = Field(..., description="Vai trò người gửi: 'user' hoặc 'model'")
    content: str = Field(..., description="Nội dung tin nhắn")

class ChatRequest(BaseModel):
    message: str = Field(..., description="Câu hỏi của khách hàng")
    sessionId: Optional[str] = Field(None, description="Mã phiên hội thoại (UUID)")
    history: Optional[List[ChatMessage]] = Field(default=[], description="Lịch sử tin nhắn trước đó")

class ChatResult(BaseModel):
    reply: str = Field(..., description="Câu trả lời từ Trợ lý AI")
    sessionId: str = Field(..., description="Mã phiên hội thoại")
    state: Optional[Dict[str, Any]] = Field(None, description="Booking State hiện tại (dùng để render UI)")
    ragMetrics: Optional[Dict[str, Any]] = Field(None, description="Chỉ số hiệu năng RAG")

class ApiResponse(BaseModel):
    code: int = 1000
    message: str = "Success"
    result: ChatResult

@router.post("/chat", response_model=ApiResponse, summary="Gửi tin nhắn tư vấn tới AI RAG Agent")
@router.post("/ai/chat", response_model=ApiResponse, summary="Gửi tin nhắn tư vấn tới AI RAG Agent (khớp đường dẫn cũ)")
async def chat_endpoint(request: ChatRequest):
    """
    Endpoint tiếp nhận tin nhắn từ giao diện khách hàng.
    Thực hiện luồng Orchestrator (RAG + Function Calling):
    """
    session_id = request.sessionId if request.sessionId and request.sessionId.strip() else str(uuid.uuid4())
    
    # Inject sessionId context cho Tools có thể truy cập
    current_session_id.set(session_id)
    
    try:
        history_dicts = [{"role": h.role, "content": h.content} for h in (request.history or [])]
        rag_output = rag_engine.generate_response(message=request.message, history=history_dicts)
        
        return ApiResponse(
            code=1000,
            message="Success",
            result=ChatResult(
                reply=rag_output["reply"],
                sessionId=session_id,
                state=rag_output.get("state"),
                ragMetrics={
                    "retrieved_count": rag_output.get("retrieved_documents_count", 0),
                    "top_similarity_score": rag_output.get("top_match_score", 0.0),
                    "sources": rag_output.get("retrieved_sources", [])
                }
            )
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi xử lý AI Chatbot: {str(e)}")
