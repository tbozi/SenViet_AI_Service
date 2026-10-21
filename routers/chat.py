import uuid
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from core.rag_engine import rag_engine
from core.context import current_session_id
from core.state_manager import state_manager

router = APIRouter(prefix="/api", tags=["AI Chatbot"])

class ChatMessage(BaseModel):
    role: str = Field(..., description="Vai trò người gửi: 'user' hoặc 'model'")
    content: str = Field(..., description="Nội dung tin nhắn")

class ChatRequest(BaseModel):
    message: str = Field(..., description="Câu hỏi của khách hàng")
    sessionId: Optional[str] = Field(None, description="Mã phiên hội thoại (UUID)")
    history: Optional[List[ChatMessage]] = Field(default=[], description="Lịch sử tin nhắn trước đó")
    userInfo: Optional[Dict[str, Any]] = Field(None, description="Thông tin tài khoản khách hàng đã đăng nhập")

class ChatResult(BaseModel):
    reply: str = Field(..., description="Câu trả lời từ Trợ lý AI")
    sessionId: str = Field(..., description="Mã phiên hội thoại")
    state: Optional[Dict[str, Any]] = Field(None, description="Booking State hiện tại (dùng để render UI)")
    ragMetrics: Optional[Dict[str, Any]] = Field(None, description="Chỉ số hiệu năng RAG")

class ApiResponse(BaseModel):
    code: int = 1000
    message: str = "Success"
    result: ChatResult

from core.chat_history import save_chat_turn, get_session_history, delete_session_history

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

    # Tự động đồng bộ thông tin khách hàng đã đăng nhập (HP-03)
    if request.userInfo:
        u_info = request.userInfo
        u_name = u_info.get("name") or u_info.get("fullName")
        u_phone = u_info.get("phone")
        u_email = u_info.get("email")
        if u_name or u_phone or u_email:
            st = state_manager.get_state(session_id)
            g_info = dict(st.guestInfo or {})
            if u_name and not g_info.get("name"):
                g_info["name"] = u_name
            if u_phone and not g_info.get("phone"):
                g_info["phone"] = u_phone
            if u_email and not g_info.get("email"):
                g_info["email"] = u_email
            state_manager.update_state(session_id, {"guestInfo": g_info})
    
    try:
        history_dicts = [{"role": h.role, "content": h.content} for h in (request.history or [])]
        rag_output = rag_engine.generate_response(message=request.message, history=history_dicts)
        reply_text = rag_output.get("reply", "")
        current_state = rag_output.get("state")
        
        # Tự động lưu lịch sử hội thoại vào PostgreSQL
        try:
            save_chat_turn(
                session_id=session_id,
                user_message=request.message,
                bot_reply=reply_text,
                state=current_state
            )
        except Exception as db_err:
            print(f"[Warning] Lưu lịch sử chat thất bại: {db_err}")
        
        return ApiResponse(
            code=1000,
            message="Success",
            result=ChatResult(
                reply=reply_text,
                sessionId=session_id,
                state=current_state,
                ragMetrics={
                    "retrieved_count": rag_output.get("retrieved_documents_count", 0),
                    "top_similarity_score": rag_output.get("top_match_score", 0.0),
                    "sources": rag_output.get("retrieved_sources", [])
                }
            )
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi xử lý AI Chatbot: {str(e)}")

@router.get("/chat/history/{session_id}", summary="Lấy lịch sử hội thoại của một phiên chat")
@router.get("/ai/chat/history/{session_id}", summary="Lấy lịch sử hội thoại của một phiên chat (alias)")
async def get_chat_history_endpoint(session_id: str):
    """Truy xuất toàn bộ lịch sử tin nhắn và trạng thái booking đã lưu theo session_id."""
    data = get_session_history(session_id)
    return {
        "code": 1000,
        "message": "Success",
        "result": data
    }

@router.delete("/chat/history/{session_id}", summary="Xóa lịch sử hội thoại của phiên chat")
@router.delete("/ai/chat/history/{session_id}", summary="Xóa lịch sử hội thoại của phiên chat (alias)")
async def delete_chat_history_endpoint(session_id: str):
    """Xóa phiên trò chuyện và các tin nhắn liên quan."""
    success = delete_session_history(session_id)
    return {
        "code": 1000,
        "message": "Success" if success else "Failed",
        "result": {"deleted": success, "sessionId": session_id}
    }

