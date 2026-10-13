import openpyxl
import re
import json
import os

def clean_str(val):
    if val is None:
        return ""
    s = str(val).strip()
    return s

def parse_turns(raw_input):
    if not raw_input:
        return []
    # Split by arrows: → or ->
    parts = re.split(r'→|->', raw_input)
    turns = []
    for p in parts:
        p = p.strip()
        # Remove surrounding quotes: ", ', “, ”
        cleaned = re.sub(r'^[“"\'\s]+|[”"\'\s]+$', '', p)
        if cleaned:
            turns.append(cleaned)
    return turns

def main():
    excel_path = r"C:\Users\admin\Downloads\KLTN_HotelManagementAI\docs\testing\Bo_Test_Case_Chatbot_Khach_San.xlsx"
    out_json = r"C:\Users\admin\Downloads\KLTN_HotelManagementAI\tests\scenarios\scenarios_188.json"

    wb = openpyxl.load_workbook(excel_path)
    ws = wb["Test Cases"]
    rows = list(ws.iter_rows(values_only=True))

    scenarios = []
    skipped = []

    for r in rows[1:]:
        if not r or not r[0]:
            continue
        test_id = clean_str(r[0])
        if test_id.startswith("AD-"):
            skipped.append(test_id)
            continue

        group = clean_str(r[1])
        priority = clean_str(r[2])
        test_type = clean_str(r[3])
        name = clean_str(r[4])
        precondition = clean_str(r[5])
        raw_input = clean_str(r[6])
        expected = clean_str(r[7])
        raw_tools = clean_str(r[8])

        turns = parse_turns(raw_input)
        tools = [t.strip() for t in raw_tools.split(",") if t.strip()] if raw_tools else []

        scenarios.append({
            "id": test_id,
            "group": group,
            "priority": priority,
            "type": test_type,
            "name": name,
            "precondition": precondition,
            "raw_input": raw_input,
            "turns": turns,
            "expected_behavior": expected,
            "tools": tools,
            "is_p0_security_or_money": priority == "P0" and (test_type in ["Security"] or "tiền" in expected.lower() or "thanh toán" in expected.lower() or "giá" in expected.lower())
        })

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(scenarios, f, ensure_ascii=False, indent=2)

    print(f"Parsed {len(scenarios)} test scenarios (skipped {len(skipped)} AD tests).")
    print(f"Saved to {out_json}")

if __name__ == "__main__":
    main()
