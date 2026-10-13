# TÀI LIỆU TEST HARNESS: HỆ THỐNG KIỂM THỬ TỰ ĐỘNG CHATBOT KHÁCH HÀNG (LUỒNG B)

Tài liệu này hướng dẫn chi tiết cách vận hành bộ khung kiểm thử tự động (Test Harness) cho Chatbot Khách hàng của Khách sạn Sen Việt, bao gồm 188 test cases (loại trừ nhóm AD của Admin).

---

## 1. Kiến trúc Test Harness

Test Harness được thiết kế theo mô hình tự động hóa toàn diện (Automated End-to-End Testing):
- **Test Runner:** Sử dụng `pytest` kết hợp với custom CLI runner (`tests/test_customer_chatbot.py`) gọi trực tiếp API FastAPI qua `httpx.AsyncClient` (ASGI in-process, không cần mở port mạng bên ngoài).
- **Freeze Time (Đóng băng thời gian):** Module `core/clock.py` cố định mốc thời gian hệ thống về **13/10/2026 (Thứ Ba)** qua biến môi trường `AI_FROZEN_DATE=2026-10-13`.
- **Database Fixtures:** Tự động seed dữ liệu cố định trong PostgreSQL (`tests/fixtures/db_seed.py`):
  - 7 chi nhánh khách sạn.
  - 4 loại phòng (`STANDARD`, `DELUXE`, `SUITE`, `FAMILY`) đầy đủ chính sách giá và sức chứa.
  - Bảng giá mùa/cuối tuần (`room_seasonal_rates`).
  - Dịch vụ đi kèm (`Spa`, `Đưa đón`, `Buffet Sáng`).
  - Toàn bộ mã khuyến mãi chuẩn theo test case (`SEN10`, `VIP20`, `TET2025`, `STAFF100`, `MAX300K`, `DEMO2K`).
  - Booking mẫu `SV12345` để kiểm thử tra cứu, hủy, sửa đơn.
- **ChromaDB Fixtures:** Nạp bộ chính sách mẫu (`tests/fixtures/sample_policies.py`):
  - Chính sách hủy 3 bậc (Miễn phí 3-7 ngày, phạt 50% 1-2 ngày, phạt 100% trong 24h/no-show).
  - Giờ nhận/trả phòng (14:00 / 12:00), chính sách trẻ em, thú cưng, tiện ích.
  - Bản chính sách hủy cũ (để test giải quyết mâu thuẫn IN-17).
  - Bản ghi gián tiếp chứa prompt injection (để test an toàn SC-15).
- **PayOS Mock (`tests/harness/mock_payos.py`):** Giả lập phản hồi PayOS và hỗ trợ bắn webhook tự động sang Backend Spring Boot với các kịch bản: thành công, thiếu tiền, dư tiền, webhook trùng lặp, webhook hết hạn.
- **Fault Injection (`tests/harness/fault_injector.py`):** Cho phép tiêm lỗi có chủ đích (timeout, HTTP 500, ChromaDB down, Gemini 429).
- **Đánh giá 2 tầng (Two-Tier Evaluation):**
  1. *Deterministic Assertions:* Áp dụng bắt buộc cho các test P0 liên quan tiền, thanh toán, bảo mật, validate, trạng thái đơn hàng.
  2. *LLM-as-Judge:* Dùng mô hình Gemini với `temperature=0` chấm điểm ngữ nghĩa cho các câu hỏi tư vấn tự nhiên theo đúng rubric trong cột "Hành vi mong đợi".

---

## 2. Hướng dẫn lệnh chạy

Đảm bảo đã kích hoạt môi trường ảo Python:
```powershell
cd C:\Users\admin\Downloads\KLTN_HotelManagementAI
.\venv\Scripts\activate
```

### 2.1. Lệnh chạy TẤT CẢ 188 Test Cases
Chạy toàn bộ 188 test case và xuất file kết quả JSON:
```powershell
python tests/test_customer_chatbot.py --output docs/testing/results_all.json
```
Hoặc chạy bằng `pytest`:
```powershell
pytest tests/test_customer_chatbot.py -v
```

### 2.2. Lệnh chạy theo Mức ưu tiên (Priority)
- **Chạy toàn bộ test P0 (Cực kỳ quan trọng - Tiền, Bảo mật, Luồng chính):**
  ```powershell
  python tests/test_customer_chatbot.py --priority P0 --output docs/testing/results_p0.json
  ```
- **Chạy toàn bộ test P1 (Biên, validate nâng cao, tính năng phụ):**
  ```powershell
  python tests/test_customer_chatbot.py --priority P1
  ```
- **Chạy toàn bộ test P2 (Edge cases ít gặp):**
  ```powershell
  python tests/test_customer_chatbot.py --priority P2
  ```

### 2.3. Lệnh chạy theo Nhóm nghiệp vụ (Group)
- **Nhóm HP (Happy Path - Luồng đặt phòng chuẩn):**
  ```powershell
  python tests/test_customer_chatbot.py --group HP
  ```
- **Nhóm SF (Slot Filling - Khai báo gộp):**
  ```powershell
  python tests/test_customer_chatbot.py --group SF
  ```
- **Nhóm CH (Change Mind - Khách đổi ý):**
  ```powershell
  python tests/test_customer_chatbot.py --group CH
  ```
- **Nhóm VA (Validation - Kiểm tra dữ liệu vào):**
  ```powershell
  python tests/test_customer_chatbot.py --group VA
  ```
- **Nhóm AV (Availability - Phòng trống / Hết phòng):**
  ```powershell
  python tests/test_customer_chatbot.py --group AV
  ```
- **Nhóm PR (Promotions - Mã giảm giá):**
  ```powershell
  python tests/test_customer_chatbot.py --group PR
  ```
- **Nhóm PM (Payment - QR PayOS & Webhook):**
  ```powershell
  python tests/test_customer_chatbot.py --group PM
  ```
- **Nhóm IN (Interruption - Hỏi chen ngang / FAQ RAG):**
  ```powershell
  python tests/test_customer_chatbot.py --group IN
  ```
- **Nhóm SC (Security - Bảo mật & Chống tấn công injection):**
  ```powershell
  python tests/test_customer_chatbot.py --group SC
  ```
- **Nhóm CA (Cancel / Audit - Tra cứu, hủy, sửa đơn):**
  ```powershell
  python tests/test_customer_chatbot.py --group CA
  ```
- **Nhóm ER (Error Handling - Xử lý lỗi hệ thống):**
  ```powershell
  python tests/test_customer_chatbot.py --group ER
  ```

### 2.4. Lệnh chạy 1 Test Case đơn lẻ (để debug)
```powershell
python tests/test_customer_chatbot.py --id HP-01
python tests/test_customer_chatbot.py --id SC-01
```

---

## 3. Khởi tạo lại hạ tầng kiểm thử độc lập
Khi cần reset hoặc nạp lại dữ liệu test vào PostgreSQL và ChromaDB:
```powershell
# Nạp dữ liệu PostgreSQL (phòng, chi nhánh, voucher, booking mẫu)
python tests/fixtures/db_seed.py

# Nạp dữ liệu ChromaDB (chính sách hủy, giờ giấc, tiện ích...)
python tests/fixtures/sample_policies.py
```
