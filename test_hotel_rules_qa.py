# -*- coding: utf-8 -*-
import sys
import os

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.append("C:/Users/admin/Downloads/KLTN_HotelManagementAI")

from core.rag_engine import rag_engine

test_scenarios = [
    {
        "topic": "1. Check-out trễ lúc 12:15 & 14:00",
        "question": "Cho mình hỏi nếu mình check out trễ lúc 12:15 thì có bị tính phí không? Còn nếu trễ đến 14:00 thì phụ thu thế nào?"
    },
    {
        "topic": "2. Check-in sớm lúc 05:30 sáng & 08:00 sáng",
        "question": "Mình tới khách sạn sớm lúc 5h30 sáng muốn nhận phòng luôn thì tính phí sao? Còn nếu 8h sáng thì sao em?"
    },
    {
        "topic": "3. Chính sách hủy phòng & hoàn tiền dịch vụ",
        "question": "Nếu mình hủy phòng trước giờ check in 30 tiếng thì bị phạt bao nhiêu? Tiền dịch vụ spa đã đặt kèm có bị trừ phạt luôn không?"
    },
    {
        "topic": "4. Mã khuyến mãi khi hủy booking",
        "question": "Mình là khách vãng lai, lỡ dùng mã giảm giá đặt phòng rồi mà giờ hủy booking thì mã đó có được cấp lại để dùng lần sau không?"
    },
    {
        "topic": "5. Thời gian hoàn tiền ngân hàng & Dịch vụ chưa dùng",
        "question": "Khách sạn hoàn tiền qua tài khoản ngân hàng mất bao lâu? Với lại dịch vụ ăn uống mình chưa dùng thì có được hoàn tiền lúc checkout không?"
    }
]

print("=" * 70)
print("TEST & REVIEW NỘI DUNG NỘI QUY KHÁCH SẠN TRÊN CHATBOT AI")
print("=" * 70)

for idx, item in enumerate(test_scenarios, 1):
    print(f"\n--- [KỊCH BẢN {idx}]: {item['topic']} ---")
    print(f"Khách hỏi: {item['question']}")
    res = rag_engine.generate_response(item['question'])
    print(f"\nAI trả lời:\n{res['reply']}")
    print("-" * 70)
