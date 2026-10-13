
import sys
sys.path.append('C:/Users/admin/Downloads/KLTN_HotelManagementAI')
from core.database import get_db_connection
conn = get_db_connection()
cur = conn.cursor()
cur.execute('SELECT * FROM bookings WHERE booking_id = %s', ('BKG_F1F496DE',))
print(cur.fetchall())

