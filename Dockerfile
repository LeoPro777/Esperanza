# Imagen base ligera de Python 3.10
FROM python:3.10-slim

# Configurar variables de entorno de Python
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Instalar dependencias primero para optimizar el cacheo de capas
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código del monolito ligero y sus recursos estáticos/plantillas
COPY src/ /app/src/
COPY templates/ /app/templates/
COPY static/ /app/static/

# Exponer el puerto estándar
EXPOSE 8000

# Ejecutar el servidor con Uvicorn escuchando en todas las interfaces de red
# Render inyecta la variable de entorno $PORT dinámicamente
CMD uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}
