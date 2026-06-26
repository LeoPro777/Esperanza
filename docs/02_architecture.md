# 2. CATEGORÍA: Arquitectura y Estructura

## 2.1. Patrón Arquitectónico

Monolito clásico estructurado por responsabilidades (Módulo de Rutas/Controladores, Servicios de Negocio y Plantillas de Presentación en Servidor). No existe separación física de Frontend y Backend, eliminando problemas de CORS y latencia de red en el cliente.

## 2.2. Árbol de Directorios Objetivo

```text
mi-plataforma-crisis/
├── src/
│   ├── __init__.py
│   ├── main.py              # Inicialización de FastAPI y Middlewares
│   ├── database.py          # Cliente Motor / MongoDB Atlas
│   ├── auth.py              # Autenticación administrativa por cookies/tokens
│   ├── config.py            # Gestión de variables de entorno (.env)
│   └── services/
│       ├── __init__.py
│       └── excel_service.py # Lógica de procesamiento de Pandas
├── templates/               # Motor Jinja2 (HTML nativo)
│   ├── buscador.html        # Vista pública indexable
│   ├── admin.html           # Panel de carga masiva
│   └── login.html           # Autenticación administrativa
├── static/                  # Archivos estáticos
│   └── style.css            # Estilos CSS nativos (Modo contingencia)
├── Dockerfile               # Configuración del contenedor único
└── requirements.txt         # Dependencias estrictas del sistema
```

## 2.3. Responsabilidad de Componentes

* `src/main.py`: Maneja las solicitudes HTTP salientes, intercepta los formularios nativos y distribuye la carga a los motores de plantillas.
* `src/services/excel_service.py`: Aísla por completo la lógica de negocio de la librería `pandas` y `openpyxl`. Transforma el binario del archivo subido en diccionarios estructurados listos para MongoDB.
* `templates/`: Exclusivamente maquetación estructural HTML sin lógica de cómputo, consumiendo variables directas inyectadas por Jinja2.

## 2.4. Protocolos y Canales de Comunicación

* **REST HTTP/S:** Uso exclusivo de métodos `GET` para consultas y `POST` para la mutación de estados y envío de formularios/archivos. No se implementan WebSockets ni arquitecturas orientadas a eventos para mitigar el consumo de red del plan gratuito.
