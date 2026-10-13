import psycopg2
from core.database import get_db_connection

try:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM promotions WHERE code = 'DEMO2K';")
    row = cur.fetchone()
    if row:
        print("DEMO2K already exists, updating...")
        cur.execute("""
            UPDATE promotions 
            SET status = 'ACTIVE', 
                discount_type = 'FIXED_AMOUNT', 
                type = 'TOTAL',
                discount_value = 999999999,
                min_booking_value = 0,
                used_count = 0,
                description = 'Mã thử nghiệm PayOS - giảm còn đúng 2.000 VNĐ'
            WHERE code = 'DEMO2K'
        """)
    else:
        print("Inserting DEMO2K...")
        cur.execute("""
            INSERT INTO promotions (
                id, code, name, description, discount_type, type,
                discount_value, max_discount_amount, min_booking_value,
                start_date, end_date, status, deleted, used_count, created_at, updated_at
            ) VALUES (
                'PRM_DEMO2K', 'DEMO2K', 'Thử nghiệm PayOS 2.000đ',
                'Mã thử nghiệm PayOS - giảm còn đúng 2.000 VNĐ',
                'FIXED_AMOUNT', 'TOTAL',
                999999999, 999999999, 0,
                '2026-01-01 00:00:00', '2030-01-01 00:00:00',
                'ACTIVE', false, 0, NOW(), NOW()
            )
        """)
    conn.commit()
    print("Success committing DEMO2K into database!")
    cur.execute("SELECT code, discount_value, status, description FROM promotions WHERE status = 'ACTIVE';")
    for r in cur.fetchall():
        print("Active promo:", r)
    cur.close()
    conn.close()
except Exception as e:
    import traceback
    traceback.print_exc()
