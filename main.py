from fastapi import FastAPI, Request, Depends
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta
import models
import sys
import subprocess
import os

# ============================================
# DIAGNOSTIC
# ============================================
print("🔍 VÉRIFICATION DES PACKAGES INSTALLÉS")
print("=" * 50)

try:
    import jinja2
    print(f"✅ jinja2 est installé (version: {jinja2.__version__})")
except ImportError:
    print("❌ jinja2 N'EST PAS installé")

try:
    import psycopg2
    print(f"✅ psycopg2 est installé")
except ImportError:
    print("❌ psycopg2 N'EST PAS installé")

print("\n📦 Liste complète des packages:")
result = subprocess.run(['pip', 'freeze'], capture_output=True, text=True)
print(result.stdout)
print("=" * 50)

# ============================================
# CONFIGURATION BASE DE DONNÉES
# ============================================
DATABASE_URL = os.environ.get('DATABASE_URL', None)

if DATABASE_URL is None:
    # URL de votre base Render
    DATABASE_URL = "postgresql://agrisuivi_admin:7w4TAfaflBx84orEne0tiMuqFCqy72lq@dpg-d6gtcd9drdic73cd8n30-a.frankfurt-postgres.render.com/agrisuivi_production?sslmode=require"
    print("⚠️  Utilisation de l'URL en dur")

if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

if 'sslmode' not in DATABASE_URL:
    if '?' in DATABASE_URL:
        DATABASE_URL += '&sslmode=require'
    else:
        DATABASE_URL += '?sslmode=require'

# Création du moteur
engine = create_engine(DATABASE_URL, pool_size=5, max_overflow=10, echo=True)

# Session locale
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Fonction get_db
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Test de connexion
try:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    print("✅ Connexion à PostgreSQL réussie")
except Exception as e:
    print(f"❌ Erreur de connexion: {e}")

# Création des tables
print("🔄 Création/vérification des tables...")
models.Base.metadata.create_all(bind=engine)
print("✅ Tables créées/vérifiées")

# ============================================
# INITIALISATION FASTAPI
# ============================================
app = FastAPI(title="AgriSuivi Bénin (Mode Test)")
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# ============================================
# FONCTIONS SIMPLIFIÉES
# ============================================
def verify_password_simple(plain_password, hashed_password):
    """Version simple sans JWT"""
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    return pwd_context.verify(plain_password, hashed_password)

# ============================================
# ROUTES D'AUTHENTIFICATION SIMPLIFIÉES
# ============================================

@app.get("/")
async def home(request: Request, db: Session = Depends(get_db)):
    """Page d'accueil simplifiée"""
    user_email = request.cookies.get("user_email")
    
    if not user_email:
        print("Home - Pas d'utilisateur, redirection vers login")
        return RedirectResponse(url="/login", status_code=303)
    
    user = db.query(models.User).filter(models.User.email == user_email).first()
    
    if not user:
        print("Home - Utilisateur non trouvé, redirection vers login")
        return RedirectResponse(url="/login", status_code=303)
    
    print(f"Home - Utilisateur connecté: {user.username}")
    
    return templates.TemplateResponse(
        "base.html",
        {"request": request, "user": user}
    )

@app.get("/login")
async def login_form(request: Request):
    """Formulaire de connexion"""
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/token")
async def login(request: Request, db: Session = Depends(get_db)):
    """Connexion simplifiée SANS JWT"""
    try:
        form = await request.form()
        email = form.get('email')
        password = form.get('password')
        
        print(f"🔍 Tentative de connexion: {email}")
        
        if not email or not password:
            return templates.TemplateResponse(
                "login.html",
                {"request": request, "error": "Email et mot de passe requis"}
            )
        
        # Chercher l'utilisateur
        user = db.query(models.User).filter(models.User.email == email).first()
        
        if not user:
            print(f"❌ Utilisateur non trouvé: {email}")
            return templates.TemplateResponse(
                "login.html",
                {"request": request, "error": "Email ou mot de passe incorrect"}
            )
        
        # Vérifier le mot de passe
        if not verify_password_simple(password, user.hashed_password):
            print(f"❌ Mot de passe incorrect pour: {email}")
            return templates.TemplateResponse(
                "login.html",
                {"request": request, "error": "Email ou mot de passe incorrect"}
            )
        
        print(f"✅ Connexion réussie pour: {email}")
        
        # Connexion réussie - on met l'email dans un cookie simple
        response = RedirectResponse(url="/dashboard", status_code=303)
        
        response.set_cookie(
            key="user_email",
            value=email,
            max_age=3600,  # 1 heure
            httponly=True,
            secure=True,   # Pour Render (HTTPS)
            samesite="lax"
        )
        
        return response
        
    except Exception as e:
        print(f"❌ Erreur dans login: {e}")
        import traceback
        traceback.print_exc()
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": f"Erreur: {str(e)}"}
        )

@app.get("/register")
async def register_form(request: Request):
    """Formulaire d'inscription"""
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register")
async def register(request: Request, db: Session = Depends(get_db)):
    """Inscription simplifiée"""
    try:
        form = await request.form()
        username = form.get('username')
        email = form.get('email')
        password = form.get('password')
        confirm_password = form.get('confirm_password')
        
        # Validations simples
        errors = []
        
        if not username or len(username) < 3:
            errors.append("Nom d'utilisateur trop court (min 3 caractères)")
        
        if not email or '@' not in email:
            errors.append("Email invalide")
        
        if not password or len(password) < 6:
            errors.append("Mot de passe trop court (min 6 caractères)")
        
        if password != confirm_password:
            errors.append("Les mots de passe ne correspondent pas")
        
        # Vérifier si l'email existe déjà
        existing_user = db.query(models.User).filter(models.User.email == email).first()
        if existing_user:
            errors.append("Cet email est déjà utilisé")
        
        if errors:
            return templates.TemplateResponse(
                "register.html",
                {"request": request, "error": errors[0]}
            )
        
        # Créer le mot de passe hashé
        from passlib.context import CryptContext
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        hashed_password = pwd_context.hash(password)
        
        # Créer l'utilisateur
        new_user = models.User(
            username=username,
            email=email,
            hashed_password=hashed_password,
            is_active=True,
            is_admin=False
        )
        
        db.add(new_user)
        db.commit()
        
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "success": "Inscription réussie ! Vous pouvez vous connecter."}
        )
        
    except Exception as e:
        print(f"❌ Erreur inscription: {e}")
        db.rollback()
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": f"Erreur: {str(e)}"}
        )

@app.get("/logout")
async def logout():
    """Déconnexion"""
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("user_email")
    return response

# ============================================
# ROUTES DE DIAGNOSTIC
# ============================================

@app.get("/debug-auth")
async def debug_auth(request: Request):
    """Voir l'état de l'authentification"""
    user_email = request.cookies.get("user_email")
    return {
        "cookies": dict(request.cookies),
        "user_email": user_email,
        "has_user_cookie": user_email is not None
    }

@app.get("/check-users")
async def check_users(db: Session = Depends(get_db)):
    """Voir les utilisateurs dans la base"""
    users = db.query(models.User).all()
    return {
        "count": len(users),
        "users": [
            {"id": u.id, "username": u.username, "email": u.email}
            for u in users
        ]
    }

@app.get("/health")
async def health():
    return {"status": "ok", "message": "Server is running"}

# ============================================
# VOS ROUTES EXISTANTES (PRODUITS, ZONES, ETC.)
# ============================================
# ... (gardez tout votre code existant pour products, zones, stocks, prices)
# MAIS modifiez-les pour utiliser le cookie user_email au lieu du token

# Exemple pour /products (à adapter pour toutes vos routes)
@app.get("/products")
async def list_products(request: Request, db: Session = Depends(get_db)):
    """Liste des produits (version adaptée)"""
    user_email = request.cookies.get("user_email")
    
    if not user_email:
        return RedirectResponse(url="/login", status_code=303)
    
    user = db.query(models.User).filter(models.User.email == user_email).first()
    
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    products = db.query(models.Product).all()
    return templates.TemplateResponse(
        "products/list.html",
        {"request": request, "products": products, "user": user}
    )

# ============================================
# DASHBOARD
# ============================================
@app.get("/dashboard")
async def dashboard(request: Request, db: Session = Depends(get_db)):
    """Dashboard (version adaptée)"""
    user_email = request.cookies.get("user_email")
    
    if not user_email:
        return RedirectResponse(url="/login", status_code=303)
    
    user = db.query(models.User).filter(models.User.email == user_email).first()
    
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    from sqlalchemy import func
    
    # Statistiques
    stats = {
        "products_count": db.query(models.Product).count(),
        "zones_count": db.query(models.Zone).count(),
        "stocks_count": db.query(models.Stock).count(),
        "prices_count": db.query(models.Price).count()
    }
    
    # Données pour graphiques
    categories = db.query(
        models.Product.category, 
        func.count(models.Product.id)
    ).group_by(models.Product.category).all()
    
    category_labels = [c[0] for c in categories] if categories else []
    category_data = [c[1] for c in categories] if categories else []
    
    # Derniers prix et stocks
    latest_prices = db.query(models.Price).order_by(models.Price.date.desc()).limit(5).all()
    latest_stocks = db.query(models.Stock).order_by(models.Stock.date.desc()).limit(5).all()
    
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "stats": stats,
            "category_labels": category_labels,
            "category_data": category_data,
            "latest_prices": latest_prices,
            "latest_stocks": latest_stocks
        }
    )

# ============================================
# POINT D'ENTRÉE
# ============================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)