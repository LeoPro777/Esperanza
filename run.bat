@echo off
echo ==============================================================
echo  Iniciando Servidor Local - Sistema Esperanza
echo ==============================================================

:: Verificar si existe el entorno virtual
if exist "venv\" goto :venv_ok
echo Creando entorno virtual Python (venv)...
python -m venv venv
if not errorlevel 1 goto :venv_ok

echo Error: No se pudo crear el entorno virtual con 'python'. Intentando con 'py'...
py -m venv venv
if not errorlevel 1 goto :venv_ok

echo Error critico: Instale Python y asegurese de agregarlo al PATH.
pause
exit /b 1

:venv_ok

:: Activar el entorno virtual
echo Activando entorno virtual...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo Error: No se pudo activar el entorno virtual.
    pause
    exit /b 1
)

:: Instalar/actualizar dependencias
echo Instalando y actualizando dependencias desde requirements.txt...
pip install -r requirements.txt
if errorlevel 1 (
    echo Error: Fallo la instalacion de dependencias.
    pause
    exit /b 1
)

:: Verificar si el archivo .env existe
if not exist ".env" (
    echo ATENCION: No se ha encontrado el archivo .env.
    echo Creando un archivo .env de ejemplo. Por favor configure sus credenciales y MONGODB_URI.
    echo MONGODB_URI=mongodb://localhost:27017/esperanza > .env
    echo JWT_SECRET=cambiar_este_secreto_super_seguro_12345 >> .env
    echo ADMIN_USERNAME=admin >> .env
    echo ADMIN_PASSWORD=admin >> .env
    echo PORT=8000 >> .env
)

:: Ejecutar FastAPI
echo Iniciando servidor FastAPI con recarga automatica en http://127.0.0.1:8000 ...
uvicorn src.main:app --reload --host 127.0.0.1 --port 8000

pause
