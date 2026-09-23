@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m streamlit run app.py --server.address 127.0.0.1
) else if exist "..\..\work\python\python.exe" (
  "..\..\work\python\python.exe" -m streamlit run app.py --server.address 127.0.0.1
) else (
  python -m streamlit run app.py --server.address 127.0.0.1
)
