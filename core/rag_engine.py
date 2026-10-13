import json
from datetime import datetime
import google.generativeai as genai
from config.settings import settings
from core.clock import get_current_date
from core.vector_store import vector_store
from core.state_manager import state_manager
from core.context import current_session_id
from core.tools import (
    list_branches,
    check_availability,
    list_services,
    list_valid_promotions,
    calculate_price,
    create_booking,
    create_payment_qr,
    update_guest_info,
    select_room_and_services,
    apply_promotion
)

genai.configure(api_key=settings.GEMINI_API_KEY)

class RAGEngine:
    def __init__(self):
        system_instruction = """Bạn là trợ lý AI (Lễ tân ảo) chuyên nghiệp của chuỗi Khách sạn Sen Việt Luxury.
Mục tiêu của bạn là giúp khách hàng đặt phòng thông qua một chu trình từng bước.

QUY TẮC BẮT BUỘC (KHÔNG ĐƯỢC LÀM TRÁI):
1. KHÔNG BAO GIỜ TỰ BỊA ĐẶT GIÁ, TÊN CHI NHÁNH, PHÒNG TRỐNG HAY MÃ KHUYẾN MÃI. Mọi thông tin phải gọi Tool để lấy dữ liệu thực tế.
2. Quản lý trạng thái bằng công cụ (Tool). Khách hàng có thể cung cấp nhiều thông tin cùng lúc (VD: "Tôi muốn đặt 1 phòng Standard ở Đà Lạt ngày mai cho 2 người"). Hãy gọi Tool `check_availability` để cập nhật trạng thái và lấy dữ liệu.
3. Chỉ hỏi những thông tin (slots) còn thiếu dựa trên State hiện tại.
4. Trả lời luôn lễ phép, xưng "em", gọi "quý khách" hoặc "anh/chị". Nếu khách hỏi câu hỏi bên lề (FAQ), hãy dựa vào [NGỮ CẢNH HỆ THỐNG] để trả lời ngắn gọn, sau đó khéo léo nhắc khách quay lại luồng đặt phòng.
5. Khi khách hàng đồng ý chốt phòng và yêu cầu thanh toán, TỰ ĐỘNG gọi tool `create_booking` rồi gọi `create_payment_qr` để lấy link QR, sau đó in ra kết quả. TUYỆT ĐỐI KHÔNG tự báo "Đặt thành công" khi chưa có thông tin từ Tool.
6. KHÔNG yêu cầu khách tự bấm nút nếu bạn có thể tự gọi Tool để xử lý cho khách (như áp mã giảm giá, chọn dịch vụ).
7. Bạn KHÔNG output thẻ ```json:booking_card``` nữa. Frontend sẽ tự động lấy state từ backend để render giao diện đồ họa. Bạn chỉ cần trả lời bằng text tự nhiên.
8. LƯU Ý QUAN TRỌNG: Thời gian giữ phòng tạm thời chờ thanh toán LUÔN LUÔN LÀ 5 PHÚT (tuyệt đối không nói 15 phút, phải đồng nhất 5 phút với giao diện thẻ giữ phòng).
9. ĐẶC BIỆT VỀ MÃ KHUYẾN MÃI DEMO2K: Mã DEMO2K là mã khách hàng được phép dùng để test thanh toán. Nếu khách hàng yêu cầu áp dụng mã DEMO2K hoặc demo2k, BẮT BUỘC bạn phải gọi tool apply_promotion('DEMO2K') và cho phép khách sử dụng. KHÔNG ĐƯỢC TỪ CHỐI với lý do mã nội bộ hay dành cho kỹ thuật.

QUY TRÌNH ĐẶT PHÒNG (State Machine):
- SELECT_BRANCH: Hỏi khách chọn chi nhánh nếu chưa biết. Dùng list_branches().
- SELECT_ROOM: Nếu có ngày và số người, gọi check_availability(). Thông báo danh sách phòng trống và giá.
- GET_GUEST_INFO: Xin thông tin họ tên, SĐT. Gọi update_guest_info().
- SELECT_SERVICES: Gợi ý các dịch vụ đi kèm. Gọi list_services(). Gọi select_room_and_services().
- SUMMARY_PROMO: Tóm tắt lại đơn hàng. Gọi list_valid_promotions() và hỏi khách có muốn áp mã. Gọi apply_promotion() và calculate_price().
- SELECT_PAYMENT: Hỏi khách thanh toán chuyển khoản hay tiền mặt. Gọi create_booking().
- PAYMENT_PROCESSING: Gọi create_payment_qr().
"""
        # Đăng ký các Tools
        self.tools = [
            list_branches,
            check_availability,
            list_services,
            list_valid_promotions,
            calculate_price,
            create_booking,
            create_payment_qr,
            update_guest_info,
            select_room_and_services,
            apply_promotion
        ]

        self.model = genai.GenerativeModel(
            model_name=settings.GEMINI_MODEL,
            tools=self.tools,
            system_instruction=system_instruction
        )

    def generate_response(self, message: str, history: list = None) -> dict:
        session_id = current_session_id.get()
        state = state_manager.get_state(session_id)
        
        # 1. Retrieval
        results = vector_store.similarity_search(query=message, k=settings.TOP_K_RESULTS)
        valid_docs = [r for r in results if r["score"] >= settings.SIMILARITY_THRESHOLD]
        context_str = "\n---\n".join([f"[{d['metadata'].get('category', 'Khác')}]: {d['text']}" for d in valid_docs])
        
        today_date = get_current_date()
        
        # Format history
        formatted_history = []
        for h in (history or []):
            role = "user" if h["role"] == "user" else "model"
            if h["content"].strip():
                formatted_history.append({"role": role, "parts": [h["content"]]})
        
        chat = self.model.start_chat(history=formatted_history, enable_automatic_function_calling=True)
        
        # Truyền State vào prompt
        enriched_message = f"""[TRẠNG THÁI BOOKING CỦA KHÁCH (STATE)]
{json.dumps(state.model_dump(), ensure_ascii=False, indent=2)}

[NGỮ CẢNH HỆ THỐNG FAQ (Dùng để trả lời câu hỏi bên lề nếu có)]
{context_str}

[THÔNG TIN THỜI GIAN THỰC]
Hôm nay là ngày: {today_date} (Dùng để quy đổi từ "hôm nay", "ngày mai").

Khách hàng nói: {message}"""

        reply_text = ""
        for attempt in range(3):
            try:
                response = chat.send_message(enriched_message)
                reply_text = response.text
                break
            except Exception as e:
                error_msg = str(e)
                print(f"[Gemini API Error attempt {attempt+1}] {error_msg}")
                if "429" in error_msg or "ResourceExhausted" in error_msg or "quota" in error_msg.lower():
                    import time
                    time.sleep(12 * (attempt + 1))
                else:
                    break
        
        if not reply_text:
            reply_text = "Dạ, hệ thống AI đang gặp chút gián đoạn kết nối. Quý khách vui lòng thử lại sau giây lát ạ!"

        # State sau khi xử lý (bị modify bởi các tools gọi ở trên)
        new_state = state_manager.get_state(session_id)

        # Trả về reply_text và state (sẽ đc router biến thành ui_components)
        return {
            "reply": reply_text,
            "state": new_state.model_dump(),
            "retrieved_documents_count": len(valid_docs),
            "top_match_score": valid_docs[0]["score"] if valid_docs else 0.0,
            "retrieved_sources": list(set([d["metadata"].get("hotel_name", "Chung") for d in valid_docs]))
        }

rag_engine = RAGEngine()
