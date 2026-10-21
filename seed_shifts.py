import datetime
import uuid
import sys
from core.database import get_db_connection

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

conn = get_db_connection()
cur = conn.cursor()

# Get Hotel 1 employees
cur.execute("SELECT employee_id, full_name, position FROM employees WHERE hotel_id = 1")
hotel1_staff = cur.fetchall()
print("Hotel 1 staff:", hotel1_staff)

receptionists = [s for s in hotel1_staff if "lễ tân" in s[2].lower()]
housekeepings = [s for s in hotel1_staff if "buồng" in s[2].lower()]

print("Receptionists:", [r[1] for r in receptionists])
print("Housekeepings:", [h[1] for h in housekeepings])

# Seed 2 weeks: 2026-10-12 (current week) and 2026-10-19 (next week)
start_dates = [datetime.date(2026, 10, 12), datetime.date(2026, 10, 19)]
count = 0

for start_monday in start_dates:
    for i in range(7):
        day = start_monday + datetime.timedelta(days=i)
        
        # Reception morning & evening
        rec_m = receptionists[i % len(receptionists)]
        rec_e = receptionists[(i + 1) % len(receptionists)]
        
        # Housekeeping morning & evening
        hk_m = housekeepings[i % len(housekeepings)]
        hk_e = housekeepings[(i + 1) % len(housekeepings)]
        
        shifts = [
            (day, "Ca sáng", "06:00 – 14:00", "Lễ tân", "Trực quầy lễ tân", rec_m[0]),
            (day, "Ca tối", "14:00 – 22:00", "Lễ tân", "Trực quầy lễ tân", rec_e[0]),
            (day, "Ca sáng", "06:00 – 14:00", "Housekeeping", "Dọn phòng theo tầng", hk_m[0]),
            (day, "Ca tối", "14:00 – 22:00", "Housekeeping", "Kiểm tra phòng cuối ngày", hk_e[0]),
        ]
        
        for w_date, s_type, s_time, role, task, emp_id in shifts:
            s_tag = "SANG" if "sáng" in s_type else "TOI"
            r_tag = "REC" if "Lễ" in role else "HK"
            s_id = f"SHIFT_{w_date.strftime('%Y%m%d')}_{r_tag}_{s_tag}"
            cur.execute("""
                INSERT INTO shift_assignments (shift_assignment_id, work_date, shift_type, shift_time, role, status, task, employee_id, hotel_id, created_at)
                VALUES (%s, %s, %s, %s, %s, 'SCHEDULED', %s, %s, 1, NOW())
                ON CONFLICT (shift_assignment_id) DO NOTHING
            """, (s_id, w_date, s_type, s_time, role, task, emp_id))
            count += 1

conn.commit()
print(f"[+] Successfully seeded {count} shift assignments!")
cur.close()
conn.close()
