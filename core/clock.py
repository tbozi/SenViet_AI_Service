import os
from datetime import datetime

def get_current_date() -> str:
    """
    Trả về ngày hiện tại dưới dạng 'YYYY-MM-DD'.
    Nếu có biến môi trường AI_FROZEN_DATE, sẽ đóng băng ngày theo giá trị đó.
    """
    frozen = os.getenv("AI_FROZEN_DATE")
    if frozen:
        return frozen.strip()
    return datetime.now().strftime("%Y-%m-%d")

def get_current_datetime() -> datetime:
    """
    Trả về datetime hiện tại.
    Hỗ trợ đóng băng thời gian qua AI_FROZEN_DATE hoặc AI_FROZEN_DATETIME.
    """
    frozen_dt = os.getenv("AI_FROZEN_DATETIME")
    if frozen_dt:
        return datetime.fromisoformat(frozen_dt.strip())
    frozen_d = os.getenv("AI_FROZEN_DATE")
    if frozen_d:
        return datetime.fromisoformat(f"{frozen_d.strip()}T14:00:00")
    return datetime.now()
