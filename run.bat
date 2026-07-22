@echo off
setlocal
cd /d "%~dp0"

if not exist "fastApi-app\.env" (
  echo [run.bat] WARNING: fastApi-app\.env not found. Copy fastApi-app\.env.example to
  echo           fastApi-app\.env and paste your HF_TOKEN before 3D features will work.
)

start "AVRoom API" /D "%~dp0fastApi-app" cmd /k "call .venv\Scripts\activate.bat && uvicorn main:app --reload"
start "AVRoom Front" /D "%~dp0react-front" cmd /k "npm run dev"

endlocal
