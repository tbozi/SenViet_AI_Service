import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor, Json
from config.settings import settings

logger = logging.getLogger(__name__)

def get_connection():
    return psycopg2.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        dbname=settings.DB_NAME,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD
    )

def init_chat_tables():
    """Khởi tạo bảng chat_sessions và chat_messages trong PostgreSQL nếu chưa có."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS chat_sessions (
                session_id VARCHAR(128) PRIMARY KEY,
                customer_name VARCHAR(255),
                customer_phone VARCHAR(50),
                customer_email VARCHAR(255),
                booking_id VARCHAR(64),
                current_step VARCHAR(64) DEFAULT 'SELECT_BRANCH',
                state_json JSONB,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS chat_messages (
                id BIGSERIAL PRIMARY KEY,
                session_id VARCHAR(128) NOT NULL REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
                role VARCHAR(32) NOT NULL, -- 'user' hoặc 'model'
                content TEXT NOT NULL,
                metadata_json JSONB,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id);
            CREATE INDEX IF NOT EXISTS idx_chat_messages_time ON chat_messages(created_at);
        """)
        conn.commit()
        cur.close()
        conn.close()
        logger.info("[ChatHistory] Đã khởi tạo các bảng chat_sessions và chat_messages thành công.")
    except Exception as e:
        logger.error(f"[ChatHistory] Lỗi khởi tạo bảng chat: {e}")

def save_chat_turn(session_id: str, user_message: str, bot_reply: str, state: Optional[Dict[str, Any]] = None):
    """
    Lưu một lượt tương tác (User nói -> Bot đáp) vào PostgreSQL.
    Tự động cập nhật session và trạng thái booking.
    """
    if not session_id:
        return

    try:
        conn = get_connection()
        cur = conn.cursor()
        
        # 1. Trích xuất thông tin khách từ state nếu có
        guest_info = state.get("guestInfo", {}) if state else {}
        name = guest_info.get("name") or None
        phone = guest_info.get("phone") or None
        email = guest_info.get("email") or None
        booking_id = state.get("bookingId") or None if state else None
        step = state.get("currentStep") or "SELECT_BRANCH" if state else "SELECT_BRANCH"
        state_data = Json(state) if state else None

        # 2. Upsert chat_sessions
        cur.execute("""
            INSERT INTO chat_sessions (session_id, customer_name, customer_phone, customer_email, booking_id, current_step, state_json, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (session_id) DO UPDATE SET
                customer_name = COALESCE(EXCLUDED.customer_name, chat_sessions.customer_name),
                customer_phone = COALESCE(EXCLUDED.customer_phone, chat_sessions.customer_phone),
                customer_email = COALESCE(EXCLUDED.customer_email, chat_sessions.customer_email),
                booking_id = COALESCE(EXCLUDED.booking_id, chat_sessions.booking_id),
                current_step = EXCLUDED.current_step,
                state_json = COALESCE(EXCLUDED.state_json, chat_sessions.state_json),
                updated_at = CURRENT_TIMESTAMP;
        """, (session_id, name, phone, email, booking_id, step, state_data))

        # 3. Lưu tin nhắn của khách
        if user_message and user_message.strip():
            cur.execute("""
                INSERT INTO chat_messages (session_id, role, content, metadata_json)
                VALUES (%s, %s, %s, %s);
            """, (session_id, "user", user_message.strip(), None))

        # 4. Lưu câu trả lời của Trợ lý AI kèm metadata tóm tắt
        if bot_reply and bot_reply.strip():
            meta = {
                "step": step,
                "has_booking": bool(booking_id),
                "booking_id": booking_id,
                "has_qr": bool(state.get("qrUrl")) if state else False
            }
            cur.execute("""
                INSERT INTO chat_messages (session_id, role, content, metadata_json)
                VALUES (%s, %s, %s, %s);
            """, (session_id, "model", bot_reply.strip(), Json(meta)))

        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logger.error(f"[ChatHistory] Lỗi lưu tin nhắn session {session_id}: {e}")

def get_session_history(session_id: str) -> Dict[str, Any]:
    """Lấy danh sách tin nhắn và thông tin phiên chat từ database."""
    if not session_id:
        return {"sessionId": session_id, "messages": [], "state": None}

    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Lấy session
        cur.execute("""
            SELECT session_id, customer_name, customer_phone, customer_email, 
                   booking_id, current_step, state_json, created_at, updated_at
            FROM chat_sessions
            WHERE session_id = %s;
        """, (session_id,))
        session = cur.fetchone()

        # Lấy tin nhắn theo thứ tự thời gian
        cur.execute("""
            SELECT id, role, content, metadata_json, created_at
            FROM chat_messages
            WHERE session_id = %s
            ORDER BY created_at ASC, id ASC;
        """, (session_id,))
        messages = cur.fetchall()
        
        cur.close()
        conn.close()

        formatted_msgs = []
        for m in messages:
            formatted_msgs.append({
                "id": m["id"],
                "role": m["role"],
                "content": m["content"],
                "metadata": m["metadata_json"],
                "createdAt": m["created_at"].isoformat() if m.get("created_at") else None
            })

        return {
            "sessionId": session_id,
            "session": {
                "customerName": session["customer_name"] if session else None,
                "customerPhone": session["customer_phone"] if session else None,
                "customerEmail": session["customer_email"] if session else None,
                "bookingId": session["booking_id"] if session else None,
                "currentStep": session["current_step"] if session else "SELECT_BRANCH",
                "createdAt": session["created_at"].isoformat() if session and session.get("created_at") else None,
                "updatedAt": session["updated_at"].isoformat() if session and session.get("updated_at") else None,
            } if session else None,
            "state": session["state_json"] if session else None,
            "messages": formatted_msgs
        }
    except Exception as e:
        logger.error(f"[ChatHistory] Lỗi truy vấn lịch sử session {session_id}: {e}")
        return {"sessionId": session_id, "messages": [], "state": None, "error": str(e)}

def delete_session_history(session_id: str) -> bool:
    """Xóa toàn bộ lịch sử của phiên chat."""
    if not session_id:
        return False
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM chat_sessions WHERE session_id = %s;", (session_id,))
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"[ChatHistory] Lỗi xóa session {session_id}: {e}")
        return False
