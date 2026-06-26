# 8. CATEGORÍA: Infraestructura, DevOps y Resiliencia

## 8.1. Entornos y Configuración (`.env`)

Variables obligatorias requeridas en la configuración del Web Service en Render:

* `MONGODB_URI`: Cadena de conexión secreta de MongoDB Atlas (`mongodb+srv://...`).
* `JWT_SECRET_KEY`: Frase larga y aleatoria para firmar las cookies administrativas.
* `ADMIN_USER`: Nombre de usuario del operador civil para el login.
* `ADMIN_PASSWORD`: Contraseña cifrada o de alta seguridad para el login del operador.

## 8.2. Containerización / Despliegue

Despliegue automatizado basado en el Dockerfile multi-etapa definido en la sección de arquitectura. Render ejecutará la compilación del entorno de Python aislando las dependencias del sistema operativo y exponiendo el puerto unificado `10000`.

## 8.3. Mecanismo de Logs y Monitoreo

* Uso de la librería nativa `logging` de Python configurada en nivel `INFO`.
* Cada evento de carga masiva debe registrar una línea de log estructurada indicando la fecha, el usuario que realizó la acción y el volumen de registros inyectados.
* Los errores críticos del controlador de base de datos se clasificarán bajo el nivel `ERROR` para su visualización inmediata en el panel de control de Render.

## 8.4. Resiliencia de Red

* **Estrategia de Conexiones a la BD:** Configuración del parámetro `maxPoolSize=10` en el cliente de Motor/MongoDB para garantizar que el backend del monolito jamás intente abrir más conexiones simultáneas que las permitidas por el límite estricto del plan gratuito M0 de Atlas.
* **Timeout:** Configuración de un timeout máximo de conexión a la base de datos de 5000ms, abortando peticiones colgadas de forma segura para no saturar los hilos de procesamiento de Uvicorn.
