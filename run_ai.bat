@echo off
title SenViet Hotel AI Microservice - Port 8000
color 0b
echo =========================================================
echo    KHOI DONG HE THONG AI MICROSERVICE - SEN VIET LUXURY
echo    Architecture: FastAPI + RAG + ChromaDB + Google Gemini
echo    Port: 8000 (Swagger: http://localhost:8000/docs)
echo =========================================================
echo.

cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo [ERROR] Khong tim thay moi truong venv!
    pause
    exit /b 1
)

echo [*] Dang kich hoat server tai http://127.0.0.1:8000 ...
echo [*] Nhan Ctrl+C de dung server.
echo.
.\venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
pause
