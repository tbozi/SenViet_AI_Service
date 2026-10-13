import os
import sys
import json
import time
import hmac
import hashlib
import requests
from typing import Dict, Any, Optional

class MockPayOSService:
    """
    Mock PayOS phục vụ kiểm thử tự động:
    - Giả lập tạo QR link (không phụ thuộc PayOS thật)
    - Giả lập bắn Webhook sang Backend Spring Boot (thành công, thiếu, thừa, trùng, trễ)
    - Kiểm tra trạng thái giao dịch
    """
    def __init__(self, backend_webhook_url: str = "http://localhost:8081/payment/webhook/payos"):
        self.backend_webhook_url = backend_webhook_url
        self.mock_orders: Dict[int, Dict[str, Any]] = {}
        self.force_error: bool = False

    def create_payment_link(self, order_code: int, amount: int, description: str) -> Dict[str, Any]:
        """Giả lập tạo link thanh toán PayOS"""
        if self.force_error:
            raise Exception("Mock PayOS 500 Internal Server Error (Simulated)")

        qr_url = f"https://api.vietqr.io/image/970418-TESTPAYOS-compact2.png?amount={amount}&addInfo=TEST_{order_code}"
        checkout_url = f"http://localhost:8080/mock-payos-checkout?orderCode={order_code}&amount={amount}"

        order_data = {
            "orderCode": order_code,
            "amount": amount,
            "description": description,
            "status": "PENDING",
            "created_at": time.time(),
            "qrCode": qr_url,
            "checkoutUrl": checkout_url
        }
        self.mock_orders[order_code] = order_data

        return {
            "code": "00",
            "desc": "success",
            "data": {
                "bin": "970418",
                "accountNumber": "TESTPAYOS",
                "accountName": "SEN VIET HOTEL TEST",
                "amount": amount,
                "description": description,
                "orderCode": order_code,
                "currency": "VND",
                "paymentLinkId": f"plink_{order_code}",
                "status": "PENDING",
                "checkoutUrl": checkout_url,
                "qrCode": qr_url
            }
        }

    def trigger_webhook(
        self,
        order_code: int,
        paid_amount: Optional[int] = None,
        code: str = "00",
        desc: str = "success"
    ) -> Dict[str, Any]:
        """
        Bắn webhook giả lập tới Backend Spring Boot.
        - paid_amount: Số tiền khách thực chuyển (để test thiếu/thừa tiền).
        """
        order = self.mock_orders.get(order_code, {"amount": 1000000, "description": f"Test {order_code}"})
        actual_amount = paid_amount if paid_amount is not None else order.get("amount", 1000000)

        payload = {
            "code": code,
            "desc": desc,
            "success": code == "00",
            "data": {
                "orderCode": order_code,
                "amount": actual_amount,
                "description": order.get("description", f"HD_{order_code}"),
                "accountNumber": "TESTPAYOS",
                "reference": f"REF_{int(time.time())}",
                "transactionDateTime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "currency": "VND",
                "paymentLinkId": f"plink_{order_code}",
                "code": code,
                "desc": desc
            },
            "signature": "mock_signature_test"
        }

        try:
            resp = requests.post(
                self.backend_webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=5
            )
            return {
                "status_code": resp.status_code,
                "response": resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text,
                "payload_sent": payload
            }
        except Exception as e:
            return {
                "status_code": 500,
                "error": str(e),
                "payload_sent": payload
            }

mock_payos = MockPayOSService()
