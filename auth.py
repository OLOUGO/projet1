# auth.py (version simplifiée - non utilisée dans la version test)
from passlib.context import CryptContext
from datetime import datetime, timedelta
import os

# Ces variables ne sont pas utilisées dans la version test
SECRET_KEY = os.environ.get("SECRET_KEY", "test-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    """Vérifie le mot de passe"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    """Hash le mot de passe"""
    return pwd_context.hash(password)

def authenticate_user(db, email: str, password: str):
    """Authentifie un utilisateur"""
    from models import User
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user

