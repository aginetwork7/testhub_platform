@echo off
chcp 65001 >nul
title TestHub Startup Script

echo ========================================
echo    TestHub Service Startup Script
echo ========================================
echo.

cd /d "%~dp0"

REM 检查Python环境
echo Checking Python environment...

REM 使用虚拟环境（如果可用）
if exist "venv\Scripts\python.exe" (
    echo Found virtual environment: venv
    set PYTHON_CMD=venv\Scripts\python.exe
    goto :found_python
)

if exist ".venv\Scripts\python.exe" (
    echo Found virtual environment: .venv
    set PYTHON_CMD=.venv\Scripts\python.exe
    goto :found_python
)

REM 检查是否已在虚拟环境中
if defined VIRTUAL_ENV (
    echo Already in virtual environment
    set PYTHON_CMD=python
    goto :found_python
)

REM 使用指定的虚拟环境
set VENV_PATH=D:\ENV\TestHub
if exist "%VENV_PATH%\Scripts\python.exe" (
    echo Using specified virtual environment: %VENV_PATH%
    set PYTHON_CMD=%VENV_PATH%\Scripts\python.exe
    goto :found_python
)

echo Error: Virtual environment not found!
echo Please create virtual environment or activate virtual environment
echo Expected path: %VENV_PATH%
pause
exit /b 1

:found_python
echo Python command: %PYTHON_CMD%
echo.

REM 激活虚拟环境（可选，用于设置环境变量）
call "%VENV_PATH%\Scripts\activate.bat"

echo [1/2] Starting Django development server...

REM 从config.yaml读取端口配置
REM 注意：脚本在后端目录中，需要从父目录读取config.yaml
for /f "tokens=2 delims=: " %%a in ('type ..\config.yaml ^| findstr /i "backend_port"') do set BACKEND_PORT=%%a

REM 如果未找到，则使用默认端口
if "%BACKEND_PORT%"=="" set BACKEND_PORT=8000

echo Starting backend server, port: %BACKEND_PORT%
start "Django Server" cmd /k "%PYTHON_CMD% manage.py runserver 0.0.0.0:%BACKEND_PORT%"

timeout /t 2 /nobreak >nul

echo [2/2] Starting Django-Q task queue service...
start "Django-Q Cluster" cmd /k "%PYTHON_CMD% manage.py qcluster"

echo.
echo ========================================
echo    All services started!
echo ========================================
echo.
echo Tips:
echo   - Press Ctrl+C to stop all services
echo   - Check logs in logs/ directory
echo.
rem pause
