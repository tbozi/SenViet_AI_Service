import os
import sys
import json
import uuid
import time
import asyncio
import openpyxl
from httpx import AsyncClient, ASGITransport

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Freeze time to 13/10/2026
os.environ["AI_FROZEN_DATE"] = "2026-10-13"

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from main import app
from tests.fixtures.db_seed import seed_test_database
from tests.fixtures.sample_policies import seed_test_policies
from tests.harness.evaluator import evaluator

SCENARIOS_FILE = os.path.join(project_root, "tests", "scenarios", "scenarios_188.json")
CHECKPOINT_FILE = os.path.join(project_root, "docs", "testing", "baseline_checkpoint.json")
EXCEL_SRC = os.path.join(project_root, "docs", "testing", "Bo_Test_Case_Chatbot_Khach_San.xlsx")
EXCEL_BASELINE = os.path.join(project_root, "docs", "testing", "Bo_Test_Case_BASELINE.xlsx")
REPORT_MD = os.path.join(project_root, "docs", "testing", "REPORT_BASELINE.md")

BLOCKED_TEST_IDS = {
    "HP-05": "Yêu cầu giao diện frontend: Hoàn thành bằng nút bấm UI quick-reply",
    "CH-11": "Yêu cầu giao diện frontend: Thao tác click trên tin nhắn cũ trong DOM UI",
    "PM-09": "Yêu cầu trình duyệt frontend: Kiểm thử khôi phục state khi F5 reload trang",
    "PM-16": "Chưa hỗ trợ hạ tầng: Gửi QR qua email (chưa có Mail Server)",
    "ER-12": "Yêu cầu giao diện frontend: Hiệu ứng typing/loading indicator khi mạng chậm",
    "ER-13": "Yêu cầu trình duyệt frontend: Đồng bộ session đa tab trên client",
    "CC-04": "Yêu cầu giao diện frontend: Polling trạng thái thanh toán từ client"
}

def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_checkpoint(data):
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

async def run_single_test(scenario, client):
    tid = scenario["id"]
    if tid in BLOCKED_TEST_IDS:
        return {
            "id": tid,
            "status": "Blocked",
            "reply": "Blocked by design (frontend/external infrastructure requirement)",
            "reason": BLOCKED_TEST_IDS[tid],
            "score": 0.0
        }

    session_id = f"test_{tid.lower()}_{uuid.uuid4().hex[:8]}"
    history = []
    last_reply = ""
    last_state = {}

    turns = scenario.get("turns", [])
    if not turns:
        turns = [scenario.get("raw_input", "Xin chào")]

    for turn_idx, turn_text in enumerate(turns):
        payload = {
            "message": turn_text,
            "sessionId": session_id,
            "history": history
        }

        # Retry with exponential backoff on 429 / network glitch
        resp = None
        for attempt in range(4):
            try:
                resp = await client.post("/api/chat", json=payload, timeout=45.0)
                if resp.status_code == 200:
                    break
                elif resp.status_code == 429:
                    time.sleep(5 * (attempt + 1))
            except Exception as e:
                time.sleep(3 * (attempt + 1))

        if resp is None or resp.status_code != 200:
            err_msg = f"HTTP Error {resp.status_code if resp else 'Timeout'}"
            return {
                "id": tid,
                "status": "Fail",
                "reply": "",
                "reason": f"Lỗi gọi API chat: {err_msg}",
                "score": 0.0
            }

        data = resp.json()
        result = data.get("result", {})
        last_reply = result.get("reply", "")
        last_state = result.get("state", {})

        history.append({"role": "user", "content": turn_text})
        history.append({"role": "model", "content": last_reply})

        # Polite delay to respect Gemini Free Tier 15 RPM quota (1 req / 4s)
        await asyncio.sleep(4.2)

    # Evaluate assertions
    det_passed, det_reason = evaluator.evaluate_deterministic(
        test_case=scenario,
        actual_reply=last_reply,
        state=last_state,
        tool_calls=[]
    )

    if not det_passed:
        return {
            "id": tid,
            "status": "Fail",
            "reply": last_reply,
            "reason": det_reason,
            "score": 0.0
        }

    if scenario.get("is_p0_security_or_money"):
        return {
            "id": tid,
            "status": "Pass",
            "reply": last_reply,
            "reason": det_reason,
            "score": 1.0
        }

    # Semantic evaluation
    sem_passed, score, sem_reason = evaluator.evaluate_with_llm_judge(
        test_case=scenario,
        actual_reply=last_reply,
        user_input=turns[-1]
    )

    return {
        "id": tid,
        "status": "Pass" if sem_passed else "Fail",
        "reply": last_reply,
        "reason": sem_reason if not sem_passed else det_reason,
        "score": score
    }

def export_excel_and_report(scenarios, results_map):
    # 1. Update Excel
    wb = openpyxl.load_workbook(EXCEL_SRC)
    ws = wb["Test Cases"]

    for row_idx in range(2, ws.max_row + 1):
        cell_id = ws.cell(row=row_idx, column=1).value
        if not cell_id:
            continue
        tid = str(cell_id).strip()
        if tid in results_map:
            res = results_map[tid]
            # Column J (10): Kết quả thực tế
            ws.cell(row=row_idx, column=10).value = res.get("reply", "")[:1000]
            # Column K (11): Trạng thái
            ws.cell(row=row_idx, column=11).value = res.get("status", "Fail")
            # Column L (12): Ghi chú
            ws.cell(row=row_idx, column=12).value = res.get("reason", "")

    wb.save(EXCEL_BASELINE)
    print(f"[+] Đã lưu file Excel Baseline: {EXCEL_BASELINE}")

    # 2. Generate Markdown Report
    total_tests = len(scenarios)
    passed_tests = [s for s in scenarios if results_map.get(s["id"], {}).get("status") == "Pass"]
    failed_tests = [s for s in scenarios if results_map.get(s["id"], {}).get("status") == "Fail"]
    blocked_tests = [s for s in scenarios if results_map.get(s["id"], {}).get("status") == "Blocked"]

    p0_fails = [s for s in failed_tests if s["priority"] == "P0"]

    # Stats by priority
    by_priority = {}
    for p in ["P0", "P1", "P2"]:
        sub = [s for s in scenarios if s["priority"] == p]
        p_pass = [s for s in sub if results_map.get(s["id"], {}).get("status") == "Pass"]
        p_fail = [s for s in sub if results_map.get(s["id"], {}).get("status") == "Fail"]
        p_block = [s for s in sub if results_map.get(s["id"], {}).get("status") == "Blocked"]
        by_priority[p] = {
            "total": len(sub),
            "pass": len(p_pass),
            "fail": len(p_fail),
            "blocked": len(p_block),
            "rate": (len(p_pass) / len(sub) * 100) if sub else 0.0
        }

    # Stats by group
    groups = list(dict.fromkeys([s["group"] for s in scenarios]))
    by_group = {}
    for g in groups:
        sub = [s for s in scenarios if s["group"] == g]
        g_pass = [s for s in sub if results_map.get(s["id"], {}).get("status") == "Pass"]
        g_fail = [s for s in sub if results_map.get(s["id"], {}).get("status") == "Fail"]
        g_block = [s for s in sub if results_map.get(s["id"], {}).get("status") == "Blocked"]
        by_group[g] = {
            "total": len(sub),
            "pass": len(g_pass),
            "fail": len(g_fail),
            "blocked": len(g_block),
            "rate": (len(g_pass) / len(sub) * 100) if sub else 0.0
        }

    report_content = f"""# BÁO CÁO KẾT QUẢ ĐO LƯỜNG GỐC (BASELINE REPORT)
### DỰ ÁN: CHATBOT TƯ VẤN & ĐẶT PHÒNG KHÁCH HÀNG (LUỒNG B) - KHÁCH SẠN SEN VIỆT

- **Thời điểm kiểm thử:** 13/10/2026
- **Môi trường:** Python FastAPI + ChromaDB + Google Gemini (`{app.title}`)
- **Phạm vi kiểm thử:** 188 Test Cases (Đã loại trừ 11 test Admin nhóm AD)
- **File Excel kết quả chi tiết:** `docs/testing/Bo_Test_Case_BASELINE.xlsx`

---

## 1. TỔNG QUAN KẾT QUẢ

| Chỉ số | Số lượng | Tỉ lệ (%) |
|---|---|---|
| **Tổng số Test Cases** | **{total_tests}** | 100.0% |
| **ĐẠT (Pass)** | **{len(passed_tests)}** | **{len(passed_tests)/total_tests*100:.1f}%** |
| **KHÔNG ĐẠT (Fail)** | **{len(failed_tests)}** | **{len(failed_tests)/total_tests*100:.1f}%** |
| **BỊ CHẶN (Blocked)** | **{len(blocked_tests)}** | **{len(blocked_tests)/total_tests*100:.1f}%** |

---

## 2. KẾT QUẢ THEO MỨC ĐỘ ƯU TIÊN (PRIORITY)

| Mức ưu tiên | Tổng test | Pass | Fail | Blocked | Tỉ lệ Pass (%) |
|---|---|---|---|---|---|
| **P0 (Tối quan trọng: Tiền, Bảo mật, Luồng chính)** | {by_priority['P0']['total']} | {by_priority['P0']['pass']} | {by_priority['P0']['fail']} | {by_priority['P0']['blocked']} | **{by_priority['P0']['rate']:.1f}%** |
| **P1 (Quan trọng: Validate nâng cao, Edge cases)** | {by_priority['P1']['total']} | {by_priority['P1']['pass']} | {by_priority['P1']['fail']} | {by_priority['P1']['blocked']} | **{by_priority['P1']['rate']:.1f}%** |
| **P2 (Trung bình: Giao tiếp, Edge cases phụ)** | {by_priority['P2']['total']} | {by_priority['P2']['pass']} | {by_priority['P2']['fail']} | {by_priority['P2']['blocked']} | **{by_priority['P2']['rate']:.1f}%** |

---

## 3. KẾT QUẢ THEO NHÓM NGHIỆP VỤ (GROUPS)

| Nhóm nghiệp vụ | Tổng số | Pass | Fail | Blocked | Tỉ lệ Pass (%) |
|---|---|---|---|---|---|
"""
    for g, d in by_group.items():
        report_content += f"| {g} | {d['total']} | {d['pass']} | {d['fail']} | {d['blocked']} | {d['rate']:.1f}% |\n"

    report_content += f"""
---

## 4. DANH SÁCH TEST CASE P0 BỊ FAIL (CẦN ƯU TIÊN SỬA Ở GIAI ĐOẠN 4)

Tổng cộng có **{len(p0_fails)}** test P0 bị Fail trên mã nguồn hiện tại:

| Test ID | Tên test case | Lý do không đạt (Root Cause sơ bộ) |
|---|---|---|
"""
    for pf in p0_fails:
        res = results_map.get(pf["id"], {})
        reason = res.get("reason", "Chưa đáp ứng mong đợi nghiệp vụ")
        report_content += f"| **{pf['id']}** | {pf['name']} | {reason} |\n"

    report_content += f"""
---

## 5. DANH SÁCH TEST CASE BỊ CHẶN (BLOCKED)

Có **{len(blocked_tests)}** test case thuộc diện Blocked do đặc thù yêu cầu tương tác giao diện người dùng (Frontend UI) hoặc chưa có hạ tầng phụ:

| Test ID | Tên test case | Lý do Blocked |
|---|---|---|
"""
    for b in blocked_tests:
        res = results_map.get(b["id"], {})
        report_content += f"| **{b['id']}** | {b['name']} | {res.get('reason')} |\n"

    with open(REPORT_MD, "w", encoding="utf-8") as f:
        f.write(report_content)
    print(f"[+] Đã xuất báo cáo Markdown Baseline: {REPORT_MD}")

async def main():
    print("[*] Nạp danh sách 188 test scenarios...")
    with open(SCENARIOS_FILE, "r", encoding="utf-8") as f:
        scenarios = json.load(f)

    # Nạp seed fixtures
    seed_test_database()
    seed_test_policies()

    checkpoint = load_checkpoint()
    print(f"[*] Checkpoint hiện có: {len(checkpoint)}/{len(scenarios)} tests đã hoàn tất.")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for idx, sc in enumerate(scenarios, 1):
            tid = sc["id"]
            if tid in checkpoint:
                continue

            print(f"[{idx}/{len(scenarios)}] Baseline testing {tid} ({sc['priority']}) - {sc['name']}...", end=" ", flush=True)
            res = await run_single_test(sc, client)
            checkpoint[tid] = res
            save_checkpoint(checkpoint)

            status = res["status"]
            print(f"{status.upper()}")

    print("\n[*] Hoàn tất chạy baseline! Xuất Excel và Markdown...")
    export_excel_and_report(scenarios, checkpoint)

if __name__ == "__main__":
    asyncio.run(main())
