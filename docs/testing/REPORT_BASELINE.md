# BÁO CÁO KẾT QUẢ ĐO LƯỜNG GỐC (BASELINE REPORT)
### DỰ ÁN: CHATBOT TƯ VẤN & ĐẶT PHÒNG KHÁCH HÀNG (LUỒNG B) - KHÁCH SẠN SEN VIỆT

- **Thời điểm kiểm thử:** 13/10/2026
- **Môi trường:** Python FastAPI + ChromaDB + Google Gemini (`Hệ thống Trợ lý ảo AI Khách sạn Sen Việt (AI Microservice)`)
- **Phạm vi kiểm thử:** 188 Test Cases (Đã loại trừ 11 test Admin nhóm AD)
- **File Excel kết quả chi tiết:** `docs/testing/Bo_Test_Case_BASELINE.xlsx`

---

## 1. TỔNG QUAN KẾT QUẢ

| Chỉ số | Số lượng | Tỉ lệ (%) |
|---|---|---|
| **Tổng số Test Cases** | **188** | 100.0% |
| **ĐẠT (Pass)** | **180** | **95.7%** |
| **KHÔNG ĐẠT (Fail)** | **1** | **0.5%** |
| **BỊ CHẶN (Blocked)** | **7** | **3.7%** |

---

## 2. KẾT QUẢ THEO MỨC ĐỘ ƯU TIÊN (PRIORITY)

| Mức ưu tiên | Tổng test | Pass | Fail | Blocked | Tỉ lệ Pass (%) |
|---|---|---|---|---|---|
| **P0 (Tối quan trọng: Tiền, Bảo mật, Luồng chính)** | 82 | 80 | 1 | 1 | **97.6%** |
| **P1 (Quan trọng: Validate nâng cao, Edge cases)** | 88 | 84 | 0 | 4 | **95.5%** |
| **P2 (Trung bình: Giao tiếp, Edge cases phụ)** | 18 | 16 | 0 | 2 | **88.9%** |

---

## 3. KẾT QUẢ THEO NHÓM NGHIỆP VỤ (GROUPS)

| Nhóm nghiệp vụ | Tổng số | Pass | Fail | Blocked | Tỉ lệ Pass (%) |
|---|---|---|---|---|---|
| Luồng đặt phòng chuẩn | 8 | 7 | 0 | 1 | 87.5% |
| Slot filling / khai báo gộp | 13 | 13 | 0 | 0 | 100.0% |
| Đổi ý / sửa thông tin | 13 | 12 | 0 | 1 | 92.3% |
| Kiểm tra dữ liệu đầu vào | 16 | 16 | 0 | 0 | 100.0% |
| Phòng trống / hết phòng | 7 | 7 | 0 | 0 | 100.0% |
| Thông tin khách | 3 | 3 | 0 | 0 | 100.0% |
| Dịch vụ đi kèm | 8 | 8 | 0 | 0 | 100.0% |
| Khuyến mãi / mã giảm giá | 14 | 13 | 1 | 0 | 92.9% |
| Xác nhận đặt phòng | 7 | 7 | 0 | 0 | 100.0% |
| Thanh toán (QR PayOS) | 16 | 14 | 0 | 2 | 87.5% |
| Hỏi chen ngang / FAQ (RAG) | 17 | 17 | 0 | 0 | 100.0% |
| Ngôn ngữ & định dạng input | 14 | 14 | 0 | 0 | 100.0% |
| Hủy / tra cứu / sửa booking | 9 | 9 | 0 | 0 | 100.0% |
| Bảo mật & lạm dụng | 15 | 15 | 0 | 0 | 100.0% |
| Ngoài phạm vi / hành vi đặc biệt | 10 | 10 | 0 | 0 | 100.0% |
| Lỗi hệ thống | 14 | 12 | 0 | 2 | 85.7% |
| Đồng thời / race condition | 4 | 3 | 0 | 1 | 75.0% |

---

## 4. DANH SÁCH TEST CASE P0 BỊ FAIL (CẦN ƯU TIÊN SỬA Ở GIAI ĐOẠN 4)

Tổng cộng có **1** test P0 bị Fail trên mã nguồn hiện tại:

| Test ID | Tên test case | Lý do không đạt (Root Cause sơ bộ) |
|---|---|---|
| **PR-05** | Mã hết hạn | LOGIC VI PHẠM: Mã hết hạn nhưng bot không thông báo hết hạn |

---

## 5. DANH SÁCH TEST CASE BỊ CHẶN (BLOCKED)

Có **7** test case thuộc diện Blocked do đặc thù yêu cầu tương tác giao diện người dùng (Frontend UI) hoặc chưa có hạ tầng phụ:

| Test ID | Tên test case | Lý do Blocked |
|---|---|---|
| **HP-05** | Hoàn thành toàn bộ luồng chỉ bằng nút bấm (quick reply) | Yêu cầu giao diện frontend: Hoàn thành bằng nút bấm UI quick-reply |
| **CH-11** | Bấm nút của bước cũ trong lịch sử chat | Yêu cầu giao diện frontend: Thao tác click trên tin nhắn cũ trong DOM UI |
| **PM-09** | Khách tải lại trang trong thời gian hold | Yêu cầu trình duyệt frontend: Kiểm thử khôi phục state khi F5 reload trang |
| **PM-16** | Xin gửi lại QR/lưu QR | Chưa hỗ trợ hạ tầng: Gửi QR qua email (chưa có Mail Server) |
| **ER-12** | Phản hồi chậm | Yêu cầu giao diện frontend: Hiệu ứng typing/loading indicator khi mạng chậm |
| **ER-13** | Hai tab/hai thiết bị cùng session | Yêu cầu trình duyệt frontend: Đồng bộ session đa tab trên client |
| **CC-04** | Webhook đến trước khi frontend polling | Yêu cầu giao diện frontend: Polling trạng thái thanh toán từ client |
