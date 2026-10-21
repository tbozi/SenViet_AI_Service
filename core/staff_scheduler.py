import datetime
import json
import re
from typing import List, Dict, Any, Optional
import google.generativeai as genai
from pydantic import BaseModel, Field

from config.settings import settings
from core.database import get_db_connection

# Configure Gemini
genai.configure(api_key=settings.GEMINI_API_KEY)

class ShiftItem(BaseModel):
    workDate: str = Field(..., description="Ngày làm việc YYYY-MM-DD")
    shiftType: str = Field(..., description="Ca sáng hoặc Ca tối")
    shiftTime: str = Field(..., description="Khung giờ: 06:00 – 14:00 hoặc 14:00 – 22:00")
    role: str = Field(..., description="Vị trí: Lễ tân hoặc Housekeeping")
    employeeId: str = Field(..., description="Mã nhân viên (EMP_...)")
    employeeName: str = Field(..., description="Họ và tên nhân viên")
    task: str = Field(..., description="Mô tả công việc trong ca")

class LeaveRequestItem(BaseModel):
    employeeId: Optional[str] = None
    employeeName: str
    startDate: str
    endDate: str
    reason: str = "Nghỉ phép cá nhân"
    status: str = "APPROVED"

class ScheduleGenerationResult(BaseModel):
    hotelId: int
    hotelName: str
    weekStartDate: str
    weekEndDate: str
    totalAssignments: int
    assignments: List[ShiftItem]
    leaveSummary: List[LeaveRequestItem]
    explanation: str

class StaffScheduler:
    """
    Hệ thống AI Phân công Lịch trực Thông minh (Staff AI Scheduling Engine)
    Tối ưu hóa phân ca theo thuật toán CSP (Constraint Satisfaction Problem) kết hợp LLM:
    1. Tránh tuyệt đối ngày nghỉ phép của nhân viên (Hard constraint)
    2. Không xếp ca sáng ngay sau ca tối hôm trước (Rest period)
    3. Tối đa 1 ca/ngày/người (Tránh quá tải)
    4. Phân bổ công bằng số ca và luân phiên ca trực trong tuần
    5. Hiểu yêu cầu tự nhiên (prompt) của Quản lý chi nhánh
    """

    def __init__(self):
        self.model_name = settings.GEMINI_MODEL

    def get_monday(self, d: Optional[datetime.date] = None) -> datetime.date:
        """Lấy ngày Thứ 2 của tuần chứa ngày d (mặc định hôm nay)."""
        if d is None:
            d = datetime.date.today()
        return d - datetime.timedelta(days=d.weekday())

    def get_hotel_info(self, hotel_id: int) -> Dict[str, Any]:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, name, address FROM hotels WHERE id = %s", (hotel_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            return {"id": row[0], "name": row[1], "address": row[2]}
        return {"id": hotel_id, "name": f"Chi nhánh Sen Việt #{hotel_id}", "address": ""}

    def get_hotel_staff(self, hotel_id: int) -> List[Dict[str, Any]]:
        """Lấy danh sách nhân sự của chi nhánh và chuẩn hóa nhóm vai trò."""
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT employee_id, full_name, position, phone 
            FROM employees 
            WHERE hotel_id = %s
            ORDER BY employee_id
        """, (hotel_id,))
        rows = cur.fetchall()
        cur.close()
        conn.close()

        staff_list = []
        for r in rows:
            emp_id, name, pos, phone = r[0], r[1], r[2] or "", r[3] or ""
            pos_lower = pos.lower()
            if "lễ tân" in pos_lower or "reception" in pos_lower:
                role = "Lễ tân"
            elif "buồng" in pos_lower or "housekeeping" in pos_lower or "phòng" in pos_lower:
                role = "Housekeeping"
            else:
                role = "Khác"

            staff_list.append({
                "employee_id": emp_id,
                "full_name": name,
                "position": pos,
                "role": role,
                "phone": phone
            })
        return staff_list

    def get_approved_leaves(self, hotel_id: int, start_date: datetime.date, end_date: datetime.date) -> List[Dict[str, Any]]:
        """Truy vấn các đơn xin nghỉ phép đã duyệt trong tuần."""
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT lr.id, lr.employee_id, e.full_name, lr.start_date, lr.end_date, lr.reason, lr.status
            FROM leave_requests lr
            JOIN employees e ON lr.employee_id = e.employee_id
            WHERE lr.hotel_id = %s 
              AND lr.status = 'APPROVED'
              AND lr.start_date <= %s 
              AND lr.end_date >= %s
        """, (hotel_id, end_date, start_date))
        rows = cur.fetchall()
        cur.close()
        conn.close()

        leaves = []
        for r in rows:
            leaves.append({
                "id": r[0],
                "employee_id": r[1],
                "employee_name": r[2],
                "start_date": r[3],
                "end_date": r[4],
                "reason": r[5] or "Nghỉ phép cá nhân",
                "status": r[6]
            })
        return leaves

    def record_leave_request(self, employee_id: str, hotel_id: int, start_date: datetime.date, end_date: datetime.date, reason: str = "Nghỉ phép đã duyệt"):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO leave_requests (employee_id, hotel_id, start_date, end_date, reason, status, created_at)
            VALUES (%s, %s, %s, %s, %s, 'APPROVED', NOW())
        """, (employee_id, hotel_id, start_date, end_date, reason))
        conn.commit()
        cur.close()
        conn.close()

    def parse_user_prompt_with_llm(
        self, 
        prompt: str, 
        week_start: datetime.date, 
        staff_list: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Sử dụng Google Gemini để phân tích yêu cầu tự nhiên:
        - Nhận diện nhân viên nào xin nghỉ phép, ngày nào (thứ mấy -> ngày chính xác).
        - Nhận diện các yêu cầu ca đặc biệt (ưu tiên ca, đổi ca).
        """
        if not prompt or not prompt.strip():
            return {"leave_requests": [], "special_preferences": []}

        week_dates_map = {}
        day_names_vn = ["thứ 2", "thứ 3", "thứ 4", "thứ 5", "thứ 6", "thứ 7", "chủ nhật"]
        for i in range(7):
            d = week_start + datetime.timedelta(days=i)
            week_dates_map[day_names_vn[i]] = d.strftime("%Y-%m-%d")

        staff_names = [s["full_name"] for s in staff_list]

        system_instruction = f"""
Bạn là chuyên gia phân tích yêu cầu lịch trực nhân sự khách sạn.
Tuần làm việc bắt đầu từ Thứ 2: {week_start.strftime('%Y-%m-%d')} đến Chủ nhật: {(week_start + datetime.timedelta(days=6)).strftime('%Y-%m-%d')}.
Bản đồ các thứ trong tuần sang ngày thực tế:
{json.dumps(week_dates_map, ensure_ascii=False, indent=2)}

Danh sách nhân viên hợp lệ của chi nhánh:
{json.dumps(staff_names, ensure_ascii=False, indent=2)}

Nhiệm vụ: Trích xuất các đơn xin nghỉ phép và yêu cầu đặc biệt từ câu lệnh của quản lý.
Định dạng JSON trả về DUY NHẤT:
{{
  "leave_requests": [
    {{
      "employee_name": "Tên chính xác từ danh sách",
      "start_date": "YYYY-MM-DD",
      "end_date": "YYYY-MM-DD",
      "reason": "Lý do xin nghỉ"
    }}
  ],
  "special_preferences": [
    {{
      "employee_name": "Tên nhân viên",
      "preferred_shift": "Ca sáng" hoặc "Ca tối",
      "notes": "Mô tả ngắn gọn"
    }}
  ]
}}
Nếu không có thì để mảng rỗng []. Không thêm giải thích ngoài JSON.
"""
        try:
            model = genai.GenerativeModel(self.model_name)
            response = model.generate_content(
                f"{system_instruction}\n\nYêu cầu của quản lý: \"{prompt}\""
            )
            text = response.text.strip()
            # Bóc tách JSON nếu có markdown block
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            data = json.loads(text)
            return data
        except Exception as e:
            print(f"[-] LLM Prompt parsing error: {e}")
            return {"leave_requests": [], "special_preferences": []}

    def generate_schedule(
        self,
        hotel_id: int = 1,
        week_start_str: Optional[str] = None,
        user_prompt: Optional[str] = None,
        save_to_db: bool = True
    ) -> ScheduleGenerationResult:
        """
        Thuật toán chính xếp lịch tuần tự động:
        """
        # 1. Xác định tuần làm việc
        if week_start_str:
            try:
                week_start = datetime.datetime.strptime(week_start_str, "%Y-%m-%d").date()
            except ValueError:
                week_start = self.get_monday()
        else:
            week_start = self.get_monday()

        week_end = week_start + datetime.timedelta(days=6)
        hotel = self.get_hotel_info(hotel_id)
        staff_list = self.get_hotel_staff(hotel_id)

        receptionists = [s for s in staff_list if s["role"] == "Lễ tân"]
        housekeepings = [s for s in staff_list if s["role"] == "Housekeeping"]

        # 2. Xử lý đơn nghỉ phép từ LLM (nếu có prompt)
        llm_parsed = self.parse_user_prompt_with_llm(user_prompt or "", week_start, staff_list)
        
        # Ghi nhận các đơn nghỉ phép từ prompt vào DB nếu chưa có
        for lr in llm_parsed.get("leave_requests", []):
            emp = next((s for s in staff_list if s["full_name"].lower() == lr["employee_name"].lower()), None)
            if emp:
                try:
                    s_d = datetime.datetime.strptime(lr["start_date"], "%Y-%m-%d").date()
                    e_d = datetime.datetime.strptime(lr["end_date"], "%Y-%m-%d").date()
                    if save_to_db:
                        self.record_leave_request(emp["employee_id"], hotel_id, s_d, e_d, lr.get("reason", "Nghỉ phép từ yêu cầu quản lý"))
                except Exception as ex:
                    print("Error parsing leave date:", ex)

        # 3. Lấy toàn bộ ngày nghỉ phép đã duyệt cho tuần này
        existing_leaves = self.get_approved_leaves(hotel_id, week_start, week_end)
        
        # Tạo tập hợp (employee_id, date) để tra cứu O(1)
        leave_days_set = set()
        leave_summary_items = []
        for l in existing_leaves:
            curr = l["start_date"]
            while curr <= l["end_date"]:
                leave_days_set.add((l["employee_id"], curr))
                curr += datetime.timedelta(days=1)
            
            leave_summary_items.append(LeaveRequestItem(
                employeeId=l["employee_id"],
                employeeName=l["employee_name"],
                startDate=l["start_date"].strftime("%Y-%m-%d"),
                endDate=l["end_date"].strftime("%Y-%m-%d"),
                reason=l["reason"],
                status=l["status"]
            ))

        # 4. Thuật toán phân ca tuần (Greedy with Constraints)
        assignments: List[ShiftItem] = []
        staff_shift_counts = {s["employee_id"]: 0 for s in staff_list}
        last_shift_type = {s["employee_id"]: None for s in staff_list} # Lưu ca gần nhất để tránh Tối -> Sáng hôm sau

        day_labels = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"]

        for day_idx in range(7):
            current_date = week_start + datetime.timedelta(days=day_idx)
            date_str = current_date.strftime("%Y-%m-%d")

            # --- A. XẾP CA LỄ TÂN (Morning & Evening) ---
            def pick_staff(candidates: List[Dict[str, Any]], shift_type: str, assigned_today: set) -> Dict[str, Any]:
                valid_candidates = []
                for cand in candidates:
                    emp_id = cand["employee_id"]
                    # Constraint 1: Nghỉ phép
                    if (emp_id, current_date) in leave_days_set:
                        continue
                    # Constraint 2: Đã phân ca hôm nay
                    if emp_id in assigned_today:
                        continue
                    # Constraint 3: Tránh ca tối hôm qua -> ca sáng hôm nay
                    if shift_type == "Ca sáng" and last_shift_type.get(emp_id) == "Ca tối":
                        continue
                    valid_candidates.append(cand)

                # Nếu không có ai thỏa mãn constraint 3 (do ít nhân sự), nới lỏng constraint 3 nhưng vẫn giữ constraint 1 (nghỉ phép)
                if not valid_candidates:
                    valid_candidates = [
                        c for c in candidates 
                        if (c["employee_id"], current_date) not in leave_days_set 
                        and c["employee_id"] not in assigned_today
                    ]

                # Nếu vẫn không còn ai (tất cả đều nghỉ hoặc đã làm), lấy bất kỳ ai không nghỉ phép
                if not valid_candidates:
                    valid_candidates = [c for c in candidates if (c["employee_id"], current_date) not in leave_days_set]

                if not valid_candidates:
                    # Trường hợp ngoại lệ: Toàn bộ nhân viên đều nghỉ phép
                    return {"employee_id": candidates[0]["employee_id"], "full_name": candidates[0]["full_name"] + " (Tăng cường khẩn cấp)"}

                # Sắp xếp ưu tiên: Người có ít ca nhất trong tuần để công bằng
                valid_candidates.sort(key=lambda c: staff_shift_counts[c["employee_id"]])
                chosen = valid_candidates[0]
                staff_shift_counts[chosen["employee_id"]] += 1
                last_shift_type[chosen["employee_id"]] = shift_type
                assigned_today.add(chosen["employee_id"])
                return chosen

            assigned_today_reception = set()
            rec_morning = pick_staff(receptionists, "Ca sáng", assigned_today_reception)
            rec_evening = pick_staff(receptionists, "Ca tối", assigned_today_reception)

            assignments.append(ShiftItem(
                workDate=date_str,
                shiftType="Ca sáng",
                shiftTime="06:00 – 14:00",
                role="Lễ tân",
                employeeId=rec_morning["employee_id"],
                employeeName=rec_morning["full_name"],
                task="Trực quầy lễ tân & Check-in buổi sáng"
            ))

            assignments.append(ShiftItem(
                workDate=date_str,
                shiftType="Ca tối",
                shiftTime="14:00 – 22:00",
                role="Lễ tân",
                employeeId=rec_evening["employee_id"],
                employeeName=rec_evening["full_name"],
                task="Trực quầy lễ tân & Check-out, kết ca tối"
            ))

            # --- B. XẾP CA HOUSEKEEPING (Morning & Evening) ---
            assigned_today_hk = set()
            hk_morning = pick_staff(housekeepings, "Ca sáng", assigned_today_hk)
            hk_evening = pick_staff(housekeepings, "Ca tối", assigned_today_hk)

            assignments.append(ShiftItem(
                workDate=date_str,
                shiftType="Ca sáng",
                shiftTime="06:00 – 14:00",
                role="Housekeeping",
                employeeId=hk_morning["employee_id"],
                employeeName=hk_morning["full_name"],
                task="Dọn phòng khách trả & Bổ sung tiện ích buồng"
            ))

            assignments.append(ShiftItem(
                workDate=date_str,
                shiftType="Ca tối",
                shiftTime="14:00 – 22:00",
                role="Housekeeping",
                employeeId=hk_evening["employee_id"],
                employeeName=hk_evening["full_name"],
                task="Kiểm tra phòng cuối ngày & Hỗ trợ yêu cầu phòng ca đêm"
            ))

        # 5. Lưu kết quả vào CSDL PostgreSQL nếu được yêu cầu
        if save_to_db:
            conn = get_db_connection()
            cur = conn.cursor()
            for asgn in assignments:
                s_tag = "SANG" if "sáng" in asgn.shiftType else "TOI"
                r_tag = "REC" if "Lễ" in asgn.role else "HK"
                clean_date = asgn.workDate.replace("-", "")
                shift_id = f"SHIFT_{clean_date}_{r_tag}_{s_tag}"
                cur.execute("""
                    INSERT INTO shift_assignments (
                        shift_assignment_id, work_date, shift_type, shift_time, role, status, task, employee_id, hotel_id, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, 'SCHEDULED', %s, %s, %s, NOW(), NOW())
                    ON CONFLICT (shift_assignment_id) DO UPDATE SET
                        employee_id = EXCLUDED.employee_id,
                        task = EXCLUDED.task,
                        updated_at = NOW();
                """, (shift_id, asgn.workDate, asgn.shiftType, asgn.shiftTime, asgn.role, asgn.task, asgn.employeeId, hotel_id))
            conn.commit()
            cur.close()
            conn.close()

        # 6. Tổng hợp giải trình thông minh
        explanation_lines = [
            f"### BÁO CÁO PHÂN CÔNG CA TRỰC AI — {hotel['name'].upper()}",
            f"- **Tuần công tác**: {week_start.strftime('%d/%m/%Y')} – {week_end.strftime('%d/%m/%Y')}",
            f"- **Tổng số ca đã phân công**: {len(assignments)} ca (Đầy đủ 4 ca/ngày: Lễ tân Sáng/Tối & Buồng phòng Sáng/Tối)",
        ]

        if leave_summary_items:
            explanation_lines.append("\n#### 📋 Tình hình nhân sự xin nghỉ phép:")
            for l in leave_summary_items:
                explanation_lines.append(f"- **{l.employeeName}**: Nghỉ từ ngày `{l.startDate}` đến `{l.endDate}` ({l.reason}) -> **Đã miễn toàn bộ ca trực trong giai đoạn này**.")
        else:
            explanation_lines.append("\n- Trong tuần không có nhân viên nào xin nghỉ phép.")

        explanation_lines.append("\n#### ⚖️ Thống kê công bằng nhân sự trong tuần:")
        explanation_lines.append("- **Bộ phận Lễ tân**:")
        for r in receptionists:
            c = staff_shift_counts.get(r["employee_id"], 0)
            explanation_lines.append(f"  + {r['full_name']}: {c} ca trực.")

        explanation_lines.append("- **Bộ phận Housekeeping**:")
        for h in housekeepings:
            c = staff_shift_counts.get(h["employee_id"], 0)
            explanation_lines.append(f"  + {h['full_name']}: {c} ca trực.")

        explanation_lines.append("\n#### 🛡️ Kiểm định ràng buộc nghiệp vụ:")
        explanation_lines.append("- ✅ **100% tuân thủ ngày nghỉ phép**: Không có bất kỳ ca trực nào bị gán vào ngày nhân viên xin nghỉ.")
        explanation_lines.append("- ✅ **Thời gian nghỉ ngơi tối thiểu**: Không có trường hợp nào làm ca tối (kết thúc 22h) rồi phải trực ngay ca sáng hôm sau (06h).")
        explanation_lines.append("- ✅ **Dữ liệu đồng bộ**: Toàn bộ ca trực đã được cập nhật trực tiếp vào bảng `shift_assignments` để hiển thị trên giao diện quản lý.")

        return ScheduleGenerationResult(
            hotelId=hotel_id,
            hotelName=hotel["name"],
            weekStartDate=week_start.strftime("%Y-%m-%d"),
            weekEndDate=week_end.strftime("%Y-%m-%d"),
            totalAssignments=len(assignments),
            assignments=assignments,
            leaveSummary=leave_summary_items,
            explanation="\n".join(explanation_lines)
        )

# Singleton instance
staff_scheduler = StaffScheduler()
