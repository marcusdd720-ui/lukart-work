@echo off
setlocal
cd /d "%~dp0"
if not defined LUKART_TRUSTED_CONFIG (
  echo LUKART LEGAL OS: konfiguracja WORK nie jest jeszcze wskazana.
  echo Ustaw LUKART_TRUSTED_CONFIG na pelna sciezke do zaufanej konfiguracji Python.
  echo Nie tworz sztucznych tokenow i nie uzywaj prywatnych danych w testach.
  exit /b 2
)
if not exist "%LUKART_TRUSTED_CONFIG%" (
  echo LUKART LEGAL OS: nie znaleziono zaufanego pliku konfiguracyjnego.
  exit /b 3
)
where python.exe >nul 2>nul
if errorlevel 1 (
  echo LUKART LEGAL OS: Python nie jest dostepny w PATH.
  exit /b 4
)
echo Uruchamiam jeden interfejs LEGAL OS, bez starego formularza Generatora 2.0.
echo Adres lokalny: http://127.0.0.1:8786/
python.exe -B -m lukart_work.operator_host --config "%LUKART_TRUSTED_CONFIG%" --port 8786 --legal-os
set EXIT_CODE=%ERRORLEVEL%
echo LUKART LEGAL OS: serwer zakonczyl dzialanie. Kod: %EXIT_CODE%
exit /b %EXIT_CODE%
