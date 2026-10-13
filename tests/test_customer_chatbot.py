import os
import sys
import json
import uuid
import asyncio
import argparse
import pytest
from httpx import AsyncClient, ASGITransport

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Freeze time
os.environ["AI_FROZEN_DATE"] = "2026-10-13"

from main import app
from tests.harness.evaluator import evaluator

def load_scenarios():
    scenarios_path = os.path.join(project_root, "tests", "scenarios", "scenarios_188.json")
    with open(scenarios_path, "r", encoding="utf-8") as f:
        return json.load(f)

ALL_SCENARIOS = load_scenarios()

async def run_single_test_scenario(scenario: dict, client: AsyncClient) -> dict:
    """
    Chạy 1 kịch bản hội thoại đầy đủ qua các turns.
    """
    tid = scenario["id"]
    session_id = f"test_{tid.lower()}_{uuid.uuid4().hex[:8]}"
    history = []
    last_reply = ""
    last_state = {}

    turns = scenario.get("turns", [])
    if not turns:
        turns = [scenario.get("raw_input", "Xin chào")]

    for turn_text in turns:
        payload = {
            "message": turn_text,
            "sessionId": session_id,
            "history": history
        }

        resp = await client.post("/api/chat", json=payload, timeout=30.0)
        if resp.status_code != 200:
            return {
                "id": tid,
                "status": "Fail",
                "error": f"HTTP {resp.status_code}: {resp.text}",
                "reply": "",
                "state": {}
            }

        data = resp.json()
        result = data.get("result", {})
        last_reply = result.get("reply", "")
        last_state = result.get("state", {})

        history.append({"role": "user", "content": turn_text})
        history.append({"role": "model", "content": last_reply})

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
            "score": 0.0,
            "state": last_state
        }

    # If P0 money / security: deterministic pass is enough
    if scenario.get("is_p0_security_or_money"):
        return {
            "id": tid,
            "status": "Pass",
            "reply": last_reply,
            "reason": det_reason,
            "score": 1.0,
            "state": last_state
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
        "score": score,
        "state": last_state
    }

# Pytest test cases
@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ALL_SCENARIOS, ids=[s["id"] for s in ALL_SCENARIOS])
async def test_chatbot_scenario(scenario, async_client):
    res = await run_single_test_scenario(scenario, async_client)
    assert res["status"] == "Pass", f"Test {scenario['id']} FAILED: {res.get('reason', res.get('error'))}"

# CLI runner support
async def main_cli():
    parser = argparse.ArgumentParser(description="Customer Chatbot Test Suite Runner")
    parser.add_argument("--id", type=str, help="Chạy 1 test case cụ thể theo ID (VD: HP-01)")
    parser.add_argument("--group", type=str, help="Chạy theo nhóm (VD: HP, SF, PR, SC...)")
    parser.add_argument("--priority", type=str, choices=["P0", "P1", "P2"], help="Chạy theo độ ưu tiên")
    parser.add_argument("--limit", type=int, default=0, help="Giới hạn số lượng test chạy")
    parser.add_argument("--output", type=str, default="", help="File lưu kết quả JSON")
    args = parser.parse_args()

    filtered = ALL_SCENARIOS
    if args.id:
        filtered = [s for s in filtered if s["id"].lower() == args.id.lower()]
    elif args.group:
        filtered = [s for s in filtered if s["id"].startswith(args.group.upper() + "-")]
    elif args.priority:
        filtered = [s for s in filtered if s["priority"] == args.priority.upper()]

    if args.limit > 0:
        filtered = filtered[:args.limit]

    print(f"[*] Bắt đầu chạy {len(filtered)} test cases...")

    transport = ASGITransport(app=app)
    results = []
    pass_count = 0
    fail_count = 0

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for idx, sc in enumerate(filtered, 1):
            print(f"[{idx}/{len(filtered)}] Running {sc['id']} ({sc['priority']}) - {sc['name']}...", end=" ", flush=True)
            res = await run_single_test_scenario(sc, client)
            results.append(res)
            if res["status"] == "Pass":
                pass_count += 1
                print("PASS")
            else:
                fail_count += 1
                print(f"FAIL ({res.get('reason', res.get('error', 'Unknown'))})")

    print("\n" + "="*50)
    print(f"TỔNG KẾT: {len(filtered)} tests | PASS: {pass_count} | FAIL: {fail_count} | Tỉ lệ: {pass_count/len(filtered)*100:.1f}%")
    print("="*50)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"[+] Đã lưu kết quả ra: {args.output}")

if __name__ == "__main__":
    asyncio.run(main_cli())
