from fastapi import FastAPI, Request, Depends, status, HTTPException 
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.utils import get_openapi
from fastapi.responses import RedirectResponse
from fastapi.responses import JSONResponse  # Ajoute en haut du fichier
from fastapi.security import OAuth2PasswordRequestForm
from jose import jwt
from sqlalchemy.orm import Session
from datetime import timedelta
import models
from auth import get_current_active_user
from database import engine, SessionLocal, get_db

import sys
import subprocess

print("🔍 VÉRIFICATION DES PACKAGES INSTALLÉS")
print("=" * 50)

# Vérifier si jinja2 est installé
try:
    import jinja2
    print(f"✅ jinja2 est installé (version: {jinja2.__version__})")
except ImportError:
    print("❌ jinja2 N'EST PAS installé")

print("\n📦 Liste complète des packages:")
result = subprocess.run(['pip', 'freeze'], capture_output=True, text=True)
print(result.stdout)
print("=" * 50)


from auth import (
    authenticate_user, create_access_token, get_current_active_user,
    get_password_hash, ACCESS_TOKEN_EXPIRE_MINUTES, SECRET_KEY, ALGORITHM
)

# Création des tables
models.Base.metadata.create_all(bind=engine)

# Initialisation FastAPI
app = FastAPI(title="AgriSuivi Bénin")

# Configuration des templates et fichiers statiques
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")


# Configuration personnalisée de Swagger
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    # Générer le schéma OpenAPI de base
    openapi_schema = get_openapi(
        title="AgriSuivi Bénin API",
        version="1.0.0",
        description="API pour la gestion des stocks et prix agricoles",
        routes=app.routes,
    )
    
    # Définir le schéma de sécurité (Bearer Token)
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
    
    # Appliquer la sécurité à toutes les routes qui en ont besoin
    # (optionnel - tu peux aussi le faire route par route)
    for path in openapi_schema["paths"].values():
        for operation in path.values():
            # Ne pas ajouter de sécurité aux routes d'authentification
            if "/token" not in operation.get("operationId", ""):
                operation["security"] = [{"BearerAuth": []}]
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi
# ========== MIDDLEWARE ==========
@app.middleware("http")
async def add_user_to_request(request: Request, call_next):
    token = request.cookies.get("access_token")
    if token and token.startswith("Bearer "):
        token = token.replace("Bearer ", "")
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            email = payload.get("sub")  # Maintenant on cherche par email
            if email:
                db = SessionLocal()
                user = db.query(models.User).filter(models.User.email == email).first()
                request.state.user = user
                db.close()
            else:
                request.state.user = None
        except:
            request.state.user = None
    else:
        request.state.user = None
    
    response = await call_next(request)
    return response
# Fonction pour les templates
def get_user_from_request(request: Request):
    return getattr(request.state, 'user', None)

templates.env.globals['get_user'] = get_user_from_request

# ========== ROUTE D'ACCUEIL ==========
@app.get("/")
async def home(request: Request):
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    # Récupérer le token depuis le cookie
    token = request.cookies.get("access_token")
    if token and token.startswith("Bearer "):
        token = token.replace("Bearer ", "")
    
    return templates.TemplateResponse(
        "base.html",  # Ou ta page d'accueil
        {
            "request": request,
            "token": token,
            "ACCESS_TOKEN_EXPIRE_MINUTES": ACCESS_TOKEN_EXPIRE_MINUTES
        }
    )

# ========== AUTHENTIFICATION ==========

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
        
        # 🔴 REDIRECTION VERS DASHBOARD au lieu de la page d'accueil
        response = RedirectResponse(url="/dashboard", status_code=303)
        
        response.set_cookie(
            key="access_token", 
            value=f"Bearer {access_token}", 
            httponly=True,
            max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60
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
    
    # Validation des données
    errors = []
    
    # Validation du nom d'utilisateur
    username = form['username']
    if len(username) < 3 or len(username) > 50:
        errors.append("Le nom d'utilisateur doit contenir entre 3 et 50 caractères")
    elif not username.replace('_', '').isalnum():
        errors.append("Le nom d'utilisateur ne peut contenir que des lettres, chiffres et _")
    
    # Validation de l'email (doit être unique)
    email = form['email']
    if '@' not in email or '.' not in email or len(email) > 100:
        errors.append("Veuillez entrer une adresse email valide")
    else:
        # Vérifier si l'email existe déjà
        existing_email = db.query(models.User).filter(models.User.email == email).first()
        if existing_email:
            errors.append("Cet email est déjà utilisé")
    
    # Validation du mot de passe
    password = form['password']
    if len(password) < 6:
        errors.append("Le mot de passe doit contenir au moins 6 caractères")
    
    # Vérification de la confirmation
    if password != form['confirm_password']:
        errors.append("Les mots de passe ne correspondent pas")
    
    # Vérifier si le nom d'utilisateur existe déjà
    existing_username = db.query(models.User).filter(models.User.username == username).first()
    if existing_username:
        errors.append("Ce nom d'utilisateur est déjà utilisé")
    
    # Si erreurs de validation
    if errors:
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request, 
                "error": errors[0],
                "form": form
            }
        )
    
    # Créer le nouvel utilisateur
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

# ========== PRODUITS ==========
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
    
    # Validation de TOUS les champs
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
    
    # Si erreurs, retourner le formulaire avec les messages
    if errors:
        return templates.TemplateResponse(
            "products/form.html",
            {
                "request": request,
                "errors": errors,
                "form": form  # Pour pré-remplir le formulaire
            }
        )
    
    # Création du produit
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

# ========== ZONES ==========
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
    
    # Validation du nom
    name = form.get('name', '').strip()
    if not name:
        errors.append("Le nom de la zone est requis")
    elif len(name) < 3:
        errors.append("Le nom de la zone doit contenir au moins 3 caractères")
    elif len(name) > 100:
        errors.append("Le nom de la zone ne peut pas dépasser 100 caractères")
    
    # Validation du type
    zone_type = form.get('type')
    if not zone_type:
        errors.append("Le type de zone est requis")
    elif zone_type not in ['Marché', 'Dépôt', 'Commune', 'Arrondissement']:
        errors.append("Type de zone invalide")
    
    # Validation du département
    department = form.get('department')
    if not department:
        errors.append("Le département est requis")
    
    # Validation de la ville
    city = form.get('city', '').strip()
    if not city:
        errors.append("La ville est requise")
    elif len(city) < 2:
        errors.append("La ville doit contenir au moins 2 caractères")
    elif len(city) > 100:
        errors.append("La ville ne peut pas dépasser 100 caractères")
    
    # Si erreurs, retourner le formulaire
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
    
    # Création de la zone
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

# ========== STOCKS ==========
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
    
    # Validation
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

# ========== PRIX ==========
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
    
    # Validation
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
    
    # Création
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
    
    # Validation
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
    
    # Mise à jour
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

# ========== API POUR L'ÉQUIPE 3 (MAINTENANT PROTÉGÉES) ==========

@app.get("/api/products")
async def get_products(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)  # ← AJOUTÉ
):
    products = db.query(models.Product).all()
    return products

@app.get("/api/zones")
async def get_zones(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)  # ← AJOUTÉ
):
    zones = db.query(models.Zone).all()
    return zones

@app.get("/api/stocks")
async def get_stocks(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)  # ← AJOUTÉ
):
    stocks = db.query(models.Stock).all()
    return stocks

@app.get("/api/prices")
async def get_prices(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)  # ← AJOUTÉ
):
    prices = db.query(models.Price).all()
    return prices

@app.get("/api/stats")
async def get_stats(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)  # ← AJOUTÉ
):
    return {
        "products_count": db.query(models.Product).count(),
        "zones_count": db.query(models.Zone).count(),
        "stocks_count": db.query(models.Stock).count(),
        "prices_count": db.query(models.Price).count()
    }
# ========== POINT D'ENTRÉE ==========
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)

# ========== DASHBOARD ==========
@app.get("/dashboard")
async def dashboard(request: Request, db: Session = Depends(get_db)):
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    # ========== DONNÉES POUR LES GRAPHIQUES ==========
    
    # 1. RÉPARTITION PAR CATÉGORIE
    from sqlalchemy import func
    categories = db.query(
        models.Product.category, 
        func.count(models.Product.id)
    ).group_by(models.Product.category).all()
    
    # Debug print
    print("🔍 Catégories trouvées:", categories)
    
    if categories:
        category_labels = [c[0] for c in categories]
        category_data = [c[1] for c in categories]
    else:
        category_labels = ['Aucune donnée']
        category_data = [1]
    
    # 2. ÉVOLUTION DES PRIX (simplifiée)
    from datetime import datetime, timedelta
    last_7_days = datetime.now() - timedelta(days=7)
    prices = db.query(models.Price)\
        .filter(models.Price.date >= last_7_days)\
        .order_by(models.Price.date).all()
    
    if prices:
        # Grouper par jour
        price_by_day = {}
        for p in prices:
            day = p.date.strftime('%d/%m')
            if day not in price_by_day:
                price_by_day[day] = []
            price_by_day[day].append(p.price)
        
        # Calculer la moyenne par jour
        price_dates = []
        price_data = []
        for day in sorted(price_by_day.keys()):
            price_dates.append(day)
            price_data.append(sum(price_by_day[day]) / len(price_by_day[day]))
    else:
        # Données par défaut
        price_dates = ['J-7', 'J-6', 'J-5', 'J-4', 'J-3', 'J-2', 'J-1', 'Aujourd\'hui']
        price_data = [500, 520, 510, 530, 540, 550, 560, 570]
    
    # 3. TOP 5 DES STOCKS
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
    
    # 4. ALERTES STOCKS FAIBLES
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
    
    # Token pour l'affichage
    token = request.cookies.get("access_token")
    if token and token.startswith("Bearer "):
        token = token.replace("Bearer ", "")
    
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "token": token,
            "ACCESS_TOKEN_EXPIRE_MINUTES": 30,
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
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    # 🔴 RÉCUPÉRER LE TOKEN DU COOKIE
    token = request.cookies.get("access_token")
    if token and token.startswith("Bearer "):
        token = token.replace("Bearer ", "")
    
    # Statistiques
    stats = {
        "products_count": db.query(models.Product).count(),
        "zones_count": db.query(models.Zone).count(),
        "stocks_count": db.query(models.Stock).count(),
        "prices_count": db.query(models.Price).count()
    }
    
    latest_prices = db.query(models.Price)\
        .order_by(models.Price.date.desc())\
        .limit(5)\
        .all()
    
    latest_stocks = db.query(models.Stock)\
        .order_by(models.Stock.date.desc())\
        .limit(5)\
        .all()
    
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "stats": stats,
            "latest_prices": latest_prices,
            "latest_stocks": latest_stocks,
            "token": token,  # 🔴 PASSER LE TOKEN AU TEMPLATE
            "ACCESS_TOKEN_EXPIRE_MINUTES": ACCESS_TOKEN_EXPIRE_MINUTES
        }
    )
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    try:
        # Statistiques générales
        stats = {
            "products_count": db.query(models.Product).count(),
            "zones_count": db.query(models.Zone).count(),
            "stocks_count": db.query(models.Stock).count(),
            "prices_count": db.query(models.Price).count()
        }
        
        # Derniers prix (5 derniers)
        latest_prices = db.query(models.Price)\
            .order_by(models.Price.date.desc())\
            .limit(5)\
            .all()
        
        # Derniers stocks (5 derniers)
        latest_stocks = db.query(models.Stock)\
            .order_by(models.Stock.date.desc())\
            .limit(5)\
            .all()
        
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "stats": stats,
                "latest_prices": latest_prices,
                "latest_stocks": latest_stocks
            }
        )
    except Exception as e:
        print(f"Erreur dashboard: {e}")
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "stats": {"products_count": 0, "zones_count": 0, "stocks_count": 0, "prices_count": 0},
                "latest_prices": [],
                "latest_stocks": []
            }
        )
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    # Statistiques générales
    stats = {
        "products_count": db.query(models.Product).count(),
        "zones_count": db.query(models.Zone).count(),
        "stocks_count": db.query(models.Stock).count(),
        "prices_count": db.query(models.Price).count()
    }
    
    # Données pour les graphiques
    from sqlalchemy import func
    
    # Répartition par catégorie
    categories = db.query(
        models.Product.category, 
        func.count(models.Product.id)
    ).group_by(models.Product.category).all()
    
    category_labels = [c[0] for c in categories]
    category_data = [c[1] for c in categories]
    
    # Top stocks
    top_stocks = db.query(
        models.Product.name,
        func.sum(models.Stock.quantity).label('total')
    ).join(models.Stock).group_by(models.Product.id)\
     .order_by(func.sum(models.Stock.quantity).desc())\
     .limit(5).all()
    
    stock_labels = [s[0] for s in top_stocks]
    stock_data = [float(s[1]) for s in top_stocks]
    
    # Alertes stocks faibles (moins de 100 unités)
    low_stock_alerts = db.query(
        models.Product.name.label('product_name'),
        models.Zone.name.label('zone_name'),
        models.Stock.quantity,
        models.Product.unit
    ).join(models.Product).join(models.Zone)\
     .filter(models.Stock.quantity < 100)\
     .order_by(models.Stock.quantity).limit(6).all()
    
    # Derniers enregistrements
    latest_prices = db.query(models.Price)\
        .order_by(models.Price.date.desc())\
        .limit(5).all()
    
    latest_stocks = db.query(models.Stock)\
        .order_by(models.Stock.date.desc())\
        .limit(5).all()
    
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "stats": stats,
            "category_labels": category_labels,
            "category_data": category_data,
            "stock_labels": stock_labels,
            "stock_data": stock_data,
            "low_stock_alerts": low_stock_alerts,
            "latest_prices": latest_prices,
            "latest_stocks": latest_stocks
        }
    )