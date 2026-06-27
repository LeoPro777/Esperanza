import logging
import os
import asyncio
import urllib.request
import re
from datetime import datetime, timezone
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

def format_spanish_number(num: int) -> str:
    """Formatea un número entero con punto como separador de miles."""
    return f"{num:,}".replace(",", ".")

def format_relative_time(dt: datetime) -> str:
    """Calcula y formatea el tiempo transcurrido desde un datetime dado."""
    if not dt:
        return "Sin registros"
    now = datetime.now(timezone.utc)
    diff = now - dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else now - dt
    seconds = diff.total_seconds()
    if seconds < 0:
        seconds = 0
    if seconds < 60:
        return "Hace unos instantes"
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"Hace {minutes} min"
    hours = int(minutes // 60)
    if hours < 24:
        return f"Hace {hours}h {minutes % 60}min"
    days = int(hours // 24)
    return f"Hace {days} día{'s' if days > 1 else ''}"

async def keep_alive_routine():
    url = os.environ.get("RENDER_EXTERNAL_URL")
    if not url:
        logger.info("RENDER_EXTERNAL_URL no configurada. Saltando rutina de keep-alive.")
        return
        
    logger.info(f"Iniciando rutina de keep-alive para {url}")
    # Esperar 60 segundos antes de comenzar los pings para asegurar que el servidor esté listo
    await asyncio.sleep(60)
    
    while True:
        try:
            def ping():
                try:
                    with urllib.request.urlopen(f"{url.rstrip('/')}/ping", timeout=10) as response:
                        return response.status
                except Exception as e:
                    return str(e)
                    
            status_or_err = await asyncio.to_thread(ping)
            logger.info(f"Ping keep-alive enviado a {url}/ping. Resultado: {status_or_err}")
        except Exception as e:
            logger.warning(f"Error en ping de keep-alive: {e}")
            
        # Esperar 10 minutos (600 segundos) antes de repetir
        await asyncio.sleep(600)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Conexión a Base de Datos en el inicio
    await database.init_db()
    
    # Iniciar la tarea de keep-alive en segundo plano
    keep_alive_task = asyncio.create_task(keep_alive_routine())
    
    yield
    
    # Cancelar la tarea de keep-alive ordenadamente al apagar
    keep_alive_task.cancel()
    try:
        await keep_alive_task
    except asyncio.CancelledError:
        pass
        
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

def format_datetime_spanish(dt) -> str:
    if not dt:
        return "Fecha desconocida"
    from datetime import datetime, timezone, timedelta
    
    # Si viene como string, intentar parsear
    if isinstance(dt, str):
        try:
            # Intentar parsear formato ISO
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except ValueError:
            return dt

    caracas_tz = timezone(timedelta(hours=-4))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt_local = dt.astimezone(caracas_tz)
    
    months = ["ene.", "feb.", "mar.", "abr.", "may.", "jun.", "jul.", "ago.", "sep.", "oct.", "nov.", "dic."]
    month_name = months[dt_local.month - 1]
    
    hour = dt_local.hour
    am_pm = "a. m." if hour < 12 else "p. m."
    hour_12 = hour % 12
    if hour_12 == 0:
        hour_12 = 12
        
    return f"{dt_local.day} {month_name} {dt_local.year}, {hour_12}:{dt_local.minute:02d} {am_pm}"

templates.env.filters["format_datetime"] = format_datetime_spanish

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

@app.get("/ping")
async def ping():
    return {"status": "ok"}

@app.get("/")
async def get_buscador(request: Request, q: str = None, page: int = 1):
    db = database.get_db()
    resultados = []
    error_busqueda = None
    total_paginas = 0
    total_resultados = 0
    ITEMS_PER_PAGE = 10
    
    # Verificar si el usuario está autenticado (para la cabecera de la UI)
    autenticado = auth.is_authenticated(request)
    
    # Obtener métricas dinámicas para las estadísticas
    try:
        total_registrados_raw = await db.pacientes.count_documents({})
        total_registrados = format_spanish_number(total_registrados_raw)
        
        # Buscar el registro más reciente
        cursor_recent = db.pacientes.find({}, {"fecha_ingreso": 1}).sort("fecha_ingreso", -1).limit(1)
        recent_list = await cursor_recent.to_list(length=1)
        if recent_list:
            dt = recent_list[0].get("fecha_ingreso")
            ultima_actualizacion = format_relative_time(dt)
        else:
            ultima_actualizacion = "Sin registros"
            
        # Contar hospitales distintos
        hospitales_distintos = await db.pacientes.distinct("ubicacion.hospital")
        total_hospitales = len([h for h in hospitales_distintos if h])
    except Exception as e:
        logger.error(f"Error al obtener estadísticas: {e}")
        total_registrados = "0"
        ultima_actualizacion = "Desconocida"
        total_hospitales = 0

    if q is not None:
        q_clean = q.strip()
        if len(q_clean) < 3:
            error_busqueda = "El término de búsqueda debe tener al menos 3 caracteres."
        else:
            try:
                # Construir consulta basada en expresiones regulares ($regex) para coincidencias parciales por tokens
                tokens = q_clean.split()
                and_filters = []
                for token in tokens:
                    escaped_token = re.escape(token)
                    # Convertir a expresión regular insensible a acentos
                    escaped_token = re.sub(r'[aáAÁ]', '[aáAÁ]', escaped_token)
                    escaped_token = re.sub(r'[eéEÉ]', '[eéEÉ]', escaped_token)
                    escaped_token = re.sub(r'[iíIÍ]', '[iíIÍ]', escaped_token)
                    escaped_token = re.sub(r'[oóOÓ]', '[oóOÓ]', escaped_token)
                    escaped_token = re.sub(r'[uúüUÚÜ]', '[uúüUÚÜ]', escaped_token)
                    token_regex = {"$regex": escaped_token, "$options": "i"}
                    token_or = [
                        {"nombres": token_regex},
                        {"apellidos": token_regex},
                        {"identificacion.numero": token_regex}
                    ]
                    # Incluir búsqueda de edad si el token es numérico y válido como edad
                    if token.isdigit() and int(token) < 120:
                        token_or.append({"edad": int(token)})
                    and_filters.append({"$or": token_or})
                
                filter_dict = {"$and": and_filters} if and_filters else {}
                
                # Obtener el número total de coincidencias para la paginación
                total_resultados = await db.pacientes.count_documents(filter_dict)
                total_paginas = (total_resultados + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
                
                # Ajustar la página actual dentro de los límites válidos
                if total_paginas > 0:
                    page = min(page, total_paginas)
                page = max(1, page)
                
                # Ejecutar consulta paginada
                skip = (page - 1) * ITEMS_PER_PAGE
                cursor = db.pacientes.find(filter_dict).sort("fecha_ingreso", -1).skip(skip).limit(ITEMS_PER_PAGE)
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
            "autenticado": autenticado,
            "total_registrados": total_registrados,
            "ultima_actualizacion": ultima_actualizacion,
            "total_hospitales": total_hospitales,
            "page": page,
            "total_paginas": total_paginas,
            "total_resultados": total_resultados
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
