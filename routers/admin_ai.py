import json
import uuid
import datetime
import unicodedata
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import google.generativeai as genai

from config.settings import settings
from core.clock import get_current_date
from core.database import get_db_connection
from core.staff_scheduler import staff_scheduler
from core.chat_history import save_chat_turn, get_session_history, delete_session_history

genai.configure(api_key=settings.GEMINI_API_KEY)

router = APIRouter(prefix="/api/admin-ai", tags=["Admin & Staff Copilot"])

# ==================== DATA SCHEMAS ====================

class AdminChatMessage(BaseModel):
    role: str = Field(..., description="Vai trò: 'user' hoặc 'model'")
    content: str = Field(..., description="Nội dung tin nhắn")

class AdminChatRequest(BaseModel):
    message: str = Field(..., description="Câu hỏi hoặc lệnh điều hành từ Admin / Nhân viên")
    sessionId: Optional[str] = Field(None, description="Mã phiên hội thoại (UUID)")
    history: Optional[List[AdminChatMessage]] = Field(default=[], description="Lịch sử tin nhắn")

class AdminChatResult(BaseModel):
    reply: str = Field(..., description="Câu trả lời từ Trợ lý AI Quản trị")
    sessionId: str = Field(..., description="Mã phiên hội thoại")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Thông tin phụ trợ (nếu có)")

class AdminApiResponse(BaseModel):
    code: int = 1000
    message: str = "Success"
    result: AdminChatResult

# ==================== HELPER FUNCTIONS ====================

def _clean_vn(text: str) -> str:
    if not text:
        return ""
    return "".join(c for c in unicodedata.normalize('NFD', text.lower()) if unicodedata.category(c) != 'Mn')

def _find_matching_hotel(cur, branch_keyword: str):
    cur.execute("SELECT id, name, address, phone FROM hotels ORDER BY id")
    hotels = cur.fetchall()
    if not hotels:
        return None
    if not branch_keyword or not branch_keyword.strip():
        return hotels[0]

    kw = _clean_vn(branch_keyword)
    for h in hotels:
        h_name = _clean_vn(h[1])
        h_addr = _clean_vn(h[2]) if h[2] else ""
        if kw in h_name or kw in h_addr:
            return h

    alias_map = [
        (["sai gon", "hcm", "sg", "ho chi minh", "quan 1"], "sai gon"),
        (["ha noi", "hn", "hoan kiem"], "ha noi"),
        (["da nang", "dn"], "da nang"),
        (["nha trang", "nt"], "nha trang"),
        (["da lat", "dl"], "da lat"),
        (["go cong", "gc"], "go cong"),
        (["an nhon", "an nhơn", "an"], "an nhon"),
    ]
    for keywords, target in alias_map:
        if any(k in kw for k in keywords):
            for h in hotels:
                if target in _clean_vn(h[1]):
                    return h

    return hotels[0]

# ==================== CÁC TOOL NGHIỆP VỤ THỰC TẾ TRONG DATABASE ====================

def query_room_availability(branch_keyword: str = "Sài Gòn", room_type: str = "") -> str:
    """
    Tra cứu số lượng phòng và trạng thái phòng thực tế trong cơ sở dữ liệu (bảng rooms và branch_room_policies).
    Trả về số phòng READY/AVAILABLE, OCCUPIED, DIRTY kèm giá niêm yết theo từng hạng phòng.
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        hotel_row = _find_matching_hotel(cur, branch_keyword)
        if not hotel_row:
            cur.close()
            conn.close()
            return json.dumps({"status": "error", "message": "Không tìm thấy chi nhánh phù hợp."}, ensure_ascii=False)

        h_id, h_name = hotel_row[0], hotel_row[1]

        # 1. Truy vấn danh sách phòng
        query = """
            SELECT r.room_id, r.room_type, r.room_status, r.base_price, f.floor_number
            FROM rooms r
            JOIN floors f ON r.floor_id = f.floor_id
            JOIN buildings b ON f.building_id = b.building_id
            WHERE b.hotel_id = %s
        """
        params = [h_id]
        if room_type and room_type.strip():
            query += " AND UPPER(r.room_type) = %s"
            params.append(room_type.strip().upper())

        cur.execute(query, tuple(params))
        room_rows = cur.fetchall()

        # 2. Truy vấn chính sách giá niêm yết theo chi nhánh
        cur.execute("""
            SELECT room_type, base_price, standard_capacity, max_extra_guests, extra_adult_fee, extra_child_fee
            FROM branch_room_policies
            WHERE hotel_id = %s
        """, (h_id,))
        policy_rows = cur.fetchall()
        policy_dict = {
            r[0].upper(): {
                "base_price": float(r[1]),
                "standard_capacity": r[2],
                "max_extra_guests": r[3],
                "extra_adult_fee": float(r[4]),
                "extra_child_fee": float(r[5])
            }
            for r in policy_rows
        }

        # Phân loại phòng theo hạng
        summary = {}
        total_rooms = len(room_rows)
        total_available = 0
        total_occupied = 0
        total_dirty = 0

        for r in room_rows:
            rtype = str(r[1]).upper()
            status = str(r[2]).upper()
            price = float(r[3]) if r[3] else policy_dict.get(rtype, {}).get("base_price", 0.0)

            if rtype not in summary:
                pol = policy_dict.get(rtype, {})
                summary[rtype] = {
                    "total": 0,
                    "available_ready": 0,
                    "occupied": 0,
                    "dirty_cleaning": 0,
                    "base_price_vnd": price,
                    "standard_capacity": pol.get("standard_capacity", 2),
                    "extra_adult_fee_vnd": pol.get("extra_adult_fee", 0.0),
                    "extra_child_fee_vnd": pol.get("extra_child_fee", 0.0)
                }

            summary[rtype]["total"] += 1
            if status in ["READY", "AVAILABLE"]:
                summary[rtype]["available_ready"] += 1
                total_available += 1
            elif status in ["OCCUPIED", "IN_HOUSE"]:
                summary[rtype]["occupied"] += 1
                total_occupied += 1
            elif status in ["DIRTY", "CLEANING"]:
                summary[rtype]["dirty_cleaning"] += 1
                total_dirty += 1
            else:
                summary[rtype]["available_ready"] += 1
                total_available += 1

        cur.close()
        conn.close()

        return json.dumps({
            "status": "success",
            "hotel_id": h_id,
            "hotel_name": h_name,
            "total_rooms_in_branch": total_rooms,
            "available_ready_count": total_available,
            "occupied_count": total_occupied,
            "dirty_cleaning_count": total_dirty,
            "details_by_room_type": summary
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

def query_booking_details(keyword: str) -> str:
    """
    Tra cứu thông tin đặt phòng thực tế trong cơ sở dữ liệu (bảng bookings, booking_details, orders, customers).
    Tìm theo: Mã booking (VD: BKG_601), Số điện thoại khách hoặc Tên khách.
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        kw = keyword.strip()
        cur.execute("""
            SELECT b.booking_id, b.booking_status, c.full_name, c.phone, c.cccd, h.name as hotel_name,
                   o.order_id, o.order_status, o.total_amount, o.paid_amount, o.remaining_amount, o.payment_status,
                   b.created_at
            FROM bookings b
            LEFT JOIN customers c ON b.customer_id = c.customer_id
            LEFT JOIN orders o ON b.order_id = o.order_id
            LEFT JOIN hotels h ON b.hotel_id = h.id
            WHERE b.booking_id ILIKE %s OR c.full_name ILIKE %s OR c.phone ILIKE %s
            ORDER BY b.created_at DESC
            LIMIT 5;
        """, (f"%{kw}%", f"%{kw}%", f"%{kw}%"))
        rows = cur.fetchall()

        if not rows:
            cur.close()
            conn.close()
            return json.dumps({"status": "not_found", "message": f"Không tìm thấy đặt phòng nào khớp với từ khóa '{keyword}' trong cơ sở dữ liệu."}, ensure_ascii=False)

        status_map = {
            0: "PENDING (Chờ xác nhận)",
            1: "CONFIRMED (Đã xác nhận)",
            2: "CANCELLED (Đã hủy)",
            3: "IN_HOUSE (Đang lưu trú)",
            4: "COMPLETED (Đã trả phòng / Hoàn tất)"
        }

        bookings_result = []
        for r in rows:
            b_id = r[0]
            # Chi tiết phòng đã đặt
            cur.execute("""
                SELECT bd.room_id, bd.checkin_time, bd.checkout_time, bd.total_price, bd.status, r.room_type
                FROM booking_details bd
                LEFT JOIN rooms r ON bd.room_id = r.room_id
                WHERE bd.booking_id = %s
            """, (b_id,))
            details_rows = cur.fetchall()
            room_items = []
            for d in details_rows:
                room_items.append({
                    "room_id": d[0] or "Chưa xếp phòng",
                    "room_type": d[5] or "STANDARD",
                    "checkin": str(d[1]) if d[1] else "",
                    "checkout": str(d[2]) if d[2] else "",
                    "sub_total": float(d[3]) if d[3] else 0.0,
                    "room_status": d[4] or "CONFIRMED"
                })

            raw_status = r[1]
            status_text = status_map.get(raw_status, str(raw_status))

            bookings_result.append({
                "booking_id": b_id,
                "booking_status": status_text,
                "customer_name": r[2] or "Khách vãng lai",
                "customer_phone": r[3] or "N/A",
                "customer_cccd": r[4] or "N/A",
                "hotel_name": r[5] or "Hệ thống Sen Việt",
                "order_id": r[6] or "N/A",
                "total_amount_vnd": float(r[8]) if r[8] else (room_items[0]["sub_total"] if room_items else 0.0),
                "paid_amount_vnd": float(r[9]) if r[9] else 0.0,
                "remaining_amount_vnd": float(r[10]) if r[10] else 0.0,
                "payment_status": r[11] or ("PAID" if r[9] and r[9] > 0 else "UNPAID"),
                "rooms": room_items
            })

        cur.close()
        conn.close()

        return json.dumps({
            "status": "success",
            "found_count": len(bookings_result),
            "bookings": bookings_result
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

def get_daily_operational_summary(branch_keyword: str = "Sài Gòn", query_date: str = "") -> str:
    """
    Báo cáo danh sách vận hành trong ngày tại chi nhánh:
    Danh sách khách check-in hôm nay, check-out hôm nay, danh sách phòng bẩn cần dọn (DIRTY) từ cơ sở dữ liệu.
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        hotel_row = _find_matching_hotel(cur, branch_keyword)
        if not hotel_row:
            cur.close()
            conn.close()
            return json.dumps({"status": "error", "message": "Không tìm thấy chi nhánh phù hợp."}, ensure_ascii=False)

        h_id, h_name = hotel_row[0], hotel_row[1]
        target_date_str = query_date.strip() if query_date and query_date.strip() else get_current_date()

        # 1. Khách check-in
        cur.execute("""
            SELECT b.booking_id, c.full_name, c.phone, bd.room_id, r.room_type, bd.checkin_time
            FROM bookings b
            JOIN booking_details bd ON b.booking_id = bd.booking_id
            LEFT JOIN customers c ON b.customer_id = c.customer_id
            LEFT JOIN rooms r ON bd.room_id = r.room_id
            WHERE b.hotel_id = %s AND DATE(bd.checkin_time) = %s
        """, (h_id, target_date_str))
        checkins = [{"booking_id": r[0], "customer": r[1] or "Khách", "phone": r[2] or "", "room": r[3] or "Chưa xếp", "type": r[4] or "", "checkin_time": str(r[5])} for r in cur.fetchall()]

        # 2. Khách check-out
        cur.execute("""
            SELECT b.booking_id, c.full_name, c.phone, bd.room_id, r.room_type, bd.checkout_time
            FROM bookings b
            JOIN booking_details bd ON b.booking_id = bd.booking_id
            LEFT JOIN customers c ON b.customer_id = c.customer_id
            LEFT JOIN rooms r ON bd.room_id = r.room_id
            WHERE b.hotel_id = %s AND DATE(bd.checkout_time) = %s
        """, (h_id, target_date_str))
        checkouts = [{"booking_id": r[0], "customer": r[1] or "Khách", "phone": r[2] or "", "room": r[3] or "Chưa xếp", "type": r[4] or "", "checkout_time": str(r[5])} for r in cur.fetchall()]

        # 3. Phòng bẩn / cần dọn (DIRTY / CLEANING)
        cur.execute("""
            SELECT r.room_id, r.room_type, f.floor_number, r.room_status
            FROM rooms r
            JOIN floors f ON r.floor_id = f.floor_id
            JOIN buildings b ON f.building_id = b.building_id
            WHERE b.hotel_id = %s AND r.room_status IN ('DIRTY', 'CLEANING')
            ORDER BY f.floor_number ASC, r.room_id ASC
        """, (h_id,))
        dirty_rooms = [{"room_id": r[0], "room_type": r[1], "floor": r[2], "status": r[3]} for r in cur.fetchall()]

        cur.close()
        conn.close()

        return json.dumps({
            "status": "success",
            "hotel_id": h_id,
            "hotel_name": h_name,
            "date": target_date_str,
            "checkin_count": len(checkins),
            "checkin_list": checkins,
            "checkout_count": len(checkouts),
            "checkout_list": checkouts,
            "dirty_rooms_count": len(dirty_rooms),
            "dirty_rooms_list": dirty_rooms
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

def get_revenue_and_occupancy_report(branch_keyword: str = "Sài Gòn") -> str:
    """
    Thống kê doanh thu và số lượng đặt phòng thực tế trong cơ sở dữ liệu (bảng orders và bookings).
    Tuyệt đối không giả lập hay tạo dữ liệu ảo.
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        hotel_row = _find_matching_hotel(cur, branch_keyword)
        h_id = hotel_row[0] if hotel_row else 1
        h_name = hotel_row[1] if hotel_row else "Sen Việt Sài Gòn"

        # Tổng số phòng
        cur.execute("""
            SELECT COUNT(*) 
            FROM rooms r
            JOIN floors f ON r.floor_id = f.floor_id
            JOIN buildings b ON f.building_id = b.building_id
            WHERE b.hotel_id = %s
        """, (h_id,))
        total_rooms = cur.fetchone()[0] or 0

        # Doanh thu thực tế từ orders
        cur.execute("""
            SELECT COUNT(b.booking_id), 
                   COALESCE(SUM(o.paid_amount), 0), 
                   COALESCE(SUM(o.total_amount), 0)
            FROM bookings b
            LEFT JOIN orders o ON b.order_id = o.order_id
            WHERE b.hotel_id = %s
        """, (h_id,))
        b_count, paid_rev, total_rev = cur.fetchone()

        # Số phòng đang có khách ở hoặc hoàn tất
        cur.execute("""
            SELECT COUNT(DISTINCT bd.room_id)
            FROM booking_details bd
            JOIN bookings b ON bd.booking_id = b.booking_id
            WHERE b.hotel_id = %s AND bd.status IN ('CONFIRMED', 'IN_HOUSE', 'COMPLETED')
        """, (h_id,))
        active_rooms = cur.fetchone()[0] or 0

        cur.close()
        conn.close()

        occupancy_pct = round((active_rooms / total_rooms) * 100, 1) if total_rooms > 0 else 0.0

        return json.dumps({
            "status": "success",
            "hotel_id": h_id,
            "hotel_name": h_name,
            "total_rooms_in_hotel": total_rooms,
            "total_bookings_recorded": b_count,
            "total_paid_revenue_vnd": float(paid_rev),
            "total_order_amount_vnd": float(total_rev),
            "current_occupied_or_booked_rooms": active_rooms,
            "occupancy_rate_percent": f"{occupancy_pct}%"
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

def get_customer_reviews_analysis(branch_keyword: str = "Sài Gòn") -> str:
    """
    Truy vấn và phân tích đánh giá thực tế của khách hàng từ bảng reviews trong cơ sở dữ liệu.
    Không dùng văn bản dựng sẵn.
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        hotel_row = _find_matching_hotel(cur, branch_keyword)
        h_id = hotel_row[0] if hotel_row else 1
        h_name = hotel_row[1] if hotel_row else "Sen Việt Sài Gòn"

        cur.execute("""
            SELECT rating, title, comment, cleanliness_rating, service_rating, facilities_rating, location_rating
            FROM reviews
            WHERE hotel_id = %s
            ORDER BY review_id DESC
        """, (h_id,))
        rows = cur.fetchall()
        cur.close()
        conn.close()

        if not rows:
            return json.dumps({
                "status": "success",
                "hotel_name": h_name,
                "total_reviews": 0,
                "message": f"Chi nhánh {h_name} hiện chưa có đánh giá nào trong hệ thống."
            }, ensure_ascii=False)

        total_rev = len(rows)
        avg_rating = round(sum(r[0] for r in rows) / total_rev, 2)
        avg_clean = round(sum((r[3] or r[0]) for r in rows) / total_rev, 2)
        avg_service = round(sum((r[4] or r[0]) for r in rows) / total_rev, 2)
        avg_facilities = round(sum((r[5] or r[0]) for r in rows) / total_rev, 2)
        avg_location = round(sum((r[6] or r[0]) for r in rows) / total_rev, 2)

        reviews_data = [
            {"rating": r[0], "title": r[1] or "", "comment": r[2] or ""}
            for r in rows
        ]

        return json.dumps({
            "status": "success",
            "hotel_name": h_name,
            "total_reviews": total_rev,
            "average_overall_rating": avg_rating,
            "average_cleanliness_rating": avg_clean,
            "average_service_rating": avg_service,
            "average_facilities_rating": avg_facilities,
            "average_location_rating": avg_location,
            "reviews_list": reviews_data
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

def get_hotel_services_and_promotions(branch_keyword: str = "") -> str:
    """
    Tra cứu danh mục dịch vụ (bảng services) và các chương trình khuyến mãi hiện có (bảng promotions) trong database.
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Dịch vụ
        cur.execute("""
            SELECT name, price, unit, category, active
            FROM services
            WHERE active = true
            ORDER BY category, name;
        """)
        services = [{"name": r[0], "price_vnd": float(r[1]), "unit": r[2] or "lượt", "category": r[3] or "Khác"} for r in cur.fetchall()]

        # Khuyến mãi
        cur.execute("""
            SELECT code, name, type, discount_value, max_discount_amount, min_booking_value, start_date, end_date, status
            FROM promotions
            WHERE status = 1 OR status = 'ACTIVE'
            ORDER BY id DESC;
        """)
        promotions = [{
            "code": r[0],
            "name": r[1],
            "discount_value": float(r[3]) if r[3] else 0.0,
            "start_date": str(r[6]) if r[6] else "",
            "end_date": str(r[7]) if r[7] else ""
        } for r in cur.fetchall()]

        cur.close()
        conn.close()

        return json.dumps({
            "status": "success",
            "total_active_services": len(services),
            "services": services,
            "total_active_promotions": len(promotions),
            "promotions": promotions
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

def get_today_duty_roster(branch_keyword: str = "Sài Gòn", query_date: str = "") -> str:
    """
    Tra cứu danh sách ca trực thực tế trong ngày từ bảng shift_assignments và leave_requests.
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        hotel_row = _find_matching_hotel(cur, branch_keyword)
        if not hotel_row:
            cur.close()
            conn.close()
            return json.dumps({"status": "error", "message": "Không tìm thấy chi nhánh phù hợp."}, ensure_ascii=False)

        h_id, h_name, h_address, h_phone = hotel_row[0], hotel_row[1], hotel_row[2], hotel_row[3]

        target_date_str = query_date.strip() if query_date and query_date.strip() else get_current_date()
        try:
            target_date = datetime.datetime.strptime(target_date_str, "%Y-%m-%d").date()
        except Exception:
            target_date = datetime.date.today()
            target_date_str = target_date.strftime("%Y-%m-%d")

        cur.execute("""
            SELECT sa.shift_type, sa.shift_time, sa.role, sa.task, e.full_name, sa.employee_id, e.phone
            FROM shift_assignments sa
            LEFT JOIN employees e ON sa.employee_id = e.employee_id
            WHERE sa.hotel_id = %s AND sa.work_date = %s
            ORDER BY sa.role DESC, sa.shift_type ASC
        """, (h_id, target_date))
        shift_rows = cur.fetchall()

        reception_shifts = []
        housekeeping_shifts = []

        for r in shift_rows:
            item = {
                "shift_type": r[0],
                "shift_time": r[1] or ("06:00 – 14:00" if "sáng" in r[0].lower() else "14:00 – 22:00"),
                "employee_name": r[4] or "Chưa phân công",
                "employee_id": r[5] or "N/A",
                "task": r[3] or "Trực ca",
                "phone": r[6] or ""
            }
            if "lễ tân" in r[2].lower() or "rec" in r[2].lower():
                reception_shifts.append(item)
            else:
                housekeeping_shifts.append(item)

        cur.execute("""
            SELECT lr.employee_id, e.full_name, lr.start_date, lr.end_date, lr.reason
            FROM leave_requests lr
            JOIN employees e ON lr.employee_id = e.employee_id
            WHERE lr.hotel_id = %s 
              AND lr.status = 'APPROVED'
              AND lr.start_date <= %s 
              AND lr.end_date >= %s
        """, (h_id, target_date, target_date))
        leave_rows = cur.fetchall()
        leaves = [{"employee_id": r[0], "employee_name": r[1], "reason": r[4] or "Nghỉ phép cá nhân"} for r in leave_rows]

        cur.close()
        conn.close()

        return json.dumps({
            "status": "success",
            "hotel_id": h_id,
            "hotel_name": h_name,
            "date": target_date_str,
            "reception_shifts": reception_shifts,
            "housekeeping_shifts": housekeeping_shifts,
            "approved_leaves_today": leaves
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

def get_weekly_schedule_overview(branch_keyword: str = "Sài Gòn", week_start_date: str = "") -> str:
    """
    Tra cứu thời khóa biểu ca trực cả tuần của chi nhánh từ bảng shift_assignments.
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        h_row = _find_matching_hotel(cur, branch_keyword)
        h_id = h_row[0] if h_row else 1
        h_name = h_row[1] if h_row else "Sen Việt Sài Gòn"

        if week_start_date:
            w_start = datetime.datetime.strptime(week_start_date, "%Y-%m-%d").date()
        else:
            today = datetime.date.today()
            w_start = today - datetime.timedelta(days=today.weekday())
        w_end = w_start + datetime.timedelta(days=6)

        cur.execute("""
            SELECT sa.work_date, sa.shift_type, sa.role, e.full_name, sa.task, sa.employee_id
            FROM shift_assignments sa
            LEFT JOIN employees e ON sa.employee_id = e.employee_id
            WHERE sa.hotel_id = %s AND sa.work_date >= %s AND sa.work_date <= %s
            ORDER BY sa.work_date ASC, sa.shift_type ASC
        """, (h_id, w_start, w_end))
        rows = cur.fetchall()
        cur.close()
        conn.close()

        schedule_by_date = {}
        for r in rows:
            d_str = str(r[0])
            if d_str not in schedule_by_date:
                schedule_by_date[d_str] = []
            schedule_by_date[d_str].append({
                "shift_type": r[1],
                "role": r[2],
                "employee_name": r[3] or "Chưa phân công",
                "employee_id": r[5],
                "task": r[4]
            })

        return json.dumps({
            "status": "success",
            "hotel_id": h_id,
            "hotel_name": h_name,
            "week_start": str(w_start),
            "week_end": str(w_end),
            "total_shifts": len(rows),
            "daily_schedule": schedule_by_date
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

def schedule_weekly_shifts_ai(hotel_id: int, week_start_date: str = "", requirements: str = "") -> str:
    """
    AI tự động phân công lịch trực tuần mới cho nhân viên dựa trên các ràng buộc nghiệp vụ thực tế và lưu vào cơ sở dữ liệu.
    """
    try:
        res = staff_scheduler.generate_schedule(
            hotel_id=hotel_id,
            week_start_str=week_start_date or None,
            user_prompt=requirements or None,
            save_to_db=True
        )
        return json.dumps({"status": "success", "schedule": res.model_dump()}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

def get_staff_directory(branch_keyword: str = "Sài Gòn") -> str:
    """
    Lấy danh bạ toàn bộ nhân sự thực tế từ bảng employees: Mã NV, họ tên, chức vụ, số điện thoại.
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        h_row = _find_matching_hotel(cur, branch_keyword)
        h_id = h_row[0] if h_row else 1
        h_name = h_row[1] if h_row else "Sen Việt Sài Gòn"

        cur.execute("""
            SELECT employee_id, full_name, position, phone
            FROM employees
            WHERE hotel_id = %s
            ORDER BY position DESC, employee_id ASC
        """, (h_id,))
        rows = cur.fetchall()
        cur.close()
        conn.close()

        staff_list = [{"id": r[0], "name": r[1], "position": r[2] or "Nhân viên", "phone": r[3] or ""} for r in rows]
        return json.dumps({"status": "success", "hotel_name": h_name, "total_staff": len(staff_list), "staff": staff_list}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

# ==================== LIST OF ALL TOOLS ====================

ADMIN_COPILOT_TOOLS = [
    query_room_availability,
    query_booking_details,
    get_daily_operational_summary,
    get_revenue_and_occupancy_report,
    get_customer_reviews_analysis,
    get_hotel_services_and_promotions,
    get_today_duty_roster,
    get_weekly_schedule_overview,
    schedule_weekly_shifts_ai,
    get_staff_directory
]

# ==================== STRICT SYSTEM INSTRUCTION ====================

def build_admin_copilot_system_instruction(today_date: str) -> str:
    return f"""Bạn là **Trợ lý AI Quản trị Khách sạn Sen Việt (Staff & Admin Copilot)** — Hỗ trợ Ban Quản lý, Lễ tân và Nhân viên vận hành của Hệ thống Khách sạn Sen Việt.

# 1. NGUYÊN TẮC BẮT BUỘC (TUÂN THỦ 100%):
1. **ĐỐI TƯỢNG PHỤC VỤ LÀ NHÂN VIÊN / ADMIN NỘI BỘ:**
   - Bạn đang nói chuyện với nhân sự nội bộ, KHÔNG PHẢI KHÁCH DU LỊCH.
   - Không hỏi khách đặt phòng mấy người hay ngày nào.
   - Xưng "em" và gọi người dùng là "Quý Quản lý", "Anh/Chị".
2. **TUYỆT ĐỐI KHÔNG BỊA ĐẶT DỮ LIỆU HOẶC QUY CHẾ:**
   - Mọi số liệu về phòng trống, đặt phòng, doanh thu, ca trực, nhân viên, dịch vụ, đánh giá PHẢI LẤY TỪ CÔNG CỤ (TOOLS) KẾT NỐI DATABASE THỰC TẾ.
   - Nếu trong cơ sở dữ liệu số liệu là 0 hoặc chưa có đơn, hãy báo đúng thực tế là 0, TUYỆT ĐỐI KHÔNG TỰ BỊA RA CON SỐ HAY TỶ LỆ PHẦN TRĂM ẢO.
   - Không bịa đặt các mức phạt đền bù, chính sách hoàn tiền ngoài dữ liệu hệ thống.

# 2. HƯỚNG DẪN GỌI CÔNG CỤ THEO ĐÚNG NGHIỆP VỤ:
- **Tra cứu phòng trống, tình trạng phòng:** Gọi `query_room_availability`. Báo cáo số phòng READY, OCCUPIED, DIRTY và giá cơ bản niêm yết.
- **Tra cứu đặt phòng (Booking):** Gọi `query_booking_details` theo mã booking, tên khách hoặc SĐT. Báo cáo đúng trạng thái booking và số tiền trong database.
- **Danh sách khách check-in, check-out, phòng bẩn hôm nay:** Gọi `get_daily_operational_summary`.
- **Báo cáo doanh thu & công suất phòng:** Gọi `get_revenue_and_occupancy_report`. Báo cáo đúng doanh thu thực tế và số booking trong DB.
- **Phân tích đánh giá khách hàng:** Gọi `get_customer_reviews_analysis`. Đọc từ danh sách đánh giá thật trong DB để tóm tắt nhận xét của khách.
- **Tra cứu dịch vụ & khuyến mãi:** Gọi `get_hotel_services_and_promotions`.
- **Tra cứu ca trực hôm nay:** Gọi `get_today_duty_roster`.
- **Tra cứu lịch trực cả tuần:** Gọi `get_weekly_schedule_overview`.
- **Xếp lịch tuần mới bằng AI:** Gọi `schedule_weekly_shifts_ai`.
- **Tra cứu danh bạ nhân sự:** Gọi `get_staff_directory`.

# 3. THỜI GIAN HIỆN TẠI:
- Hôm nay là ngày: {today_date}.
"""

# ==================== ENDPOINT HANDLERS ====================

@router.post("/chat", response_model=AdminApiResponse, summary="Gửi câu hỏi tới Trợ lý AI Quản trị & Vận hành")
async def admin_chat_endpoint(request: AdminChatRequest):
    session_id = request.sessionId if request.sessionId and request.sessionId.strip() else str(uuid.uuid4())
    today_date = get_current_date()

    try:
        model = genai.GenerativeModel(
            model_name=settings.GEMINI_MODEL,
            tools=ADMIN_COPILOT_TOOLS,
            system_instruction=build_admin_copilot_system_instruction(today_date)
        )

        formatted_history = []
        for h in (request.history or []):
            role = "user" if h.role == "user" else "model"
            if h.content.strip():
                formatted_history.append({"role": role, "parts": [h.content]})

        chat = model.start_chat(history=formatted_history, enable_automatic_function_calling=True)

        user_input_prompt = f"""[YÊU CẦU NGHIỆP VỤ TỪ QUẢN TRỊ VIÊN / NHÂN VIÊN]
Hôm nay là ngày: {today_date}.
Tin nhắn của Quản trị viên: {request.message}"""

        reply_text = ""
        for attempt in range(3):
            try:
                response = chat.send_message(user_input_prompt)
                reply_text = response.text
                break
            except Exception as e:
                error_msg = str(e)
                print(f"[Admin Copilot Gemini attempt {attempt+1}] {error_msg}")
                if "429" in error_msg or "ResourceExhausted" in error_msg or "quota" in error_msg.lower():
                    import time
                    time.sleep(10 * (attempt + 1))
                else:
                    break

        if not reply_text:
            reply_text = "Dạ, hệ thống Trợ lý Quản trị AI đang tạm bận. Quý Quản lý vui lòng thử lại sau giây lát ạ!"

        # Lưu lịch sử chat của admin vào PostgreSQL
        try:
            save_chat_turn(
                session_id=session_id,
                user_message=request.message,
                bot_reply=reply_text,
                state={"role": "ADMIN_COPILOT"}
            )
        except Exception as db_err:
            print(f"[Warning] Lưu lịch sử Admin chat thất bại: {db_err}")

        return AdminApiResponse(
            code=1000,
            message="Success",
            result=AdminChatResult(
                reply=reply_text,
                sessionId=session_id,
                metadata={"role": "ADMIN_COPILOT", "date": today_date}
            )
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi xử lý Trợ lý Quản trị AI: {str(e)}")

@router.get("/chat/history/{session_id}", summary="Lấy lịch sử hội thoại Quản trị")
async def get_admin_chat_history(session_id: str):
    data = get_session_history(session_id)
    return {
        "code": 1000,
        "message": "Success",
        "result": data
    }

@router.delete("/chat/history/{session_id}", summary="Xóa lịch sử hội thoại Quản trị")
async def delete_admin_chat_history(session_id: str):
    success = delete_session_history(session_id)
    return {
        "code": 1000,
        "message": "Success" if success else "Failed",
        "result": {"deleted": success, "sessionId": session_id}
    }
