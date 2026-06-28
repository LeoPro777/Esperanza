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
from bson import ObjectId, errors as bson_errors

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
async def get_buscador(
    request: Request,
    q: str = None,
    page: int = 1,
    exito: str = None,
    error: str = None
):
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
            "exito": exito,
            "error_msg": error,
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
async def obtener_datos_admin():
    db = database.get_db()
    
    # 1. Total Pacientes
    total_pacientes = await db.pacientes.count_documents({})
    
    # 2. Total Hospitales
    hospitales = await db.pacientes.distinct("ubicacion.hospital")
    total_hospitales = len(hospitales)
    
    # 3. Cantidades por Estado
    status_counts = {"Estable": 0, "Crítico": 0, "Reservado": 0, "De Alta": 0, "Fallecido": 0}
    try:
        pipeline_status = [{"$group": {"_id": "$estado_salud", "count": {"$sum": 1}}}]
        async for res in db.pacientes.aggregate(pipeline_status):
            st = res.get("_id")
            if st in status_counts:
                status_counts[st] = res.get("count", 0)
    except Exception as e:
        logger.error(f"Error al obtener métricas por estado: {e}")
        
    # 4. Pacientes por Hospital
    hospital_list = []
    try:
        pipeline_hosp = [
            {"$group": {"_id": "$ubicacion.hospital", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        async for res in db.pacientes.aggregate(pipeline_hosp):
            h_name = res.get("_id") or "Desconocido"
            hospital_list.append({"hospital": h_name, "count": res.get("count", 0)})
    except Exception as e:
        logger.error(f"Error al obtener métricas por hospital: {e}")

    # 5. Duplicados por Cédula (más de 1 coincidencia en número, excluyendo vacíos/nulos)
    duplicados_cedula = []
    try:
        pipeline_dup_ced = [
            {"$match": {"identificacion.numero": {"$nin": [None, ""]}}},
            {"$group": {
                "_id": "$identificacion.numero",
                "count": {"$sum": 1},
                "pacientes": {
                    "$push": {
                        "id": "$_id",
                        "nombres": "$nombres",
                        "apellidos": "$apellidos",
                        "hospital": "$ubicacion.hospital",
                        "piso_ala": "$ubicacion.piso_ala",
                        "edad": "$edad",
                        "estado_salud": "$estado_salud",
                        "fecha_ingreso": "$fecha_ingreso"
                    }
                }
            }},
            {"$match": {"count": {"$gt": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 50}
        ]
        async for res in db.pacientes.aggregate(pipeline_dup_ced):
            for p in res.get("pacientes", []):
                p["id"] = str(p["id"])
            duplicados_cedula.append(res)
    except Exception as e:
        logger.error(f"Error al obtener duplicados de cédula: {e}")

    # 6. Duplicados por Nombre (deshabilitado: cédulas vacías no coinciden)
    duplicados_nombre = []

    # 7. Registros Incompletos / Inválidos
    registros_incompletos = []
    try:
        cursor_inc = db.pacientes.find({
            "$or": [
                {"nombres": None}, {"apellidos": None},
                {"nombres": ""}, {"apellidos": ""},
                {"ubicacion.hospital": None}, {"ubicacion.hospital": ""}
            ]
        }).limit(50)
        async for doc in cursor_inc:
            doc["_id"] = str(doc["_id"])
            registros_incompletos.append(doc)
    except Exception as e:
        logger.error(f"Error al obtener registros incompletos: {e}")

    return {
        "total_pacientes": total_pacientes,
        "total_hospitales": total_hospitales,
        "status_counts": status_counts,
        "hospital_list": hospital_list,
        "duplicados_cedula": duplicados_cedula,
        "duplicados_nombre": duplicados_nombre,
        "registros_incompletos": registros_incompletos
    }

@app.get("/admin")
async def get_admin(
    request: Request,
    exito: str = None,
    error: str = None,
    username: str = Depends(auth.get_current_admin)
):
    stats = await obtener_datos_admin()
    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "username": username,
            "exito": exito,
            "error_msg": error,
            "autenticado": True,
            **stats
        }
    )

@app.post("/admin/eliminar-paciente/{paciente_id}")
async def post_eliminar_paciente(
    request: Request,
    paciente_id: str,
    username: str = Depends(auth.get_current_admin)
):
    import urllib.parse
    db = database.get_db()
    try:
        res = await db.pacientes.delete_one({"_id": ObjectId(paciente_id)})
        referer = request.headers.get("referer")
        
        # Si la petición viene del buscador (página principal), redirigir de vuelta preservando los parámetros de búsqueda
        if referer and "/admin" not in referer:
            from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
            parsed_url = urlparse(referer)
            query_params = parse_qs(parsed_url.query)
            if res.deleted_count > 0:
                query_params["exito"] = ["Paciente eliminado con éxito"]
                logger.info(f"Paciente {paciente_id} eliminado con éxito por {username}.")
            else:
                query_params["error"] = ["No se encontró el paciente"]
            new_query = urlencode(query_params, doseq=True)
            new_url = urlunparse((parsed_url.scheme, parsed_url.netloc, parsed_url.path, parsed_url.params, new_query, parsed_url.fragment))
            return RedirectResponse(url=new_url, status_code=status.HTTP_303_SEE_OTHER)

        if res.deleted_count > 0:
            logger.info(f"Paciente {paciente_id} eliminado con éxito por {username}.")
            return RedirectResponse(url="/admin?exito=Paciente+eliminado+con+exito", status_code=status.HTTP_303_SEE_OTHER)
        else:
            return RedirectResponse(url="/admin?error=No+se+encontro+el+paciente", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Error al eliminar paciente {paciente_id}: {e}")
        referer = request.headers.get("referer")
        if referer and "/admin" not in referer:
            from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
            parsed_url = urlparse(referer)
            query_params = parse_qs(parsed_url.query)
            query_params["error"] = [f"Error interno al eliminar: {str(e)}"]
            new_query = urlencode(query_params, doseq=True)
            new_url = urlunparse((parsed_url.scheme, parsed_url.netloc, parsed_url.path, parsed_url.params, new_query, parsed_url.fragment))
            return RedirectResponse(url=new_url, status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url=f"/admin?error=Error+interno+al+eliminar+{urllib.parse.quote(str(e))}", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/admin/auto-limpiar-duplicados")
async def post_auto_limpiar_duplicados(
    request: Request,
    username: str = Depends(auth.get_current_admin)
):
    db = database.get_db()
    deleted_total = 0
    try:
        # 1. Limpiar por cédula (mantener el más reciente)
        pipeline_ced = [
            {"$match": {"identificacion.numero": {"$ne": None, "$ne": ""}}},
            {"$group": {
                "_id": "$identificacion.numero",
                "ids": {"$push": "$_id"},
                "fechas": {"$push": "$fecha_ingreso"},
                "count": {"$sum": 1}
            }},
            {"$match": {"count": {"$gt": 1}}}
        ]
        
        async for dup in db.pacientes.aggregate(pipeline_ced):
            combined = list(zip(dup["ids"], dup["fechas"]))
            combined.sort(key=lambda x: x[1] if x[1] else datetime.min.replace(tzinfo=timezone.utc), reverse=True)
            to_delete = [c[0] for c in combined[1:]]
            res = await db.pacientes.delete_many({"_id": {"$in": to_delete}})
            deleted_total += res.deleted_count
            
        # 2. Limpiar por nombre (sin cédula)
        pipeline_nom = [
            {"$match": {"$or": [{"identificacion": None}, {"identificacion.numero": None}, {"identificacion.numero": ""}]}},
            {"$group": {
                "_id": {
                    "nombres": {"$toLower": "$nombres"},
                    "apellidos": {"$toLower": "$apellidos"}
                },
                "ids": {"$push": "$_id"},
                "fechas": {"$push": "$fecha_ingreso"},
                "count": {"$sum": 1}
            }},
            {"$match": {"count": {"$gt": 1}}}
        ]
        
        async for dup in db.pacientes.aggregate(pipeline_nom):
            combined = list(zip(dup["ids"], dup["fechas"]))
            combined.sort(key=lambda x: x[1] if x[1] else datetime.min.replace(tzinfo=timezone.utc), reverse=True)
            to_delete = [c[0] for c in combined[1:]]
            res = await db.pacientes.delete_many({"_id": {"$in": to_delete}})
            deleted_total += res.deleted_count

        logger.info(f"Limpieza de duplicados completada por {username}: {deleted_total} eliminados.")
        return RedirectResponse(url=f"/admin?exito=Se+eliminaron+exitosamente+{deleted_total}+registros+duplicados.", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Error en auto-limpieza de duplicados: {e}")
        return RedirectResponse(url=f"/admin?error=Error+interno+al+limpiar+duplicados", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/admin/acciones-masivas")
async def post_acciones_masivas(
    request: Request,
    accion: str = Form(...),
    hosp_origen: str = Form(None),
    hosp_destino: str = Form(None),
    hosp_estado: str = Form(None),
    nuevo_estado: str = Form(None),
    username: str = Depends(auth.get_current_admin)
):
    import urllib.parse
    db = database.get_db()
    try:
        if accion == "reasignar_hospital":
            if not hosp_origen or not hosp_destino:
                return RedirectResponse(url="/admin?error=Debe+especificar+hospital+origen+y+destino", status_code=status.HTTP_303_SEE_OTHER)
            res = await db.pacientes.update_many(
                {"ubicacion.hospital": hosp_origen},
                {"$set": {"ubicacion.hospital": hosp_destino}}
            )
            exito_msg = f"Se reasignaron {res.modified_count} pacientes de '{hosp_origen}' a '{hosp_destino}'."
            logger.info(f"Reasignación masiva por {username}: {exito_msg}")
            return RedirectResponse(url=f"/admin?exito={urllib.parse.quote(exito_msg)}", status_code=status.HTTP_303_SEE_OTHER)
            
        elif accion == "cambiar_estado":
            if not hosp_estado or not nuevo_estado:
                return RedirectResponse(url="/admin?error=Debe+especificar+hospital+y+nuevo+estado", status_code=status.HTTP_303_SEE_OTHER)
            res = await db.pacientes.update_many(
                {"ubicacion.hospital": hosp_estado},
                {"$set": {"estado_salud": nuevo_estado}}
            )
            exito_msg = f"Se actualizo el estado de {res.modified_count} pacientes en '{hosp_estado}' a '{nuevo_estado}'."
            logger.info(f"Cambio masivo de estado por {username}: {exito_msg}")
            return RedirectResponse(url=f"/admin?exito={urllib.parse.quote(exito_msg)}", status_code=status.HTTP_303_SEE_OTHER)
            
        elif accion == "vaciar_bdd":
            res = await db.pacientes.delete_many({})
            exito_msg = f"Base de datos vaciada con exito. Se eliminaron {res.deleted_count} registros."
            logger.info(f"Base de datos vaciada por {username}.")
            return RedirectResponse(url=f"/admin?exito={urllib.parse.quote(exito_msg)}", status_code=status.HTTP_303_SEE_OTHER)
            
        else:
            return RedirectResponse(url="/admin?error=Accion+masiva+no+reconocida", status_code=status.HTTP_303_SEE_OTHER)
            
    except Exception as e:
        logger.error(f"Error al realizar accion masiva: {e}")
        return RedirectResponse(url=f"/admin?error=Error+interno+al+procesar+accion+masiva", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/admin/cargar-masiva")
async def post_cargar_masiva(
    request: Request,
    file: UploadFile = File(...),
    username: str = Depends(auth.get_current_admin)
):
    db = database.get_db()
    exito_msg = None
    errores_list = None
    rejected_count = 0
    
    try:
        # Leer los bytes del archivo subido
        file_bytes = await file.read()
        filename = file.filename
        
        # Procesar con el excel service
        registros, errores_list = await excel_service.procesar_archivo(file_bytes, filename)
        
        if errores_list:
            rejected_count = sum(1 for err in errores_list if err.get("fila", 0) > 0)
            
        inserted_count = 0
        if registros:
            # Operación atómica de inserción por lotes
            result = await db.pacientes.insert_many(registros)
            inserted_count = len(result.inserted_ids)
            exito_msg = f"Se cargaron exitosamente {inserted_count} registros."
            if rejected_count > 0:
                exito_msg += f" Se rechazaron {rejected_count} registros."
            logger.info(f"Carga masiva: {inserted_count} registros insertados, {rejected_count} registros rechazados por {username}.")
        elif rejected_count > 0:
            logger.info(f"Carga masiva: 0 registros insertados, {rejected_count} registros rechazados por {username}.")
        
        if not registros and not errores_list:
            # Archivo vacío
            errores_list = [{"fila": 0, "error": "El archivo no contiene filas procesables."}]
            
    except Exception as e:
        logger.error(f"Error procesando carga masiva: {e}")
        errores_list = [{"fila": 0, "error": f"Error interno del servidor al procesar el archivo: {str(e)}"}]
        
    stats = await obtener_datos_admin()
    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "username": username,
            "exito": exito_msg,
            "errores": errores_list,
            "rejected_count": rejected_count,
            "autenticado": True,
            **stats
        }
    )

@app.get("/admin/descargar-datos")
async def get_descargar_datos(
    username: str = Depends(auth.get_current_admin)
):
    import json
    from fastapi.responses import StreamingResponse
    from bson import json_util
    import io
    from datetime import datetime
    
    db = database.get_db()
    try:
        # Obtener todos los registros de pacientes ordenados por fecha de ingreso
        cursor = db.pacientes.find({}).sort("fecha_ingreso", -1)
        pacientes = await cursor.to_list(length=None)
        
        # Serializar usando json_util de bson para manejar ObjectIds y fechas
        data_str = json_util.dumps(pacientes, indent=2, ensure_ascii=False)
        
        # Crear un archivo en memoria
        bio = io.BytesIO(data_str.encode("utf-8"))
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"esperanza_backup_{timestamp}.json"
        
        logger.info(f"Base de datos exportada y descargada por {username}.")
        return StreamingResponse(
            bio,
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        logger.error(f"Error al descargar la base de datos: {e}")
        return RedirectResponse(url=f"/admin?error=Error+al+descargar+la+base+de+datos", status_code=status.HTTP_303_SEE_OTHER)
