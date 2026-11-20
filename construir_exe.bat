@echo off
setlocal
REM Genera dist\PDFTaller\PDFTaller.exe (no necesita Python para ejecutarse).
cd /d "%~dp0"
title Construir PDF Taller

set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY ( python -c "import sys" >nul 2>&1 && set "PY=python" )
if not defined PY ( echo [ERROR] No se encontro Python. & goto :fallo )

if not exist ".venv-build\Scripts\python.exe" (
    echo Creando entorno de construccion...
    %PY% -m venv .venv-build || goto :fallo
)
set "VPY=.venv-build\Scripts\python.exe"
"%VPY%" -m pip install --upgrade pip || goto :fallo
"%VPY%" -m pip install -e ".[gui]" pyinstaller || goto :fallo

echo Construyendo el ejecutable...
"%VPY%" -m PyInstaller --noconfirm --clean PDFTaller.spec || goto :fallo

echo.
echo Listo: %CD%\dist\PDFTaller\PDFTaller.exe
echo Puede copiar la carpeta dist\PDFTaller a cualquier PC con Windows.
pause
exit /b 0

:fallo
echo.
echo [ERROR] La construccion fallo. Copie el texto de esta ventana y envielo.
pause
exit /b 1
