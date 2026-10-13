# GIAI ĐOẠN 0 — KHẢO SÁT & KẾ HOẠCH TEST CHATBOT KHÁCH HÀNG (LUỒNG B)

> Trạng thái: **CHƯA CODE**. Tài liệu này chỉ mô tả hiện trạng, chỗ lệch so với prompt mục tiêu và kế hoạch. Cần anh/chị trả lời mục 7 trước khi sang Giai đoạn 1.
> Phạm vi: 188 test (bỏ 11 test nhóm AD). Ngày test: 13/10/2026 (Thứ Ba).

---

## 1. Stack thực tế

| Thành phần | Hiện trạng |
|---|---|
| AI service | Python 3.12, FastAPI, `google-generativeai` (function calling tự động), model `gemini-flash-lite-latest` (`.env`) |
| Endpoint chat của khách | `POST /api/chat`, `POST /api/ai/chat`, `POST /ai/chat` (cùng một handler, `routers/chat.py`) — **không có xác thực**, FE gọi trực tiếp |
| VectorDB | ChromaDB persistent `./chroma_data`, collection `senviet_hotel_knowledge`, `hnsw:space=cosine`, embedding mặc định của Chroma (all-MiniLM-L6-v2, 384 chiều, **không tối ưu tiếng Việt**). `TOP_K=15`, ngưỡng 0.35 |
| Backend nghiệp vụ | Spring Boot 4.1 / Java 17 (JDK máy là 23), PostgreSQL 18 DB `hotelmanagement` |
| Tạo booking từ chat | AI gọi `POST http://localhost:8081/api/internal/chatbot/book` (`ChatbotController` → `ChatbotBookingServiceImpl`) — **permitAll, không xác thực service-to-service** |
| PayOS | AI tự gọi `api-merchant.payos.vn` trong `create_payment_qr`; webhook `POST /payment/webhook/payos` ở Spring Boot |
| Hết hạn hold | `BookingExpiryScheduler`: mỗi 60s hủy booking `PENDING` quá **5 phút** (hardcode) |
| Frontend khách | `SenVietHotelManagement` (React/Vite), render UI từ trường `state` trả về |

## 2. Hiện trạng orchestration Luồng B

```
FE ──POST /api/chat {message, sessionId, history}──► FastAPI
   1. similarity_search(message, k=15) → lọc score ≥ 0.35 → nhồi vào message (luôn chạy, không phải tool)
   2. Ghép [STATE JSON] + [FAQ context] + [ngày datetime.now()] + câu khách
   3. Gemini + automatic function calling (10 tool) → text tự do
   4. Trả {reply, sessionId, state(BookingState đầy đủ), ragMetrics}
```

- **Không có bước phân loại intent riêng.** Gemini tự quyết gọi tool nào. "Intent" trong sơ đồ chỉ tồn tại ngầm trong prompt.
- **BookingState có** (`core/state_manager.py`) nhưng: lưu **in-memory** (mất khi restart, không chia sẻ giữa worker), không có `holdExpiresAt`, `step` chỉ do tool gán, không có tầng validate/transition — state machine thực chất nằm trong prompt.
- Câu trả lời là **text tự do**, không phải JSON theo schema.

## 3. Lệch so với system prompt mục tiêu

### 3.1 Schema đầu ra

| Mục tiêu | Hiện tại | Ghi chú |
|---|---|---|
| `{text, ui_components[], state_update, next_step, tool_calls}` | `{reply, sessionId, state, ragMetrics}` | FE đang render card từ `state` (availableRooms, availableServices, availablePromotions, qrUrl...). Đổi schema = phải sửa FE → **cần quyết định (Q1)** |

### 3.2 Tool

| Tool mục tiêu | Tool hiện có | Lệch |
|---|---|---|
| `list_branches()` | `list_branches()` | Không lọc chi nhánh active |
| `check_availability(branch, checkIn, checkOut, guests)` | `check_availability(branch_id, check_in, check_out, adults, children)` | **`availableQty` hardcode = 5**, không kiểm tra booking trùng ngày, không loại MAINTENANCE, không validate ngày, giá chỉ `base_price` (không tính cuối tuần/lễ) |
| `list_services(branch)` | `list_services(branch_id)` | **Bỏ qua branch_id** (lấy dịch vụ mọi chi nhánh) |
| `list_valid_promotions(bookingDraft)` | `list_valid_promotions()` | Chỉ lọc `status='ACTIVE'`; không kiểm tra hạn, đơn tối thiểu, phạm vi, lượt dùng |
| `calculate_price(bookingDraft)` | `calculate_price(room_price, nights, room_qty, promo_code)` | **LLM truyền `room_price`** → LLM có thể đưa giá sai; dịch vụ luôn tính `adults × nights` cho mọi loại; `FIXED_AMOUNT` không giới hạn; hack `DEMO2K` → tổng 2.000đ |
| `create_booking(bookingDraft)` | `create_booking(payment_method)` | Không idempotent (gọi 2 lần = 2 booking); chọn phòng `LIMIT n` không khóa; fallback ngày cứng `2026-10-15`, tên "Khách Ẩn Danh", SĐT `0000000000` |
| `create_payment_qr(bookingId)` | `create_payment_qr(booking_id, amount)` | **LLM truyền `amount`** → số tiền QR có thể lệch tổng booking; **khóa PayOS thật hardcode làm giá trị mặc định trong code**; lỗi PayOS → fallback QR VietQR tĩnh thay vì báo lỗi |
| `get_payment_status(bookingId)` | — | **Thiếu** |
| `get_booking(bookingCode, auth)` | — | **Thiếu** |
| `cancel_booking(bookingId)` | — | **Thiếu** |
| `search_faq(query)` | (RAG nhồi sẵn mỗi lượt) | Không phải tool; luôn chạy kể cả câu đặt phòng |
| — | `update_guest_info`, `select_room_and_services`, `apply_promotion` | Không validate (SĐT/email/tên); `apply_promotion` nhận mọi chuỗi |

### 3.3 State machine

| Bước mục tiêu | Hiện tại |
|---|---|
| branch → dates_guests → room → guest_info → services → summary_promo → confirm → payment_method → awaiting_payment → done | SELECT_BRANCH → SELECT_ROOM → GET_GUEST_INFO → SELECT_SERVICES → SUMMARY_PROMO → SELECT_PAYMENT → PAYMENT_PROCESSING |
| Thứ tự: thông tin khách **trước** dịch vụ | `select_room_and_services` gộp phòng + dịch vụ rồi mới hỏi thông tin khách |
| Bước **confirm** riêng | **Không có** — prompt hiện tại (quy tắc 5) cho phép "đồng ý chốt" → gọi thẳng `create_booking` + QR |
| Reset phụ thuộc khi đổi chi nhánh/ngày | **Không có** |
| `faq`, `handoff`, `done` | Không có |

### 3.4 Biến cần inject

| Biến | Hiện tại |
|---|---|
| `current_date` | `datetime.now()` trong `rag_engine.py` — **không freeze được**, chỉ có ngày không có giờ (VA-09 cần giờ) |
| `hold_minutes` | Prompt ép **5 phút**; scheduler hardcode 5; prompt mục tiêu ví dụ 15 → **Q3** |
| `payment_methods` | `BANK_TRANSFER`, `CASH` (prompt nói "chuyển khoản hay tiền mặt") → **Q4** |
| `hotline` | Không có trong code/prompt → **Q5** |
| `max_nights`, `max_days_ahead` | Không có → **Q6** |

### 3.5 Các điểm nguy cơ khác (phát hiện khi đọc code)

1. **Quy tắc DEMO2K** trong prompt hiện tại *bắt buộc* AI chấp nhận mã nội bộ, và backend hack `DEMO2K` đặt tổng = 2.000đ. Mâu thuẫn trực tiếp với SC-12, PR-12, ER-06 → **Q2**.
2. `SecurityConfig` để `permitAll` cho `/api/internal/chatbot/**`, `/bookings/**`, `/orders/**`, `/payment/**`, `/customer/**`... → ai cũng gọi được API booking qua HTTP, không xác thực quyền sở hữu (ảnh hưởng CA-03, CA-05, SC-05, SC-06).
3. Webhook PayOS: chưa xác minh có kiểm tra chữ ký (`signature`) và idempotent không → kiểm tra ở Giai đoạn 1 (PM-13).
4. Không có rate limit ở FastAPI lẫn Spring Boot (SC-10).
5. CORS `allow_origins=["*"]` + `allow_credentials=True`.
6. Lỗi tool trả nguyên `str(e)` cho LLM → có thể lộ tên bảng/SQL ra khách (ER-02).
7. `chat.py` trả `HTTPException(500, detail=str(e))` → lộ chi tiết lỗi.

## 4. (a) Bảng ánh xạ dữ liệu mẫu → dữ liệu thật

| Trong test | Dữ liệu thật / đề xuất seed test |
|---|---|
| CN "Quận 1" / "Q1" | `Sen Việt Sài Gòn` (id 1, 123 Lê Lợi, Quận 1) |
| CN "Đà Nẵng" | `Sen Việt Đà Nẵng` (id 3) |
| Hạng Standard / Deluxe | Có thật (`branch_room_policies`, enum `STANDARD`, `DELUXE`) |
| Hạng Superior / Suite | **Chưa có trong DB thật.** Đề xuất: seed vào DB test nếu enum `RoomType` của Java có giá trị tương ứng; nếu không → **Q7** |
| Spa / Đưa đón / Ăn sáng | `Spa & Massage` (500.000đ/lượt), `Đưa đón sân bay` (300.000đ/chuyến), `Buffet Sáng` (250.000đ/khách) — đã seed mỗi chi nhánh |
| SEN10, VIP20 (min 2.000.000đ), TET2025 (hết hạn), STAFF100 (nội bộ), mã chỉ Suite, mã 1 lần/khách, mã 50% trần 300.000đ | Chỉ seed trong **DB test**, không đụng DB thật |
| Booking `SV12345`, `ZZZ999` | Seed booking test gắn với khách test; mã thật dạng `bookingId`/`orderCode` |
| Giá cuối tuần/lễ | Bảng `room_seasonal_rates` (đang trống) → seed DB test |

| Tool trong test | Tool/API thật |
|---|---|
| `list_branches` | `core/tools.list_branches` (SQL trực tiếp) |
| `check_availability` | `core/tools.check_availability` (SQL) |
| `list_services` | `core/tools.list_services` |
| `list_valid_promotions` | `core/tools.list_valid_promotions` |
| `calculate_price` | `core/tools.calculate_price` (Python) — **trùng logic với giá tính ở Spring Boot** `createCustomerBooking` → có thể lệch nhau |
| `create_booking` | `tools.create_booking` → `POST /api/internal/chatbot/book` |
| `create_payment_qr` | `tools.create_payment_qr` → PayOS trực tiếp từ Python (Spring Boot cũng có `PaymentServiceImpl` tạo QR riêng) |
| `get_payment_status`, `get_booking`, `cancel_booking`, `search_faq` | **Chưa có** |

## 5. (b) Kiến trúc test harness đề xuất

```
pytest (tests/chatbot/)
 ├─ conftest.py
 │   ├─ DB test: PostgreSQL `hotelmanagement_test` (seed SQL cố định, reset mỗi test/module)
 │   ├─ Freeze time: module `core/clock.py` (now() đọc từ biến môi trường AI_FROZEN_NOW, mặc định giờ thật)
 │   ├─ ChromaDB test: thư mục tạm, nạp bộ chính sách mẫu (gồm chính sách hủy anh/chị cung cấp + 1 đoạn "cũ" cho IN-17 + 1 đoạn chứa injection cho SC-15)
 │   ├─ PayOS mock: FastAPI stub (localhost:9100) — tạo link/QR, bắn webhook: thành công / thiếu / dư / trùng / trễ / hết hạn / lỗi
 │   └─ Fault injection: biến môi trường/monkeypatch cho timeout/500 từng tool, Chroma down, Gemini 429/5xx/JSON hỏng
 ├─ scenarios/*.yaml  (188 kịch bản, giữ nguyên ID; mỗi kịch bản: preconditions, turns[], assertions)
 ├─ runner: gọi FastAPI qua httpx (ASGI in-process) → POST /api/chat, ghi trace tool call
 ├─ assertions
 │   ├─ deterministic: tool được/không được gọi, state, số tiền khớp DB, số booking/QR trong DB, trạng thái booking
 │   └─ judge: Gemini temperature=0 + rubric từ cột H (KHÔNG dùng cho P0 tiền/bảo mật)
 └─ reporter: điền cột J/K/L vào BẢN SAO xlsx + REPORT_*.md
```

- Chạy lặp: P0/P1 × 3 lần (Pass khi cả 3 đạt), P2 × 1–2 lần; ghi tỉ lệ flaky.
- Test cần Spring Boot (create_booking, webhook, CC-*): chạy Spring Boot với profile `test` trỏ DB `hotelmanagement_test`, PayOS client trỏ mock.
- Trace tool call: bọc mỗi tool bằng decorator ghi log vào context của request (không đổi hành vi).

## 6. (c) Phân loại khả năng tự động hóa

| Loại | Test | Cách xử lý |
|---|---|---|
| Tự động qua API chat (đa số) | HP, SF, CH, VA, SV, PR, CF, IN, LG, OT, SC (trừ SC-10), CA | Kịch bản nhiều lượt |
| Cần mock PayOS / Spring Boot test profile | HP-01/04, PM-01..16, CH-08/09, CF-07, AV-03, ER-08/09, CC-01..04 | PayOS stub + webhook giả |
| Cần tiêm lỗi | ER-01..05, ER-07, IN-09, ER-03 | Fault injection |
| Cần biến thể seed | HP-06 (1 chi nhánh), AV-01/05, AV-07, SV-08, ER-07, PR-02 | Seed riêng theo test |
| Phụ thuộc frontend → dự kiến **Blocked** hoặc kiểm tra một phần qua API | HP-05 & CH-11 (bấm nút — API chưa có payload nút), ER-12 (typing indicator), ER-13 (2 tab), PM-09 (khôi phục QR khi F5 — kiểm phần API theo sessionId), CC-04 (polling FE), PM-16 (gửi email QR) | Ghi rõ lý do ở cột L |
| Cần đo tải | SC-10 (rate limit) | Script bắn N request; hiện chắc chắn Fail (chưa có rate limit) |

## 7. (d) Rủi ro

| Rủi ro | Mức | Giảm thiểu |
|---|---|---|
| **Quota Gemini**: 188 test × ~3–6 lượt × 3 lần lặp + judge ≈ 3.000–6.000 request/lần chạy; free tier flash-lite ~1.500 request/ngày | Cao | Cần key test có trả phí, hoặc chạy chia nhiều ngày / giảm lặp |
| Codebase AI **không có git repo riêng** (git root là `C:\Users\admin\Downloads`) → không commit nhỏ an toàn được | Cao | Q8 |
| Khóa PayOS thật đang hardcode trong `core/tools.py` | Cao | Chuyển sang biến môi trường, mock trong test; khuyến nghị đổi khóa (đã lộ trong code) |
| Freeze time phía Java (scheduler, validate ngày) | Trung bình | Chỉ freeze phía AI; phía Java dùng ngày thật (hôm nay cũng là 13/10/2026), ghi chú khi chạy ngày khác |
| Hai nơi tính giá (Python `calculate_price` và Java) có thể lệch | Trung bình | Đề xuất Giai đoạn 4: một nguồn giá duy nhất (Spring Boot) |
| LLM không tất định → flaky | Trung bình | temperature=0, 3 lần lặp, assertion tất định cho P0 |
| Embedding MiniLM yếu tiếng Việt → test RAG fail do retrieval | Trung bình | Ghi nhận ở baseline; đề xuất đổi embedding đa ngữ ở Giai đoạn 4 (cần re-index) |

---

## 8. CÂU HỎI CẦN ANH/CHỊ QUYẾT ĐỊNH (chặn Giai đoạn 1)

**Q1. Schema đầu ra.** Prompt mục tiêu yêu cầu JSON `{text, ui_components, state_update, next_step, tool_calls}`, còn FE đang đọc `{reply, state}`. Chọn:
- (a) Giữ API cũ cho FE; bên trong FastAPI dùng JSON mục tiêu rồi map sang `reply` + `state` (+ thêm trường `ui_components`, `next_step` không làm vỡ FE). *Đề xuất.*
- (b) Đổi hẳn API và sửa FE.

**Q2. Mã DEMO2K.** Prompt hiện tại ép AI chấp nhận DEMO2K, backend hack tổng = 2.000đ. Điều này làm Fail SC-12/PR-12/ER-06. Chọn: (a) bỏ hẳn hack, DEMO2K thành mã thật trong bảng promotions (nếu cần demo); (b) chỉ bật DEMO2K qua cờ cấu hình khi demo, tắt trong test; (c) giữ nguyên (chấp nhận Fail).

**Q3. Thời gian giữ phòng (`hold_minutes`)**: 5 phút (như hiện tại) hay 15 phút?

**Q4. Phương thức thanh toán thật sự bật**: chỉ chuyển khoản QR PayOS? Có "thanh toán tại khách sạn" (`CASH` → `CONFIRMED_PAY_AT_HOTEL`) không? Nếu không, HP-04 và CH-09 sẽ được kiểm theo hướng "bot từ chối đúng".

**Q5. Hotline** dùng trong câu trả lời là số nào?

**Q6. Giới hạn**: `max_nights` (đề xuất 30), `max_days_ahead` (đề xuất 365), số người tối đa mỗi phòng/booking, giờ cut-off nhận phòng muộn (VA-09)?

**Q7. Hạng phòng**: hệ thống chỉ có Standard/Deluxe. Cho phép seed thêm Superior/Suite **trong DB test** (nếu enum Java hỗ trợ) hay chuyển các test nhắc Superior/Suite sang Standard/Deluxe tương đương (ghi chú cột L, không sửa cột A–I)?

**Q8. Git**: thư mục AI đang nằm trong một repo git chung ở `Downloads` (chứa nhiều project khác). Cho phép em `git init` repo riêng cho `KLTN_HotelManagementAI` (kèm `.gitignore` loại `.env`, `venv`, `chroma_data`) để commit nhỏ theo từng nhóm sửa? Phần sửa Spring Boot sẽ commit vào repo `KLTN_HotelManagementBE` (đang có thay đổi chưa commit — em sẽ không đụng các file đó trừ khi cần).

**Q9. Khóa Gemini cho test**: dùng key nào (riêng cho test, có trả phí hay free)? Nếu free, chấp nhận giảm lặp (P0/P1 × 2) hoặc chạy chia nhiều ngày?

**Q10. Chính sách hủy** — cần làm rõ ranh giới để tính số tiền hoàn tất định (CA-04, CA-07, PM-15):
- Hủy **trước hơn 7 ngày**: miễn phí (100%) như mục 3–7 ngày?
- "Trước 1–2 ngày (50%)" và "trong vòng 24 giờ trước check-in (100%)": em đề xuất mốc tính theo giờ check-in 14:00: ≥ 72h → hoàn 100%; 24h–72h → hoàn 50%; < 24h hoặc no-show → không hoàn. Đúng không?
- "Phạt 100% tiền cọc hoặc tiền đêm đầu tiên": hệ thống thanh toán toàn bộ trước qua QR, vậy no-show là mất toàn bộ số đã trả hay chỉ tiền đêm đầu?
- Booking "thanh toán tại khách sạn" (nếu có) hủy thì xử lý thế nào?

**Q11. Nghiệp vụ chat**: có hỗ trợ trên chat (a) tra cứu booking, (b) hủy booking đã thanh toán, (c) sửa ngày booking đã xác nhận, (d) đặt hộ người khác, (e) cộng dồn 2 mã giảm giá? Phần nào "chưa hỗ trợ → chuyển nhân viên" là hành vi đúng?
