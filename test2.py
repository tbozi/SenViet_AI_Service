
import urllib.request
import urllib.error
import json

payload = {
    'customerName': 'Hi?u',
    'customerPhone': '0901234567',
    'hotelId': 1,
    'roomIds': ['ROOM20260922101'],
    'checkInTime': '2026-10-15T14:00:00',
    'checkOutTime': '2026-10-16T12:00:00',
    'numAdults': 2,
    'numChildren': 0,
    'serviceIds': [],
    'promoCode': 'DEMO2K',
    'paymentMethod': 'BANK_TRANSFER'
}

req = urllib.request.Request(
    'http://localhost:8081/api/internal/chatbot/book',
    data=json.dumps(payload).encode('utf-8'),
    headers={'Content-Type': 'application/json'}
)

try:
    with urllib.request.urlopen(req) as f:
        print(f.read().decode('utf-8'))
except urllib.error.HTTPError as e:
    print('HTTP Error:', e.code)
    print('Body:', e.read().decode('utf-8'))

