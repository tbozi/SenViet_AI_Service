
import sys
sys.path.append('C:/Users/admin/Downloads/KLTN_HotelManagementAI')
from core.database import get_db_connection
conn = get_db_connection()
cur = conn.cursor()
cur.execute('SELECT r.room_id FROM rooms r JOIN floors f ON r.floor_id = f.floor_id JOIN buildings b ON f.building_id = b.building_id WHERE b.hotel_id = 1 AND r.room_status = \'READY\' AND r.room_type = \'STANDARD\' LIMIT 1')
print(cur.fetchall())

