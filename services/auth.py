import bcrypt
from jose import jwt, JWTError
from datetime import datetime, timedelta

# Clave secreta para firmar los tokens (En producción, usa variables de entorno)
SECRET_KEY = "tu_clave_secreta_super_segura_cambiala_luego"
ALGORITHM = "HS256"

def verificar_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica si la contraseña en texto plano coincide con el hash guardado."""
    # bcrypt requiere que los strings se conviertan a bytes (codificación utf-8)
    password_bytes = plain_password.encode('utf-8')
    hash_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_bytes, hash_bytes)

def obtener_password_hash(password: str) -> str:
    """Genera un hash seguro a partir de una contraseña."""
    password_bytes = password.encode('utf-8')
    # Generamos la "sal" (salt) y creamos el hash
    salt = bcrypt.gensalt()
    hashed_bytes = bcrypt.hashpw(password_bytes, salt)
    # Devolvemos el hash como string para guardarlo en la base de datos (SQLite)
    return hashed_bytes.decode('utf-8')

def crear_token_acceso(data: dict, expires_delta: timedelta = None):
    """Genera el token JWT para mantener la sesión del usuario."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta if expires_delta else timedelta(hours=12))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)