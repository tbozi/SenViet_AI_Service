# PHÂN TÍCH NGUYÊN NHÂN GỐC RỄ (ROOT CAUSE ANALYSIS)
### DỰ ÁN: CHATBOT TƯ VẤN & ĐẶT PHÒNG KHÁCH HÀNG (LUỒNG B) - SEN VIỆT LUXURY
**Giai đoạn:** Giai đoạn 3 (Sau khi hoàn tất Baseline, trước khi sửa mã nguồn)  
**Ngày thực hiện:** 14/10/2026  
**Dữ liệu đầu vào:** [`Bo_Test_Case_BASELINE.xlsx`](./Bo_Test_Case_BASELINE.xlsx) & [`REPORT_BASELINE.md`](./REPORT_BASELINE.md)  

---

## 1. TỔNG QUAN PHÂN LOẠI NGUYÊN NHÂN

Qua quá trình đo lường thực nghiệm 188 test case trên hệ thống hiện tại, tổng hợp kết quả như sau:
- **Đạt (Pass):** 180 / 188 test (95.7%)
- **Không đạt (Fail):** 1 / 188 test (0.5%)
- **Bị chặn (Blocked):** 7 / 188 test (3.7%)

Theo yêu cầu chuẩn mực của đề tài, các vấn đề và lỗi được phân loại theo 5 nhóm nguyên nhân chính:
1. **`PROMPT`**: Hiểu sai ngữ cảnh, thiếu quy tắc nghiệp vụ cốt lõi, thiếu few-shot, chưa cập nhật prompt mục tiêu.
2. **`BACKEND`**: Thiếu hàm kiểm tra/validate dữ liệu độc lập, ràng buộc logic trong cơ sở dữ liệu hoặc API.
3. **`DATA/RAG`**: Thiếu dữ liệu quy chế/chính sách, cấu trúc dữ liệu chưa hỗ trợ kịch bản đa phòng.
4. **`ORCHESTRATION`**: Máy trạng thái (State Machine) quá cứng nhắc, ràng buộc thứ tự gọi tool không linh hoạt.
5. **`TEST / OUT_OF_SCOPE`**: Yêu cầu đặc thù của giao diện người dùng (Frontend DOM UI / Trình duyệt) hoặc hạ tầng dịch vụ bên thứ ba chưa kích hoạt.

---

## 2. BẢNG PHÂN TÍCH NGUYÊN NHÂN GỐC RỄ CHI TIẾT

| Mã Test | Mức ưu tiên | Tên test case / Vấn đề phát hiện | Nhóm nguyên nhân | Nguyên nhân gốc rễ (Root Cause) | Giải pháp khắc phục đề xuất | Độ phức tạp / Công sức | Rủi ro |
|:---:|:---:|---|:---:|---|---|:---:|:---:|
| **PR-05** | **P0** | **Mã khuyến mãi hết hạn (TET2025)**<br>*Khách nhập mã hết hạn ở đầu luồng* | **ORCHESTRATION & BACKEND** | Tool `apply_promotion` trong `core/tools.py` bị ràng buộc chặt chẽ với `room_type` và `total_price` (bước `SUMMARY_PROMO`). Khi khách đưa mã ở đầu luồng, bot không gọi tool tra cứu độc lập được nên trả lời trì hoãn sang bước sau thay vì từ chối ngay. | 1. Cập nhật tool `apply_promotion` (hoặc bổ sung `validate_promo_code`) cho phép kiểm tra HSD, trạng thái của mã độc lập mà không bắt buộc phải có phòng trước.<br>2. Bổ sung rule vào System Prompt: Từ chối ngay lập tức khi mã hết hạn/không hợp lệ. | **Thấp**<br>(1 giờ) | **Rất thấp** |
| **AV-04**<br>*(và mở rộng ca 8 người)* | **P1** | **Không có phòng đơn đủ sức chứa**<br>*Khách hỏi đặt 6 hoặc 8 người (phòng lớn nhất Family 4 người)* | **PROMPT & ORCHESTRATION** | 1. `check_availability` tìm phòng đơn có `capacity >= guests`, khi không có phòng nào đủ 8 người thì trả về danh sách rỗng.<br>2. State hiện tại chỉ lưu 1 phòng đơn lẻ `selectedRoom`.<br>3. Prompt chưa có quy tắc hướng dẫn tư vấn chia phòng. | 1. Bổ sung quy tắc trong System Prompt (theo đúng Dòng 65 của System Prompt mục tiêu): Giải thích phòng lớn nhất là 4 người và chủ động đề xuất 2-3 phương án ghép phòng (ví dụ: 2 phòng Family hoặc 4 phòng Deluxe).<br>2. Gợi ý hotline `1900 6868` để lễ tân hỗ trợ sắp xếp phòng liền kề (connecting rooms). | **Trung bình**<br>(1.5 giờ) | **Thấp** |
| **SYS-PROMPT** | **P0** | **System Prompt chưa đồng bộ với bản thiết kế mục tiêu** | **PROMPT** | File `core/rag_engine.py` hiện đang dùng bản prompt rút gọn tạm thời (~15 dòng rules cơ bản), chưa inject đầy đủ các biến môi trường: `today_date`, `hold_minutes=5`, `payment_methods`, `hotline="1900 6868"`, quy tắc FAQ RAG, quy tắc chống prompt injection. | Thay thế nội dung prompt trong `core/rag_engine.py` bằng bản chuẩn giữa `=== BẮT ĐẦU PROMPT ===` và `=== KẾT THÚC PROMPT ===` từ file `System_Prompt_Chatbot_Khach_San.md`. | **Thấp**<br>(0.5 giờ) | **Thấp** |
| **JUDGE-EVAL** | **P1** | **LLM-as-judge sử dụng model bị deprecated (gemini-2.0-flash)** | **TEST / HARNESS** | File `tests/harness/evaluator.py` hardcode `model_name="gemini-2.0-flash"`, khi Google API trả về 404 thì evaluator phải kích hoạt fallback heuristic (chấm điểm mặc định 0.7). | Cập nhật `evaluator.py` đồng bộ sử dụng `settings.GEMINI_MODEL` (`gemini-flash-lite-latest`), bổ sung timeout 30s để đảm bảo việc chấm điểm tự nhiên đạt độ tin cậy tuyệt đối. | **Rất thấp**<br>(15 phút) | **Không có** |
| **HP-05** | P1 | Hoàn thành toàn bộ luồng chỉ bằng nút bấm (quick reply) | **TEST / OUT_OF_SCOPE** | Yêu cầu kiểm thử thao tác click chuột trên các nút bấm UI quick-reply của Frontend DOM. | Ghi nhận thuộc phạm vi Frontend UI, nằm ngoài kiểm thử backend/AI API. | Không sửa code AI | Không |
| **CH-11** | P1 | Bấm nút của bước cũ trong lịch sử chat | **TEST / OUT_OF_SCOPE** | Yêu cầu sự kiện click trên tin nhắn cũ trong DOM UI trình duyệt. | Ghi nhận phạm vi Frontend client. | Không sửa code AI | Không |
| **PM-09** | P0 | Khách tải lại trang (F5) trong thời gian hold phòng | **TEST / OUT_OF_SCOPE** | Yêu cầu kiểm thử khôi phục session state từ LocalStorage/SessionStorage của trình duyệt client. | Đã được xử lý ở Web Frontend client (`localStorage.getItem`). | Không sửa code AI | Không |
| **PM-16** | P2 | Gửi lại mã QR qua Email | **TEST / OUT_OF_SCOPE** | Yêu cầu hạ tầng Mail Server SMTP (chưa cấu hình gửi mail tự động từ AI). | Hướng dẫn khách lưu ảnh QR trực tiếp hoặc tra cứu lại trên giao diện. | Không sửa code AI | Không |
| **ER-12** | P2 | Hiệu ứng phản hồi chậm (Typing/Loading indicator) | **TEST / OUT_OF_SCOPE** | Yêu cầu visual loading effect trên CSS/React Frontend khi mạng chập chờn. | Đã hiện diện ở component `ChatWidget.tsx` trên Frontend. | Không sửa code AI | Không |
| **ER-13** | P1 | Đồng bộ session đa tab trên cùng thiết bị | **TEST / OUT_OF_SCOPE** | Yêu cầu cơ chế BroadcastChannel hoặc WebSocket client giữa các tab trình duyệt. | Thuộc phạm vi Frontend Client Architecture. | Không sửa code AI | Không |
| **CC-04** | P1 | Webhook đến trước khi Frontend Polling | **TEST / OUT_OF_SCOPE** | Yêu cầu kiểm thử cơ chế polling/SSE/WebSocket ở tầng client nhận thông báo từ Backend. | Đã có API `GET /payment/check-order-status/{orderId}` ở Backend hỗ trợ đồng bộ. | Không sửa code AI | Không |

---

## 3. GOM NHÓM LỖI & THỨ TỰ ƯU TIÊN XỬ LÝ (ACTION PLAN CHO GIAI ĐOẠN 4)

Để đảm bảo quy trình cải tiến hệ thống đạt hiệu quả cao nhất và không gây hồi quy (regression), các công việc sửa lỗi ở **Giai đoạn 4** sẽ được gom nhóm và thực hiện tuần tự như sau:

### 🎯 Nhóm 1: Ưu tiên P0 (Bắt buộc cho nghiệp vụ & bảo mật)
1. **Nâng cấp Tool Kiểm tra & Áp dụng Khuyến mãi (`PR-05`):**
   * Cho phép kiểm tra trạng thái khuyến mãi (Active, Hết hạn, Đơn tối thiểu) ngay lập tức khi khách đề cập mã, không cần chờ đến bước thanh toán.
   * Nếu mã hết hạn (ví dụ `TET2025`), bot trả lời từ chối dứt khoát và hướng dẫn khách dùng mã khác hoặc thanh toán giá gốc.
2. **Tích hợp System Prompt mục tiêu (`SYS-PROMPT`):**
   * Thay thế prompt trong `core/rag_engine.py` bằng bản thiết kế chuẩn `System_Prompt_Chatbot_Khach_San.md`.
   * Đảm bảo inject đúng 6 biến động: `today_date=2026-10-13`, `hold_minutes=5`, `hotline="1900 6868"`, `max_nights=30`, `max_days_ahead=365`, `payment_methods=["VietQR PayOS"]`.

### 🎯 Nhóm 2: Ưu tiên P1 (Tối ưu trải nghiệm đặt phòng & Ghép phòng)
1. **Xử lý số lượng khách vượt sức chứa 1 phòng (`AV-04`, `VA-05`):**
   * Bổ sung quy tắc vào prompt và tool: Khi `guests > 4`, bot giải thích sức chứa phòng lớn nhất của Sen Việt là 4 người, tự động tính toán và đưa ra các phương án ghép phòng hợp lý (2 phòng Family hoặc 4 phòng Deluxe) thay vì chỉ báo "hết phòng".
   * Đưa thông tin Hotline `1900 6868` hỗ trợ phòng liền kề cho đoàn.
2. **Cập nhật Model cho Evaluator LLM-as-judge (`JUDGE-EVAL`):**
   * Cập nhật `tests/harness/evaluator.py` sang `gemini-flash-lite-latest` để khôi phục 100% khả năng chấm điểm ngữ nghĩa tự động, loại bỏ fallback heuristic.

### 🎯 Nhóm 3: Nhóm Bị Chặn (Blocked / Out of scope)
* Giữ nguyên trạng thái `Blocked` kèm lý do giải trình minh bạch trong file báo cáo, phục vụ giải trình hội đồng khóa luận (các test này phụ thuộc 100% vào tương tác giao diện người dùng Web Frontend, không thuộc phạm vi xử lý của backend AI microservice).

---

## 4. KẾT LUẬN & ĐỀ XUẤT PHÊ DUYỆT

- **Tổng số lỗi cần sửa:** 1 lỗi P0 (`PR-05`) + 1 ca nâng cấp prompt ghép phòng P1 (`AV-04`) + 1 ca cập nhật System Prompt mục tiêu.
- **Rủi ro kỹ thuật:** Rất thấp (các thay đổi chủ yếu tập trung vào Prompt và hàm validate độc lập của tool, không phá vỡ cấu trúc database PostgreSQL hay PayOS webhook).
- **Thời gian dự kiến hoàn thành Giai đoạn 4:** Khoảng 1.5 – 2 giờ làm việc.
- **Đề xuất:** Kính trình duyệt kế hoạch phân tích nguyên nhân gốc trên để chính thức bước vào **Giai đoạn 4: Sửa lỗi theo vòng lặp (P0 ➔ P1 ➔ P2)**.
