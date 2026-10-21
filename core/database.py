import psycopg2
from psycopg2.extras import RealDictCursor
from typing import List, Dict, Any
from config.settings import settings

def get_db_connection():
    return psycopg2.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        dbname=settings.DB_NAME,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD
    )

def fetch_hotel_knowledge() -> List[Dict[str, Any]]:
    """
    Trích xuất toàn bộ dữ liệu nghiệp vụ khách sạn từ PostgreSQL 
    và đóng gói thành các đoạn tài liệu (chunks) kèm metadata phục vụ Vector Database.
    """
    documents = []

    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # 1. Thông tin các chi nhánh khách sạn
        cur.execute("""
            SELECT h.id, h.name, h.address, h.phone, p.name AS province_name
            FROM hotels h
            LEFT JOIN provinces p ON h.province_id = p.province_id;
        """)
        hotels = cur.fetchall()
        for h in hotels:
            text = (
                f"Chi nhánh khách sạn: {h['name']}.\n"
                f"Địa chỉ: {h['address']}.\n"
                f"Tỉnh/Thành phố: {h['province_name'] or 'N/A'}.\n"
                f"Số điện thoại liên hệ hotline: {h['phone'] or '1900 8888'}."
            )
            documents.append({
                "id": f"hotel_{h['id']}",
                "text": text,
                "metadata": {
                    "category": "hotel_branch",
                    "hotel_id": h["id"],
                    "hotel_name": h["name"]
                }
            })

        # 2. Chính sách loại phòng và bảng giá theo chi nhánh
        cur.execute("""
            SELECT brp.policy_id AS id, brp.room_type, brp.base_price, brp.standard_capacity, 
                   brp.extra_adult_fee, brp.extra_child_fee, brp.max_extra_guests,
                   h.name AS hotel_name, h.id AS hotel_id, p.name AS province_name, h.address
            FROM branch_room_policies brp
            JOIN hotels h ON brp.hotel_id = h.id
            LEFT JOIN provinces p ON h.province_id = p.province_id;
        """)
        policies = cur.fetchall()
        for pol in policies:
            base_price = int(pol['base_price']) if pol['base_price'] else 0
            prov = pol['province_name'] or ''
            addr = pol['address'] or ''
            text = (
                f"Bảng giá phòng chi nhánh {pol['hotel_name']} (tại {prov}, {addr}):\n"
                f"- Hạng phòng: {pol['room_type']}.\n"
                f"- Giá niêm yết cơ bản: {base_price:,} VNĐ/đêm.\n"
                f"- Sức chứa tiêu chuẩn: {pol['standard_capacity']} khách người lớn.\n"
                f"- Phụ thu người lớn thêm: {int(pol['extra_adult_fee'] or 0):,} VNĐ/người.\n"
                f"- Phụ thu trẻ em thêm: {int(pol['extra_child_fee'] or 0):,} VNĐ/trẻ."
            )
            documents.append({
                "id": f"policy_{pol['id']}",
                "text": text,
                "metadata": {
                    "category": "room_policy",
                    "hotel_id": pol["hotel_id"],
                    "hotel_name": pol["hotel_name"],
                    "province": prov,
                    "room_type": pol["room_type"]
                }
            })

        # 3. Tiện ích phòng (Amenities)
        cur.execute("SELECT amenity_id, name, price FROM amenities;")
        amenities = cur.fetchall()
        for a in amenities:
            price_val = int(a['price']) if a['price'] else 0
            price_str = f"{price_val:,} VNĐ" if price_val > 0 else "Miễn phí đi kèm phòng"
            text = f"Tiện ích phòng: {a['name']}. Đơn giá: {price_str}."
            documents.append({
                "id": f"amenity_{a['amenity_id']}",
                "text": text,
                "metadata": {"category": "amenity", "amenity_name": a["name"]}
            })

        # 4. Dịch vụ gia tăng của khách sạn (Services)
        cur.execute("""
            SELECT service_id, name, price, unit, category, description, hotel_id
            FROM services
            WHERE active = TRUE;
        """)
        services = cur.fetchall()
        for s in services:
            price_val = int(s['price']) if s['price'] else 0
            text = (
                f"Dịch vụ khách sạn: {s['name']}.\n"
                f"- Phân loại: {s['category'] or 'Tiện ích'}.\n"
                f"- Đơn giá: {price_val:,} VNĐ/{s['unit'] or 'lượt'}.\n"
                f"- Mô tả chi tiết: {s['description'] or 'Dịch vụ cao cấp chuẩn 5 sao.'}"
            )
            documents.append({
                "id": f"service_{s['service_id']}",
                "text": text,
                "metadata": {"category": "service", "service_name": s["name"]}
            })

        # 5. Khuyến mãi & Ưu đãi đang áp dụng (Promotions)
        cur.execute("""
            SELECT id, code, name, description, type, discount_value, max_discount_amount, 
                   min_booking_value, start_date, end_date, discount_type
            FROM promotions
            WHERE status = 'ACTIVE' AND (end_date IS NULL OR end_date >= NOW());
        """)
        promotions = cur.fetchall()
        for p in promotions:
            dtype = p.get('discount_type') or 'PERCENTAGE'
            val = p['discount_value']
            val_str = f"{val}%" if 'PERCENT' in str(dtype) or 'PERCENT' in str(p['type']) else f"{int(val):,} VNĐ"
            text = (
                f"Chương trình khuyến mãi giảm giá:\n"
                f"- Mã voucher (Code): {p['code']}\n"
                f"- Tên chương trình: {p['name']}\n"
                f"- Mức giảm: {val_str}\n"
                f"- Giá trị đơn tối thiểu áp dụng: {int(p['min_booking_value'] or 0):,} VNĐ\n"
                f"- Hạn dùng: từ {p['start_date']} đến {p['end_date']}\n"
                f"- Nội dung: {p['description'] or 'Ưu đãi dành cho khách hàng đặt phòng trực tuyến.'}"
            )
            documents.append({
                "id": f"promotion_{p['id']}",
                "text": text,
                "metadata": {"category": "promotion", "promo_code": p["code"]}
            })

        # 6. Quy định & Chính sách chung của Khách sạn Sen Việt (General Hotel Policies - Cập nhật chuẩn từ Nội quy)
        general_policies = [
            {
                "id": "policy_cancellation_refund",
                "text": (
                    "Chính sách hủy phòng và hoàn tiền do hủy booking tại Chuỗi Khách sạn Sen Việt Luxury:\n"
                    "- Mức khấu trừ tiền phòng phụ thuộc vào thời điểm yêu cầu hủy so với giờ check-in đầu tiên của booking:\n"
                    "  + Từ 72 giờ trước check-in trở lên (trước từ 3 ngày trở lên): Không áp dụng phạt tiền phòng (Hoàn 100% tiền phòng).\n"
                    "  + Từ 24 đến dưới 72 giờ (từ 1 ngày đến dưới 3 ngày trước check-in): Mức phạt là 50% phần tiền phòng được phân bổ (Hoàn 50% tiền phòng).\n"
                    "  + Dưới 24 giờ hoặc khách không đến (No-show): Mức phạt là 100% phần tiền phòng được phân bổ (Không hoàn tiền phòng).\n"
                    "- QUY ĐỊNH HOÀN DỊCH VỤ KHI HỦY: Toàn bộ phần tiền đã thanh toán được phân bổ cho dịch vụ ĐƯỢC HOÀN 100%; mức phạt hủy CHỈ khấu trừ vào phần tiền phòng.\n"
                    "- Số tiền hoàn cuối cùng căn cứ vào số đã thanh toán và cách phân bổ giữa tiền phòng, dịch vụ, giảm giá và phụ thu của booking; nhân viên kiểm tra yêu cầu hoàn trước khi xác nhận."
                ),
                "metadata": {"category": "Nội quy khách sạn", "topic": "cancellation_refund"}
            },
            {
                "id": "policy_checkin_checkout",
                "text": (
                    "Quy định thời gian nhận phòng và trả phòng tại Chuỗi Khách sạn Sen Việt:\n"
                    "- Giờ nhận phòng tiêu chuẩn (Check-in): từ 14:00 trở đi.\n"
                    "- Giờ trả phòng tiêu chuẩn (Check-out): trước 12:00 trưa.\n"
                    "- Chính sách phụ thu Nhận phòng sớm (Check-in sớm):\n"
                    "  + Trước 06:00 sáng: Phụ thu 100% giá phòng ngày đó.\n"
                    "  + Từ 06:00 đến 09:00 sáng: Phụ thu 50% giá phòng ngày đó.\n"
                    "  + Sau 09:00 đến trước giờ check-in đã đặt (14:00): Phụ thu 30% giá phòng ngày đó.\n"
                    "  + Nếu nhận phòng từ ngày trước ngày đặt: Tính 100% giá phòng của ngày nhận sớm đó; nhận sớm nhiều ngày tính đủ giá từng ngày sớm.\n"
                    "- Chính sách phụ thu Trả phòng trễ (Check-out trễ):\n"
                    "  + Đến trước 12:30 trưa: MIỄN PHÍ, KHÔNG TÍNH PHỤ THU (khách sạn hỗ trợ quý khách trả phòng đến 12:30).\n"
                    "  + Từ 12:30 đến 15:00 chiều: Phụ thu 30% giá phòng ngày đó.\n"
                    "  + Sau 15:00 đến 18:00 chiều: Phụ thu 50% giá phòng ngày đó.\n"
                    "  + Sau 18:00 tối hoặc trả sang ngày hôm sau: Phụ thu 100% giá phòng ngày đó."
                ),
                "metadata": {"category": "Nội quy khách sạn", "topic": "checkin_checkout"}
            },
            {
                "id": "policy_child_extra_bed",
                "text": (
                    "Chính sách phụ thu người ở thêm và trẻ em tại Khách sạn Sen Việt:\n"
                    "- Em bé dưới 2 tuổi: Miễn phí lưu trú (ngủ chung giường với bố mẹ).\n"
                    "- Trẻ em từ 2 đến dưới 12 tuổi: Phụ thu 100.000 VNĐ / trẻ / đêm.\n"
                    "- Phụ thu người lớn thêm (từ 12 tuổi trở lên, vượt sức chứa tiêu chuẩn): 200.000 VNĐ / người / đêm.\n"
                    "- Mỗi phòng chỉ cho phép tối đa 2 khách phụ thu thêm theo quy định phòng."
                ),
                "metadata": {"category": "Nội quy khách sạn", "topic": "children_and_surcharges"}
            },
            {
                "id": "policy_khuyen_mai",
                "text": (
                    "Quy định sử dụng và hủy mã khuyến mãi (Voucher / Mã giảm giá):\n"
                    "- Mỗi mã khuyến mãi chỉ được áp dụng một lần cho từng khách hàng.\n"
                    "- Khách có tài khoản chính thức được sử dụng mỗi mã tối đa một lần cho tài khoản đó.\n"
                    "- Khách vãng lai cũng chỉ được sử dụng mỗi mã một lần; ghi nhận việc sử dụng theo thông tin khách trên booking (SĐT/Email).\n"
                    "- Khi mã đã được áp dụng vào booking, quyền sử dụng mã được tính là ĐÃ DÙNG.\n"
                    "- Nếu booking đó bị hủy, mã khuyến mãi KHÔNG ĐƯỢC HOÀN LẠI và khách KHÔNG THỂ DÙNG LẠI MÃ ĐÓ."
                ),
                "metadata": {"category": "Nội quy khách sạn", "topic": "promotion_rules"}
            },
            {
                "id": "policy_hoan_tien_du_checkout",
                "text": (
                    "Chính sách hoàn tiền dư khi checkout:\n"
                    "- Đây là khoản hoàn phát sinh khi đối soát lúc checkout, không phải khoản hoàn do hủy booking.\n"
                    "- Phát sinh khi khách đã thanh toán nhiều hơn tổng chi phí thực tế, ví dụ: dịch vụ đã thanh toán trước nhưng chưa sử dụng và được hủy trước checkout.\n"
                    "- Hoàn theo số tiền khách thực trả vượt quá số tiền cuối cùng phải thanh toán; không áp dụng mức phạt hủy phòng.\n"
                    "- Phương thức hoàn: Tiền mặt tại quầy lễ tân hoặc chuyển khoản/hoàn tiền online."
                ),
                "metadata": {"category": "Nội quy khách sạn", "topic": "checkout_refund"}
            },
            {
                "id": "policy_dich_vu_khach_san",
                "text": (
                    "Quy định về dịch vụ khách sạn:\n"
                    "- Nhân viên xác nhận dịch vụ sau khi khách sử dụng. Dịch vụ ĐÃ SỬ DỤNG KHÔNG THỂ HỦY.\n"
                    "- Đối chiếu tên dịch vụ, số lượng và đơn giá với khách.\n"
                    "- Nếu dịch vụ CHƯA SỬ DỤNG, hãy hủy trước khi checkout để cập nhật lại số tiền khách cần thanh toán hoặc được hoàn tiền dư."
                ),
                "metadata": {"category": "Nội quy khách sạn", "topic": "services_rules"}
            },
            {
                "id": "policy_doi_soat_thanh_toan_email",
                "text": (
                    "Quy định đối soát thanh toán, hoàn tiền và thông báo email:\n"
                    "- Tổng cuối cùng = Tiền phòng + Dịch vụ + Phụ thu check-in sớm + Phụ thu check-out trễ + Phụ thu khác - Giảm giá.\n"
                    "- Thời gian hoàn tiền qua tài khoản ngân hàng: Dự kiến mất từ 1 – 3 ngày làm việc.\n"
                    "- Khách sẽ nhận email xác nhận tự động khi: (1) Đặt booking, (2) Thanh toán được ghi nhận, (3) Checkout hoàn tất, (4) Khoản hoàn tiền đã được xử lý (khi có email hợp lệ)."
                ),
                "metadata": {"category": "Nội quy khách sạn", "topic": "payment_reconciliation"}
            },
            {
                "id": "policy_food",
                "text": (
                    "Chính sách ăn uống (F&B) và Bữa sáng tại Khách sạn Sen Việt:\n"
                    "- Giá niêm yết các hạng phòng cơ bản là giá phòng đơn thuần (Room Only).\n"
                    "- Quý khách có thể chọn thêm dịch vụ Buffet sáng cao cấp (150.000 VNĐ/suất) khi đặt phòng hoặc mua trực tiếp tại quầy lễ tân."
                ),
                "metadata": {"category": "Nội quy khách sạn", "topic": "food_breakfast"}
            },
            {
                "id": "policy_payment_methods",
                "text": (
                    "Phương thức thanh toán được chấp nhận tại Chuỗi Khách sạn Sen Việt:\n"
                    "1. Thanh toán chuyển khoản trực tuyến quét mã VietQR tự động qua cổng PayOS (giữ phòng ưu tiên trong 5 phút).\n"
                    "2. Thanh toán trực tiếp tại quầy lễ tân (bằng tiền mặt hoặc thẻ POS) khi khách làm thủ tục nhận phòng (Check-in).\n"
                    "3. Thanh toán bằng thẻ tín dụng quốc tế (Visa, MasterCard)."
                ),
                "metadata": {"category": "Nội quy khách sạn", "topic": "payment"}
            }
        ]
        documents.extend(general_policies)

        cur.close()
        conn.close()

    except Exception as e:
        print(f"[Database Ingest Error] {e}")

    return documents
