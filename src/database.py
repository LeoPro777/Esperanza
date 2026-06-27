import logging
from motor.motor_asyncio import AsyncIOMotorClient
from src import config

logger = logging.getLogger(__name__)

# Instancias globales de base de datos
client = None
db = None

def get_db():
    return db

async def init_db():
    global client, db
    logger.info("Conectando a MongoDB...")
    client = AsyncIOMotorClient(config.MONGODB_URI)
    
    # Extraer el nombre de la base de datos de la URI, por defecto 'esperanza'
    db_name = "esperanza"
    try:
        # Separar por '/'
        parts = config.MONGODB_URI.split("/")
        if len(parts) > 3:
            potential_db = parts[3].split("?")[0]
            if potential_db:
                db_name = potential_db
    except Exception:
        pass
        
    db = client[db_name]
    logger.info(f"Base de datos configurada: {db_name}")
    
    # Configuración de índices requeridos
    try:
        # 1. Índice de Texto Compuesto: BuscadorMultiparametroIndex
        # nombres (Peso: 3), apellidos (Peso: 5), identificacion.numero (Peso: 10)
        index_name = "BuscadorMultiparametroIndex"
        await db.pacientes.create_index(
            [
                ("nombres", "text"),
                ("apellidos", "text"),
                ("identificacion.numero", "text")
            ],
            weights={
                "nombres": 3,
                "apellidos": 5,
                "identificacion.numero": 10
            },
            name=index_name
        )
        logger.info(f"Índice de texto compuesto '{index_name}' creado/verificado.")
        
        # 2. Índice Simple: {"edad": 1}
        await db.pacientes.create_index(
            [("edad", 1)],
            name="edad_index"
        )
        logger.info("Índice simple 'edad_index' creado/verificado.")
    except Exception as e:
        logger.error(f"Error al verificar/crear índices en MongoDB: {e}")

async def close_db():
    global client
    if client:
        client.close()
        logger.info("Conexión a MongoDB cerrada de manera ordenada.")
