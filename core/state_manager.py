import json
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

class BookingState(BaseModel):
    sessionId: str
    currentStep: str = "SELECT_BRANCH"
    branch: Optional[Dict[str, Any]] = None
    checkIn: Optional[str] = None
    checkOut: Optional[str] = None
    guests: Dict[str, int] = Field(default_factory=lambda: {"adults": 0, "children": 0})
    roomType: Optional[Dict[str, Any]] = None
    roomQty: int = 1
    services: list = Field(default_factory=list)
    guestInfo: Dict[str, str] = Field(default_factory=lambda: {"name": "", "phone": "", "email": ""})
    promoCode: Optional[str] = None
    paymentMethod: Optional[str] = None
    holdId: Optional[str] = None
    bookingId: Optional[str] = None
    orderId: Optional[str] = None
    status: str = "DRAFT"
    
    # UI Data fields for frontend to render
    availableRooms: list = Field(default_factory=list)
    availableServices: list = Field(default_factory=list)
    availablePromotions: list = Field(default_factory=list)
    qrUrl: Optional[str] = None
    checkoutUrl: Optional[str] = None
    orderCode: Optional[int] = None
    amountToPay: Optional[float] = None

class StateManager:
    def __init__(self):
        self.sessions: Dict[str, BookingState] = {}

    def get_state(self, session_id: str = None) -> BookingState:
        sid = session_id or "default_session"
        if sid not in self.sessions:
            self.sessions[sid] = BookingState(sessionId=sid)
        return self.sessions[sid]

    def update_state(self, session_id: str, updates: Dict[str, Any]) -> BookingState:
        sid = session_id or "default_session"
        state = self.get_state(sid)
        for key, value in updates.items():
            if hasattr(state, key):
                setattr(state, key, value)
        return state

    def reset_state(self, session_id: str) -> BookingState:
        self.sessions[session_id] = BookingState(sessionId=session_id)
        return self.sessions[session_id]

state_manager = StateManager()
