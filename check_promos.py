import psycopg2
from core.database import get_db_connection

try:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'promotions';")
    cols = cur.fetchall()
    print('Columns:')
    for c in cols:
        print(c)
    cur.execute("SELECT * FROM promotions;")
    rows = cur.fetchall()
    print('Existing promos:')
    for r in rows:
        print(r)
    cur.close()
    conn.close()
except Exception as e:
    import traceback
    traceback.print_exc()
