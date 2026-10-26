@echo off
setlocal
cd /d "%~dp0"
if not defined LUKART_TRUSTED_CONFIG (
 echo BRAK KONFIGURACJI: Ustaw LUKART_TRUSTED_CONFIG na zaufany plik build_operator().
 echo Instrukcja: docs\LEGAL_OS_URUCHOMIENIE_WINDOWS_PL.md
 exit /b 2
)
if not exist "%LUKART_TRUSTED_CONFIG%" (
 echo BRAK PLIKU KONFIGURACJI: %LUKART_TRUSTED_CONFIG%
 exit /b 3
)
if exist "%~dp0.venv\Scripts\python.exe" (
 set "LUKART_PYTHON=%~dp0.venv\Scripts\python.exe"
) else (
 where python.exe >nul 2>nul
 if errorlevel 1 (
  echo BRAK PYTHON: Utworz .venv zgodnie z instrukcja.
  exit /b 4
 )
 set "LUKART_PYTHON=python.exe"
)
echo LUKART LEGAL OS - interfejs: http://127.0.0.1:8786/
echo Generator Pism 2.0 dziala w tle. Zatrzymanie: Ctrl+C
"%LUKART_PYTHON%" -B -m lukart_work.operator_host --config "%LUKART_TRUSTED_CONFIG%" --port 8786 --legal-os
set "LUKART_EXIT=%ERRORLEVEL%"
echo LUKART LEGAL OS - kod wyjscia: %LUKART_EXIT%
exit /b %LUKART_EXIT%
