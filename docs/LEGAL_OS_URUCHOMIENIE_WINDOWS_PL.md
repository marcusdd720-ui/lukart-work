# LUKART LEGAL OS — uruchomienie na Windows 11

**Data:** 26.10.2026. **Status:** kod integracyjny przetestowany w GitHub Actions, lokalne uruchomienie na Windows niepotwierdzone.

**Ostrzeżenie:** START-LUKART-LEGAL-OS.cmd jest skryptem uruchamiającym, a nie instalatorem. Bez istniejącego, zaufanego pliku Python z funkcją build_operator() i sesji HUMAN aplikacja nie obsłuży spraw. Nie wolno tworzyć fikcyjnych uprawnień ani przesyłać prawdziwych danych do testowego GitHub CI.

## Krok 1. Pobierz kod z prawidłowej gałęzi

Otwórz prywatne repozytorium: https://github.com/marcusdd720-ui/lukart-work

Wybierz gałąź integration/legal-os-hidden-document-engine-v1, następnie Code → Download ZIP. Rozpakuj do **nowego** folderu, np. C:\Users\LukaszA\Projects\LUKART-LEGAL-OS-TEST. W katalogu głównym powinny być START-LUKART-LEGAL-OS.cmd i pyproject.toml.

Alternatywnie w Windows PowerShell:

~~~powershell
$Repo = Join-Path $env:USERPROFILE 'Projects\LUKART-LEGAL-OS-TEST'
New-Item -ItemType Directory -Force (Split-Path $Repo) | Out-Null
git clone --branch integration/legal-os-hidden-document-engine-v1 --single-branch https://github.com/marcusdd720-ui/lukart-work.git $Repo
Set-Location $Repo
git rev-parse HEAD
~~~

Jeśli folder już istnieje, nie nadpisuj go ani nie uruchamiaj git reset --hard. Sprawdź git status --short.

## Krok 2. Utwórz niezależne środowisko Python

W PowerShell, w katalogu z pyproject.toml:

~~~powershell
py -3.14 --version
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[postgres,ingestion]"
~~~

Jeżeli py -3.14 nie działa, sprawdź python --version i użyj rzeczywiście dostępnego Python 3.11 lub nowszego. Skrypt CMD automatycznie wybierze .venv\Scripts\python.exe, gdy ten plik istnieje. Nie musisz uruchamiać Activate.ps1 ani zmieniać ExecutionPolicy.

## Krok 3. Sprawdź, czy posiadasz prawdziwy plik konfiguracji WORK

Wymagany jest **zaufany** plik Python, który definiuje funkcję build_operator() bez argumentów i buduje skonfigurowany GeneratorPismOperator z dostępem do Twojej istniejącej testowej bazy PostgreSQL oraz wymaganych profili.

Uwaga: lukart_work/operator_config.py to **fabryka wymagająca argumentów**, a nie gotowy plik uruchomieniowy.

Sprawdź dokładną, istniejącą ścieżkę; poniższy napis jest tylko przykładem i musi zostać zastąpiony:

~~~powershell
$Config = 'C:\TUTAJ_RZECZYWISTA_SCIEZKA\trusted_work_config.py'
Test-Path -LiteralPath $Config
~~~

Jeśli wynik jest False: **STOP**. Trzeba najpierw dokończyć lokalne zaufane powiązanie WORK z PostgreSQL i uwierzytelnianiem. Nie wolno wpisywać ścieżki do przypadkowego pliku ani wymyślać tokenów.

Jeśli wynik True i plik został zweryfikowany:

~~~powershell
$env:LUKART_TRUSTED_CONFIG = $Config
~~~

Nie wklejaj zawartości pliku konfiguracyjnego, haseł ani tokenów do chatu.

## Krok 4. Uruchom program

W tym samym oknie PowerShell:

~~~powershell
Set-Location $Repo
.\START-LUKART-LEGAL-OS.cmd
~~~

Jeśli konfiguracja WORK działa, przeglądarka może otworzyć adres **http://127.0.0.1:8786/**. Okno konsoli musi pozostać otwarte. Zatrzymanie: Ctrl+C.

Powinien pojawić się ekran **LUKART LEGAL OS — Moja sprawa**. Generator Pism 2.0 działa w tle.

## Krok 5. Otwórz sprawę

Ekran wymaga tokenu prywatnej sesji WORK wystawionego przez ten sam skonfigurowany TokenAuthority. Nie jest to token GitHub, klucz OpenAI ani hasło Windows.

Po autoryzacji program umożliwia odczyt istniejącej sprawy, import PDF/JPG/PNG/TIFF/DOCX/TXT i wpisanie opisu, HUMAN review kandydatów, edycję istniejących Draft oraz pobranie zapisanych plików. Limit importu obecnej wersji to 700 KiB na plik. Nie ukończono jednolitego logowania ani nowej sprawy od podstaw.

## Krok 6. Jeśli wystąpi błąd

- **BRAK KONFIGURACJI:** nie ustawiono LUKART_TRUSTED_CONFIG.
- **HOST_CONFIGURATION_FAILED:** konfiguracja nie jest zaufana/kompletna lub nie może uruchomić operatora; bez dostępu do lokalnych usług nie da się tego zweryfikować.
- **ModuleNotFoundError:** nie użyto prawidłowej .venv albo katalogu repo.
- **WinError 10048:** port 8786 zajęty; nie zatrzymuj w ciemno procesu.
- **403 CASE_OPERATION_REJECTED:** token lub uprawnienia nie dotyczą aktualnej sprawy.
- **Za duże zdjęcie:** obecnie >700 KiB nie jest obsługiwane.

Sprawdzanie diagnostyczne bez haseł:

~~~powershell
py -3.14 --version
$Repo = Join-Path $env:USERPROFILE 'Projects\LUKART-LEGAL-OS-TEST'
Test-Path -LiteralPath (Join-Path $Repo 'START-LUKART-LEGAL-OS.cmd')
[string]::IsNullOrWhiteSpace($env:LUKART_TRUSTED_CONFIG)
Get-NetTCPConnection -LocalPort 8786 -State Listen -ErrorAction SilentlyContinue | Select LocalPort,OwningProcess
~~~

Wynik True przy IsNullOrWhiteSpace oznacza **brak** zmiennej konfiguracji.

**Bezpieczeństwo:** tylko 127.0.0.1, testowe dane syntetyczne, brak zmian V5 na 8784, brak merge do main, brak płatnych usług. Lokalny E2E pozostaje NOT VERIFIED, dopóki nie zostanie rzeczywiście uruchomiony na Windows.
