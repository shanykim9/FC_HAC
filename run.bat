@echo off
chcp 65001 >nul
cd /d %~dp0
if not exist .venv (
  py -3.12 -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install -q -r requirements.txt
python -m streamlit run app.py