
# -*- coding: utf-8 -*-
import sys
sys.path.append('C:/Users/admin/Downloads/KLTN_HotelManagementAI')
from core.vector_store import VectorStoreManager
vm = VectorStoreManager()
policy_text = '''Chính sách ăn uống (F&B) và Bữa sáng:
- Tất cả các hạng phòng tại Chuỗi Khách sạn Sen Việt có giá niêm yết là giá phòng đơn thuần (Room Only).
- Giá phòng KHÔNG bao gồm bất kỳ dịch vụ ăn uống nào (kể cả bữa sáng/buffet sáng).
- Nếu quý khách có nhu cầu dùng bữa, có thể liên hệ lễ tân để được hỗ trợ mua thêm voucher ăn sáng hoặc đặt bàn tại nhà hàng của khách sạn.'''
doc = {
    'id': 'policy_food',
    'text': policy_text,
    'metadata': {'category': 'Quy định - Chính sách', 'type': 'FoodAndBeverage'}
}
vm.index_documents([doc])
print('Added food policy.')

