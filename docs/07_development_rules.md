# 7. CATEGORÍA: Reglas de Desarrollo y Estilo

## 7.1. Stack Tecnológico

* **Lenguaje:** Python 3.11-slim (Imagen base oficial de Docker).
* **Framework Core:** FastAPI versión `>=0.100.0`.
* **Motor de Plantillas:** Jinja2 v3.1.
* **Procesamiento de Archivos:** Pandas v2.0 + Openpyxl v3.1.
* **Driver BD:** Motor (Async MongoDB Driver) v3.3.

## 7.2. Convenciones de Código

* **Backend:** Estricto cumplimiento de `PEP 8`. Nombres de funciones y variables en `snake_case`. Tipado de datos estricto obligatorio mediante Type Hints nativos de Python y modelos de validación con `Pydantic v2`.
* **HTML/CSS:** Etiquetas en minúsculas. Clases CSS estructuradas bajo metodología simplificada, evitando selectores anidados profundos que ralenticen el renderizado en navegadores móviles antiguos.

## 7.3. Estrategia de Manejo de Errores

* Implementación de un bloque `try/except` global en el proceso de lectura de Pandas para evitar que filas con caracteres extraños o celdas corruptas detengan el flujo del contenedor de FastAPI.
* Uso controlado de `FastAPI.HTTPException` para retornar mensajes claros, cortos y descriptivos directamente a la interfaz de administración.

## 7.4. Lista de "Prohibiciones Strict"

* **VETO-01:** Queda totalmente prohibido el uso de CDNs externos para librerías CSS (ej. Bootstrap o Tailwind externo vía URL) en el módulo público; todo el CSS debe ser nativo y servido localmente desde `/static/style.css` o incrustado.
* **VETO-02:** Prohibido realizar consultas de MongoDB sin el uso explícito de operadores asíncronos (`await`).
* **VETO-03:** Prohibido omitir la validación de extensiones de archivo en el backend, confiando en los filtros visuales del navegador del operador.
