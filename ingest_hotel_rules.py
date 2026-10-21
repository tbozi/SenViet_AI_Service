# -*- coding: utf-8 -*-
"""
Script nạp toàn bộ Nội quy khách sạn (Hotel Rules) vào Vector Store (ChromaDB + PostgreSQL)
và cập nhật system prompt của RAG Engine trong KLTN_HotelManagementAI.
"""
import sys
import os

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.append("C:/Users/admin/Downloads/KLTN_HotelManagementAI")

from core.vector_store import VectorStoreManager

documents = [
    {
        "id": "policy_dat_phong",
        "text": """Quy định Đặt phòng Khách sạn Sen Việt:
- Kiểm tra ngày lưu trú, loại phòng, số lượng khách và thông tin liên hệ trước khi xác nhận booking.
- Giá và tình trạng phòng được áp dụng theo booking đã xác nhận.
- Các dịch vụ đặt kèm được tính theo số lượng và đơn giá ghi trên booking.""",
        "metadata": {
            "category": "Nội quy khách sạn",
            "type": "BookingRules",
            "title": "Quy định Đặt phòng",
            "keywords": "đặt phòng, kiểm tra booking, giá phòng, dịch vụ kèm, xác nhận booking"
        }
    },
    {
        "id": "policy_khuyen_mai",
        "text": """Quy định Sử dụng và Hủy Khuyến mãi (Voucher / Mã giảm giá):
- Mỗi mã khuyến mãi chỉ được áp dụng một lần cho từng khách hàng.
- Khách có tài khoản chính thức được sử dụng mỗi mã tối đa một lần cho tài khoản đó.
- Khách vãng lai cũng chỉ được sử dụng mỗi mã một lần; hệ thống ghi nhận việc sử dụng theo thông tin khách trên booking (Số điện thoại / Email).
- Khi mã đã được áp dụng vào booking, quyền sử dụng mã được tính là ĐÃ DÙNG.
- ĐẶC BIỆT: Nếu booking đó bị hủy, mã khuyến mãi KHÔNG ĐƯỢC HOÀN LẠI và khách KHÔNG THỂ DÙNG LẠI MÃ ĐÓ.""",
        "metadata": {
            "category": "Nội quy khách sạn",
            "type": "PromotionRules",
            "title": "Quy định Khuyến mãi & Hủy mã",
            "keywords": "khuyến mãi, voucher, giảm giá, mã ưu đãi, khách vãng lai, hủy booking có mã, hoàn mã khuyến mãi"
        }
    },
    {
        "id": "policy_checkin_som",
        "text": """Chính sách Phụ thu Nhận phòng sớm (Check-in sớm):
Giờ check-in tiêu chuẩn của khách sạn là 14:00. Có thể phát sinh phụ thu tùy thời điểm khách nhận phòng thực tế so với giờ check-in đã đặt:
- Trước 06:00 sáng: Phụ thu 100% giá phòng ngày đó.
- Từ 06:00 đến 09:00 sáng: Phụ thu 50% giá phòng ngày đó.
- Sau 09:00 đến trước giờ check-in đã đặt (14:00): Phụ thu 30% giá phòng ngày đó.
- Nếu nhận phòng từ ngày trước ngày đặt: Tính 100% giá phòng của ngày nhận sớm đó; nhận sớm nhiều ngày thì tính đủ giá từng ngày sớm.""",
        "metadata": {
            "category": "Nội quy khách sạn",
            "type": "EarlyCheckin",
            "title": "Chính sách Check-in sớm",
            "keywords": "checkin sớm, nhận phòng sớm, phụ thu checkin sớm, mấy giờ nhận phòng, trước 6h, 6h đến 9h, sau 9h"
        }
    },
    {
        "id": "policy_checkout_tre",
        "text": """Chính sách Phụ thu Trả phòng trễ (Check-out trễ):
Giờ check-out tiêu chuẩn là 12:00. Phụ thu được tính theo giá phòng ngày check-out và tự cập nhật vào tổng booking khi phát sinh:
- Đến trước 12:30: MIỄN PHÍ, KHÔNG TÍNH PHỤ THU (khách sạn hỗ trợ quý khách trả phòng đến 12:30 không tính thêm tiền).
- Từ 12:30 đến 15:00: Phụ thu 30% giá phòng ngày đó.
- Sau 15:00 đến 18:00: Phụ thu 50% giá phòng ngày đó.
- Sau 18:00 hoặc trả sang ngày hôm sau: Phụ thu 100% giá phòng ngày đó.""",
        "metadata": {
            "category": "Nội quy khách sạn",
            "type": "LateCheckout",
            "title": "Chính sách Check-out trễ",
            "keywords": "checkout trễ, trả phòng trễ, muộn, phụ thu trả trễ, 12h30, 15h, 18h, miễn phí đến 12h30"
        }
    },
    {
        "id": "policy_hoan_tien_huy_booking",
        "text": """Chính sách Hủy booking & Hoàn tiền (Cancellation & Refund Policy):
Mức khấu trừ tiền phòng phụ thuộc vào thời điểm yêu cầu hủy so với giờ check-in đầu tiên của booking:
- Từ 72 giờ trước check-in trở lên (trước từ 3 ngày trở lên): KHÔNG ÁP DỤNG PHẠT TIỀN PHÒNG (Hoàn 100% tiền phòng).
- Từ 24 đến dưới 72 giờ (từ 1 ngày đến dưới 3 ngày trước check-in): Mức phạt là 50% phần tiền phòng được phân bổ (Hoàn 50% tiền phòng).
- Dưới 24 giờ hoặc khách không đến (No-show): Mức phạt là 100% phần tiền phòng được phân bổ (Phạt toàn bộ tiền phòng, không hoàn).
QUY ĐỊNH HOÀN TIỀN DỊCH VỤ KHI HỦY:
- Toàn bộ phần tiền đã thanh toán được phân bổ cho DỊCH VỤ ĐƯỢC HOÀN 100%; mức phạt hủy CHỈ KHẤU TRỪ VÀO PHẦN TIỀN PHÒNG!
- Số tiền hoàn cuối cùng căn cứ vào số đã thanh toán và cách phân bổ giữa tiền phòng, dịch vụ, giảm giá và phụ thu của booking; nhân viên sẽ kiểm tra yêu cầu hoàn trước khi xác nhận.""",
        "metadata": {
            "category": "Nội quy khách sạn",
            "type": "CancellationRefund",
            "title": "Hoàn tiền do hủy booking",
            "keywords": "hủy phòng, hủy booking, hoàn tiền, phạt hủy, 72 giờ, 24 giờ, no show, hoàn tiền dịch vụ, chính sách hủy"
        }
    },
    {
        "id": "policy_hoan_tien_du_checkout",
        "text": """Chính sách Hoàn tiền dư khi Checkout:
- Đây là khoản hoàn phát sinh khi đối soát lúc checkout, KHÔNG PHẢI khoản hoàn do hủy booking.
- Phát sinh khi khách đã thanh toán nhiều hơn tổng chi phí thực tế, ví dụ: dịch vụ đã thanh toán trước nhưng chưa sử dụng và được hủy trước checkout.
- Hoàn theo số tiền khách thực trả vượt quá số tiền cuối cùng phải thanh toán; KHÔNG áp dụng mức phạt hủy phòng.
- Nhân viên kiểm tra lại tiền phòng, dịch vụ đã dùng, dịch vụ đã hủy, phụ thu và giảm giá trước khi xác nhận số tiền hoàn.
- Xử lý theo phương thức hoàn đã chọn: Tiền mặt tại quầy lễ tân hoặc chuyển khoản/hoàn online.""",
        "metadata": {
            "category": "Nội quy khách sạn",
            "type": "ExcessRefundCheckout",
            "title": "Hoàn tiền dư khi Checkout",
            "keywords": "hoàn tiền dư, đối soát checkout, tiền thừa, dịch vụ chưa sử dụng được hủy, hoàn tiền mặt, hoàn chuyển khoản"
        }
    },
    {
        "id": "policy_dich_vu_khach_san",
        "text": """Quy định về Dịch vụ Khách sạn:
- Nhân viên xác nhận dịch vụ sau khi khách sử dụng.
- Dịch vụ ĐÃ SỬ DỤNG: KHÔNG THỂ HỦY.
- Đối chiếu tên dịch vụ, số lượng và đơn giá với khách.
- Dịch vụ CHƯA SỬ DỤNG: Nếu dịch vụ chưa sử dụng, hãy hủy trước khi checkout để cập nhật lại số tiền khách cần thanh toán hoặc được hoàn lại.""",
        "metadata": {
            "category": "Nội quy khách sạn",
            "type": "HotelServicesRules",
            "title": "Quy định Dịch vụ khách sạn",
            "keywords": "dịch vụ khách sạn, hủy dịch vụ, dịch vụ đã dùng, dịch vụ chưa dùng, xác nhận dịch vụ"
        }
    },
    {
        "id": "policy_doi_soat_thanh_toan_email",
        "text": """Quy định Đối soát Thanh toán, Thời gian hoàn tiền & Thông báo Email:
- Công thức tổng cuối cùng: Tổng cuối cùng bao gồm tiền phòng + dịch vụ + phụ thu check-in sớm + phụ thu check-out trễ + phụ thu khác - giảm giá.
- Đối soát: So sánh tổng booking với số đã thanh toán để xác định số còn phải thu hoặc số tiền cần hoàn.
- Chọn đúng phương thức hoàn tiền và xác nhận giao tiền/chuyển khoản theo quy trình của khách sạn.
- THỜI GIAN HOÀN TIỀN: Hoàn tiền qua tài khoản ngân hàng dự kiến mất từ 1 – 3 ngày làm việc.
- THÔNG BÁO EMAIL: Khách sẽ nhận email xác nhận tự động khi:
  1. Khi đặt booking
  2. Khi thanh toán được ghi nhận
  3. Khi checkout hoàn tất
  4. Khi khoản hoàn tiền đã được xử lý
  (Lưu ý: Email chỉ gửi được khi booking có địa chỉ email hợp lệ).""",
        "metadata": {
            "category": "Nội quy khách sạn",
            "type": "PaymentReconciliationEmail",
            "title": "Đối soát thanh toán & Email",
            "keywords": "đối soát thanh toán, công thức tính tổng, thời gian hoàn tiền, 1 đến 3 ngày, email xác nhận, gửi email"
        }
    }
]

def main():
    print("=" * 60)
    print("NẠP 8 TÀI LIỆU NỘI QUY KHÁCH SẠN VÀO VECTOR STORE (CHROMADB + POSTGRESQL)")
    print("=" * 60)
    vm = VectorStoreManager()
    count = vm.index_documents(documents)
    print(f"[+] Thành công nạp {count} tài liệu nội quy vào ChromaDB & PostgreSQL!")

    print("\n[+] Kiểm tra thử nghiệm Similarity Search:")
    test_queries = [
        "Tôi muốn check in sớm lúc 7h sáng thì phụ thu bao nhiêu?",
        "Trả phòng muộn lúc 12h15 có mất tiền không?",
        "Hủy phòng trước 2 ngày bị phạt bao nhiêu phần trăm?",
        "Hủy booking thì có được dùng lại mã giảm giá không?",
        "Hoàn tiền qua ngân hàng mất mấy ngày?",
        "Dịch vụ đã dùng rồi có hủy được không?"
    ]
    for q in test_queries:
        res = vm.similarity_search(q, k=1)
        if res:
            top = res[0]
            print(f" -> Query: '{q}'\n    Top Match: [{top['id']}] (score: {top['score']:.4f}) - {top['text'][:80]}...\n")

if __name__ == "__main__":
    main()
