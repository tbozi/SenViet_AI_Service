import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from core.staff_scheduler import (
    staff_scheduler, 
    ScheduleGenerationResult, 
    ShiftItem, 
    LeaveRequestItem
)

router = APIRouter(prefix="/api/staff-ai", tags=["Staff AI - Shift Scheduling"])

class ScheduleRequest(BaseModel):
    hotelId: int = Field(1, description="ID khách sạn / chi nhánh cần xếp ca")
    weekStartDate: Optional[str] = Field(None, description="Ngày Thứ 2 đầu tuần (YYYY-MM-DD). Bỏ trống để xếp cho tuần kế tiếp")
    userPrompt: Optional[str] = Field(
        None, 
        description="Yêu cầu bằng ngôn ngữ tự nhiên từ Quản lý (VD: 'Thảo xin nghỉ thứ 4 và thứ 5, ưu tiên Bảo ca tối')"
    )
    saveToDb: bool = Field(True, description="Lưu trực tiếp kết quả vào bảng shift_assignments trong PostgreSQL")

class LeaveCreateRequest(BaseModel):
    employeeId: str = Field(..., description="Mã nhân viên (EMP_...)")
    hotelId: int = Field(1, description="ID khách sạn / chi nhánh")
    startDate: str = Field(..., description="Ngày bắt đầu nghỉ YYYY-MM-DD")
    endDate: str = Field(..., description="Ngày kết thúc nghỉ YYYY-MM-DD")
    reason: str = Field("Nghỉ phép cá nhân", description="Lý do xin nghỉ phép")

class ApiResponse(BaseModel):
    code: int = 1000
    message: str = "Success"
    result: Any

@router.post("/schedule", response_model=ApiResponse, summary="AI Tự động Xếp Lịch Trực Tuần theo Đơn Nghỉ Phép")
async def generate_weekly_shift_schedule(request: ScheduleRequest):
    """
    Tự động phân công ca trực tuần thông minh bằng AI:
    - Tiếp nhận yêu cầu bằng văn bản tự nhiên (Natural Language Processing qua Gemini).
    - Phân tích và trích xuất đơn xin nghỉ phép, yêu cầu ca trực ưu tiên.
    - Áp dụng thuật toán CSP giải bài toán xếp ca tối ưu.
    - Đảm bảo 100% không trùng ngày nghỉ phép, tránh ca tối -> ca sáng hôm sau, phân bổ công bằng.
    - Đồng bộ tự động vào cơ sở dữ liệu `shift_assignments` cho giao diện Web Quản lý.
    """
    try:
        result = staff_scheduler.generate_schedule(
            hotel_id=request.hotelId,
            week_start_str=request.weekStartDate,
            user_prompt=request.userPrompt,
            save_to_db=request.saveToDb
        )
        return ApiResponse(
            code=1000,
            message="Phân công lịch trực tuần bằng AI thành công",
            result=result
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi xếp ca bằng AI: {str(e)}")

@router.get("/leaves", response_model=ApiResponse, summary="Tra cứu danh sách đơn xin nghỉ phép trong tuần")
async def get_leave_requests(
    hotelId: int = Query(1, description="ID khách sạn"),
    startDate: str = Query(..., description="Từ ngày YYYY-MM-DD"),
    endDate: str = Query(..., description="Đến ngày YYYY-MM-DD")
):
    try:
        s_d = datetime.datetime.strptime(startDate, "%Y-%m-%d").date()
        e_d = datetime.datetime.strptime(endDate, "%Y-%m-%d").date()
        leaves = staff_scheduler.get_approved_leaves(hotelId, s_d, e_d)
        return ApiResponse(
            code=1000,
            message="Lấy danh sách đơn nghỉ phép thành công",
            result=leaves
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Lỗi truy vấn đơn nghỉ phép: {str(e)}")

@router.post("/leaves", response_model=ApiResponse, summary="Đăng ký đơn xin nghỉ phép mới cho nhân viên")
async def create_leave_request(request: LeaveCreateRequest):
    try:
        s_d = datetime.datetime.strptime(request.startDate, "%Y-%m-%d").date()
        e_d = datetime.datetime.strptime(request.endDate, "%Y-%m-%d").date()
        staff_scheduler.record_leave_request(
            employee_id=request.employeeId,
            hotel_id=request.hotelId,
            start_date=s_d,
            end_date=e_d,
            reason=request.reason
        )
        return ApiResponse(
            code=1000,
            message="Đăng ký đơn nghỉ phép thành công và đã được tự động phê duyệt",
            result={"status": "APPROVED", "employeeId": request.employeeId, "startDate": request.startDate, "endDate": request.endDate}
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Lỗi tạo đơn nghỉ phép: {str(e)}")
