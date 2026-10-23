@echo off
setlocal
if defined BENCH_PYTHON goto chosen
if exist "%~dp0.venv\Scripts\python.exe" set "BENCH_PYTHON=%~dp0.venv\Scripts\python.exe"
if defined BENCH_PYTHON goto chosen
if exist "C:\Espressif\python_env\idf5.5_py3.14_env\Scripts\python.exe" set "BENCH_PYTHON=C:\Espressif\python_env\idf5.5_py3.14_env\Scripts\python.exe"
if defined BENCH_PYTHON goto chosen
if exist "C:\Espressif\python_env\idf5.5_py3.11_env\Scripts\python.exe" set "BENCH_PYTHON=C:\Espressif\python_env\idf5.5_py3.11_env\Scripts\python.exe"
if not defined BENCH_PYTHON (
  echo Python environment not found. See pc/README.md.
  pause
  exit /b 1
)
:chosen
"%BENCH_PYTHON%" "%~dp0launcher.py"
if errorlevel 1 pause
