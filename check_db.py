from core.database import get_db_connection

conn = get_db_connection()
cur = conn.cursor()

for t in ["services", "rooms", "amenities"]:
    cur.execute(f"""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = '{t}'
        ORDER BY ordinal_position;
    """)
    print(f"\n=== Columns of {t} ===")
    for r in cur.fetchall():
        print(f"  {r[0]}: {r[1]}")

cur.close()
conn.close()
