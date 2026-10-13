import os
import sys
import pytest
from httpx import AsyncClient, ASGITransport

# Set freeze time default for all tests
os.environ["AI_FROZEN_DATE"] = "2026-10-13"

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from main import app
from tests.fixtures.db_seed import seed_test_database
from tests.fixtures.sample_policies import seed_test_policies

@pytest.fixture(scope="session", autouse=True)
def setup_test_infrastructure():
    """Tự động seed database và chính sách mẫu trước khi chạy test suite"""
    print("\n[*] Initializing test infrastructure...")
    seed_test_database()
    seed_test_policies()
    print("[+] Test infrastructure ready!")

@pytest.fixture
async def async_client():
    """Async HTTP Client gọi thẳng FastAPI app in-process"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
