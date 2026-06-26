# 4. CATEGORÍA: Modelo y Estado de Datos

## 4.1. Motor de Base de Datos

* **Motor:** MongoDB Atlas (Instancia compartida en la nube, capa M0).
* **Estrategia de Acceso:** Motor de IO asíncrono para Python (`motor`).

## 4.2. Esquema Detallado (Colección: `pacientes`)

* `_id`: `ObjectId` (Nativo de Mongo, Clave Primaria).
* `nombres`: `String` (Strict, Requerido).
* `apellidos`: `String` (Strict, Requerido).
* `identificacion`: `Document` (Nullable)
  * `tipo`: `String` (Valores válidos: "V", "E", "P" o Null).
  * `numero`: `String` (Indexado, Nullable).
* `edad`: `Int` (Min: 0, Max: 120, Nullable).
* `estado_salud`: `String` (Strict, enum implícito: `Estable`, `Crítico`, `Reservado`, `De Alta`, `Fallecido`).
* `ubicacion`: `Document` (Strict)
  * `hospital`: `String` (Requerido, ej: "Hospital Pérez Carreño").
  * `piso_ala`: `String` (Default: "No especificado").
  * `ciudad`: `String` (Fixed: "Caracas").
* `observaciones`: `String` (Nullable, Max: 500 caracteres).
* `fecha_ingreso`: `DateTime` (Default: UTC Now).

## 4.3. Restricciones e Índices Estrictos

* **Índice de Texto Compuesto:** `BuscadorMultiparametroIndex` conformado por:
  * `nombres` (Peso: 3)
  * `apellidos` (Peso: 5)
  * `identificacion.numero` (Peso: 10)

* **Índice Simple:** `{"edad": 1}` para acelerar búsquedas numéricas directas en paralelo al índice de texto.

## 4.4. Seeders (Datos Iniciales)

Al ser una base de datos orientada a documentos dinámica, no requiere seeders estructurales de tablas de catálogos. El único dato requerido por defecto se gestiona a nivel de infraestructura para el control de acceso del único operador (ver Sección 5).
