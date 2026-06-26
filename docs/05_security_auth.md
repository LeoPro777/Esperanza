# 5. CATEGORÍA: Seguridad, Autenticación y Sesiones

## 5.1. Estrategia de Autenticación

Autenticación basada en proveedor local simplificado. No se almacenan credenciales administrativas en colecciones de la base de datos para evitar vectores de ataque o retrasos en la configuración. Las credenciales maestras se inyectan directamente en las variables de entorno del contenedor de Render.

## 5.2. Ciclo de Vida de la Sesión

* **Tipo de Token:** Token JWT firmado con algoritmo `HS256`.
* **Persistencia:** Almacenado en el cliente mediante una Cookie HTTP-Only con banderas de seguridad activas (`Secure=True`, `SameSite=Strict`).
* **Expiración:** El token tiene un tiempo de vida corto y estricto de **6 horas** continuas desde el inicio de sesión del operador civil, forzando la re-autenticación automática por seguridad.

## 5.3. Modelo de Autorización (Matriz RBAC Simplificada)

| Endpoint / Ruta | Método HTTP | Rol: Público (Anónimo) | Rol: Admin (Operador) |
| --- | --- | --- | --- |
| `/` (Buscador) | `GET` | **PERMITIDO** | **PERMITIDO** |
| `/static/*` | `GET` | **PERMITIDO** | **PERMITIDO** |
| `/admin` (Panel) | `GET` | DENEGADO (Redirige a /login) | **PERMITIDO** |
| `/api/admin/cargar-masiva` | `POST` | DENEGADO (401 Unauthorized) | **PERMITIDO** |
