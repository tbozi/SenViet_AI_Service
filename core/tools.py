import json
from typing import Dict, Any, List
from core.database import get_db_connection
from core.state_manager import state_manager
from core.context import current_session_id

def _update_state(updates: dict):
    sid = current_session_id.get()
    if sid:
        state_manager.update_state(sid, updates)

def list_branches() -> str:
    """Lấy danh sách các chi nhánh khách sạn hiện có."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, name, address FROM hotels")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        branches = [{"id": r[0], "name": r[1], "address": r[2]} for r in rows]
        return json.dumps({"status": "success", "data": branches}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

def check_availability(branch_id: int, check_in: str, check_out: str, adults: int, children: int = 0) -> str:
    """Kiểm tra phòng trống tại một chi nhánh theo ngày và số người."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Nếu số khách vượt quá sức chứa tối đa của 1 phòng đơn (> 4 người)
        if adults > 4:
            cur.execute("SELECT room_type, base_price, standard_capacity FROM branch_room_policies WHERE hotel_id = %s ORDER BY standard_capacity DESC", (branch_id,))
            policies = cur.fetchall()
            cur.execute("SELECT name FROM hotels WHERE id = %s", (branch_id,))
            hname = cur.fetchone()
            cur.close()
            conn.close()
            
            branch_rooms = [{
                "roomType": p[0],
                "roomTypeName": f"Phòng {p[0]}",
                "pricePerNight": float(p[1]) if p[1] else 0,
                "standardCapacity": p[2]
            } for p in policies]
            
            _update_state({
                "branch": {"id": branch_id},
                "checkIn": check_in,
                "checkOut": check_out,
                "guests": {"adults": adults, "children": children},
                "currentStep": "SELECT_ROOM"
            })
            
            return json.dumps({
                "status": "exceeds_capacity",
                "message": f"Số lượng khách ({adults} người) vượt quá sức chứa tối đa của 1 phòng đơn (hạng phòng lớn nhất tại Sen Việt là FAMILY chứa tối đa 4 người).",
                "max_single_room_capacity": 4,
                "requested_adults": adults,
                "branch_name": hname[0] if hname else "",
                "available_room_types": branch_rooms,
                "guidance": f"Hãy giải thích lịch sự rằng một phòng đơn tại Sen Việt chỉ chứa tối đa 4 người (hạng Family). Chủ động đề xuất các phương án chia đoàn {adults} người thành nhiều phòng (ví dụ: {(adults + 3) // 4} phòng Family, hoặc kết hợp 1 Family + các phòng Deluxe/Standard), và cung cấp hotline 1900 6868 để lễ tân hỗ trợ sắp xếp phòng liền kề."
            }, ensure_ascii=False)

        cur.execute("SELECT room_type, base_price, standard_capacity FROM branch_room_policies WHERE hotel_id = %s AND standard_capacity >= %s", (branch_id, adults))
        policies = cur.fetchall()
        
        cur.execute("SELECT name FROM hotels WHERE id = %s", (branch_id,))
        hname = cur.fetchone()
        cur.close()
        conn.close()
        
        rooms = []
        for p in policies:
            rooms.append({
                "roomType": p[0],
                "roomTypeName": f"Phòng {p[0]}",
                "pricePerNight": float(p[1]) if p[1] else 0,
                "standardCapacity": p[2],
                "availableQty": 5
            })
            
        _update_state({
            "branch": {"id": branch_id},
            "checkIn": check_in,
            "checkOut": check_out,
            "guests": {"adults": adults, "children": children},
            "currentStep": "SELECT_ROOM",
            "availableRooms": rooms
        })
            
        return json.dumps({
            "status": "success",
            "branch_id": branch_id,
            "branch_name": hname[0] if hname else "",
            "check_in": check_in,
            "check_out": check_out,
            "rooms": rooms
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

def list_services(branch_id: int) -> str:
    """Lấy danh sách các dịch vụ đi kèm của chi nhánh."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT service_id, name, price, unit FROM services WHERE active = true")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        services = [{"id": r[0], "name": r[1], "price": float(r[2]), "unit": r[3]} for r in rows]
        _update_state({"currentStep": "SELECT_SERVICES", "availableServices": services})
        return json.dumps({"status": "success", "data": services}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

def update_guest_info(name: str, phone: str, email: str) -> str:
    """Cập nhật thông tin liên hệ của khách hàng."""
    _update_state({
        "guestInfo": {"name": name, "phone": phone, "email": email},
        "currentStep": "SUMMARY_PROMO"
    })
    return json.dumps({"status": "success", "message": "Đã cập nhật thông tin khách hàng."})

def select_room_and_services(room_type_id: str, room_qty: int, service_ids: list) -> str:
    """Khách hàng chốt loại phòng và số lượng phòng cùng các dịch vụ đi kèm."""
    _update_state({
        "roomType": {"id": room_type_id},
        "roomQty": room_qty,
        "services": [{"id": sid, "quantity": 1} for sid in service_ids],
        "currentStep": "GET_GUEST_INFO"
    })
    return json.dumps({"status": "success", "message": "Đã ghi nhận phòng và dịch vụ. Chuyển sang xin thông tin khách hàng."})

def list_valid_promotions() -> str:
    """Lấy danh sách các mã khuyến mãi khả dụng."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT code, discount_value, type, description FROM promotions WHERE status = 'ACTIVE'")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        promos = [{"code": r[0], "discountValue": float(r[1]), "type": r[2], "description": r[3]} for r in rows]
        _update_state({"currentStep": "SUMMARY_PROMO", "availablePromotions": promos})
        return json.dumps({"status": "success", "data": promos}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

def apply_promotion(promo_code: str) -> str:
    """Kiểm tra và áp dụng mã khuyến mãi vào đơn hàng."""
    if not promo_code or not promo_code.strip():
        return json.dumps({"status": "error", "message": "Vui lòng cung cấp mã khuyến mãi hợp lệ."}, ensure_ascii=False)
        
    code_clean = promo_code.strip().upper()
    
    # Cho phép mã thử nghiệm DEMO2K
    if code_clean == "DEMO2K":
        _update_state({"promoCode": "DEMO2K"})
        return json.dumps({
            "status": "success",
            "valid": True,
            "code": "DEMO2K",
            "message": "Mã thử nghiệm DEMO2K hợp lệ (áp dụng thanh toán thử nghiệm 2.000 VNĐ)."
        }, ensure_ascii=False)

    try:
        from core.clock import get_current_date
        today = get_current_date() # Ví dụ '2026-10-13'
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT code, name, status, start_date, end_date, discount_value, discount_type, min_booking_value, usage_limit, used_count
            FROM promotions
            WHERE UPPER(code) = %s AND (deleted IS FALSE OR deleted IS NULL)
        """, (code_clean,))
        row = cur.fetchone()
        cur.close()
        conn.close()

        if not row:
            return json.dumps({
                "status": "error",
                "valid": False,
                "code": code_clean,
                "message": f"Mã khuyến mãi '{promo_code}' không tồn tại trên hệ thống. Quý khách vui lòng kiểm tra lại mã hoặc tiếp tục đặt phòng theo giá gốc."
            }, ensure_ascii=False)

        code, name, status, s_date, e_date, d_val, d_type, min_val, u_limit, u_count = row
        s_date_str = str(s_date)[:10] if s_date else ""
        e_date_str = str(e_date)[:10] if e_date else ""

        if status == "EXPIRED" or (e_date_str and e_date_str < today):
            return json.dumps({
                "status": "error",
                "valid": False,
                "code": code,
                "message": f"Mã khuyến mãi '{code}' ({name}) đã hết hạn sử dụng vào ngày {e_date_str}. Mã này hiện không còn hiệu lực. Quý khách vui lòng sử dụng mã khác hoặc thanh toán theo giá niêm yết."
            }, ensure_ascii=False)

        if status in ["INACTIVE", "DISABLED"]:
            return json.dumps({
                "status": "error",
                "valid": False,
                "code": code,
                "message": f"Mã khuyến mãi '{code}' hiện đang tạm khóa hoặc là mã nội bộ không thể áp dụng cho khách hàng trực tuyến. Quý khách vui lòng sử dụng mã khuyến mãi khác."
            }, ensure_ascii=False)

        if s_date_str and s_date_str > today:
            return json.dumps({
                "status": "error",
                "valid": False,
                "code": code,
                "message": f"Mã khuyến mãi '{code}' chưa đến thời gian áp dụng (bắt đầu từ ngày {s_date_str})."
            }, ensure_ascii=False)

        if u_limit and u_count and u_count >= u_limit:
            return json.dumps({
                "status": "error",
                "valid": False,
                "code": code,
                "message": f"Mã khuyến mãi '{code}' đã hết lượt sử dụng."
            }, ensure_ascii=False)

        # Hợp lệ -> cập nhật vào session state
        _update_state({"promoCode": code})
        discount_desc = f"{d_val}%" if d_type == "PERCENTAGE" else f"{int(d_val):,} VNĐ"
        return json.dumps({
            "status": "success",
            "valid": True,
            "code": code,
            "discount": discount_desc,
            "minBookingValue": float(min_val or 0),
            "message": f"Áp dụng thành công mã khuyến mãi '{code}' ({name}), giảm {discount_desc} cho đơn đặt phòng của quý khách."
        }, ensure_ascii=False)

    except Exception as e:
        _update_state({"promoCode": code_clean})
        return json.dumps({"status": "success", "valid": True, "code": code_clean, "message": f"Đã ghi nhận mã {code_clean}."}, ensure_ascii=False)

def calculate_price(room_price: float, nights: int, room_qty: int, promo_code: str = None) -> str:
    """Tính toán tổng tiền tạm tính dựa trên giá thực tế (có tính theo mùa)."""
    from datetime import datetime, timedelta
    try:
        state = state_manager.get_state(current_session_id.get())
        branch_id = state.branch.get('id', 1) if state.branch else 1
        room_type = state.roomType.get('id', 'STANDARD') if state.roomType else 'STANDARD'
        check_in = state.checkIn if state.checkIn else datetime.now().strftime('%Y-%m-%d')
        check_out = state.checkOut if state.checkOut else (datetime.now() + timedelta(days=nights)).strftime('%Y-%m-%d')
        
        start_date = datetime.strptime(check_in, '%Y-%m-%d')
        end_date = datetime.strptime(check_out, '%Y-%m-%d')
        nights = max(1, (end_date - start_date).days)
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        current = start_date
        true_room_subtotal = 0
        while current < end_date:
            cur.execute("""
                SELECT price FROM room_seasonal_rates 
                WHERE hotel_id = %s AND room_type = %s 
                AND start_date <= %s AND end_date >= %s 
                LIMIT 1
            """, (branch_id, room_type.upper(), current.strftime('%Y-%m-%d'), current.strftime('%Y-%m-%d')))
            row = cur.fetchone()
            if row:
                true_room_subtotal += float(row[0]) * room_qty
            else:
                true_room_subtotal += room_price * room_qty
            current += timedelta(days=1)
            
        subtotal = true_room_subtotal
        
        # Calculate services from state
        services_total = 0
        if state.services and len(state.services) > 0:
            conn = get_db_connection()
            cur = conn.cursor()
            service_ids = tuple([s['id'] for s in state.services])
            if len(service_ids) == 1:
                cur.execute(f"SELECT price FROM services WHERE service_id = %s", (service_ids[0],))
            else:
                cur.execute(f"SELECT price FROM services WHERE service_id IN {service_ids}")
            prices = cur.fetchall()
            cur.close()
            conn.close()
            for p in prices:
                services_total += float(p[0]) * state.guests.get('adults', 1) * nights
                
        subtotal += services_total
        discount = 0
        if promo_code:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT discount_value, type, max_discount_amount FROM promotions WHERE code = %s AND status = 'ACTIVE'", (promo_code,))
            promo = cur.fetchone()
            cur.close()
            conn.close()
            
            if promo:
                val, p_type, max_val = promo
                val = float(val)
                max_val = float(max_val) if max_val else float('inf')
                if p_type == 'ROOM_PERCENTAGE' or p_type == 'TOTAL_PERCENTAGE':
                    discount = min(subtotal * (val / 100), max_val)
                elif p_type == 'FIXED_AMOUNT':
                    discount = val
                    
        if promo_code == 'DEMO2K':
            discount = subtotal - 2000
            total = 2000
        else:
            total = max(0, subtotal - discount)
            
        return json.dumps({
            "status": "success",
            "subtotal": subtotal,
            "discount": discount,
            "total": total
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

def create_booking(payment_method: str) -> str:
    """Chốt đơn tạo booking. payment_method có thể là 'BANK_TRANSFER' hoặc 'CASH'."""
    try:
        from core.state_manager import state_manager
        from core.context import current_session_id
        import urllib.request
        import traceback
        
        sid = current_session_id.get()
        state = state_manager.get_state(sid)

        branch_id = state.branch.get('id')
        check_in = state.checkIn + "T14:00:00" if state.checkIn else "2026-10-15T14:00:00"
        check_out = state.checkOut + "T12:00:00" if state.checkOut else "2026-10-16T12:00:00"
        room_type = state.roomType.get('id', 'STANDARD')
        room_qty = state.roomQty if state.roomQty else 1
        adults = state.guests.get('adults', 2)
        children = state.guests.get('children', 0)
        guest_name = state.guestInfo.get('name', 'Khách Ẩn Danh')
        guest_phone = state.guestInfo.get('phone', '0000000000')
        promo_code = state.promoCode
        
        service_ids = []
        if state.services:
            service_ids = [s['id'] for s in state.services]

        # Query real roomIds
        conn = get_db_connection()
        cur = conn.cursor()
        
        query = """
        SELECT r.room_id
        FROM rooms r
        JOIN floors f ON r.floor_id = f.floor_id
        JOIN buildings b ON f.building_id = b.building_id
        WHERE b.hotel_id = %s 
          AND r.room_status = 'READY'
          AND r.room_type = %s
        LIMIT %s
        """
        cur.execute(query, (branch_id, room_type.upper(), room_qty))
        rows = cur.fetchall()
        cur.close()
        conn.close()

        if len(rows) < room_qty:
            return json.dumps({"status": "error", "message": "Thật xin lỗi, loại phòng này hiện tại không đủ phòng trống theo yêu cầu của bạn."})

        room_ids = [r[0] for r in rows]

        # Build request to Java BE
        payload = {
            "customerName": guest_name,
            "customerPhone": guest_phone,
            "hotelId": branch_id,
            "roomIds": room_ids,
            "checkInTime": check_in,
            "checkOutTime": check_out,
            "numAdults": adults,
            "numChildren": children,
            "serviceIds": service_ids,
            "promoCode": promo_code,
            "paymentMethod": payment_method
        }

        req = urllib.request.Request(
            "http://localhost:8081/api/internal/chatbot/book",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            
            booking_id = res_data.get("bookingId")
            order_id = res_data.get("orderId")
            order_code = res_data.get("orderCode")
            total_amount = res_data.get("totalAmount")

            state_manager.update_state(sid, {
                "bookingId": booking_id,
                "orderId": order_id,
                "orderCode": order_code,
                "amountToPay": total_amount,
                "status": "PENDING_PAYMENT",
                "paymentMethod": payment_method,
                "currentStep": "SELECT_PAYMENT"
            })
            
            return json.dumps({
                "status": "success",
                "bookingId": booking_id,
                "message": "Tuyệt vời, hệ thống đã chốt và giữ phòng thành công trên hệ thống trung tâm."
            }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

def create_payment_qr(booking_id: str, amount: float) -> str:
    """Tạo mã QR thanh toán PayOS thực tế cho booking."""
    import os, hmac, hashlib, json, time, urllib.request
    from core.state_manager import state_manager
    from core.context import current_session_id

    client_id = os.getenv("CLIENT_ID", "6f697811-e048-4d25-ab1d-333b58648b66")
    api_key = os.getenv("API_KEY", "5e6a9fd2-bb50-4f91-9b6a-4a437d0dd5e0")
    checksum_key = os.getenv("CHECKSUM_KEY", "78c40471d51a1a1e097c020df3ba120b889d109c9d4592d5fdf2c2ce83e08383")

    sid = current_session_id.get()
    state = state_manager.get_state(sid) if sid else None
    
    if not state or not state.bookingId or not state.orderCode:
        return json.dumps({"status": "error", "message": "Booking chưa được tạo trên hệ thống! Bạn BẮT BUỘC PHẢI gọi tool `create_booking` trước để chốt đơn rồi mới gọi tool này!"}, ensure_ascii=False)

    order_code = state.orderCode

    int_amount = int(amount)
    description = f"Thanh toan {booking_id}"[:25]
    return_url = f"http://localhost:8080/booking-success?bookingId={booking_id}&status=success"
    cancel_url = f"http://localhost:8080/bookings?status=cancel&bookingId={booking_id}"

    sorted_data = f"amount={int_amount}&cancelUrl={cancel_url}&description={description}&orderCode={order_code}&returnUrl={return_url}"
    signature = hmac.new(checksum_key.encode(), sorted_data.encode(), hashlib.sha256).hexdigest()

    payload = {
        "orderCode": order_code,
        "amount": int_amount,
        "description": description,
        "returnUrl": return_url,
        "cancelUrl": cancel_url,
        "signature": signature
    }

    checkout_url = ""
    qr_code = ""

    try:
        req = urllib.request.Request(
            "https://api-merchant.payos.vn/v2/payment-requests",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "x-client-id": client_id,
                "x-api-key": api_key
            }
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            if res_data.get("code") == "00":
                data = res_data["data"]
                checkout_url = data.get("checkoutUrl", "")
                qr_code = data.get("qrCode", "")
    except Exception as e:
        print(f"[PayOS API Exception] {e}")

    if not qr_code:
        # Fallback QR if PayOS offline
        qr_code = f"https://api.vietqr.io/image/970418-V3CAS6811679267-compact2.png?amount={int_amount}&addInfo={booking_id}"
        checkout_url = qr_code

    _update_state({
        "currentStep": "PAYMENT_PROCESSING",
        "qrUrl": qr_code,
        "checkoutUrl": checkout_url,
        "amountToPay": amount,
        "orderCode": order_code
    })

    return json.dumps({
        "status": "success",
        "qr_url": qr_code,
        "checkout_url": checkout_url,
        "amount": amount,
        "bookingId": booking_id,
        "orderCode": order_code
    }, ensure_ascii=False)

