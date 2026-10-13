from typing import Optional, Dict, Any
import time

class FaultInjector:
    """
    Quản lý tiêm lỗi có kiểm soát cho hệ thống test (Fault Injection):
    - Tool timeout / 500
    - ChromaDB down
    - Gemini 429 / 5xx / Malformed Output
    """
    def __init__(self):
        self.active_faults: Dict[str, Any] = {}

    def set_fault(self, target: str, fault_type: str, details: Optional[Dict[str, Any]] = None):
        """
        Kích hoạt một lỗi tiêm.
        - target: 'check_availability', 'create_booking', 'chromadb', 'gemini'
        - fault_type: 'timeout', '500', 'rate_limit_429', 'bad_json'
        """
        self.active_faults[target] = {
            "type": fault_type,
            "details": details or {}
        }

    def clear_fault(self, target: Optional[str] = None):
        """Xóa lỗi đã tiêm"""
        if target:
            self.active_faults.pop(target, None)
        else:
            self.active_faults.clear()

    def check_and_apply(self, target: str):
        """Kiểm tra và kích hoạt lỗi nếu target đang bị tiêm lỗi"""
        if target in self.active_faults:
            fault = self.active_faults[target]
            ftype = fault["type"]

            if ftype == "timeout":
                time.sleep(fault["details"].get("seconds", 11))
                raise TimeoutError(f"Simulated timeout error for {target}")
            elif ftype == "500":
                raise Exception(f"Simulated 500 Internal Server Error for {target}")
            elif ftype == "rate_limit_429":
                raise Exception("429 Resource Exhausted: Quota exceeded for model (Simulated)")
            elif ftype == "chroma_down":
                raise ConnectionError("Simulated ChromaDB Connection Error: Service Unavailable")

fault_injector = FaultInjector()
