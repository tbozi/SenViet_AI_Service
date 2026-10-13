from core.database import get_db_connection
import traceback
try:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
    INSERT INTO promotions (id, code, description, type, discount_value, max_discount_amount, start_date, end_date, status, minimum_order_value, current_usage, max_usage)
    VALUES (
        'PROMO_DEMO2K', 'DEMO2K', 'Ma giam gia Demo test QR 2000 VND', 'FIXED_AMOUNT', 9999999, NULL, '2026-01-01', '2027-01-01', 'ACTIVE', 0, 0, 1000
    ) ON CONFLICT (code) DO NOTHING;
    ''')
    conn.commit()
    print('Inserted DEMO2K promotion!')
    cur.close()
    conn.close()
except Exception as e:
    traceback.print_exc()
