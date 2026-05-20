@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ===============================================
echo   MCP Forge
echo   Режим: задан в .env (AI_MODE / CHAT_MODE)
echo ===============================================
echo.

REM ── Путь к проекту ────────────────────────────────────────────────────────
REM Единственная настройка здесь. Всё остальное — в .env
set SCRIPT_DIR=%~dp0
set SCRIPT_DIR=%SCRIPT_DIR:~0,-1%

REM ── [1/5] Переход в директорию проекта ───────────────────────────────────
echo [1/5] Переход в директорию проекта...
cd /d "%SCRIPT_DIR%"
if errorlevel 1 (
    echo [ОШИБКА] Не удалось перейти в: %SCRIPT_DIR%
    pause & exit /b 1
)
echo        OK: %SCRIPT_DIR%
echo.

REM ── [2/5] Проверка .env ───────────────────────────────────────────────────
echo [2/5] Проверка .env...
if not exist ".env" (
    echo [ОШИБКА] Файл .env не найден в %SCRIPT_DIR%
    echo          Скопируйте env.example -^> .env и заполните настройки.
    pause & exit /b 1
)
echo        OK
echo.

REM ── Читаем нужные ключи из .env через findstr ────────────────────────────
REM findstr надёжен с UTF-8 LF-only .env (читает только одну строку)
set MCP_SERVER_HOST=127.0.0.1
set MCP_SERVER_PORT=8000
set CHAT_MODE=TERMINAL

for /f "tokens=2 delims==" %%A in ('findstr /i /b "MCP_SERVER_HOST=" ".env"') do (
    for /f "tokens=*" %%X in ("%%A") do set MCP_SERVER_HOST=%%X
)
for /f "tokens=2 delims==" %%A in ('findstr /i /b "MCP_SERVER_PORT=" ".env"') do (
    for /f "tokens=*" %%X in ("%%A") do set MCP_SERVER_PORT=%%X
)
for /f "tokens=2 delims==" %%A in ('findstr /i /b "CHAT_MODE=" ".env"') do (
    for /f "tokens=*" %%X in ("%%A") do set _VAL=%%X
    if not "!_VAL!"=="" set CHAT_MODE=!_VAL!
)

REM Точка входа по CHAT_MODE
if /i "%CHAT_MODE%"=="WEB" (
    set ENTRY_SCRIPT=mcp_forge_chat.py
    set ENTRY_LABEL=веб-чат
) else (
    set ENTRY_SCRIPT=mcp_forge_terminal.py
    set CHAT_MODE=TERMINAL
    set ENTRY_LABEL=терминал
)

REM ── [3/5] Активация виртуального окружения ───────────────────────────────
echo [3/5] Активация виртуального окружения...
set VENV_DIR=%SCRIPT_DIR%\.venv
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo [ОШИБКА] venv не найден: %VENV_DIR%
    echo          Создайте: python -m venv .venv
    echo          Зависимости: pip install -r requirements.txt
    pause & exit /b 1
)
call "%VENV_DIR%\Scripts\activate.bat"
if errorlevel 1 (
    echo [ОШИБКА] Не удалось активировать venv
    pause & exit /b 1
)
echo        OK
echo.

REM ── [4/5] Запуск MCP Forge Server ────────────────────────────────────────
echo [4/5] Запуск MCP Forge Server на %MCP_SERVER_HOST%:%MCP_SERVER_PORT%...
if not exist "mcp_forge_server.py" (
    echo [ОШИБКА] Файл не найден: mcp_forge_server.py
    pause & exit /b 1
)

start "MCP Forge Server" cmd /k "%SCRIPT_DIR%\_run_mcp_forge_server.bat"

echo        Ожидание запуска сервера (до 15 сек)...
set WAIT=0
:WAIT_LOOP
timeout /t 1 >nul
set /a WAIT+=1
netstat -an 2>nul | find "%MCP_SERVER_PORT%" | find "LISTENING" >nul 2>&1
if not errorlevel 1 goto SERVER_READY
if %WAIT% GEQ 15 (
    echo [ПРЕДУПРЕЖДЕНИЕ] Сервер не ответил за 15 сек — продолжаем...
    goto START_HOST
)
goto WAIT_LOOP

:SERVER_READY
echo        OK: сервер слушает порт %MCP_SERVER_PORT%
echo.

REM ── [5/5] Запуск точки входа ─────────────────────────────────────────────
:START_HOST
echo [5/5] Запуск хоста [CHAT_MODE=%CHAT_MODE%]...
if not exist "%ENTRY_SCRIPT%" (
    echo [ОШИБКА] Файл не найден: %ENTRY_SCRIPT%
    pause & exit /b 1
)

echo.
echo ===============================================
echo   Система запущена
echo   Директория: %SCRIPT_DIR%
echo   AI_MODE   : читается из .env
echo   MCP-сервер: %MCP_SERVER_HOST%:%MCP_SERVER_PORT%  (из .env)
echo   CHAT_MODE : %CHAT_MODE%  ^(%ENTRY_LABEL%^)
echo   Хост      : в этом окне
echo   Сервер    : в окне "MCP Forge Server"
echo ===============================================
echo.

python "%ENTRY_SCRIPT%"

echo.
echo [INFO] Хост завершил работу.
echo        Закройте окно сервера вручную или нажмите любую клавишу.
pause
