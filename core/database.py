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

        # 6. Quy định & Chính sách chung của Khách sạn Sen Việt (General Hotel Policies)
        general_policies = [
            {
                "id": "policy_checkin_checkout",
                "text": (
                    "Quy định thời gian nhận và trả phòng tại Chuỗi Khách sạn Sen Việt:\n"
                    "- Giờ nhận phòng tiêu chuẩn (Check-in): từ 14:00 trở đi.\n"
                    "- Giờ trả phòng tiêu chuẩn (Check-out): trước 12:00 trưa.\n"
                    "- Nhận phòng sớm hoặc trả phòng trễ tùy thuộc vào tình trạng phòng thực tế và có thể áp dụng phụ thu."
                ),
                "metadata": {"category": "general_policy", "topic": "checkin_checkout"}
            },
            {
                "id": "policy_child_extra_bed",
                "text": (
                    "Chính sách trẻ em và giường phụ:\n"
                    "- Trẻ em dưới 6 tuổi: Miễn phí ngủ chung giường với bố mẹ.\n"
                    "- Trẻ em từ 6 đến 11 tuổi: Phụ thu theo chính sách trẻ em của từng chi nhánh.\n"
                    "- Khách từ 12 tuổi trở lên: Tính như người lớn."
                ),
                "metadata": {"category": "general_policy", "topic": "children"}
            },
            {
                "id": "policy_payment_methods",
                "text": (
                    "Phương thức thanh toán được chấp nhận tại Chuỗi Khách sạn Sen Việt:\n"
                    "1. Thanh toán chuyển khoản trực tuyến quét mã VietQR tự động qua cổng PayOS (giữ phòng ưu tiên trong 5 phút).\n"
                    "2. Thanh toán trực tiếp tại quầy lễ tân (bằng tiền mặt hoặc thẻ POS) khi khách làm thủ tục nhận phòng (Check-in).\n"
                    "3. Thanh toán bằng thẻ tín dụng quốc tế (Visa, MasterCard)."
                ),
                "metadata": {"category": "general_policy", "topic": "payment"}
            }
        ]
        documents.extend(general_policies)

        cur.close()
        conn.close()

    except Exception as e:
        print(f"[Database Ingest Error] {e}")

    return documents
