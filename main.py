from fastapi import FastAPI, Request, Depends
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.utils import get_openapi
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import models
from database import engine, SessionLocal, get_db
import sys
import subprocess
from auth import authenticate_user, verify_password, get_password_hash

# ============================================
# 1. DIAGNOSTIC DE DÉMARRAGE
# ============================================
print("🔍 VÉRIFICATION DES PACKAGES INSTALLÉS")
print("=" * 50)

try:
    import jinja2
    print(f"✅ jinja2 est installé (version: {jinja2.__version__})")
except ImportError:
    print("❌ jinja2 N'EST PAS installé")

print("\n📦 Liste complète des packages:")
result = subprocess.run(['pip', 'freeze'], capture_output=True, text=True)
print(result.stdout)
print("=" * 50)

# ============================================
# 2. CRÉATION DES TABLES
# ============================================
models.Base.metadata.create_all(bind=engine)

# ============================================
# 3. INITIALISATION FASTAPI
# ============================================
app = FastAPI(title="AgriSuivi Bénin")
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# ============================================
# 4. MIDDLEWARE D'AUTHENTIFICATION SIMPLIFIÉ
# ============================================
@app.middleware("http")
async def add_user_to_request(request: Request, call_next):
    """Récupère l'utilisateur depuis la session (sans JWT)"""
    user_id = request.cookies.get("user_id")
    
    if user_id:
        db = SessionLocal()
        try:
            user = db.query(models.User).filter(models.User.id == int(user_id)).first()
            request.state.user = user
        except:
            request.state.user = None
        finally:
            db.close()
    else:
        request.state.user = None
    
    response = await call_next(request)
    return response

# ============================================
# 5. FONCTION POUR LES TEMPLATES
# ============================================
def get_user_from_request(request: Request):
    """Récupère l'utilisateur depuis request.state pour les templates"""
    return getattr(request.state, 'user', None)

# AJOUTEZ CETTE FONCTION
def get_notification(request: Request):
    """Récupère une notification pour les templates"""
    # Pour l'instant, retourne None (pas de notification)
    # Tu pourras implémenter les notifications plus tard
    return None

templates.env.globals['get_user'] = get_user_from_request
templates.env.globals['get_notification'] = get_notification  # ← AJOUTEZ CETTE LIGNE


# ============================================
# 6. CONFIGURATION SWAGGER
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
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# ============================================
# 7. ROUTES D'AUTHENTIFICATION
# ============================================

@app.get("/")
async def home(request: Request):
    """Page d'accueil"""
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    return templates.TemplateResponse(
        "base.html",
        {"request": request}
    )

@app.get("/login")
async def login_form(request: Request):
    """Formulaire de connexion"""
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/token")
async def login(request: Request, db: Session = Depends(get_db)):
    """Connexion utilisateur - SANS JWT"""
    try:
        form = await request.form()
        email = form.get('email')
        password = form.get('password')
        
        if not email or not password:
            return templates.TemplateResponse(
                "login.html",
                {"request": request, "error": "Email et mot de passe requis"}
            )
        
        # Utilisation de la fonction d'authentification
        user = authenticate_user(db, email, password)
        
        if not user:
            return templates.TemplateResponse(
                "login.html",
                {"request": request, "error": "Email ou mot de passe incorrect"}
            )
        
        # Créer la réponse avec redirection vers dashboard
        response = RedirectResponse(url="/dashboard", status_code=303)
        
        # Stocker l'ID de l'utilisateur dans un cookie simple
        response.set_cookie(
            key="user_id",
            value=str(user.id),
            max_age=3600,  # 1 heure
            httponly=True,
            secure=False,  # Mettre True en production (HTTPS)
            samesite="lax"
        )
        
        return response
        
    except Exception as e:
        print(f"❌ Erreur login: {e}")
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Erreur lors de la connexion"}
        )

@app.get("/register")
async def register_form(request: Request):
    """Formulaire d'inscription"""
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register")
async def register(request: Request, db: Session = Depends(get_db)):
    """Inscription utilisateur"""
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
            {"request": request, "error": errors[0], "form": form}
        )
    
    # Création du nouvel utilisateur
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
        {"request": request, "success": "Inscription réussie ! Vous pouvez maintenant vous connecter."}
    )

@app.get("/logout")
async def logout():
    """Déconnexion"""
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("user_id")
    return response

# ============================================
# 8. ROUTE DE DEBUG
# ============================================
@app.get("/debug-state")
async def debug_state(request: Request):
    """Debug - voir l'état de l'authentification"""
    user = getattr(request.state, 'user', None)
    
    result = {
        "authenticated": user is not None,
        "cookies": dict(request.cookies),
    }
    
    if user:
        result["user"] = {
            "id": user.id,
            "username": user.username,
            "email": user.email
        }
    
    return result

# ============================================
# 9. DASHBOARD
# ============================================
@app.get("/dashboard")
async def dashboard(request: Request, db: Session = Depends(get_db)):
    """Tableau de bord avec statistiques"""
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    from sqlalchemy import func
    
    # 1. Statistiques générales
    stats = {
        "products_count": db.query(models.Product).count(),
        "zones_count": db.query(models.Zone).count(),
        "stocks_count": db.query(models.Stock).count(),
        "prices_count": db.query(models.Price).count(),
    }
    
    # 2. Répartition par catégorie
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
    
    # 3. Évolution des prix (7 derniers jours)
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
        price_dates = []
        price_data = []
    
    # 4. Top 5 des stocks
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
        stock_labels = []
        stock_data = []
    
    # 5. Alertes stocks faibles
    low_stock_alerts = db.query(
        models.Product.name.label('product_name'),
        models.Zone.name.label('zone_name'),
        models.Stock.quantity,
        models.Product.unit
    ).join(models.Product).join(models.Zone)\
     .filter(models.Stock.quantity < 100)\
     .order_by(models.Stock.quantity)\
     .limit(10).all()
    
    # 6. Derniers enregistrements
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
# 10. ROUTES PRODUITS
# ============================================
@app.get("/products")
async def list_products(request: Request, db: Session = Depends(get_db)):
    """Liste tous les produits"""
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    products = db.query(models.Product).all()
    return templates.TemplateResponse(
        "products/list.html",
        {"request": request, "products": products}
    )

@app.get("/products/add")
async def add_product_form(request: Request):
    """Formulaire d'ajout de produit"""
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    return templates.TemplateResponse("products/form.html", {"request": request})

@app.post("/products/add")
async def add_product(request: Request, db: Session = Depends(get_db)):
    """Ajoute un produit"""
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    form = await request.form()
    errors = []
    
    name = form.get('name', '').strip()
    if not name:
        errors.append("Le nom du produit est requis")
    elif len(name) < 2:
        errors.append("Le nom du produit doit contenir au moins 2 caractères")
    
    if not form.get('category'):
        errors.append("La catégorie est requise")
    
    if not form.get('unit'):
        errors.append("L'unité de mesure est requise")
    
    description = form.get('description', '').strip()
    if not description:
        errors.append("La description est requise")
    elif len(description) < 5:
        errors.append("La description doit contenir au moins 5 caractères")
    
    if errors:
        return templates.TemplateResponse(
            "products/form.html",
            {"request": request, "errors": errors, "form": dict(form)}
        )
    
    product = models.Product(
        name=name,
        category=form['category'],
        unit=form['unit'],
        description=description,
        created_by=user.id
    )
    db.add(product)
    db.commit()
    
    return RedirectResponse(url="/products", status_code=303)

@app.get("/products/edit/{product_id}")
async def edit_product_form(request: Request, product_id: int, db: Session = Depends(get_db)):
    """Formulaire d'édition de produit"""
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    return templates.TemplateResponse(
        "products/edit.html",
        {"request": request, "product": product}
    )

@app.post("/products/edit/{product_id}")
async def edit_product(request: Request, product_id: int, db: Session = Depends(get_db)):
    """Modifie un produit"""
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    form = await request.form()
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    
    product.name = form['name']
    product.category = form['category']
    product.unit = form['unit']
    product.description = form.get('description', '')
    db.commit()
    
    return RedirectResponse(url="/products", status_code=303)

@app.get("/products/delete/{product_id}")
async def delete_product(request: Request, product_id: int, db: Session = Depends(get_db)):
    """Supprime un produit"""
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    db.delete(product)
    db.commit()
    
    return RedirectResponse(url="/products", status_code=303)


# ============================================
# 11. ROUTES ZONES
# ============================================

@app.get("/zones")
async def list_zones(request: Request, db: Session = Depends(get_db)):
    """Liste toutes les zones"""
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    zones = db.query(models.Zone).all()
    return templates.TemplateResponse(
        "zones/list.html",
        {"request": request, "zones": zones}
    )

@app.get("/zones/add")
async def add_zone_form(request: Request):
    """Formulaire d'ajout de zone"""
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    return templates.TemplateResponse("zones/form.html", {"request": request})

@app.post("/zones/add")
async def add_zone(request: Request, db: Session = Depends(get_db)):
    """Ajoute une zone"""
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
    department = form.get('department', '').strip()
    if not department:
        errors.append("Le département est requis")
    
    # Validation de la ville
    city = form.get('city', '').strip()
    if not city:
        errors.append("La ville est requise")
    elif len(city) < 2:
        errors.append("La ville doit contenir au moins 2 caractères")
    
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
        print(f"❌ Erreur ajout zone: {e}")
        return templates.TemplateResponse(
            "zones/form.html",
            {
                "request": request,
                "errors": ["Erreur lors de l'enregistrement"],
                "form": dict(form)
            }
        )

@app.get("/zones/edit/{zone_id}")
async def edit_zone_form(request: Request, zone_id: int, db: Session = Depends(get_db)):
    """Formulaire d'édition de zone"""
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    zone = db.query(models.Zone).filter(models.Zone.id == zone_id).first()
    if not zone:
        return RedirectResponse(url="/zones", status_code=303)
    
    return templates.TemplateResponse(
        "zones/edit.html",
        {"request": request, "zone": zone}
    )

@app.post("/zones/edit/{zone_id}")
async def edit_zone(request: Request, zone_id: int, db: Session = Depends(get_db)):
    """Modifie une zone"""
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    form = await request.form()
    zone = db.query(models.Zone).filter(models.Zone.id == zone_id).first()
    
    if not zone:
        return RedirectResponse(url="/zones", status_code=303)
    
    zone.name = form.get('name', zone.name)
    zone.type = form.get('type', zone.type)
    zone.department = form.get('department', zone.department)
    zone.city = form.get('city', zone.city)
    db.commit()
    
    return RedirectResponse(url="/zones", status_code=303)

@app.get("/zones/delete/{zone_id}")
async def delete_zone(request: Request, zone_id: int, db: Session = Depends(get_db)):
    """Supprime une zone"""
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    zone = db.query(models.Zone).filter(models.Zone.id == zone_id).first()
    if zone:
        db.delete(zone)
        db.commit()
    
    return RedirectResponse(url="/zones", status_code=303)


# ============================================
# 12. ROUTES STOCKS
# ============================================

@app.get("/stocks")
async def list_stocks(request: Request, db: Session = Depends(get_db)):
    """Liste tous les stocks"""
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
    """Formulaire d'ajout de stock"""
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    # Récupérer les produits et zones pour les menus déroulants
    products = db.query(models.Product).order_by(models.Product.name).all()
    zones = db.query(models.Zone).order_by(models.Zone.name).all()
    
    return templates.TemplateResponse(
        "stocks/form.html",
        {
            "request": request,
            "products": products,
            "zones": zones
        }
    )

@app.post("/stocks/add")
async def add_stock(request: Request, db: Session = Depends(get_db)):
    """Ajoute un stock"""
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    form = await request.form()
    errors = []
    
    # Récupérer les produits et zones en cas d'erreur
    products = db.query(models.Product).order_by(models.Product.name).all()
    zones = db.query(models.Zone).order_by(models.Zone.name).all()
    
    # Validation
    try:
        product_id = int(form.get('product_id', 0))
        if product_id <= 0:
            errors.append("Le produit est requis")
    except ValueError:
        errors.append("Produit invalide")
        product_id = 0
    
    try:
        zone_id = int(form.get('zone_id', 0))
        if zone_id <= 0:
            errors.append("La zone est requise")
    except ValueError:
        errors.append("Zone invalide")
        zone_id = 0
    
    try:
        quantity = float(form.get('quantity', 0))
        if quantity <= 0:
            errors.append("La quantité doit être supérieure à 0")
    except ValueError:
        errors.append("La quantité doit être un nombre valide")
        quantity = 0
    
    if errors:
        return templates.TemplateResponse(
            "stocks/form.html",
            {
                "request": request,
                "errors": errors,
                "form": dict(form),
                "products": products,
                "zones": zones
            }
        )
    
    # Création du stock
    try:
        stock = models.Stock(
            product_id=product_id,
            zone_id=zone_id,
            quantity=quantity,
            notes=form.get('notes', ''),
            created_by=user.id
        )
        
        # Gestion de la date si fournie
        if form.get('date'):
            try:
                stock.date = datetime.fromisoformat(form.get('date'))
            except:
                pass
        
        db.add(stock)
        db.commit()
        
        return RedirectResponse(url="/stocks", status_code=303)
        
    except Exception as e:
        print(f"❌ Erreur ajout stock: {e}")
        return templates.TemplateResponse(
            "stocks/form.html",
            {
                "request": request,
                "errors": ["Erreur lors de l'enregistrement"],
                "form": dict(form),
                "products": products,
                "zones": zones
            }
        )

@app.get("/stocks/edit/{stock_id}")
async def edit_stock_form(request: Request, stock_id: int, db: Session = Depends(get_db)):
    """Formulaire d'édition de stock"""
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    stock = db.query(models.Stock).filter(models.Stock.id == stock_id).first()
    if not stock:
        return RedirectResponse(url="/stocks", status_code=303)
    
    products = db.query(models.Product).order_by(models.Product.name).all()
    zones = db.query(models.Zone).order_by(models.Zone.name).all()
    
    return templates.TemplateResponse(
        "stocks/edit.html",
        {
            "request": request,
            "stock": stock,
            "products": products,
            "zones": zones
        }
    )

@app.post("/stocks/edit/{stock_id}")
async def edit_stock(request: Request, stock_id: int, db: Session = Depends(get_db)):
    """Modifie un stock"""
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    form = await request.form()
    stock = db.query(models.Stock).filter(models.Stock.id == stock_id).first()
    
    if not stock:
        return RedirectResponse(url="/stocks", status_code=303)
    
    # Mise à jour
    try:
        stock.product_id = int(form.get('product_id', stock.product_id))
        stock.zone_id = int(form.get('zone_id', stock.zone_id))
        stock.quantity = float(form.get('quantity', stock.quantity))
        stock.notes = form.get('notes', stock.notes)
        db.commit()
        
    except Exception as e:
        print(f"❌ Erreur modification stock: {e}")
    
    return RedirectResponse(url="/stocks", status_code=303)

@app.get("/stocks/delete/{stock_id}")
async def delete_stock(request: Request, stock_id: int, db: Session = Depends(get_db)):
    """Supprime un stock"""
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    stock = db.query(models.Stock).filter(models.Stock.id == stock_id).first()
    if stock:
        db.delete(stock)
        db.commit()
    
    return RedirectResponse(url="/stocks", status_code=303)

@app.get("/stocks/product/{product_id}")
async def stocks_by_product(request: Request, product_id: int, db: Session = Depends(get_db)):
    """Voir les stocks d'un produit spécifique"""
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    stocks = db.query(models.Stock).filter(models.Stock.product_id == product_id).all()
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    
    return templates.TemplateResponse(
        "stocks/by_product.html",
        {
            "request": request,
            "stocks": stocks,
            "product": product
        }
    )

@app.get("/stocks/zone/{zone_id}")
async def stocks_by_zone(request: Request, zone_id: int, db: Session = Depends(get_db)):
    """Voir les stocks d'une zone spécifique"""
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    stocks = db.query(models.Stock).filter(models.Stock.zone_id == zone_id).all()
    zone = db.query(models.Zone).filter(models.Zone.id == zone_id).first()
    
    return templates.TemplateResponse(
        "stocks/by_zone.html",
        {
            "request": request,
            "stocks": stocks,
            "zone": zone
        }
    )

# ============================================
# 13. ROUTES PRIX
# ============================================

@app.get("/prices")
async def list_prices(request: Request, db: Session = Depends(get_db)):
    """Liste tous les prix"""
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
    """Formulaire d'ajout de prix"""
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    # Récupérer les produits et zones pour les menus déroulants
    products = db.query(models.Product).order_by(models.Product.name).all()
    zones = db.query(models.Zone).order_by(models.Zone.name).all()
    
    return templates.TemplateResponse(
        "prices/form.html",
        {
            "request": request,
            "products": products,
            "zones": zones
        }
    )

@app.post("/prices/add")
async def add_price(request: Request, db: Session = Depends(get_db)):
    """Ajoute un prix"""
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    form = await request.form()
    errors = []
    
    # Récupérer les produits et zones en cas d'erreur
    products = db.query(models.Product).order_by(models.Product.name).all()
    zones = db.query(models.Zone).order_by(models.Zone.name).all()
    
    # Validation
    try:
        product_id = int(form.get('product_id', 0))
        if product_id <= 0:
            errors.append("Le produit est requis")
    except ValueError:
        errors.append("Produit invalide")
        product_id = 0
    
    try:
        zone_id = int(form.get('zone_id', 0))
        if zone_id <= 0:
            errors.append("La zone est requise")
    except ValueError:
        errors.append("Zone invalide")
        zone_id = 0
    
    try:
        price_value = float(form.get('price', 0))
        if price_value <= 0:
            errors.append("Le prix doit être supérieur à 0")
    except ValueError:
        errors.append("Le prix doit être un nombre valide")
        price_value = 0
    
    if errors:
        return templates.TemplateResponse(
            "prices/form.html",
            {
                "request": request,
                "errors": errors,
                "form": dict(form),
                "products": products,
                "zones": zones
            }
        )
    
    # Création du prix
    try:
        price = models.Price(
            product_id=product_id,
            zone_id=zone_id,
            price=price_value,
            notes=form.get('notes', ''),
            created_by=user.id
        )
        
        # Gestion de la date si fournie
        if form.get('date'):
            try:
                price.date = datetime.fromisoformat(form.get('date'))
            except:
                pass
        
        db.add(price)
        db.commit()
        
        return RedirectResponse(url="/prices", status_code=303)
        
    except Exception as e:
        print(f"❌ Erreur ajout prix: {e}")
        return templates.TemplateResponse(
            "prices/form.html",
            {
                "request": request,
                "errors": ["Erreur lors de l'enregistrement"],
                "form": dict(form),
                "products": products,
                "zones": zones
            }
        )

@app.get("/prices/edit/{price_id}")
async def edit_price_form(request: Request, price_id: int, db: Session = Depends(get_db)):
    """Formulaire d'édition de prix"""
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    price = db.query(models.Price).filter(models.Price.id == price_id).first()
    if not price:
        return RedirectResponse(url="/prices", status_code=303)
    
    products = db.query(models.Product).order_by(models.Product.name).all()
    zones = db.query(models.Zone).order_by(models.Zone.name).all()
    
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
    """Modifie un prix"""
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    form = await request.form()
    price = db.query(models.Price).filter(models.Price.id == price_id).first()
    
    if not price:
        return RedirectResponse(url="/prices", status_code=303)
    
    # Mise à jour
    try:
        price.product_id = int(form.get('product_id', price.product_id))
        price.zone_id = int(form.get('zone_id', price.zone_id))
        price.price = float(form.get('price', price.price))
        price.notes = form.get('notes', price.notes)
        db.commit()
        
    except Exception as e:
        print(f"❌ Erreur modification prix: {e}")
    
    return RedirectResponse(url="/prices", status_code=303)

@app.get("/prices/delete/{price_id}")
async def delete_price(request: Request, price_id: int, db: Session = Depends(get_db)):
    """Supprime un prix"""
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    price = db.query(models.Price).filter(models.Price.id == price_id).first()
    if price:
        db.delete(price)
        db.commit()
    
    return RedirectResponse(url="/prices", status_code=303)

@app.get("/prices/product/{product_id}")
async def prices_by_product(request: Request, product_id: int, db: Session = Depends(get_db)):
    """Voir les prix d'un produit spécifique"""
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    prices = db.query(models.Price).filter(models.Price.product_id == product_id).order_by(models.Price.date.desc()).all()
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    
    return templates.TemplateResponse(
        "prices/by_product.html",
        {
            "request": request,
            "prices": prices,
            "product": product
        }
    )

@app.get("/prices/zone/{zone_id}")
async def prices_by_zone(request: Request, zone_id: int, db: Session = Depends(get_db)):
    """Voir les prix d'une zone spécifique"""
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    prices = db.query(models.Price).filter(models.Price.zone_id == zone_id).order_by(models.Price.date.desc()).all()
    zone = db.query(models.Zone).filter(models.Zone.id == zone_id).first()
    
    return templates.TemplateResponse(
        "prices/by_zone.html",
        {
            "request": request,
            "prices": prices,
            "zone": zone
        }
    )

@app.get("/prices/latest")
async def latest_prices(request: Request, db: Session = Depends(get_db)):
    """Voir les derniers prix enregistrés"""
    user = getattr(request.state, 'user', None)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    # Récupérer les prix les plus récents pour chaque produit
    from sqlalchemy import func
    
    subquery = db.query(
        models.Price.product_id,
        func.max(models.Price.date).label('max_date')
    ).group_by(models.Price.product_id).subquery()
    
    latest_prices = db.query(models.Price).join(
        subquery,
        (models.Price.product_id == subquery.c.product_id) &
        (models.Price.date == subquery.c.max_date)
    ).order_by(models.Price.date.desc()).all()
    
    return templates.TemplateResponse(
        "prices/latest.html",
        {
            "request": request,
            "prices": latest_prices
        }
    )


# ============================================
# 14. ROUTES API (optionnelles)
# ============================================
@app.get("/api/products")
async def get_products(request: Request, db: Session = Depends(get_db)):
    """API pour les produits"""
    user = getattr(request.state, 'user', None)
    if not user:
        return {"error": "Non authentifié"}
    
    products = db.query(models.Product).all()
    return products

@app.get("/api/zones")
async def get_zones(request: Request, db: Session = Depends(get_db)):
    """API pour les zones"""
    user = getattr(request.state, 'user', None)
    if not user:
        return {"error": "Non authentifié"}
    
    zones = db.query(models.Zone).all()
    return zones

@app.get("/api/stocks")
async def get_stocks(request: Request, db: Session = Depends(get_db)):
    """API pour les stocks"""
    user = getattr(request.state, 'user', None)
    if not user:
        return {"error": "Non authentifié"}
    
    stocks = db.query(models.Stock).all()
    return stocks

@app.get("/api/prices")
async def get_prices(request: Request, db: Session = Depends(get_db)):
    """API pour les prix"""
    user = getattr(request.state, 'user', None)
    if not user:
        return {"error": "Non authentifié"}
    
    prices = db.query(models.Price).all()
    return prices

@app.get("/api/stats")
async def get_stats(request: Request, db: Session = Depends(get_db)):
    """API pour les statistiques"""
    user = getattr(request.state, 'user', None)
    if not user:
        return {"error": "Non authentifié"}
    
    return {
        "products_count": db.query(models.Product).count(),
        "zones_count": db.query(models.Zone).count(),
        "stocks_count": db.query(models.Stock).count(),
        "prices_count": db.query(models.Price).count()
    }

# ============================================
# 15. POINT D'ENTRÉE
# ============================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)