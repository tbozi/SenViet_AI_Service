import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import psycopg2
from core.database import get_db_connection

def seed_test_database():
    """
    Nạp dữ liệu test cố định vào database PostgreSQL:
    - 7 chi nhánh
    - 4 loại phòng (STANDARD, DELUXE, SUITE, FAMILY)
    - Chính sách giá theo mùa/cuối tuần (room_seasonal_rates)
    - Dịch vụ đi kèm
    - Các mã khuyến mãi theo bộ test (SEN10, VIP20, TET2025, STAFF100, DEMO2K, MAX300K...)
    - Booking mẫu SV12345
    """
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # 1. Đảm bảo 7 chi nhánh có đủ chính sách cho cả 4 loại phòng
        room_types = [
            ("STANDARD", 850000.0, 2, 1, 25.0, 200000.0, 100000.0),
            ("DELUXE", 1200000.0, 2, 1, 35.0, 250000.0, 120000.0),
            ("SUITE", 2500000.0, 2, 2, 55.0, 350000.0, 150000.0),
            ("FAMILY", 2000000.0, 4, 2, 60.0, 300000.0, 150000.0),
        ]

        for h_id in range(1, 8):
            for r_type, base_p, std_cap, max_extra, area, adult_f, child_f in room_types:
                policy_id = f"P{h_id}_{r_type[:3]}"
                cur.execute("""
                    INSERT INTO branch_room_policies (
                        policy_id, hotel_id, room_type, base_price,
                        standard_capacity, max_extra_guests, room_area,
                        extra_adult_fee, extra_child_fee
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (hotel_id, room_type) DO UPDATE SET
                        base_price = EXCLUDED.base_price,
                        standard_capacity = EXCLUDED.standard_capacity;
                """, (policy_id, h_id, r_type, base_p, std_cap, max_extra, area, adult_f, child_f))

        # 2. Bảng giá cuối tuần / mùa lễ (room_seasonal_rates) cho AV-06
        cur.execute("""
            CREATE TABLE IF NOT EXISTS room_seasonal_rates (
                id SERIAL PRIMARY KEY,
                hotel_id BIGINT,
                room_type VARCHAR(50),
                start_date DATE,
                end_date DATE,
                price DOUBLE PRECISION,
                season_name VARCHAR(100)
            );
        """)
        # Seed cuối tuần tháng 10/2026 (VD Thứ 7 17/10/2026 và 24/10/2026 giá Deluxe tăng lên 1.500.000)
        cur.execute("""
            DELETE FROM room_seasonal_rates WHERE rate_name = 'TEST_WEEKEND_OCT';
            INSERT INTO room_seasonal_rates (hotel_id, room_type, start_date, end_date, price, rate_name)
            VALUES 
                (1, 'DELUXE', '2026-10-17', '2026-10-18', 1500000.0, 'TEST_WEEKEND_OCT'),
                (1, 'DELUXE', '2026-10-24', '2026-10-25', 1500000.0, 'TEST_WEEKEND_OCT');
        """)

        # 3. Dịch vụ (services)
        services = [
            ("SRV_SPA", "Spa & Massage", 500000.0, "lượt", "Dịch vụ spa thư giãn", True, 1),
            ("SRV_TRANS", "Đưa đón sân bay", 300000.0, "chuyến", "Đưa đón tận nơi", True, 1),
            ("SRV_BF", "Buffet Sáng", 250000.0, "khách/ngày", "Buffet sáng tiêu chuẩn 5 sao", True, 1),
        ]
        for s_id, s_name, s_price, s_unit, s_desc, s_active, h_id in services:
            cur.execute("""
                INSERT INTO services (service_id, name, price, unit, description, active)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (service_id) DO UPDATE SET
                    price = EXCLUDED.price,
                    active = EXCLUDED.active;
            """, (s_id, s_name, s_price, s_unit, s_desc, s_active))

        # 4. Khuyến mãi (promotions)
        promos = [
            ("PRM_SEN10", "SEN10", "Giảm 10% hóa đơn", "TOTAL", "PERCENTAGE", 10.0, 500000.0, 0.0, "2026-01-01", "2030-01-01", "ACTIVE", 0, 1000),
            ("PRM_VIP20", "VIP20", "Giảm 20% đơn từ 2 triệu", "TOTAL", "PERCENTAGE", 20.0, 1000000.0, 2000000.0, "2026-01-01", "2030-01-01", "ACTIVE", 0, 1000),
            ("PRM_TET2025", "TET2025", "Khuyến mãi Tết 2025 (Hết hạn)", "TOTAL", "PERCENTAGE", 30.0, 1000000.0, 0.0, "2025-01-01", "2025-02-15", "EXPIRED", 0, 0),
            ("PRM_STAFF100", "STAFF100", "Mã nội bộ nhân viên", "TOTAL", "FIXED_AMOUNT", 100000.0, 100000.0, 0.0, "2026-01-01", "2030-01-01", "INACTIVE", 0, 0),
            ("PRM_MAX300K", "MAX300K", "Giảm 50% tối đa 300.000đ", "TOTAL", "PERCENTAGE", 50.0, 300000.0, 0.0, "2026-01-01", "2030-01-01", "ACTIVE", 0, 1000),
            ("PRM_DEMO2K", "DEMO2K", "Thử nghiệm PayOS 2.000đ", "TOTAL", "FIXED_AMOUNT", 999999999.0, 999999999.0, 0.0, "2026-01-01", "2030-01-01", "ACTIVE", 0, 1000),
        ]

        for p_id, p_code, p_name, p_type, d_type, d_val, max_d, min_v, s_date, e_date, status, used, limit in promos:
            cur.execute("""
                INSERT INTO promotions (
                    id, code, name, type, discount_type, discount_value,
                    max_discount_amount, min_booking_value, start_date, end_date,
                    status, used_count, usage_limit, deleted, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, false, NOW(), NOW())
                ON CONFLICT (id) DO UPDATE SET
                    code = EXCLUDED.code,
                    status = EXCLUDED.status,
                    discount_value = EXCLUDED.discount_value,
                    max_discount_amount = EXCLUDED.max_discount_amount,
                    min_booking_value = EXCLUDED.min_booking_value,
                    start_date = EXCLUDED.start_date,
                    end_date = EXCLUDED.end_date;
            """, (p_id, p_code, p_name, p_type, d_type, d_val, max_d, min_v, s_date, e_date, status, used, limit))

        # 5. Booking mẫu SV12345 để test tra cứu / hủy / sửa (CA-02, CA-04, CA-06)
        cur.execute("""
            INSERT INTO customers (customer_id, full_name, phone, email, loyalty_tier, is_registered, total_bookings, total_spent)
            VALUES ('CUST_TEST_01', 'Nguyễn Văn Test', '0901234567', 'test@senviet.vn', 'BRONZE', false, 0, 0.0)
            ON CONFLICT (customer_id) DO NOTHING;
        """)

        cur.execute("""
            INSERT INTO bookings (booking_id, customer_id, hotel_id, booking_status, booking_channel, created_at)
            VALUES ('SV12345', 'CUST_TEST_01', 1, 1, 0, NOW())
            ON CONFLICT (booking_id) DO UPDATE SET
                booking_status = 1;
        """)

        conn.commit()
        print("[+] Seed test database thành công!")
    except Exception as e:
        conn.rollback()
        print(f"[-] Lỗi seed test database: {e}")
        raise e
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    seed_test_database()
