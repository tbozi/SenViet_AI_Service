import sys
import json

sys.stdout.reconfigure(encoding='utf-8')

transcript_path = r'C:\Users\admin\.gemini\antigravity\brain\a84b762b-d117-4170-9e74-58f310d0c69c\.system_generated\logs\transcript.jsonl'
lines_to_check = [19022, 19023, 19024, 19025, 19026]

with open(transcript_path, 'r', encoding='utf-8') as f:
    for idx, line in enumerate(f):
        if idx in lines_to_check:
            d = json.loads(line)
            print(f"=== LINE {idx} ({d.get('type')}) ===")
            print(d.get('content'))
            print("\n" + "="*50 + "\n")
