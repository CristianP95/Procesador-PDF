@echo off
setlocal
REM PDF Taller - inicia la aplicacion. La primera vez crea el entorno e instala dependencias.
cd /d "%~dp0"
title PDF Taller

REM 1) Buscar Python (lanzador "py" o "python" real, no el atajo de Microsoft Store)
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
    python -c "import sys" >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo.
    echo [ERROR] No se encontro Python en este equipo.
    echo Instale Python 3.10 o superior desde https://www.python.org/downloads/
    echo y marque la casilla "Add python.exe to PATH" durante la instalacion.
    goto :fallo
)
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 (
    echo [ERROR] Se necesita Python 3.10 o superior. Version encontrada:
    %PY% --version
    goto :fallo
)

REM 2) Crear el entorno virtual si no existe
if not exist ".venv\Scripts\python.exe" (
    echo Creando entorno virtual...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo [ERROR] No se pudo crear el entorno virtual.
        goto :fallo
    )
)

REM 3) Instalar dependencias (solo hasta que termine bien una vez)
if not exist ".venv\.instalado" (
    echo Instalando dependencias, puede tardar unos minutos...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -e ".[gui,dev]"
    if errorlevel 1 (
        echo [ERROR] Fallo la instalacion de dependencias. Revise su conexion a Internet.
        goto :fallo
    )
    echo ok> ".venv\.instalado"
)

REM 4) Abrir la aplicacion
echo Abriendo PDF Taller...
".venv\Scripts\python.exe" -m pdftaller %*
if errorlevel 1 (
    echo.
    echo [ERROR] La aplicacion termino con un error. El detalle esta arriba.
    goto :fallo
)
exit /b 0

:fallo
echo.
echo Copie el texto de esta ventana y envielo para revisarlo.
pause
exit /b 1
