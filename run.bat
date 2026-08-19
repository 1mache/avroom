@echo off
setlocal
cd /d "%~dp0"

if not exist "fastApi-app\.env" (
  echo [run.bat] WARNING: fastApi-app\.env not found. Copy fastApi-app\.env.example to
  echo           fastApi-app\.env and paste your HF_TOKEN before 3D features will work.
)

echo [run.bat] Starting Postgres (docker compose up -d --wait db)...
docker compose up -d --wait db
if errorlevel 1 (
  echo [run.bat] ERROR: Postgres failed to start/become healthy. Is Docker running?
  exit /b 1
)

echo [run.bat] Applying DB migrations and importing any local sidecar data...
pushd fastApi-app
call ..\.venv\Scripts\activate.bat
alembic upgrade head
if errorlevel 1 (
  echo [run.bat] ERROR: alembic upgrade head failed.
  popd
  exit /b 1
)
python scripts\migrate_local_sidecars_to_db.py
popd

if defined INFERENCE_WORKERS (
  echo [run.bat] INFERENCE_WORKERS=%INFERENCE_WORKERS%
) else (
  echo [run.bat] INFERENCE_WORKERS not set — app defaults to inline mode.
  echo           PowerShell: $env:INFERENCE_WORKERS=2; ./run.bat
  echo           Or set INFERENCE_WORKERS in fastApi-app\.env
)

start "AVRoom API" /D "%~dp0fastApi-app" cmd /k "call ..\.venv\Scripts\activate.bat && set INFERENCE_WORKERS=%INFERENCE_WORKERS% && uvicorn main:app --reload"
start "AVRoom Front" /D "%~dp0react-front" cmd /k "npm run dev"

endlocal