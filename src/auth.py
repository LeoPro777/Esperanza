import jwt
from datetime import datetime, timedelta, timezone
from fastapi import Request, HTTPException, status
from src import config

ALGORITHM = "HS256"
COOKIE_NAME = "session_token"

def create_access_token(username: str) -> str:
    """Genera un token JWT con vigencia de 6 horas."""
    expire = datetime.now(timezone.utc) + timedelta(hours=6)
    to_encode = {"sub": username, "exp": expire}
    encoded_jwt = jwt.encode(to_encode, config.JWT_SECRET, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str) -> str | None:
    """Valida el token JWT y retorna el nombre del usuario si es correcto."""
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
        return username
    except jwt.PyJWTError:
        return None

def get_current_admin(request: Request) -> str:
    """Dependency para endpoints de FastAPI que requieren autenticación de operador."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Acceso denegado: No se encontro cookie de sesion."
        )
    username = verify_token(token)
    if not username or username != config.ADMIN_USERNAME:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Acceso denegado: Sesion invalida o expirada."
        )
    return username

def is_authenticated(request: Request) -> bool:
    """Verifica si la sesión del cliente es válida de forma silenciosa (para render de vistas)."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return False
    username = verify_token(token)
    return username == config.ADMIN_USERNAME
