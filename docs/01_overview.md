# 1. CATEGORÍA: Visión General y Alcance

## 1.1. Propósito del Sistema

El sistema nace como respuesta directa a la contingencia del sismo en Caracas, resolviendo el vacío de información en tiempo real sobre la localización, estado de salud y centros de reclusión/atención de las víctimas. El objetivo principal es ofrecer una plataforma web de consulta pública ultra-ligera, resiliente e indexable por motores de búsqueda, con un panel administrativo simplificado de carga masiva en lote para que un operador civil actualice centralizadamente los datos recolectados.

## 1.2. Alcance del Proyecto

* **Dentro del Alcance (In Scope):**
  * Módulo público de consulta optimizado para redes móviles saturadas (HTML/CSS nativo renderizado en servidor).
  * Buscador multiparámetro (Nombre, Apellido, Cédula, Edad) con lógica de coincidencia en backend.
  * Módulo administrativo protegido para carga masiva mediante archivos de Excel (`.xlsx`, `.xls`) y `.csv`.
  * Soporte explícito para el estado "Fallecido" con tratamiento visual e informativo diferenciado.
  * Despliegue unificado en un único contenedor monolítico dentro de la infraestructura de Render.

* **Fuera del Alcance (Out of Scope):**
  * Registro abierto de usuarios públicos o crowdsourcing directo de datos (para evitar noticias falsas).
  * Pasarelas de donaciones, mapas interactivos pesados en tiempo real o geolocalización por GPS en el cliente.
  * Aplicaciones móviles nativas (Android/iOS).

## 1.3. Reglas de Negocio Globales

* **RN-01 (Cero Dependencias en el Cliente):** El módulo público no debe requerir frameworks de JavaScript (React, Vue, Angular) en el cliente para renderizar datos; todo el HTML final se genera en el servidor para garantizar la carga en conexiones con baja cobertura móvil (3G/Edge).
* **RN-02 (Inserción Optimizada):** Toda actualización masiva proveniente de Excel debe ejecutarse de forma atómica en bloques (`insert_many`) para no saturar las conexiones limitadas de la base de datos.
* **RN-03 (Protección de Integridad):** Ninguna consulta pública puede mutar el estado de la base de datos; la escritura está estrictamente restringida a la sesión administrativa verificada.

## 1.4. Glosario de Términos

* **Monolito Ligero:** Aplicación de un solo contenedor donde el servidor de backend (FastAPI) también actúa como servidor de interfaz enviando documentos HTML estáticos prerenderizados.
* **Estado de Salud:** Clasificación estricta de la condición de la persona, limitada a: *Estable, Crítico, Reservado, De Alta* y *Fallecido*.
* **Carga en Lote (Bulk Insert):** Técnica de persistencia de datos que envía múltiples registros en una sola operación de red a la base de datos, optimizando el uso de la CPU y las conexiones concurrentes.
* **Debounce:** Técnica de desarrollo que retrasa la ejecución de una petición HTTP hasta que el usuario deja de escribir por un tiempo determinado (ej. 500ms).
