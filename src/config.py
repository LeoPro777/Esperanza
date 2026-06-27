import os
from dotenv import load_dotenv

# Cargar variables desde el archivo .env si existe
load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/esperanza")
JWT_SECRET = os.getenv("JWT_SECRET", "default_secret_key_change_me_in_production")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
PORT = int(os.getenv("PORT", "8000"))
