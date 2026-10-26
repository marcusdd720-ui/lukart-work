@echo off
setlocal
cd /d "%~dp0"
if not defined LUKART_TRUSTED_CONFIG goto missing_config
if not exist "%LUKART_TRUSTED_CONFIG%" goto missing_config_file
if exist "%~dp0.venv\Scripts\python.exe" goto local_python
where python.exe >nul 2>nul
if errorlevel 1 goto missing_python
set "LUKART_PYTHON=python.exe"
goto start_server

:local_python
set "LUKART_PYTHON=%~dp0.venv\Scripts\python.exe"
goto start_server

:start_server
echo LUKART LEGAL OS - adres: http://127.0.0.1:8786/
echo Generator Pism 2.0 pozostaje w tle. Zatrzymanie: Ctrl+C
"%LUKART_PYTHON%" -B -m lukart_work.operator_host --config "%LUKART_TRUSTED_CONFIG%" --port 8786 --legal-os
set "LUKART_EXIT=%ERRORLEVEL%"
echo LUKART LEGAL OS - kod wyjscia: %LUKART_EXIT%
exit /b %LUKART_EXIT%

:missing_config
echo BRAK KONFIGURACJI WORK. Ustaw LUKART_TRUSTED_CONFIG.
echo Instrukcja: docs\LEGAL_OS_URUCHOMIENIE_WINDOWS_PL.md
exit /b 2

:missing_config_file
echo BRAK PLIKU ZAUFANEJ KONFIGURACJI WORK.
exit /b 3

:missing_python
echo BRAK PYTHON. Utworz .venv wedlug instrukcji.
exit /b 4
