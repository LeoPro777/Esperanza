# 6. CATEGORÍA: Contratos de Integración y API

## 6.1. Especificación de Endpoints Administrativos

* **Ruta:** `/api/admin/cargar-masiva`
* **Método:** `POST`
* **Content-Type:** `multipart/form-data`

## 6.2. Contrato de Entrada (Estructura interna esperada del binario Excel/CSV)

El archivo binario adjunto bajo la llave `file` debe poseer una estructura tabular plana con las siguientes cabeceras textuales en la primera fila (Fila 0):

```text
nombres, apellidos, cedula, edad, estado_salud, hospital, piso_ala, observaciones
```

## 6.3. Contrato de Salida Exitosa

* **Código HTTP:** `200 OK`
* **Payload JSON:**

```json
{
  "status": "Éxito",
  "registros_cargados": 412,
  "mensaje": "Se han añadido 412 personas al listado de Caracas."
}
```

## 6.4. Catálogo de Errores Estándar

* **Error 400 Bad Request (Archivo Inválido):**

```json
{
  "detail": "Formato inválido. Debe ser Excel (.xlsx) o CSV."
}
```

* **Error 400 Bad Request (Estructura de Excel Rota):**

```json
{
  "detail": "Falta la columna mandatoria: 'hospital'"
}
```

* **Error 401 Unauthorized (Sesión inválida o expirada):**

```json
{
  "detail": "No autorizado. Token de sesión inválido o ausente."
}
```
