# HỆ THỐNG AI MICROSERVICE TƯ VẤN ĐẶT PHÒNG - SEN VIỆT LUXURY
> **Đồ án Tốt nghiệp**: Hệ thống Quản trị & Đặt phòng Chuỗi Khách sạn Sen Việt Luxury  
> **Kiến trúc**: Microservices + Retrieval-Augmented Generation (RAG) + Hybrid Database (PostgreSQL Vector)  
> **Ngôn ngữ & Công nghệ**: Python 3.12, FastAPI, PostgreSQL, ChromaDB, Google Gemini LLM  

---

## 1. TỔNG QUAN KIẾN TRÚC HỆ THỐNG (SYSTEM ARCHITECTURE)

Hệ thống được thiết kế theo mô hình **Microservices** hiện đại, phân tách rõ ràng trách nhiệm giữa nghiệp vụ quản trị lõi và các tác vụ tính toán trí tuệ nhân tạo:

```
[ FRONTEND LAYER ]
├── SenVietHotelManagement (Customer Web - Port 8080)
└── KLTN_HotelManagementFE  (Staff Web    - Port 8082)
            │                           │
            ▼                           ▼
[ BACKEND & GATEWAY LAYER ]
└── KLTN_HotelManagementBE (Spring Boot - Port 8081)
    ├── Quản lý đặt phòng, xếp ca, hóa đơn, nhân viên
    ├── Tích hợp thanh toán PayOS VietQR
    └── API Gateway định tuyến yêu cầu AI sang Python Service
            │
            ▼ (HTTP REST / JSON)
[ AI MICROSERVICE LAYER ]
└── KLTN_HotelManagementAI (FastAPI - Port 8000)
    ├── Quản lý luồng RAG (Retrieval-Augmented Generation)
    ├── Trích xuất và vector hóa dữ liệu nghiệp vụ
    ├── Thuật toán tìm kiếm tương đồng Cosine Similarity
    └── Sinh câu trả lời & tạo thẻ tương tác (Booking Card, VietQR PayOS)
            │
            ▼ (psycopg2 / SQL Query)
[ DATA LAYER - HYBRID POSTGRESQL (Port 5432) ]
└── Database: hotelmanagement
    ├── Bảng nghiệp vụ: hotels, branch_room_policies, rooms, services, promotions
    └── Bảng Vector AI: hotel_knowledge_vectors (Lưu trữ Embeddings 384D)
```

---

## 2. CƠ SỞ DỮ LIỆU VECTOR TRONG POSTGRESQL

Đúng theo định hướng chuẩn học thuật: Sử dụng chính cơ sở dữ liệu **PostgreSQL** của dự án làm **Hybrid Database**, lưu trữ đồng thời cả dữ liệu quan hệ và toạ độ vector của AI.

### 2.1. Cấu trúc bảng `hotel_knowledge_vectors`
| Cột | Kiểu dữ liệu | Ý nghĩa |
|---|---|---|
| `id` | `VARCHAR(64) PRIMARY KEY` | Mã định danh đoạn tri thức (VD: `hotel_1`, `policy_4`) |
| `category` | `VARCHAR(64)` | Phân loại: `hotel_branch`, `room_policy`, `amenity`, `service`, `promotion`, `general_policy` |
| `content` | `TEXT` | Nội dung văn bản tiếng Việt đầy đủ ngữ nghĩa |
| `metadata_json` | `JSONB` | Siêu dữ liệu chi tiết phục vụ lọc dữ liệu nâng cao |
| `embedding` | `FLOAT8[]` / `VECTOR` | Mảng toạ độ vector ngữ nghĩa đa chiều |
| `updated_at` | `TIMESTAMP` | Thời điểm cập nhật dữ liệu gần nhất |

### 2.2. Hàm tính khoảng cách Cosine Similarity trong PostgreSQL
```sql
CREATE OR REPLACE FUNCTION cosine_similarity(a FLOAT8[], b FLOAT8[])
RETURNS FLOAT8 AS $$
DECLARE
    dot_product FLOAT8 := 0.0;
    norm_a FLOAT8 := 0.0;
    norm_b FLOAT8 := 0.0;
    i INT;
    dim INT;
BEGIN
    dim := array_length(a, 1);
    IF dim IS NULL OR dim <> array_length(b, 1) THEN
        RETURN 0.0;
    END IF;
    FOR i IN 1..dim LOOP
        dot_product := dot_product + (a[i] * b[i]);
        norm_a := norm_a + (a[i] * a[i]);
        norm_b := norm_b + (b[i] * b[i]);
    END LOOP;
    IF norm_a = 0.0 OR norm_b = 0.0 THEN
        RETURN 0.0;
    END IF;
    RETURN dot_product / (sqrt(norm_a) * sqrt(norm_b));
END;
$$ LANGUAGE plpgsql IMMUTABLE;
```

---

## 3. NGUYÊN LÝ HOẠT ĐỘNG CỦA PIPELINE RAG (5 BƯỚC)

1. **Thu thập dữ liệu (Ingestion)**: Service Python truy vấn trực tiếp các bảng nghiệp vụ (`hotels`, `policies`, `services`, `promotions`) từ PostgreSQL.
2. **Phân đoạn ngữ nghĩa (Chunking)**: Dữ liệu được cắt thành 113 đoạn tri thức độc lập kèm metadata nhãn loại phòng, chi nhánh.
3. **Nhúng toạ độ (Embedding)**: Chuyển đổi các đoạn văn bản thành vector toạ độ 384 chiều và lưu đồng thời vào bảng `hotel_knowledge_vectors` trên PostgreSQL và bộ đệm ChromaDB.
4. **Tìm kiếm ngữ nghĩa (Semantic Retrieval)**:
   - Nhận câu hỏi từ khách -> Chuyển câu hỏi thành vector.
   - Tính toán Cosine Similarity trong không gian vector -> Lọc ra Top 4 đoạn thông tin có độ khớp cao nhất (> 0.35).
5. **Sinh câu trả lời (Augmented Generation)**:
   - Ghép dữ liệu thực tế tìm được vào System Prompt gửi tới LLM.
   - LLM đọc đúng dữ liệu khách sạn của Sen Việt, trả lời tự nhiên, chính xác 100%, không bị ảo giác.

---

## 4. DANH SÁCH API ENDPOINTS

- **Swagger UI Tài liệu tương tác**: `http://localhost:8000/docs`
- **Kiểm tra trạng thái & số lượng vector**: `GET http://localhost:8000/api/health`
- **Đồng bộ lại dữ liệu từ PostgreSQL**: `POST http://localhost:8000/api/ingest`
- **Hội thoại với AI Chatbot**: `POST http://localhost:8000/api/chat` hoặc `POST http://localhost:8000/ai/chat`

---

## 5. HƯỚNG DẪN KHỞI CHẠY (QUICK START)

### Kích hoạt môi trường và khởi động server:
```powershell
cd C:\Users\admin\Downloads\KLTN_HotelManagementAI
.\venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```
Mở trình duyệt truy cập: `http://localhost:8000/docs` để trải nghiệm trực quan.
