import io
from datetime import datetime, timezone
import csv
import openpyxl
import logging
from typing import List, Dict, Tuple, Any
from src import database

logger = logging.getLogger(__name__)

# Estados válidos
ESTADOS_VALIDOS = ["Estable", "Crítico", "Reservado", "De Alta", "Fallecido"]

def normalize_estado_salud(val: Any) -> str | None:
    """Normaliza y valida el estado de salud, manejando acentos y mayúsculas/minúsculas."""
    if val is None:
        return None
    val_str = str(val).strip().lower()
    
    if val_str in ["estable"]:
        return "Estable"
    elif val_str in ["critico", "crítico"]:
        return "Crítico"
    elif val_str in ["reservado"]:
        return "Reservado"
    elif val_str in ["de alta", "alta", "de_alta"]:
        return "De Alta"
    elif val_str in ["fallecido", "muerto"]:
        return "Fallecido"
    
    return None

def clean_string(val: Any) -> str | None:
    """Limpia cadenas, convirtiendo NaNs a None y quitando espacios."""
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None

def clean_identificacion_numero(val: Any) -> str | None:
    """Evita que números de cédula se importen como floats, remueve puntuaciones/letras de tipo y valida que sea numérica."""
    if val is None:
        return None
    s = str(val).strip()
    if s.endswith(".0"):
        s = s[:-2]
    # Remover puntos, comas, espacios y guiones usuales
    s_clean = s.replace(".", "").replace(",", "").replace(" ", "").replace("-", "")
    # Remover letra de nacionalidad si existe al inicio (V, E, P)
    if len(s_clean) > 1 and s_clean[0].upper() in ["V", "E", "P"]:
        s_clean = s_clean[1:]
    # Debe ser puramente numérica
    if s_clean.isdigit():
        return s_clean
    return None

def clean_edad(val: Any) -> int | str | None:
    """Limpia el campo de edad y lo retorna como entero o 'invalido' en caso de error."""
    if val is None:
        return None
    if isinstance(val, int):
        return val
    try:
        s = str(val).strip()
        if s.endswith(".0"):
            s = s[:-2]
        return int(s)
    except ValueError:
        return "invalido"

def procesar_csv(file_bytes: bytes) -> Tuple[List[str], List[Dict[str, Any]], str | None]:
    """Procesa un archivo CSV en memoria."""
    try:
        content = file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        try:
            content = file_bytes.decode("latin-1")
        except Exception as e:
            return [], [], f"Error de codificacion: {str(e)}"
            
    f = io.StringIO(content)
    reader = csv.reader(f)
    try:
        rows = list(reader)
    except Exception as e:
        return [], [], f"Error al leer el CSV: {str(e)}"
        
    if not rows:
        return [], [], "El archivo CSV esta vacio."
        
    headers = [str(h).strip().lower() for h in rows[0] if h is not None]
    data_rows = []
    
    for r in rows[1:]:
        if not any(r): # Ignorar filas vacías
            continue
        row_dict = {}
        for idx, h in enumerate(headers):
            val = r[idx] if idx < len(r) else None
            # Convertir string vacío a None
            if val == "":
                val = None
            row_dict[h] = val
        data_rows.append(row_dict)
        
    return headers, data_rows, None

def procesar_xlsx(file_bytes: bytes) -> Tuple[List[str], List[Dict[str, Any]], str | None]:
    """Procesa un archivo Excel moderno (.xlsx) en memoria usando openpyxl en modo de solo lectura."""
    try:
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
        sheet = wb.active
        if not sheet:
            return [], [], "No se encontro hoja activa en el archivo Excel."
            
        rows_generator = sheet.iter_rows(values_only=True)
        try:
            first_row = next(rows_generator)
        except StopIteration:
            return [], [], "El archivo Excel esta vacio."
            
        headers = [str(h).strip().lower() for h in first_row if h is not None]
        data_rows = []
        
        for r in rows_generator:
            if not any(v is not None for v in r):
                continue
            row_dict = {}
            for idx, h in enumerate(headers):
                val = r[idx] if idx < len(r) else None
                if val == "":
                    val = None
                row_dict[h] = val
            data_rows.append(row_dict)
            
        wb.close()
        return headers, data_rows, None
    except Exception as e:
        return [], [], f"Error al leer el archivo Excel: {str(e)}"

def procesar_json(file_bytes: bytes) -> Tuple[List[str], List[Dict[str, Any]], str | None]:
    """Procesa un archivo JSON en memoria."""
    import json
    try:
        content = file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        try:
            content = file_bytes.decode("latin-1")
        except Exception as e:
            return [], [], f"Error de codificacion: {str(e)}"
            
    try:
        data = json.loads(content)
    except Exception as e:
        return [], [], f"Error al parsear el JSON: {str(e)}"
        
    if not isinstance(data, list):
        return [], [], "El archivo JSON debe contener una lista de objetos."
        
    if not data:
        return [], [], "El archivo JSON esta vacio."
        
    # Obtener todas las claves de los objetos
    headers_set = set()
    for item in data:
        if isinstance(item, dict):
            headers_set.update(item.keys())
            
    headers = [str(h).strip().lower() for h in headers_set]
    
    # Normalizar claves a minúsculas
    data_rows = []
    for item in data:
        if not isinstance(item, dict):
            continue
        row_dict = {}
        for k, v in item.items():
            row_dict[str(k).strip().lower()] = v
        data_rows.append(row_dict)
        
    return headers, data_rows, None

async def procesar_archivo(file_bytes: bytes, filename: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Procesa un archivo binario subido (.xlsx, .xls, .csv o .json).
    Retorna (registros_validos, errores).
    """
    registros_validos: List[Dict[str, Any]] = []
    errores: List[Dict[str, Any]] = []
    pacientes_procesados = set()
    
    # Distinguir formato y leer filas en memoria
    if filename.endswith(".csv"):
        headers, data_rows, error_read = procesar_csv(file_bytes)
    elif filename.endswith((".xlsx", ".xls")):
        headers, data_rows, error_read = procesar_xlsx(file_bytes)
    elif filename.endswith(".json"):
        headers, data_rows, error_read = procesar_json(file_bytes)
    else:
        return [], [{"fila": 0, "error": "Formato de archivo no soportado. Suba un archivo .xlsx, .xls, .csv o .json."}]
        
    if error_read:
        return [], [{"fila": 0, "error": error_read}]
    
    # Mapeo de columnas esperadas
    col_mapping = {
        "nombres": ["nombres", "nombre", "first_name", "name"],
        "apellidos": ["apellidos", "apellido", "last_name", "surname"],
        "tipo_documento": ["tipo_documento", "tipo documento", "identificacion_tipo", "tipo", "doc_tipo"],
        "numero_documento": ["numero_documento", "numero documento", "identificacion_numero", "identificacion numero", "numero", "cedula", "documento", "doc_numero", "doc numero"],
        "edad": ["edad", "age"],
        "estado_salud": ["estado_salud", "estado salud", "estado", "salud", "status"],
        "hospital": ["hospital", "centro_medico", "ubicacion_hospital"],
        "piso_ala": ["piso_ala", "piso ala", "piso", "ala", "seccion"],
        "observaciones": ["observaciones", "observacion", "comentario", "observaciones_salud"]
    }
    
    # Resolver qué encabezado del archivo mapea a qué campo
    resolved_headers = {}
    for key, aliases in col_mapping.items():
        found = False
        for h in headers:
            if h in aliases:
                resolved_headers[key] = h
                found = True
                break
        if not found:
            resolved_headers[key] = None

    # Procesar fila por fila
    for idx, row in enumerate(data_rows):
        num_fila = idx + 2 # Fila 1 es el header
        
        # Extraer valores usando el mapeo resuelto
        raw_nombres = row.get(resolved_headers["nombres"]) if resolved_headers["nombres"] else None
        raw_apellidos = row.get(resolved_headers["apellidos"]) if resolved_headers["apellidos"] else None
        raw_tipo_doc = row.get(resolved_headers["tipo_documento"]) if resolved_headers["tipo_documento"] else None
        raw_num_doc = row.get(resolved_headers["numero_documento"]) if resolved_headers["numero_documento"] else None
        raw_edad = row.get(resolved_headers["edad"]) if resolved_headers["edad"] else None
        raw_estado = row.get(resolved_headers["estado_salud"]) if resolved_headers["estado_salud"] else None
        raw_hospital = row.get(resolved_headers["hospital"]) if resolved_headers["hospital"] else None
        raw_piso_ala = row.get(resolved_headers["piso_ala"]) if resolved_headers["piso_ala"] else None
        raw_observaciones = row.get(resolved_headers["observaciones"]) if resolved_headers["observaciones"] else None

        # Lista de errores para esta fila
        errores_fila = []
        
        # Limpieza de campos
        nombres = clean_string(raw_nombres)
        apellidos = clean_string(raw_apellidos)
        
        tipo_doc = clean_string(raw_tipo_doc)
        if tipo_doc:
            tipo_doc = tipo_doc.upper()
            if tipo_doc not in ["V", "E", "P"]:
                errores_fila.append("El 'tipo_documento' debe ser V, E o P (o estar vacio).")
                
        num_doc = clean_identificacion_numero(raw_num_doc)
        
        # Validar límite de cédula
        if num_doc:
            if num_doc.isdigit():
                if int(num_doc) > 32000000:
                    # Cédula inválida -> Se elimina el campo, NO el registro
                    num_doc = None
                    tipo_doc = None

        # Validar que al menos uno de los tres campos de identidad esté presente
        if not nombres and not apellidos and not num_doc:
            errores_fila.append("El registro debe contener al menos un nombre, apellido o cédula.")
        else:
            # Clave de de-duplicación insensible a acentos/case
            def get_norm_key(s: str) -> str:
                import unicodedata
                if not s:
                    return ""
                return "".join(c for c in unicodedata.normalize('NFD', s.strip()) if unicodedata.category(c) != 'Mn').lower()
            
            dup_key = (get_norm_key(nombres), get_norm_key(apellidos), num_doc)
            
            if dup_key in pacientes_procesados:
                if num_doc:
                    errores_fila.append(f"El paciente '{nombres or ''} {apellidos or ''}' con cédula '{num_doc}' ya existe duplicado en el archivo.")
                else:
                    errores_fila.append(f"El paciente '{nombres or ''} {apellidos or ''}' (sin cédula) ya existe duplicado en el archivo.")
            else:
                pacientes_procesados.add(dup_key)
                db = database.get_db()
                if db is not None:
                    try:
                        import re
                        def clean_accents_regex(s: str) -> str:
                            escaped = re.escape(s)
                            escaped = re.sub(r'[aáAÁ]', '[aáAÁ]', escaped)
                            escaped = re.sub(r'[eéEÉ]', '[eéEÉ]', escaped)
                            escaped = re.sub(r'[iíIÍ]', '[iíIÍ]', escaped)
                            escaped = re.sub(r'[oóOÓ]', '[oóOÓ]', escaped)
                            escaped = re.sub(r'[uúUÚ]', '[uúUÚ]', escaped)
                            return f"^{escaped}$"

                        if num_doc:
                            # Caso 1: Tiene cédula. Coincidencia al máximo (nombres, apellidos y cédula)
                            query_filter = {
                                "identificacion.numero": num_doc
                            }
                            if nombres:
                                query_filter["nombres"] = {"$regex": clean_accents_regex(nombres), "$options": "i"}
                            else:
                                query_filter["nombres"] = {"$in": [None, ""]}
                                
                            if apellidos:
                                query_filter["apellidos"] = {"$regex": clean_accents_regex(apellidos), "$options": "i"}
                            else:
                                query_filter["apellidos"] = {"$in": [None, ""]}
                        else:
                            # Caso 2: Cédula vacía. Coincidencia de nombres y apellidos donde la cédula también está vacía/None
                            query_filter = {
                                "$or": [
                                    {"identificacion": None},
                                    {"identificacion.numero": None},
                                    {"identificacion.numero": ""}
                                ]
                            }
                            if nombres:
                                query_filter["nombres"] = {"$regex": clean_accents_regex(nombres), "$options": "i"}
                            else:
                                query_filter["nombres"] = {"$in": [None, ""]}
                                
                            if apellidos:
                                query_filter["apellidos"] = {"$regex": clean_accents_regex(apellidos), "$options": "i"}
                            else:
                                query_filter["apellidos"] = {"$in": [None, ""]}

                        existente = await db.pacientes.find_one(query_filter)
                        if existente:
                            if num_doc:
                                errores_fila.append(f"El paciente '{nombres or ''} {apellidos or ''}' con cédula '{num_doc}' ya está registrado en el sistema.")
                            else:
                                errores_fila.append(f"El paciente '{nombres or ''} {apellidos or ''}' (sin cédula) ya está registrado en el sistema.")
                    except Exception as e:
                        logger.error(f"Error al verificar duplicado de {nombres} {apellidos} en BD: {e}")
        
        edad = clean_edad(raw_edad)
        if edad == "invalido":
            errores_fila.append("La 'edad' debe ser un numero entero.")
            edad = None
        elif edad is not None:
            if edad < 0 or edad > 120:
                errores_fila.append("La 'edad' debe estar en el rango de 0 a 120.")
                
        # Estado de salud flexible: si está vacío, por defecto debe ser "Reservado"
        estado = None
        if raw_estado is not None and str(raw_estado).strip() != "":
            estado = normalize_estado_salud(raw_estado)
            if not estado:
                errores_fila.append(f"El 'estado_salud' debe ser uno de: {', '.join(ESTADOS_VALIDOS)}.")
        else:
            estado = "Reservado"
            
        hospital = clean_string(raw_hospital)
        if not hospital:
            errores_fila.append("El campo 'hospital' es requerido.")
            
        piso_ala = clean_string(raw_piso_ala)
        observaciones = clean_string(raw_observaciones)
        if observaciones and len(observaciones) > 500:
            observaciones = observaciones[:500]

        # Si hay errores en esta fila, registrarlos y no agregar al listado válido
        if errores_fila:
            nombre_completo_err = f"{nombres or 'Nombre incompleto'} {apellidos or ''}".strip()
            errores.append({
                "fila": num_fila,
                "error": " | ".join(errores_fila),
                "nombre_persona": nombre_completo_err
            })
        else:
            # Crear documento que coincide con el esquema de MongoDB (valores vacíos se guardan como None)
            documento = {
                "nombres": nombres,
                "apellidos": apellidos,
                "identificacion": {
                    "tipo": tipo_doc,
                    "numero": num_doc
                } if (tipo_doc or num_doc) else None,
                "edad": edad,
                "estado_salud": estado,
                "ubicacion": {
                    "hospital": hospital,
                    "piso_ala": piso_ala,
                    "ciudad": "Caracas"
                },
                "observaciones": observaciones,
                "fecha_ingreso": datetime.now(timezone.utc)
            }
            registros_validos.append(documento)
            
    return registros_validos, errores
