import psycopg2
from config.settings import settings

def init_postgres_vector_storage():
    """
    Khởi tạo bảng lưu trữ Vector và hàm tính Cosine Similarity ngay trong PostgreSQL.
    Đúng chuẩn kiến trúc Hybrid Database lưu trữ Vector trên cùng PostgreSQL của đồ án.
    """
    conn = psycopg2.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        dbname=settings.DB_NAME,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD
    )
    cur = conn.cursor()

    # 1. Bảng lưu trữ vector tri thức
    cur.execute("""
        CREATE TABLE IF NOT EXISTS hotel_knowledge_vectors (
            id VARCHAR(64) PRIMARY KEY,
            category VARCHAR(64) NOT NULL,
            content TEXT NOT NULL,
            metadata_json JSONB,
            embedding FLOAT8[],
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 2. Hàm tính Cosine Similarity chuẩn mực trong PostgreSQL
    cur.execute("""
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
    """)

    conn.commit()
    print("[+] Da khoi tao bang hotel_knowledge_vectors va ham cosine_similarity trong PostgreSQL thanh cong!")
    cur.close()
    conn.close()

if __name__ == "__main__":
    init_postgres_vector_storage()
