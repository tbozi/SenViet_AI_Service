import os
import sys
import json
import openpyxl
from core.database import get_db_connection

# Force UTF-8 stdout
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = r"C:\Users\admin\Downloads\FILE_DU_LIEU_TEST_DOAN"

def import_services():
    print("[*] 1. Importing Services from mau-nhap-dich-vu.xlsx...")
    file_path = os.path.join(BASE_DIR, "dichvu", "mau-nhap-dich-vu.xlsx")
    if not os.path.exists(file_path):
        print("[-] File not found:", file_path)
        return

    wb = openpyxl.load_workbook(file_path, data_only=True)
    ws = wb.active

    conn = get_db_connection()
    cur = conn.cursor()

    count = 0
    # Spa image fallback
    default_img = "https://images.unsplash.com/photo-1540555700478-4be289fbecef?q=80&w=800"

    for row_idx in range(2, ws.max_row + 1):
        name = ws.cell(row_idx, 1).value
        if not name:
            continue
        desc = ws.cell(row_idx, 2).value or ""
        price = float(ws.cell(row_idx, 3).value or 0)
        unit = ws.cell(row_idx, 4).value or "Lần"
        category = ws.cell(row_idx, 5).value or "Spa"
        img = ws.cell(row_idx, 6).value or default_img

        if not str(img).startswith("http"):
            img = default_img

        cur.execute("SELECT service_id FROM services WHERE name = %s", (name,))
        existing = cur.fetchone()
        if not existing:
            srv_id = f"SRV_IMPORT_{row_idx}"
            cur.execute("""
                INSERT INTO services (service_id, name, description, price, unit, category, image_url, active)
                VALUES (%s, %s, %s, %s, %s, %s, %s, true)
            """, (srv_id, name, desc, price, unit, category, img))
            count += 1
            print(f"  + Added service: {name} ({price:,.0f} VNĐ)")

    conn.commit()
    cur.close()
    conn.close()
    print(f"[+] Hoàn tất nạp {count} dịch vụ mới.")

def import_amenities():
    print("\n[*] 2. Importing Amenities from mau-nhap-tien-ich.xlsx...")
    file_path = os.path.join(BASE_DIR, "mau-nhap-tien-ich.xlsx")
    if not os.path.exists(file_path):
        print("[-] File not found:", file_path)
        return

    wb = openpyxl.load_workbook(file_path, data_only=True)
    ws = wb.active

    conn = get_db_connection()
    cur = conn.cursor()

    count = 0
    for row_idx in range(2, ws.max_row + 1):
        name = ws.cell(row_idx, 1).value
        if not name:
            continue
        price = float(ws.cell(row_idx, 2).value or 0)

        cur.execute("SELECT amenity_id FROM amenities WHERE name = %s", (str(name),))
        existing = cur.fetchone()
        if not existing:
            cur.execute("""
                INSERT INTO amenities (name, price)
                VALUES (%s, %s)
            """, (str(name), price))
            count += 1
            print(f"  + Added amenity: {name} ({price:,.0f} VNĐ)")

    conn.commit()
    cur.close()
    conn.close()
    print(f"[+] Hoàn tất nạp {count} tiện ích mới.")

def import_bed_types():
    print("\n[*] 3. Importing Bed Types from phong.xlsx...")
    file_path = os.path.join(BASE_DIR, "dulieuphong", "phong.xlsx")
    if not os.path.exists(file_path):
        print("[-] File not found:", file_path)
        return

    wb = openpyxl.load_workbook(file_path, data_only=True)
    if "Danh mục" not in wb.sheetnames:
        return

    bed_defs = [
        ("Giường đơn (Single)", 1, False, "Giường đơn tiêu chuẩn 1 người (1m x 2m)"),
        ("Giường đôi (Queen)", 2, False, "Giường đôi cỡ Queen 2 người (1.6m x 2m)"),
        ("Giường King", 2, False, "Giường lớn cỡ King sang trọng (1.8m x 2m)"),
        ("Sofa bed", 1, True, "Sofa đa năng kéo ra thành giường 1 người"),
        ("Giường phụ (Extra bed)", 1, True, "Giường phụ di động kê thêm theo yêu cầu"),
    ]

    conn = get_db_connection()
    cur = conn.cursor()

    count = 0
    for name, cap, is_extra, desc in bed_defs:
        cur.execute("SELECT id FROM bed_types WHERE name = %s", (name,))
        if not cur.fetchone():
            cur.execute("""
                INSERT INTO bed_types (name, capacity, is_extra_bed, description)
                VALUES (%s, %s, %s, %s)
            """, (name, cap, is_extra, desc))
            count += 1
            print(f"  + Added bed type: {name} (sức chứa: {cap})")

    conn.commit()
    cur.close()
    conn.close()
    print(f"[+] Hoàn tất nạp {count} loại giường.")

def import_rooms():
    print("\n[*] 4. Importing Rooms from phong.xlsx...")
    file_path = os.path.join(BASE_DIR, "dulieuphong", "phong.xlsx")
    if not os.path.exists(file_path):
        print("[-] File not found:", file_path)
        return

    wb = openpyxl.load_workbook(file_path, data_only=True)
    ws = wb["Dữ liệu phòng"]

    conn = get_db_connection()
    cur = conn.cursor()

    sample_images = [
        {"url": "https://images.unsplash.com/photo-1618773928121-c32242e63f39?q=80&w=1000", "isDefault": True},
        {"url": "https://images.unsplash.com/photo-1590490360182-c33d57733427?q=80&w=1000", "isDefault": False},
        {"url": "https://images.unsplash.com/photo-1566665797739-1674de7a421a?q=80&w=1000", "isDefault": False},
        {"url": "https://images.unsplash.com/photo-1582719478250-c89cae4dc85b?q=80&w=1000", "isDefault": False}
    ]

    count = 0
    for row_idx in range(2, ws.max_row + 1):
        room_num = str(ws.cell(row_idx, 1).value or "").strip()
        if not room_num or room_num.lower() == "none":
            continue
        room_type = str(ws.cell(row_idx, 2).value or "STANDARD").strip().upper()
        
        # Check if room already exists
        cur.execute("SELECT room_id FROM rooms WHERE room_number = %s", (room_num,))
        existing = cur.fetchone()
        if not existing:
            room_id = f"ROOM20261015{room_num}"
            avatar_json = json.dumps(sample_images)
            base_price = 850000.0 if room_type == "STANDARD" else (1200000.0 if room_type == "DELUXE" else (2000000.0 if room_type == "FAMILY" else 2500000.0))
            
            cur.execute("""
                INSERT INTO rooms (room_id, room_number, room_type, room_status, floor_id, base_price, avatar_url)
                VALUES (%s, %s, %s, 'READY', '1', %s, %s::json)
            """, (room_id, room_num, room_type, base_price, avatar_json))
            count += 1
            print(f"  + Added room: {room_num} ({room_type}, tầng 1, giá {base_price:,.0f} VNĐ)")

    conn.commit()
    cur.close()
    conn.close()
    print(f"[+] Hoàn tất nạp {count} phòng mới.")

def import_permissions():
    print("\n[*] 5. Importing Role Permissions from role-permissions-initial-admin.xlsx...")
    file_path = os.path.join(BASE_DIR, "role-permissions-initial-admin.xlsx")
    if not os.path.exists(file_path):
        print("[-] File not found:", file_path)
        return

    wb = openpyxl.load_workbook(file_path, data_only=True)
    ws = wb["Phân quyền"]

    conn = get_db_connection()
    cur = conn.cursor()

    # Map role code -> role_id
    cur.execute("SELECT code, role_id FROM roles")
    role_map = {r[0]: r[1] for r in cur.fetchall()}

    count_perms = 0
    count_links = 0
    for row_idx in range(2, ws.max_row + 1):
        role_code = ws.cell(row_idx, 1).value
        perm_code = ws.cell(row_idx, 2).value
        perm_name = ws.cell(row_idx, 3).value
        perm_category = ws.cell(row_idx, 4).value
        perm_desc = ws.cell(row_idx, 5).value or ""
        granted = ws.cell(row_idx, 6).value

        if not role_code or not perm_code:
            continue

        role_code = str(role_code).strip()
        perm_code = str(perm_code).strip()

        # 1. Ensure permission exists in `permissions` table
        cur.execute("SELECT permission_id FROM permissions WHERE code = %s", (perm_code,))
        p_row = cur.fetchone()
        if not p_row:
            cur.execute("""
                INSERT INTO permissions (code, name, category, description)
                VALUES (%s, %s, %s, %s)
                RETURNING permission_id
            """, (perm_code, str(perm_name), str(perm_category), str(perm_desc)))
            perm_id = cur.fetchone()[0]
            count_perms += 1
            print(f"  + Created permission: {perm_code} ({perm_name})")
        else:
            perm_id = p_row[0]

        # 2. Link role_permission if granted == 'Có'
        if str(granted).strip().lower() == "có" and role_code in role_map:
            role_id = role_map[role_code]
            cur.execute("""
                INSERT INTO role_permissions (role_id, permission_id)
                VALUES (%s, %s)
                ON CONFLICT (role_id, permission_id) DO NOTHING
            """, (role_id, perm_id))
            if cur.rowcount > 0:
                count_links += 1

    conn.commit()
    cur.close()
    conn.close()
    print(f"[+] Hoàn tất đồng bộ phân quyền: {count_perms} permissions mới, {count_links} role permissions mới được cấp.")

if __name__ == "__main__":
    print("=" * 60)
    print("CẬP NHẬT DỮ LIỆU TỪ DUNG VÀO DATABASE POSTGRESQL")
    print("Folder:", BASE_DIR)
    print("=" * 60)
    import_services()
    import_amenities()
    import_bed_types()
    import_rooms()
    import_permissions()
    print("\n[+] ĐÃ HOÀN THÀNH TẤT CẢ 5 HẠNG MỤC DỮ LIỆU!")
