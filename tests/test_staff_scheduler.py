import sys
import os
import datetime
import json

sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

from core.staff_scheduler import staff_scheduler

def run_tests():
    print("=" * 70)
    print("KIỂM THỬ MODULE STAFF AI: TỰ ĐỘNG XẾP CA TRỰC THEO ĐƠN NGHỈ PHÉP")
    print("=" * 70)

    hotel_id = 1
    target_monday = "2026-10-19" # Tuần từ 19/10 đến 25/10/2026

    # Test 1: Lập lịch với yêu cầu nghỉ phép cụ thể
    prompt = (
        "Bạn Lê Thị Thu Thảo xin nghỉ phép vào Thứ 4 (21/10/2026) và Thứ 5 (22/10/2026) do có việc riêng. "
        "Hãy tự động xếp ca làm việc cho bộ phận Lễ tân và Buồng phòng chi nhánh Sài Gòn tuần 19/10 - 25/10/2026, "
        "đảm bảo không phân ca cho Thảo vào 2 ngày này và phân bổ công bằng cho các bạn khác."
    )

    print(f"\n[*] 1. Gửi yêu cầu tới Staff AI Scheduler:\n   \"{prompt}\"\n")
    result = staff_scheduler.generate_schedule(
        hotel_id=hotel_id,
        week_start_str=target_monday,
        user_prompt=prompt,
        save_to_db=True
    )

    print(f"[+] Khách sạn: {result.hotelName} (ID: {result.hotelId})")
    print(f"[+] Tuần: {result.weekStartDate} đến {result.weekEndDate}")
    print(f"[+] Tổng số ca: {result.totalAssignments}")
    
    print("\n[*] 2. Đơn nghỉ phép đã trích xuất & áp dụng:")
    for l in result.leaveSummary:
        print(f"   - Nhân viên: {l.employeeName} | Nghỉ từ: {l.startDate} đến {l.endDate} | Lý do: {l.reason}")

    # Kiểm tra ràng buộc nghỉ phép
    thao_wed_thu_shifts = [
        a for a in result.assignments 
        if "Thảo" in a.employeeName and a.workDate in ["2026-10-21", "2026-10-22"]
    ]
    if len(thao_wed_thu_shifts) == 0:
        print("   -> [PASS] Lê Thị Thu Thảo KHÔNG bị xếp bất kỳ ca nào vào Thứ 4 và Thứ 5!")
    else:
        print(f"   -> [FAIL] Thảo bị xếp ca vào ngày nghỉ: {thao_wed_thu_shifts}")

    # Kiểm tra ca trực của các bạn thay thế vào Thứ 4 và Thứ 5
    wed_thu_rec_shifts = [
        a for a in result.assignments 
        if a.role == "Lễ tân" and a.workDate in ["2026-10-21", "2026-10-22"]
    ]
    print("\n[*] 3. Các ca Lễ tân thay thế trong ngày Thứ 4 & Thứ 5:")
    for s in wed_thu_rec_shifts:
        print(f"   - Ngày {s.workDate} | {s.shiftType} ({s.shiftTime}): {s.employeeName} ({s.task})")

    # Kiểm tra ràng buộc Ca tối -> Ca sáng hôm sau
    rest_violations = []
    assignments_by_emp = {}
    for a in result.assignments:
        assignments_by_emp.setdefault(a.employeeId, []).append(a)

    for emp_id, emp_shifts in assignments_by_emp.items():
        emp_shifts.sort(key=lambda x: x.workDate)
        for i in range(len(emp_shifts) - 1):
            s1 = emp_shifts[i]
            s2 = emp_shifts[i+1]
            d1 = datetime.datetime.strptime(s1.workDate, "%Y-%m-%d").date()
            d2 = datetime.datetime.strptime(s2.workDate, "%Y-%m-%d").date()
            if (d2 - d1).days == 1 and s1.shiftType == "Ca tối" and s2.shiftType == "Ca sáng":
                rest_violations.append((s1.employeeName, s1.workDate, s2.workDate))

    if not rest_violations:
        print("\n   -> [PASS] 100% tuân thủ quy tắc nghỉ ngơi: Không có nhân viên nào làm Ca tối rồi trực ngay Ca sáng hôm sau!")
    else:
        print(f"\n   -> [WARN] Có vi phạm ca tối -> ca sáng: {rest_violations}")

    # Thống kê số ca từng người
    print("\n[*] 4. Thống kê công bằng số ca phân công:")
    for emp_id, emp_shifts in assignments_by_emp.items():
        name = emp_shifts[0].employeeName
        role = emp_shifts[0].role
        print(f"   - {name} ({role}): {len(emp_shifts)} ca")

    print("\n[*] 5. Toàn văn giải trình từ Staff AI:")
    print(result.explanation)

    print("\n" + "=" * 70)
def test_staff_scheduler():
    run_tests()

if __name__ == "__main__":
    run_tests()
