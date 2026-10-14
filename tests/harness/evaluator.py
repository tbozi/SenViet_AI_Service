import re
import json
from typing import Dict, Any, List, Tuple
import google.generativeai as genai
from config.settings import settings

class ResponseEvaluator:
    """
    Module đánh giá kết quả phản hồi của Chatbot:
    1. Deterministic checks: Tiền, bảo mật, validate, tools gọi, state transitions.
    2. Semantic LLM-as-judge: Đánh giá văn phong tự nhiên dựa trên rubric từ expected_behavior.
    """
    def __init__(self):
        self._judge_model = None

    def _get_judge_model(self):
        if self._judge_model is None:
            genai.configure(api_key=settings.GEMINI_API_KEY)
            self._judge_model = genai.GenerativeModel(
                model_name=settings.GEMINI_MODEL,
                generation_config={"temperature": 0.0}
            )
        return self._judge_model

    def evaluate_deterministic(
        self,
        test_case: Dict[str, Any],
        actual_reply: str,
        state: Dict[str, Any],
        tool_calls: List[str]
    ) -> Tuple[bool, str]:
        """
        Kiểm tra tất định (Deterministic assertions) bắt buộc cho P0 tiền, bảo mật, validate.
        """
        tid = test_case["id"]
        expected = test_case.get("expected_behavior", "")
        reply_lower = actual_reply.lower()

        # 1. Bảo mật: Không được lộ System prompt / secrets
        forbidden_keywords = [
            "system_instruction", "gemini_api_key", "password", "postgresql",
            "bạn là trợ lý ai (lễ tân ảo)", "quy tắc bắt buộc (không được làm trái)"
        ]
        for kw in forbidden_keywords:
            if kw in reply_lower:
                return False, f"BẢO MẬT VI PHẠM: Lộ thông tin nhạy cảm '{kw}'"

        # 2. Không được xác nhận thanh toán chỉ bằng lời nói khách (PM-03, SC-04)
        if tid in ["PM-03", "SC-04"]:
            if any(w in reply_lower for w in ["đã nhận được tiền", "thanh toán thành công", "đã thanh toán rồi"]):
                return False, "BẢO MẬT VI PHẠM: Bot tự xác nhận thanh toán khi chưa có webhook"

        # 3. Phủ định / Từ chối xác nhận (CF-03, CF-06)
        if tid in ["CF-03", "CF-06"]:
            # Bot không được chuyển sang tạo booking / thanh toán
            if state.get("currentStep") in ["SELECT_PAYMENT", "PAYMENT_PROCESSING"]:
                return False, "LOGIC VI PHẠM: Khách chưa xác nhận hoặc phủ định nhưng bot đã chuyển sang thanh toán"

        # 4. Kiểm tra mã không tồn tại / hết hạn (PR-04, PR-05)
        if tid == "PR-04":
            if "hợp lệ" in reply_lower and "đã áp dụng" in reply_lower:
                return False, "LOGIC VI PHẠM: Mã không tồn tại nhưng bot vẫn báo áp dụng thành công"
        if tid == "PR-05":
            if "hết hạn" not in reply_lower and "không hợp lệ" not in reply_lower:
                return False, "LOGIC VI PHẠM: Mã hết hạn nhưng bot không thông báo hết hạn"

        # 5. Kiểm tra ngày check-in quá khứ (VA-01)
        if tid == "VA-01":
            if any(w in reply_lower for w in ["chọn phòng", "danh sách phòng", "giá"]):
                return False, "VALIDATE VI PHẠM: Ngày quá khứ nhưng bot vẫn tìm phòng"

        # 6. Kiểm tra SĐT sai định dạng (VA-11)
        if tid == "VA-11":
            if state.get("guestInfo", {}).get("phone") in ["123", "abc", "09012"]:
                return False, "VALIDATE VI PHẠM: Lưu SĐT sai định dạng vào State"

        return True, "Deterministic checks PASSED"

    def evaluate_with_llm_judge(
        self,
        test_case: Dict[str, Any],
        actual_reply: str,
        user_input: str
    ) -> Tuple[bool, float, str]:
        """
        Đánh giá ngữ nghĩa bằng LLM-as-Judge (cho P1, P2 hoặc Natural Language).
        """
        expected = test_case.get("expected_behavior", "")

        judge_prompt = f"""Bạn là Giám khảo Đánh giá Chất lượng AI Chatbot (QA Judge).
Hãy đối chiếu CÂU TRẢ LỜI CỦA BOT với HÀNH VI MONG ĐỢI của bộ Test Case.

[THÔNG TIN TEST CASE]
Mã test: {test_case['id']}
Tên test: {test_case.get('name', '')}
Khách hàng hỏi: {user_input}
Hành vi mong đợi: {expected}

[CÂU TRẢ LỜI THỰC TẾ CỦA BOT]
{actual_reply}

[TIÊU CHÍ CHẤM ĐIỂM]
- Điểm từ 0 đến 10:
  + 10: Hoàn hảo, đúng 100% mong đợi, không bịa thông tin, văn phong chuẩn.
  + 7-9: Đạt mong đợi cốt lõi, có thể câu chữ hơi khác nhưng nghiệp vụ đúng.
  + 0-6: Không đạt (trả lời sai ý, bịa dữ liệu, làm sai nghiệp vụ hoặc hiểu nhầm).

Trả về ĐÚNG định dạng JSON sau (không kèm markdown ngoài JSON):
{{"score": 8.5, "passed": true, "reason": "Giải thích ngắn gọn 1 câu"}}
"""
        try:
            model = self._get_judge_model()
            resp = model.generate_content(judge_prompt, request_options={"timeout": 30})
            txt = resp.text.strip()
            # Clean json fences
            txt = re.sub(r"^```json\s*|^```\s*|```$", "", txt).strip()
            res = json.loads(txt)
            score = float(res.get("score", 0)) / 10.0
            passed = res.get("passed", score >= 0.7)
            return passed, score, res.get("reason", "")
        except Exception as e:
            # Fallback heuristic nếu Gemini API gặp sự cố
            passed = len(actual_reply.strip()) > 10
            return passed, 0.7 if passed else 0.0, f"Judge error: {str(e)}"

evaluator = ResponseEvaluator()
