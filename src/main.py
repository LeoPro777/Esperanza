import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response, Form, File, UploadFile, Depends, status, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from src import config, database, auth
from src.services import excel_service

# Configuración del Logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("esperanza")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Conexión a Base de Datos en el inicio
    await database.init_db()
    yield
    # Cierre de conexión al apagar
    await database.close_db()

app = FastAPI(
    title="Plataforma de Emergencia - Esperanza",
    lifespan=lifespan
)

# Montar archivos estáticos
app.mount("/static", StaticFiles(directory="static"), name="static")

# Configurar motor de plantillas Jinja2
templates = Jinja2Templates(directory="templates")

# Manejador de excepciones 401 para redirigir vistas al Login
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    # Si la petición es del panel administrativo (/admin) y no está autenticado, redirigir a login
    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        if request.url.path.startswith("/admin"):
            return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        # Para endpoints API retornar JSON
        if request.url.path.startswith("/api/"):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": exc.detail}
            )
    # Por defecto retornar la respuesta HTTP estándar
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

# ---------------------------------------------------------
# RUTAS PÚBLICAS
# ---------------------------------------------------------

@app.get("/")
async def get_buscador(request: Request, q: str = None):
    db = database.get_db()
    resultados = []
    error_busqueda = None
    
    # Verificar si el usuario está autenticado (para la cabecera de la UI)
    autenticado = auth.is_authenticated(request)
    
    if q is not None:
        q_clean = q.strip()
        if len(q_clean) < 3:
            error_busqueda = "El término de búsqueda debe tener al menos 3 caracteres."
        else:
            try:
                # Determinar si el término es numérico y menor a 120 (búsqueda de edad)
                if q_clean.isdigit() and int(q_clean) < 120:
                    filter_dict = {
                        "$or": [
                            {"$text": {"$search": q_clean}},
                            {"edad": int(q_clean)}
                        ]
                    }
                else:
                    filter_dict = {"$text": {"$search": q_clean}}
                
                # Intentar buscar con proyección de relevancia (textScore)
                try:
                    cursor = db.pacientes.find(
                        filter_dict,
                        {"score": {"$meta": "textScore"}}
                    ).sort([("score", {"$meta": "textScore"})]).limit(30)
                    
                    async for doc in cursor:
                        doc["_id"] = str(doc["_id"])
                        resultados.append(doc)
                except Exception as db_err:
                    logger.warning(f"Fallo ordenamiento por score de texto, reintentando sin score: {db_err}")
                    # Búsqueda de respaldo sin proyección de score (por si falla en algún motor)
                    cursor = db.pacientes.find(filter_dict).sort("fecha_ingreso", -1).limit(30)
                    async for doc in cursor:
                        doc["_id"] = str(doc["_id"])
                        resultados.append(doc)
                        
            except Exception as e:
                logger.error(f"Error al realizar la búsqueda: {e}")
                error_busqueda = "Ocurrió un error en el servidor al realizar la búsqueda."

    return templates.TemplateResponse(
        "buscador.html",
        {
            "request": request,
            "q": q,
            "resultados": resultados,
            "error_busqueda": error_busqueda,
            "autenticado": autenticado
        }
    )

@app.get("/login")
async def get_login(request: Request):
    # Si ya está autenticado, enviarlo directo al panel de control
    if auth.is_authenticated(request):
        return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login")
async def post_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    if username == config.ADMIN_USERNAME and password == config.ADMIN_PASSWORD:
        # Generar token y guardar en cookie HttpOnly
        token = auth.create_access_token(username)
        response = RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
        # Configurar cookie segura
        is_secure = request.url.scheme == "https"
        response.set_cookie(
            key=auth.COOKIE_NAME,
            value=token,
            httponly=True,
            max_age=6 * 60 * 60, # 6 horas en segundos
            expires=6 * 60 * 60,
            samesite="strict",
            secure=is_secure
        )
        logger.info(f"Sesión iniciada con éxito para el usuario: {username}")
        return response
    
    # Credenciales incorrectas
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": "Credenciales inválidas. Intente de nuevo."}
    )

@app.post("/logout")
async def post_logout():
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key=auth.COOKIE_NAME)
    logger.info("Sesión cerrada correctamente.")
    return response

# ---------------------------------------------------------
# RUTAS DE ADMINISTRACIÓN (PROTEGIDAS)
# ---------------------------------------------------------

@app.get("/admin")
async def get_admin(request: Request, username: str = Depends(auth.get_current_admin)):
    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "username": username,
            "exito": None,
            "errores": None,
            "autenticado": True
        }
    )

@app.post("/admin/cargar-masiva")
async def post_cargar_masiva(
    request: Request,
    file: UploadFile = File(...),
    username: str = Depends(auth.get_current_admin)
):
    db = database.get_db()
    exito_msg = None
    errores_list = None
    
    try:
        # Leer los bytes del archivo subido
        file_bytes = await file.read()
        filename = file.filename
        
        # Procesar con el excel service
        registros, errores_list = await excel_service.procesar_archivo(file_bytes, filename)
        
        inserted_count = 0
        if registros:
            # Operación atómica de inserción por lotes
            result = await db.pacientes.insert_many(registros)
            inserted_count = len(result.inserted_ids)
            exito_msg = f"Se cargaron exitosamente {inserted_count} registros."
            logger.info(f"Carga masiva exitosa: {inserted_count} registros insertados por {username}.")
        
        if not registros and not errores_list:
            # Archivo vacío
            errores_list = [{"fila": 0, "error": "El archivo no contiene filas procesables."}]
            
    except Exception as e:
        logger.error(f"Error procesando carga masiva: {e}")
        errores_list = [{"fila": 0, "error": f"Error interno del servidor al procesar el archivo: {str(e)}"}]
        
    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "username": username,
            "exito": exito_msg,
            "errores": errores_list,
            "autenticado": True
        }
    )
