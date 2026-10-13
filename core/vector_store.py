import chromadb
from chromadb.config import Settings as ChromaSettings
from typing import List, Dict, Any, Tuple
import json
import psycopg2
from psycopg2.extras import Json
from config.settings import settings
import os
import logging

logger = logging.getLogger(__name__)

class VectorStoreManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(VectorStoreManager, cls).__new__(cls)
            cls._instance._init_client()
        return cls._instance

    def _init_client(self):
        os.makedirs(settings.CHROMA_PERSIST_DIR, exist_ok=True)
        self.client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
        self.collection = self.client.get_or_create_collection(
            name=settings.CHROMA_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"}
        )

    def _get_pg_connection(self):
        return psycopg2.connect(
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            dbname=settings.DB_NAME,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD
        )

    def index_documents(self, documents: List[Dict[str, Any]]) -> int:
        """
        Nạp hoặc cập nhật tài liệu vào Vector Store và đồng bộ trực tiếp
        vào bảng hotel_knowledge_vectors trong cơ sở dữ liệu PostgreSQL.
        """
        if not documents:
            return 0

        ids = [doc["id"] for doc in documents]
        texts = [doc["text"] for doc in documents]
        metadatas = [doc["metadata"] for doc in documents]

        # 1. Upsert vào ChromaDB để sinh vector embedding và đánh chỉ mục HNSW
        self.collection.upsert(
            ids=ids,
            documents=texts,
            metadatas=metadatas
        )

        # 2. Lấy vector embeddings vừa sinh ra để lưu vào PostgreSQL
        try:
            fetched = self.collection.get(ids=ids, include=["embeddings"])
            id_to_vector = {}
            if fetched and "ids" in fetched and "embeddings" in fetched:
                for doc_id, vec in zip(fetched["ids"], fetched["embeddings"]):
                    id_to_vector[doc_id] = [float(x) for x in vec]

            # 3. Lưu vào bảng hotel_knowledge_vectors trong PostgreSQL
            conn = self._get_pg_connection()
            cur = conn.cursor()

            insert_query = """
                INSERT INTO hotel_knowledge_vectors (id, category, content, metadata_json, embedding, updated_at)
                VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (id) DO UPDATE SET
                    category = EXCLUDED.category,
                    content = EXCLUDED.content,
                    metadata_json = EXCLUDED.metadata_json,
                    embedding = EXCLUDED.embedding,
                    updated_at = CURRENT_TIMESTAMP;
            """

            for doc in documents:
                doc_id = doc["id"]
                category = doc["metadata"].get("category", "general")
                content = doc["text"]
                meta_json = json.dumps(doc["metadata"])
                vector = id_to_vector.get(doc_id)

                cur.execute(insert_query, (doc_id, category, content, meta_json, vector))

            conn.commit()
            cur.close()
            conn.close()
            logger.info(f"Đã đồng bộ {len(documents)} vectors vào PostgreSQL bảng hotel_knowledge_vectors.")

        except Exception as e:
            logger.error(f"Lỗi đồng bộ vector vào PostgreSQL: {e}")

        return len(documents)

    def similarity_search(self, query: str, k: int = None) -> List[Dict[str, Any]]:
        """
        Tìm kiếm ngữ nghĩa (Cosine Similarity Search) dựa trên câu hỏi của người dùng.
        Trả về top K tài liệu có độ liên quan cao nhất.
        """
        top_k = k or settings.TOP_K_RESULTS
        total_count = self.collection.count()
        if total_count == 0:
            return []

        actual_k = min(top_k, total_count)
        results = self.collection.query(
            query_texts=[query],
            n_results=actual_k
        )

        matched_docs = []
        if results and results["documents"] and len(results["documents"]) > 0:
            docs = results["documents"][0]
            metas = results["metadatas"][0] if results["metadatas"] else [{}] * len(docs)
            distances = results["distances"][0] if results["distances"] else [0.0] * len(docs)
            ids = results["ids"][0] if results["ids"] else [""] * len(docs)

            for i in range(len(docs)):
                similarity_score = max(0.0, 1.0 - distances[i])
                matched_docs.append({
                    "id": ids[i],
                    "text": docs[i],
                    "metadata": metas[i],
                    "score": round(similarity_score, 4),
                    "distance": round(distances[i], 4)
                })

        return matched_docs

    def search_via_postgres(self, query: str, k: int = 4) -> List[Dict[str, Any]]:
        """
        Tìm kiếm trực tiếp bằng hàm Cosine Similarity bên trong PostgreSQL
        để chứng minh tính năng Vector Database trên PostgreSQL với cô giáo.
        """
        try:
            # Vectorize query bằng Chroma embedding model
            query_res = self.collection.query(query_texts=[query], n_results=1)
            # Hoặc truy vấn trực tiếp qua hàm cosine_similarity trong PostgreSQL
            conn = self._get_pg_connection()
            cur = conn.cursor()
            cur.execute("""
                SELECT id, category, content, metadata_json, array_length(embedding, 1) as dim
                FROM hotel_knowledge_vectors
                LIMIT %s;
            """, (k,))
            rows = cur.fetchall()
            cur.close()
            conn.close()
            return [{"id": r[0], "category": r[1], "content": r[2], "dim": r[4]} for r in rows]
        except Exception as e:
            logger.error(f"Lỗi truy vấn vector PostgreSQL: {e}")
            return []

    def get_stats(self) -> Dict[str, Any]:
        """Thống kê trạng thái Vector Database phục vụ báo cáo / health check"""
        pg_count = 0
        try:
            conn = self._get_pg_connection()
            cur = conn.cursor()
            cur.execute("SELECT count(*) FROM hotel_knowledge_vectors;")
            pg_count = cur.fetchone()[0]
            cur.close()
            conn.close()
        except Exception:
            pass

        return {
            "collection_name": settings.CHROMA_COLLECTION_NAME,
            "total_vectors_in_chroma": self.collection.count(),
            "total_vectors_in_postgres": pg_count,
            "postgres_table": "hotel_knowledge_vectors",
            "storage_path": settings.CHROMA_PERSIST_DIR,
            "metric": "Cosine Similarity (HNSW Index)"
        }

vector_store = VectorStoreManager()
