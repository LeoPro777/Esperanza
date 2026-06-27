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
    """Evita que números de cédula se importen como floats (ej. 12345.0)."""
    if val is None:
        return None
    s = str(val).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s if s else None

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

async def procesar_archivo(file_bytes: bytes, filename: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Procesa un archivo binario subido (.xlsx, .xls o .csv).
    Retorna (registros_validos, errores).
    """
    registros_validos: List[Dict[str, Any]] = []
    errores: List[Dict[str, Any]] = []
    cedulas_procesadas = set()
    nombres_apellidos_procesados = set()
    
    # Distinguir formato y leer filas en memoria
    if filename.endswith(".csv"):
        headers, data_rows, error_read = procesar_csv(file_bytes)
    elif filename.endswith((".xlsx", ".xls")):
        headers, data_rows, error_read = procesar_xlsx(file_bytes)
    else:
        return [], [{"fila": 0, "error": "Formato de archivo no soportado. Suba un archivo .xlsx, .xls o .csv."}]
        
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
        if not nombres:
            errores_fila.append("El campo 'nombres' es requerido.")
        apellidos = clean_string(raw_apellidos)
        
        tipo_doc = clean_string(raw_tipo_doc)
        if tipo_doc:
            tipo_doc = tipo_doc.upper()
            if tipo_doc not in ["V", "E", "P"]:
                errores_fila.append("El 'tipo_documento' debe ser V, E o P (o estar vacio).")
                
        num_doc = clean_identificacion_numero(raw_num_doc)
        if num_doc:
            if num_doc in cedulas_procesadas:
                errores_fila.append(f"La cédula '{num_doc}' está duplicada en el archivo.")
            else:
                cedulas_procesadas.add(num_doc)
                db = database.get_db()
                if db is not None:
                    try:
                        existente = await db.pacientes.find_one({"identificacion.numero": num_doc})
                        if existente:
                            errores_fila.append(f"La cédula '{num_doc}' ya está registrada en el sistema.")
                    except Exception as e:
                        logger.error(f"Error al verificar duplicado de cédula {num_doc} en BD: {e}")
        elif nombres and apellidos:
            # Si no tiene cédula, comprobar si ya existe por nombres y apellidos (con insensibilidad de acentos)
            import re
            def clean_accents_regex(s: str) -> str:
                escaped = re.escape(s)
                escaped = re.sub(r'[aáAÁ]', '[aáAÁ]', escaped)
                escaped = re.sub(r'[eéEÉ]', '[eéEÉ]', escaped)
                escaped = re.sub(r'[iíIÍ]', '[iíIÍ]', escaped)
                escaped = re.sub(r'[oóOÓ]', '[oóOÓ]', escaped)
                escaped = re.sub(r'[uúUÚ]', '[uúUÚ]', escaped)
                return f"^{escaped}$"

            # Clave de normalización simple sin acentos para la caché del archivo
            def remove_accents(s: str) -> str:
                import unicodedata
                return "".join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')

            name_key = f"{remove_accents(nombres).lower()}|{remove_accents(apellidos).lower()}"
            if name_key in nombres_apellidos_procesados:
                errores_fila.append(f"El paciente '{nombres} {apellidos}' está duplicado en el archivo.")
            else:
                nombres_apellidos_procesados.add(name_key)
                db = database.get_db()
                if db is not None:
                    try:
                        existente = await db.pacientes.find_one({
                            "nombres": {"$regex": clean_accents_regex(nombres), "$options": "i"},
                            "apellidos": {"$regex": clean_accents_regex(apellidos), "$options": "i"},
                            "$or": [
                                {"identificacion": None},
                                {"identificacion.numero": None}
                            ]
                        })
                        if existente:
                            errores_fila.append(f"El paciente '{nombres} {apellidos}' ya está registrado en el sistema.")
                    except Exception as e:
                        logger.error(f"Error al verificar duplicado por nombre en BD: {e}")
        
        edad = clean_edad(raw_edad)
        if edad == "invalido":
            errores_fila.append("La 'edad' debe ser un numero entero.")
            edad = None
        elif edad is not None:
            if edad < 0 or edad > 120:
                errores_fila.append("La 'edad' debe estar en el rango de 0 a 120.")
                
        # Estado de salud flexible: si está vacío no da error. Si se proporciona, se valida.
        estado = None
        if raw_estado is not None and str(raw_estado).strip() != "":
            estado = normalize_estado_salud(raw_estado)
            if not estado:
                errores_fila.append(f"El 'estado_salud' debe ser uno de: {', '.join(ESTADOS_VALIDOS)}.")
            
        hospital = clean_string(raw_hospital)
            
        piso_ala = clean_string(raw_piso_ala) or "No especificado"
        observaciones = clean_string(raw_observaciones)
        if observaciones and len(observaciones) > 500:
            observaciones = observaciones[:500]

        # Si hay errores en esta fila, registrarlos y no agregar al listado válido
        if errores_fila:
            errores.append({
                "fila": num_fila,
                "error": " | ".join(errores_fila),
                "nombre_persona": f"{nombres or 'Nombre incompleto'} {apellidos or ''}".strip()
            })
        else:
            # Crear documento que coincide con el esquema de MongoDB
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
