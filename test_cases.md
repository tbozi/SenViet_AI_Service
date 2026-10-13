# Bộ Test Case Hội Thoại Đặt Phòng - AI Chatbot (State Machine)

## Luồng chuẩn (Happy Path)
**Test 1: Khách đặt phòng từng bước**
- User: "Mình muốn đặt phòng ở Đà Lạt" -> Bot: Xin ngày check-in, số người.
- User: "Ngày mai đến, ở 2 đêm, 2 người lớn" -> Bot: Gọi check_availability, render card các hạng phòng.
- User: "Chọn phòng Standard" -> Bot: Gọi select_room_and_services, xin thông tin khách.
- User: "Mình là Hiếu, 0909123456, hieu@gmail.com" -> Bot: Gọi update_guest_info, đưa ra tóm tắt, hỏi có mã giảm giá không.
- User: "Không có mã, thanh toán đi" -> Bot: Gọi create_booking, create_payment_qr, render QR code.

## Khai báo gộp (Slot Filling đa tham số)
**Test 2: Khách cung cấp nhiều thông tin cùng lúc**
- User: "Cho mình 1 phòng Deluxe tại Sài Gòn cuối tuần này (thứ 7) cho 2 người lớn và 1 trẻ em."
- Bot: Hiểu chi nhánh "Sài Gòn", ngày checkin (thứ 7 tuần này), số người. Gọi ngay `check_availability` -> Render danh sách phòng -> Hỏi xác nhận phòng Deluxe và xin thông tin cá nhân. Bỏ qua hoàn toàn các bước hỏi chi nhánh, hỏi ngày, hỏi người.

## Thay đổi ý định (Intent Change)
**Test 3: Khách đổi ngày / đổi chi nhánh giữa chừng**
- (Đang ở bước xin thông tin cá nhân sau khi chọn phòng Sài Gòn)
- User: "À thôi, đổi cho mình sang đi Đà Lạt vào tuần sau nhé."
- Bot: Cập nhật State, xóa Room cũ, đổi chi nhánh và ngày. Gọi lại `check_availability` cho Đà Lạt -> Trả về danh sách phòng ở Đà Lạt.

**Test 4: Khách đổi hạng phòng**
- (Đã chọn phòng Standard)
- User: "Thôi cho mình lấy phòng Deluxe cho rộng"
- Bot: Gọi `select_room_and_services(room_type="DELUXE")` -> Cập nhật giá, tóm tắt lại.

## Xử lý Ngoại lệ
**Test 5: Hết phòng**
- User: "Mình muốn đặt phòng Sài Gòn ngày 1/1/2026 cho 20 người"
- Bot: Gọi `check_availability` -> Kết quả mảng `rooms` rỗng. Bot xin lỗi, gợi ý khách thử ngày khác hoặc chi nhánh khác.

**Test 6: Mã giảm giá không hợp lệ**
- (Đang ở bước SUMMARY_PROMO)
- User: "Áp mã HACKER99"
- Bot: Gọi tool `apply_promotion` -> Không tìm thấy mã (hoặc `calculate_price` trả về discount = 0). Bot báo mã không hợp lệ, hỏi có muốn áp mã khác hay tiếp tục thanh toán gốc.

**Test 7: QR hết hạn / Đổi ý thanh toán**
- (Đã hiện QR thanh toán)
- User: "Mã QR bị lỗi rồi, cho mình xin mã khác"
- Bot: Gọi lại `create_payment_qr` để sinh QR mới với `amountToPay` hiện tại.

**Test 8: Gõ tiếng Việt không dấu**
- User: "dat phong da lat 2 nguoi ngay mai"
- Bot: Hiểu ý định -> Gọi `check_availability` -> Render các phòng tại Đà Lạt.

## Chen ngang (Interruption - FAQ)
**Test 9: Hỏi chính sách giữa lúc đặt phòng**
- (Bot đang hỏi thông tin cá nhân)
- User: "Khách sạn có cho mang chó mèo vào không em?"
- Bot: Tìm Context RAG -> "Dạ khách sạn Sen Việt không hỗ trợ mang thú cưng ạ. Anh/chị thông cảm nhé! Để tiếp tục đặt phòng, anh/chị cho em xin Họ Tên và SĐT nha!"

**Test 10: Lỗi hệ thống Backend (Giả lập)**
- User: "Cho mình danh sách chi nhánh"
- (Nếu Tool `list_branches` bị sập DB, trả về `{"status": "error"}`)
- Bot: Đọc status "error", nhẹ nhàng báo: "Dạ hiện tại hệ thống đang nâng cấp nên em chưa lấy được danh sách. Anh/chị chờ vài phút hoặc gọi hotline 19008888 nhé!"
