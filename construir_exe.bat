@echo off
setlocal
REM Genera dist\ProcesadorPDF\ProcesadorPDF.exe (no necesita Python para ejecutarse).
cd /d "%~dp0"
title Construir Procesador PDF

set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY ( python -c "import sys" >nul 2>&1 && set "PY=python" )
for %%P in (python3 python3.13 python3.12 python3.11 python3.10) do if not defined PY ( %%P -c "import sys" >nul 2>&1 && set "PY=%%P" )
if not defined PY ( echo [ERROR] No se encontro Python. & goto :fallo )

if not exist ".venv-build\Scripts\python.exe" (
    echo Creando entorno de construccion...
    %PY% -m venv .venv-build || goto :fallo
)
set "VPY=.venv-build\Scripts\python.exe"
"%VPY%" -m pip install --upgrade pip || goto :fallo
"%VPY%" -m pip install -e ".[gui]" pyinstaller || goto :fallo

REM Datos de OCR (espanol e ingles, version rapida) para incluirlos en el ejecutable
if not exist "tessdata" mkdir tessdata
for %%L in (spa eng) do (
    if not exist "tessdata\%%L.traineddata" (
        echo Descargando datos de OCR: %%L...
        curl -L -f -o "tessdata\%%L.traineddata" "https://github.com/tesseract-ocr/tessdata_fast/raw/main/%%L.traineddata" || echo [AVISO] No se pudo descargar %%L; el OCR necesitara Tesseract instalado.
    )
)

echo Construyendo el ejecutable...
"%VPY%" -m PyInstaller --noconfirm --clean ProcesadorPDF.spec || goto :fallo

echo.
echo Listo: %CD%\dist\ProcesadorPDF\ProcesadorPDF.exe
echo Puede copiar la carpeta dist\ProcesadorPDF a cualquier PC con Windows.
pause
exit /b 0

:fallo
echo.
echo [ERROR] La construccion fallo. Copie el texto de esta ventana y envielo.
pause
exit /b 1
