from fastapi import FastAPI, Request, Depends, status, HTTPException 
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.utils import get_openapi
from fastapi.responses import RedirectResponse
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from jose import jwt
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from datetime import timedelta, datetime
import models
from auth import get_current_active_user
import sys
import subprocess
import os

# ============================================
# PARTIE 1: DIAGNOSTIC (à garder temporairement)
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
# PARTIE 2: IMPORTS DE VOS MODULES
# ============================================
from auth import (
    authenticate_user, create_access_token, get_current_active_user,
    get_password_hash, ACCESS_TOKEN_EXPIRE_MINUTES, SECRET_KEY, ALGORITHM
)

# ============================================
# PARTIE 3: CONFIGURATION POSTGRESQL
# ============================================

# Récupérer l'URL depuis les variables d'environnement Render
DATABASE_URL = os.environ.get('DATABASE_URL', None)

if DATABASE_URL is None:
    # 🔴 REMPLACEZ CETTE LIGNE PAR VOTRE VRAIE URL POSTGRESQL
    DATABASE_URL = "postgresql://agrisuivi_admin:7w4TAfaflBx84orEne0tiMuqFCqy72lq@dpg-d6gtcd9drdic73cd8n30-a.frankfurt-postgres.render.com/agrisuivi_production"
    print("⚠️  UTILISATION DE L'URL EN DUR - POUR TEST LOCAL SEULEMENT")
else:
    print("✅ Variable DATABASE_URL trouvée dans l'environnement")

# Correction pour les URLs qui commencent par postgres://
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    print("🔄 URL convertie")

# Ajouter sslmode=require si nécessaire (obligatoire sur Render)
if 'sslmode' not in DATABASE_URL:
    if '?' in DATABASE_URL:
        DATABASE_URL += '&sslmode=require'
    else:
        DATABASE_URL += '?sslmode=require'
    print("🔒 Ajout de sslmode=require")

# Création du moteur SQLAlchemy pour PostgreSQL
engine = create_engine(
    DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    echo=True  # Met à False en production
)

# Création de la session locale
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Fonction get_db pour les dépendances
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
    print("✅ Connexion à PostgreSQL (agrisuivi-db) réussie !")
except Exception as e:
    print(f"❌ Erreur de connexion: {e}")

# ============================================
# PARTIE 4: CRÉATION DES TABLES
# ============================================
print("🔄 Création/vérification des tables...")
models.Base.metadata.create_all(bind=engine)
print("✅ Tables créées/vérifiées")

# ============================================
# PARTIE 5: INITIALISATION FASTAPI
# ============================================
app = FastAPI(title="AgriSuivi Bénin")

# Configuration des templates et fichiers statiques
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# ============================================
# PARTIE 6: ROUTE DE TEST POUR LA BASE DE DONNÉES
# ============================================
@app.get("/health-db")
async def health_db():
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT current_database()"))
            db_name = result.scalar()
            return {
                "status": "ok",
                "database": db_name,
                "message": f"✅ Connecté à {db_name}"
            }
    except Exception as e:
        return {
            "status": "error",
            "message": f"❌ {str(e)}"
        }

# ============================================
# PARTIE 7: CONFIGURATION SWAGGER
# ============================================
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title="AgriSuivi Bénin API",
        version="1.0.0",
        description="API pour la gestion des stocks et prix agricoles",
        routes=app.routes,
    )
    
    openapi_schema["components"] = {
        "securitySchemes": {
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "Entrez votre token JWT précédé de 'Bearer '"
            }
        }
    }
    
    for path in openapi_schema["paths"].values():
        for operation in path.values():
            if "/token" not in operation.get("operationId", ""):
                operation["security"] = [{"BearerAuth": []}]
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# ============================================
# PARTIE 8: MIDDLEWARE
# ============================================

@app.get("/check-data")
async def check_data(db: Session = Depends(get_db)):
    """Vérifie les données dans PostgreSQL"""
    return {
        "users_count": db.query(models.User).count(),
        "products_count": db.query(models.Product).count(),
        "zones_count": db.query(models.Zone).count(),
        "stocks_count": db.query(models.Stock).count(),
        "prices_count": db.query(models.Price).count(),
        "sample_users": [
            {"id": u.id, "username": u.username, "email": u.email}
            for u in db.query(models.User).limit(5).all()
        ],
        "sample_products": [
            {"id": p.id, "name": p.name, "category": p.category}
            for p in db.query(models.Product).limit(5).all()
        ]
    }

@app.middleware("http")
async def add_user_to_request(request: Request, call_next):
    try:
        token = request.cookies.get("access_token")
        print(f"Middleware - Token présent: {bool(token)}")  # DEBUG
        
        if token and token.startswith("Bearer "):
            token = token.replace("Bearer ", "")
            try:
                payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
                email = payload.get("sub")
                print(f"Middleware - Email du token: {email}")  # DEBUG
                
                if email:
                    db = SessionLocal()
                    try:
                        user = db.query(models.User).filter(models.User.email == email).first()
                        request.state.user = user
                        print(f"Middleware - Utilisateur trouvé: {user.username if user else 'Non'}")  # DEBUG
                    finally:
                        db.close()
                else:
                    request.state.user = None
            except Exception as e:
                print(f"Middleware - Erreur JWT: {e}")  # DEBUG
                request.state.user = None
        else:
            request.state.user = None
    except Exception as e:
        print(f"Middleware - Erreur générale: {e}")
        request.state.user = None
    
    response = await call_next(request)
    return response

# Fonction pour les templates
def get_user_from_request(request: Request):
    return getattr(request.state, 'user', None)

templates.env.globals['get_user'] = get_user_from_request

# ============================================
# PARTIE 9: ROUTES D'AUTHENTIFICATION
# ============================================

# 1. Pour voir l'état de l'authentification à un instant T
@app.get("/debug-auth-state")
async def debug_auth_state(request: Request):
    """Voir le contenu des cookies et l'état de l'utilisateur"""
    token = request.cookies.get("access_token")
    auth_status = {
        "cookies_keys": list(request.cookies.keys()),
        "has_token": token is not None,
        "token_preview": token[:20] + "..." if token and len(token) > 20 else token,
        "user_from_state": getattr(request.state, 'user', None),
    }
    
    # Essayer de décoder le token si présent
    if token and token.startswith("Bearer "):
        try:
            token_value = token.replace("Bearer ", "")
            payload = jwt.decode(token_value, SECRET_KEY, algorithms=[ALGORITHM])
            auth_status["token_payload"] = payload
            auth_status["token_valid"] = True
        except Exception as e:
            auth_status["token_error"] = str(e)
            auth_status["token_valid"] = False
            
    return auth_status

# 2. Pour tester la connexion sans passer par le formulaire HTML
@app.post("/debug-test-login")
async def debug_test_login(email: str, password: str, db: Session = Depends(get_db)):
    """Teste la connexion et retourne le token sans redirection"""
    user = authenticate_user(db, email, password)
    if not user:
        return {"success": False, "error": "Identifiants invalides"}
    
    access_token = create_access_token(data={"sub": user.email})
    return {
        "success": True,
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user.id,
        "username": user.username
    }

@app.get("/debug-test-login-get")
async def debug_test_login_get(email: str, password: str, db: Session = Depends(get_db)):
    """Version GET pour tester facilement depuis le navigateur"""
    user = authenticate_user(db, email, password)
    if not user:
        return {"success": False, "error": "Identifiants invalides"}
    
    access_token = create_access_token(data={"sub": user.email})
    return {
        "success": True,
        "access_token": access_token,
        "user_id": user.id,
        "username": user.username
    }

@app.get("/verify-migration")
async def verify_migration(db: Session = Depends(get_db)):
    return {
        "users": [{"id": u.id, "username": u.username, "email": u.email} for u in db.query(User).all()],
        "products_count": db.query(Product).count(),
        "zones_count": db.query(Zone).count(),
        "stocks_count": db.query(Stock).count(),
        "prices_count": db.query(Price).count()
    }

@app.get("/debug-auth")
async def debug_auth(request: Request):
    """Diagnostic d'authentification"""
    result = {
        "cookies": dict(request.cookies),
        "has_token": "access_token" in request.cookies,
        "user_state": getattr(request.state, 'user', None),
        "headers": {
            "host": request.headers.get("host"),
            "x-forwarded-proto": request.headers.get("x-forwarded-proto"),
        }
    }
    
    token = request.cookies.get("access_token")
    if token:
        result["token_starts_with_bearer"] = token.startswith("Bearer ")
        if token.startswith("Bearer "):
            token_value = token.replace("Bearer ", "")
            try:
                payload = jwt.decode(token_value, SECRET_KEY, algorithms=[ALGORITHM])
                result["token_payload"] = payload
                result["token_valid"] = True
            except Exception as e:
                result["token_error"] = str(e)
                result["token_valid"] = False
    
    return result

@app.get("/check-render-db")
async def check_render_db(db: Session = Depends(get_db)):
    """Vérifie que la base Render a les données"""
    return {
        "users_count": db.query(models.User).count(),
        "users": [{"id": u.id, "username": u.username, "email": u.email} 
                  for u in db.query(models.User).limit(5).all()],
        "products_count": db.query(models.Product).count(),
        "zones_count": db.query(models.Zone).count(),
        "stocks_count": db.query(models.Stock).count(),
        "prices_count": db.query(models.Price).count()
    }



@app.get("/")
async def home(request: Request):
    user = getattr(request.state, 'user', None)
    print(f"Home - User: {user}")  # DEBUG
    
    if not user:
        print("Home - Pas d'utilisateur, redirection vers login")
        return RedirectResponse(url="/login", status_code=303)
    
    print(f"Home - Utilisateur connecté: {user.username}")
    token = request.cookies.get("access_token")
    if token and token.startswith("Bearer "):
        token = token.replace("Bearer ", "")
    
    return templates.TemplateResponse(
        "base.html",
        {
            "request": request,
            "token": token,
            "ACCESS_TOKEN_EXPIRE_MINUTES": ACCESS_TOKEN_EXPIRE_MINUTES
        }
    )
@app.get("/login")
async def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/token")
async def login(request: Request, db: Session = Depends(get_db)):
    try:
        form = await request.form()
        email = form.get('email')
        password = form.get('password')
        
        if not email or not password:
            return templates.TemplateResponse(
                "login.html",
                {"request": request, "error": "Email et mot de passe requis"}
            )
        
        user = authenticate_user(db, email, password)
        
        if not user:
            return templates.TemplateResponse(
                "login.html",
                {"request": request, "error": "Email ou mot de passe incorrect"}
            )
        
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user.email}, 
            expires_delta=access_token_expires
        )
        
        response = RedirectResponse(url="/dashboard", status_code=303)
        
        response.set_cookie(
              key="access_token", 
              value=f"Bearer {access_token}", 
              httponly=True,
              max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
              secure=True,  # IMPORTANT pour HTTPS
              samesite="lax"
        )
        
        return response
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Erreur lors de la connexion"}
        )

@app.get("/register")
async def register_form(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register")
async def register(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    
    errors = []
    
    username = form['username']
    if len(username) < 3 or len(username) > 50:
        errors.append("Le nom d'utilisateur doit contenir entre 3 et 50 caractères")
    elif not username.replace('_', '').isalnum():
        errors.append("Le nom d'utilisateur ne peut contenir que des lettres, chiffres et _")
    
    email = form['email']
    if '@' not in email or '.' not in email or len(email) > 100:
        errors.append("Veuillez entrer une adresse email valide")
    else:
        existing_email = db.query(models.User).filter(models.User.email == email).first()
        if existing_email:
            errors.append("Cet email est déjà utilisé")
    
    password = form['password']
    if len(password) < 6:
        errors.append("Le mot de passe doit contenir au moins 6 caractères")
    
    if password != form['confirm_password']:
        errors.append("Les mots de passe ne correspondent pas")
    
    existing_username = db.query(models.User).filter(models.User.username == username).first()
    if existing_username:
        errors.append("Ce nom d'utilisateur est déjà utilisé")
    
    if errors:
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request, 
                "error": errors[0],
                "form": form
            }
        )
    
    hashed_password = get_password_hash(password)
    user = models.User(
        username=username,
        email=email,
        hashed_password=hashed_password,
        is_active=True,
        is_admin=False
    )
    db.add(user)
    db.commit()
    
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "success": "Inscription réussie ! Vous pouvez maintenant vous connecter avec votre email."}
    )

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("access_token")
    return response

# ============================================
# PARTIE 10: ROUTES PRODUITS
# ============================================

@app.get("/products")
async def list_products(request: Request, db: Session = Depends(get_db)):
    products = db.query(models.Product).all()
    return templates.TemplateResponse(
        "products/list.html",
        {"request": request, "products": products}
    )

@app.get("/products/add")
async def add_product_form(request: Request):
    return templates.TemplateResponse("products/form.html", {"request": request})

@app.post("/products/add")
async def add_product(request: Request, db: Session = Depends(get_db)):
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    form = await request.form()
    errors = []
    
    if not form.get('name') or not form['name'].strip():
        errors.append("Le nom du produit est requis")
    elif len(form['name'].strip()) < 2:
        errors.append("Le nom du produit doit contenir au moins 2 caractères")
    
    if not form.get('category'):
        errors.append("La catégorie est requise")
    
    if not form.get('unit'):
        errors.append("L'unité de mesure est requise")
    
    if not form.get('description') or not form['description'].strip():
        errors.append("La description est requise")
    elif len(form['description'].strip()) < 5:
        errors.append("La description doit contenir au moins 5 caractères")
    
    if errors:
        return templates.TemplateResponse(
            "products/form.html",
            {
                "request": request,
                "errors": errors,
                "form": form
            }
        )
    
    product = models.Product(
        name=form['name'].strip(),
        category=form['category'],
        unit=form['unit'],
        description=form['description'].strip(),
        created_by=user.id
    )
    db.add(product)
    db.commit()
    
    return RedirectResponse(url="/products", status_code=303)

@app.get("/products/edit/{product_id}")
async def edit_product_form(request: Request, product_id: int, db: Session = Depends(get_db)):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    return templates.TemplateResponse(
        "products/edit.html",
        {"request": request, "product": product}
    )

@app.post("/products/edit/{product_id}")
async def edit_product(request: Request, product_id: int, db: Session = Depends(get_db)):
    form = await request.form()
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    product.name = form['name']
    product.category = form['category']
    product.unit = form['unit']
    product.description = form.get('description', '')
    db.commit()
    return RedirectResponse(url="/products", status_code=303)

@app.get("/products/delete/{product_id}")
async def delete_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    db.delete(product)
    db.commit()
    return RedirectResponse(url="/products", status_code=303)

# ============================================
# PARTIE 11: ROUTES ZONES
# ============================================

@app.get("/zones")
async def list_zones(request: Request, db: Session = Depends(get_db)):
    zones = db.query(models.Zone).all()
    return templates.TemplateResponse(
        "zones/list.html",
        {"request": request, "zones": zones}
    )

@app.get("/zones/add")
async def add_zone_form(request: Request):
    return templates.TemplateResponse("zones/form.html", {"request": request})

@app.post("/zones/add")
async def add_zone(request: Request, db: Session = Depends(get_db)):
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    form = await request.form()
    errors = []
    
    name = form.get('name', '').strip()
    if not name:
        errors.append("Le nom de la zone est requis")
    elif len(name) < 3:
        errors.append("Le nom de la zone doit contenir au moins 3 caractères")
    elif len(name) > 100:
        errors.append("Le nom de la zone ne peut pas dépasser 100 caractères")
    
    zone_type = form.get('type')
    if not zone_type:
        errors.append("Le type de zone est requis")
    elif zone_type not in ['Marché', 'Dépôt', 'Commune', 'Arrondissement']:
        errors.append("Type de zone invalide")
    
    department = form.get('department')
    if not department:
        errors.append("Le département est requis")
    
    city = form.get('city', '').strip()
    if not city:
        errors.append("La ville est requise")
    elif len(city) < 2:
        errors.append("La ville doit contenir au moins 2 caractères")
    elif len(city) > 100:
        errors.append("La ville ne peut pas dépasser 100 caractères")
    
    if errors:
        return templates.TemplateResponse(
            "zones/form.html",
            {
                "request": request,
                "errors": errors,
                "form": {
                    "name": name,
                    "type": zone_type,
                    "department": department,
                    "city": city
                }
            }
        )
    
    try:
        zone = models.Zone(
            name=name,
            type=zone_type,
            department=department,
            city=city
        )
        db.add(zone)
        db.commit()
        return RedirectResponse(url="/zones", status_code=303)
    except Exception as e:
        db.rollback()
        errors.append(f"Erreur lors de l'enregistrement : {str(e)}")
        return templates.TemplateResponse(
            "zones/form.html",
            {
                "request": request,
                "errors": errors,
                "form": form
            }
        )

@app.get("/zones/edit/{zone_id}")
async def edit_zone_form(request: Request, zone_id: int, db: Session = Depends(get_db)):
    zone = db.query(models.Zone).filter(models.Zone.id == zone_id).first()
    return templates.TemplateResponse(
        "zones/edit.html",
        {"request": request, "zone": zone}
    )

@app.post("/zones/edit/{zone_id}")
async def edit_zone(request: Request, zone_id: int, db: Session = Depends(get_db)):
    form = await request.form()
    zone = db.query(models.Zone).filter(models.Zone.id == zone_id).first()
    zone.name = form['name']
    zone.type = form['type']
    zone.department = form['department']
    zone.city = form['city']
    db.commit()
    return RedirectResponse(url="/zones", status_code=303)

@app.get("/zones/delete/{zone_id}")
async def delete_zone(zone_id: int, db: Session = Depends(get_db)):
    zone = db.query(models.Zone).filter(models.Zone.id == zone_id).first()
    db.delete(zone)
    db.commit()
    return RedirectResponse(url="/zones", status_code=303)

# ============================================
# PARTIE 12: ROUTES STOCKS
# ============================================

@app.get("/stocks")
async def list_stocks(request: Request, db: Session = Depends(get_db)):
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    stocks = db.query(models.Stock).order_by(models.Stock.date.desc()).all()
    return templates.TemplateResponse(
        "stocks/list.html",
        {"request": request, "stocks": stocks}
    )

@app.get("/stocks/add")
async def add_stock_form(request: Request, db: Session = Depends(get_db)):
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    products = db.query(models.Product).all()
    zones = db.query(models.Zone).all()
    return templates.TemplateResponse(
        "stocks/form.html",
        {"request": request, "products": products, "zones": zones}
    )

@app.post("/stocks/add")
async def add_stock(request: Request, db: Session = Depends(get_db)):
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    form = await request.form()
    errors = []
    
    if not form.get('product_id'):
        errors.append("Le produit est requis")
    if not form.get('zone_id'):
        errors.append("La zone est requise")
    if not form.get('quantity') or float(form['quantity']) <= 0:
        errors.append("La quantité doit être supérieure à 0")
    
    if errors:
        products = db.query(models.Product).all()
        zones = db.query(models.Zone).all()
        return templates.TemplateResponse(
            "stocks/form.html",
            {"request": request, "errors": errors, "form": form, 
             "products": products, "zones": zones}
        )
    
    stock = models.Stock(
        product_id=int(form['product_id']),
        zone_id=int(form['zone_id']),
        quantity=float(form['quantity']),
        notes=form.get('notes', ''),
        created_by=user.id
    )
    
    if form.get('date'):
        try:
            stock.date = datetime.fromisoformat(form['date'])
        except:
            pass
    
    db.add(stock)
    db.commit()
    return RedirectResponse(url="/stocks", status_code=303)

@app.get("/stocks/edit/{stock_id}")
async def edit_stock_form(request: Request, stock_id: int, db: Session = Depends(get_db)):
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    stock = db.query(models.Stock).filter(models.Stock.id == stock_id).first()
    products = db.query(models.Product).all()
    zones = db.query(models.Zone).all()
    return templates.TemplateResponse(
        "stocks/edit.html",
        {"request": request, "stock": stock, "products": products, "zones": zones}
    )

@app.post("/stocks/edit/{stock_id}")
async def edit_stock(request: Request, stock_id: int, db: Session = Depends(get_db)):
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    form = await request.form()
    stock = db.query(models.Stock).filter(models.Stock.id == stock_id).first()
    
    stock.product_id = int(form['product_id'])
    stock.zone_id = int(form['zone_id'])
    stock.quantity = float(form['quantity'])
    stock.notes = form.get('notes', '')
    
    db.commit()
    return RedirectResponse(url="/stocks", status_code=303)

@app.get("/stocks/delete/{stock_id}")
async def delete_stock(stock_id: int, db: Session = Depends(get_db)):
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    stock = db.query(models.Stock).filter(models.Stock.id == stock_id).first()
    db.delete(stock)
    db.commit()
    return RedirectResponse(url="/stocks", status_code=303)

# ============================================
# PARTIE 13: ROUTES PRIX
# ============================================

@app.get("/prices")
async def list_prices(request: Request, db: Session = Depends(get_db)):
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    prices = db.query(models.Price).order_by(models.Price.date.desc()).all()
    return templates.TemplateResponse(
        "prices/list.html",
        {"request": request, "prices": prices}
    )

@app.get("/prices/add")
async def add_price_form(request: Request, db: Session = Depends(get_db)):
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    products = db.query(models.Product).all()
    zones = db.query(models.Zone).all()
    return templates.TemplateResponse(
        "prices/form.html",
        {"request": request, "products": products, "zones": zones}
    )

@app.post("/prices/add")
async def add_price(request: Request, db: Session = Depends(get_db)):
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    form = await request.form()
    errors = []
    
    if not form.get('product_id'):
        errors.append("Le produit est requis")
    
    if not form.get('zone_id'):
        errors.append("La zone est requise")
    
    if not form.get('price'):
        errors.append("Le prix est requis")
    else:
        try:
            price_value = float(form['price'])
            if price_value <= 0:
                errors.append("Le prix doit être supérieur à 0")
            if not price_value.is_integer():
                errors.append("Le prix doit être un nombre entier")
        except ValueError:
            errors.append("Le prix doit être un nombre valide")
    
    if errors:
        products = db.query(models.Product).all()
        zones = db.query(models.Zone).all()
        return templates.TemplateResponse(
            "prices/form.html",
            {
                "request": request, 
                "errors": errors, 
                "form": form,
                "products": products, 
                "zones": zones
            }
        )
    
    price = models.Price(
        product_id=int(form['product_id']),
        zone_id=int(form['zone_id']),
        price=float(form['price']),
        notes=form.get('notes', ''),
        created_by=user.id
    )
    
    if form.get('date'):
        try:
            price.date = datetime.fromisoformat(form['date'])
        except:
            pass
    
    db.add(price)
    db.commit()
    return RedirectResponse(url="/prices", status_code=303)

@app.get("/prices/edit/{price_id}")
async def edit_price_form(request: Request, price_id: int, db: Session = Depends(get_db)):
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    price = db.query(models.Price).filter(models.Price.id == price_id).first()
    if not price:
        return RedirectResponse(url="/prices", status_code=303)
    
    products = db.query(models.Product).all()
    zones = db.query(models.Zone).all()
    return templates.TemplateResponse(
        "prices/edit.html",
        {
            "request": request, 
            "price": price, 
            "products": products, 
            "zones": zones
        }
    )

@app.post("/prices/edit/{price_id}")
async def edit_price(request: Request, price_id: int, db: Session = Depends(get_db)):
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    form = await request.form()
    price = db.query(models.Price).filter(models.Price.id == price_id).first()
    
    if not price:
        return RedirectResponse(url="/prices", status_code=303)
    
    errors = []
    
    if not form.get('product_id'):
        errors.append("Le produit est requis")
    
    if not form.get('zone_id'):
        errors.append("La zone est requise")
    
    if not form.get('price'):
        errors.append("Le prix est requis")
    else:
        try:
            price_value = float(form['price'])
            if price_value <= 0:
                errors.append("Le prix doit être supérieur à 0")
            if not price_value.is_integer():
                errors.append("Le prix doit être un nombre entier")
        except ValueError:
            errors.append("Le prix doit être un nombre valide")
    
    if errors:
        products = db.query(models.Product).all()
        zones = db.query(models.Zone).all()
        return templates.TemplateResponse(
            "prices/edit.html",
            {
                "request": request, 
                "errors": errors, 
                "price": price,
                "products": products, 
                "zones": zones
            }
        )
    
    price.product_id = int(form['product_id'])
    price.zone_id = int(form['zone_id'])
    price.price = float(form['price'])
    price.notes = form.get('notes', '')
    
    if form.get('date'):
        try:
            price.date = datetime.fromisoformat(form['date'])
        except:
            pass
    
    db.commit()
    return RedirectResponse(url="/prices", status_code=303)

@app.get("/prices/delete/{price_id}")
async def delete_price(price_id: int, db: Session = Depends(get_db)):
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    price = db.query(models.Price).filter(models.Price.id == price_id).first()
    if price:
        db.delete(price)
        db.commit()
    return RedirectResponse(url="/prices", status_code=303)

# ============================================
# PARTIE 14: API POUR L'ÉQUIPE 3
# ============================================

@app.get("/api/products")
async def get_products(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    products = db.query(models.Product).all()
    return products

@app.get("/api/zones")
async def get_zones(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    zones = db.query(models.Zone).all()
    return zones

@app.get("/api/stocks")
async def get_stocks(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    stocks = db.query(models.Stock).all()
    return stocks

@app.get("/api/prices")
async def get_prices(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    prices = db.query(models.Price).all()
    return prices

@app.get("/api/stats")
async def get_stats(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    return {
        "products_count": db.query(models.Product).count(),
        "zones_count": db.query(models.Zone).count(),
        "stocks_count": db.query(models.Stock).count(),
        "prices_count": db.query(models.Price).count()
    }

# ============================================
# PARTIE 15: DASHBOARD
# ============================================

@app.get("/dashboard")
async def dashboard(request: Request, db: Session = Depends(get_db)):
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    from sqlalchemy import func
    
    # Répartition par catégorie
    categories = db.query(
        models.Product.category, 
        func.count(models.Product.id)
    ).group_by(models.Product.category).all()
    
    if categories:
        category_labels = [c[0] for c in categories]
        category_data = [c[1] for c in categories]
    else:
        category_labels = ['Aucune donnée']
        category_data = [1]
    
    # Évolution des prix
    from datetime import datetime, timedelta
    last_7_days = datetime.now() - timedelta(days=7)
    prices = db.query(models.Price)\
        .filter(models.Price.date >= last_7_days)\
        .order_by(models.Price.date).all()
    
    if prices:
        price_by_day = {}
        for p in prices:
            day = p.date.strftime('%d/%m')
            if day not in price_by_day:
                price_by_day[day] = []
            price_by_day[day].append(p.price)
        
        price_dates = []
        price_data = []
        for day in sorted(price_by_day.keys()):
            price_dates.append(day)
            price_data.append(sum(price_by_day[day]) / len(price_by_day[day]))
    else:
        price_dates = ['J-7', 'J-6', 'J-5', 'J-4', 'J-3', 'J-2', 'J-1', 'Aujourd\'hui']
        price_data = [500, 520, 510, 530, 540, 550, 560, 570]
    
    # Top 5 des stocks
    top_stocks = db.query(
        models.Product.name,
        models.Stock.quantity
    ).join(models.Stock)\
     .order_by(models.Stock.quantity.desc())\
     .limit(5).all()
    
    if top_stocks:
        stock_labels = [s[0][:15] + '...' if len(s[0]) > 15 else s[0] for s in top_stocks]
        stock_data = [float(s[1]) for s in top_stocks]
    else:
        stock_labels = ['Maïs', 'Riz', 'Tomate', 'Manioc', 'Haricot']
        stock_data = [1500, 800, 200, 450, 300]
    
    # Alertes stocks faibles
    low_stock_alerts = db.query(
        models.Product.name.label('product_name'),
        models.Zone.name.label('zone_name'),
        models.Stock.quantity,
        models.Product.unit
    ).join(models.Product).join(models.Zone)\
     .filter(models.Stock.quantity < 100)\
     .order_by(models.Stock.quantity)\
     .limit(10).all()
    
    # Statistiques
    stats = {
        "products_count": db.query(models.Product).count(),
        "zones_count": db.query(models.Zone).count(),
        "stocks_count": db.query(models.Stock).count(),
        "prices_count": db.query(models.Price).count(),
    }
    
    # Derniers enregistrements
    latest_prices = db.query(models.Price)\
        .order_by(models.Price.date.desc())\
        .limit(5).all()
    
    latest_stocks = db.query(models.Stock)\
        .order_by(models.Stock.date.desc())\
        .limit(5).all()
    
    token = request.cookies.get("access_token")
    if token and token.startswith("Bearer "):
        token = token.replace("Bearer ", "")
    
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "token": token,
            "ACCESS_TOKEN_EXPIRE_MINUTES": ACCESS_TOKEN_EXPIRE_MINUTES,
            "stats": stats,
            "category_labels": category_labels,
            "category_data": category_data,
            "price_dates": price_dates,
            "price_data": price_data,
            "stock_labels": stock_labels,
            "stock_data": stock_data,
            "low_stock_alerts": low_stock_alerts,
            "latest_prices": latest_prices,
            "latest_stocks": latest_stocks
        }
    )

# ============================================
# PARTIE 16: POINT D'ENTRÉE
# ============================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)