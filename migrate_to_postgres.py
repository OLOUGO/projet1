# migrate_to_postgres.py
import sqlite3
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker
from models import Base, User, Product, Zone, Stock, Price
import os
from datetime import datetime
import sys

# ============================================
# CONFIGURATION
# ============================================

# Ancienne base SQLite (locale) - CORRIGÉ avec votre nom de fichier
SQLITE_PATH = "agriculture.db"

# Nouvelle base PostgreSQL (Render) - VOTRE URL
POSTGRES_URL = "postgresql://agrisuivi_admin:7w4TAfaflBx84orEne0tiMuqFCqy72lq@dpg-d6gtcd9drdic73cd8n30-a.frankfurt-postgres.render.com/agrisuivi_production?sslmode=require"

print("=" * 60)
print("🔍 MIGRATION SQLITE → POSTGRESQL")
print("=" * 60)

# ============================================
# 1. CONNEXION À SQLITE (source)
# ============================================
print(f"\n📂 Connexion à SQLite: {SQLITE_PATH}")

if not os.path.exists(SQLITE_PATH):
    print(f"❌ ERREUR: Le fichier {SQLITE_PATH} n'existe pas!")
    print(f"📁 Répertoire actuel: {os.getcwd()}")
    print("📋 Fichiers .db trouvés:")
    for file in os.listdir('.'):
        if file.endswith('.db'):
            print(f"   - {file}")
    sys.exit(1)

try:
    # Connexion avec row_factory pour accéder aux colonnes par nom
    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_conn.row_factory = sqlite3.Row
    print("✅ Connexion SQLite réussie")
    
    # Vérifier les tables existantes
    cursor = sqlite_conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    table_names = [t[0] for t in tables]
    print(f"📊 Tables trouvées: {table_names}")
    
    # Compter les enregistrements dans chaque table
    for table in table_names:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        print(f"   - {table}: {count} enregistrements")
    
except Exception as e:
    print(f"❌ Erreur connexion SQLite: {e}")
    sys.exit(1)

# ============================================
# 2. CONNEXION À POSTGRESQL (destination)
# ============================================
print(f"\n🐘 Connexion à PostgreSQL (Render)...")

try:
    # Créer le moteur SQLAlchemy
    engine = create_engine(POSTGRES_URL, echo=False)
    
    # Tester la connexion
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    print("✅ Connexion PostgreSQL réussie")
    
    # Créer les tables si elles n'existent pas
    print("🔄 Création des tables PostgreSQL...")
    Base.metadata.create_all(bind=engine)
    print("✅ Tables PostgreSQL créées/vérifiées")
    
    # Vérifier les tables créées
    inspector = inspect(engine)
    pg_tables = inspector.get_table_names()
    print(f"📊 Tables PostgreSQL: {pg_tables}")
    
    # Créer une session
    SessionPostgres = sessionmaker(bind=engine)
    pg_session = SessionPostgres()
    
except Exception as e:
    print(f"❌ Erreur connexion PostgreSQL: {e}")
    sys.exit(1)

# ============================================
# 3. FONCTIONS DE MIGRATION PAR TABLE
# ============================================

def clean_value(value):
    """Nettoie les valeurs pour PostgreSQL"""
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() if value.strip() else None
    return value

def migrate_users():
    print("\n👤 Migration des utilisateurs...")
    cursor = sqlite_conn.cursor()
    
    # Vérifier si la table existe
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    if not cursor.fetchone():
        print("⚠️  Table 'users' non trouvée dans SQLite, ignorée")
        return 0
    
    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()
    
    if not users:
        print("ℹ️  Aucun utilisateur à migrer")
        return 0
    
    count = 0
    errors = 0
    
    for user_row in users:
        try:
            user_dict = dict(user_row)
            
            # Nettoyer les données
            username = clean_value(user_dict.get('username'))
            email = clean_value(user_dict.get('email'))
            
            if not username or not email:
                print(f"  ⚠️  Utilisateur ignoré (données incomplètes): {user_dict}")
                continue
            
            # Vérifier si l'utilisateur existe déjà
            existing = pg_session.query(User).filter(
                (User.username == username) | (User.email == email)
            ).first()
            
            if existing:
                print(f"  ⚠️  Utilisateur déjà existant: {username}, ignoré")
                continue
            
            user = User(
                id=user_dict.get('id'),
                username=username,
                email=email,
                hashed_password=user_dict.get('hashed_password', ''),
                is_active=bool(user_dict.get('is_active', 1)),
                is_admin=bool(user_dict.get('is_admin', 0))
            )
            
            pg_session.add(user)
            count += 1
            
            if count % 50 == 0:
                pg_session.commit()
                print(f"  ✓ {count} utilisateurs migrés...")
                
        except Exception as e:
            errors += 1
            print(f"  ❌ Erreur utilisateur {user_dict.get('username', 'inconnu')}: {e}")
            pg_session.rollback()
    
    pg_session.commit()
    print(f"✅ {count} utilisateurs migrés ({errors} erreurs)")
    return count

def migrate_products():
    print("\n📦 Migration des produits...")
    cursor = sqlite_conn.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='products'")
    if not cursor.fetchone():
        print("⚠️  Table 'products' non trouvée dans SQLite, ignorée")
        return 0
    
    cursor.execute("SELECT * FROM products")
    products = cursor.fetchall()
    
    if not products:
        print("ℹ️  Aucun produit à migrer")
        return 0
    
    count = 0
    errors = 0
    
    for product_row in products:
        try:
            product_dict = dict(product_row)
            
            name = clean_value(product_dict.get('name'))
            if not name:
                continue
            
            existing = pg_session.query(Product).filter(Product.name == name).first()
            if existing:
                print(f"  ⚠️  Produit déjà existant: {name}, ignoré")
                continue
            
            product = Product(
                id=product_dict.get('id'),
                name=name,
                category=clean_value(product_dict.get('category', 'Non catégorisé')),
                unit=clean_value(product_dict.get('unit', 'pièce')),
                description=clean_value(product_dict.get('description', '')),
                created_by=product_dict.get('created_by')
            )
            
            pg_session.add(product)
            count += 1
            
            if count % 50 == 0:
                pg_session.commit()
                print(f"  ✓ {count} produits migrés...")
                
        except Exception as e:
            errors += 1
            print(f"  ❌ Erreur produit: {e}")
            pg_session.rollback()
    
    pg_session.commit()
    print(f"✅ {count} produits migrés ({errors} erreurs)")
    return count

def migrate_zones():
    print("\n📍 Migration des zones...")
    cursor = sqlite_conn.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='zones'")
    if not cursor.fetchone():
        print("⚠️  Table 'zones' non trouvée dans SQLite, ignorée")
        return 0
    
    cursor.execute("SELECT * FROM zones")
    zones = cursor.fetchall()
    
    if not zones:
        print("ℹ️  Aucune zone à migrer")
        return 0
    
    count = 0
    errors = 0
    
    for zone_row in zones:
        try:
            zone_dict = dict(zone_row)
            
            name = clean_value(zone_dict.get('name'))
            if not name:
                continue
            
            existing = pg_session.query(Zone).filter(Zone.name == name).first()
            if existing:
                print(f"  ⚠️  Zone déjà existante: {name}, ignorée")
                continue
            
            zone = Zone(
                id=zone_dict.get('id'),
                name=name,
                type=clean_value(zone_dict.get('type', 'Marché')),
                department=clean_value(zone_dict.get('department', '')),
                city=clean_value(zone_dict.get('city', ''))
            )
            
            pg_session.add(zone)
            count += 1
            
            if count % 50 == 0:
                pg_session.commit()
                print(f"  ✓ {count} zones migrées...")
                
        except Exception as e:
            errors += 1
            print(f"  ❌ Erreur zone: {e}")
            pg_session.rollback()
    
    pg_session.commit()
    print(f"✅ {count} zones migrées ({errors} erreurs)")
    return count

def migrate_stocks():
    print("\n📊 Migration des stocks...")
    cursor = sqlite_conn.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='stocks'")
    if not cursor.fetchone():
        print("⚠️  Table 'stocks' non trouvée dans SQLite, ignorée")
        return 0
    
    cursor.execute("SELECT * FROM stocks")
    stocks = cursor.fetchall()
    
    if not stocks:
        print("ℹ️  Aucun stock à migrer")
        return 0
    
    count = 0
    errors = 0
    
    for stock_row in stocks:
        try:
            stock_dict = dict(stock_row)
            
            # Gérer les dates
            date_value = stock_dict.get('date')
            if date_value:
                if isinstance(date_value, str):
                    try:
                        date_value = datetime.fromisoformat(date_value.replace('Z', '+00:00'))
                    except:
                        date_value = datetime.now()
                elif isinstance(date_value, (int, float)):
                    date_value = datetime.fromtimestamp(date_value)
            
            stock = Stock(
                id=stock_dict.get('id'),
                product_id=stock_dict.get('product_id'),
                zone_id=stock_dict.get('zone_id'),
                quantity=float(stock_dict.get('quantity', 0)),
                date=date_value,
                notes=clean_value(stock_dict.get('notes', '')),
                created_by=stock_dict.get('created_by')
            )
            
            pg_session.add(stock)
            count += 1
            
            if count % 50 == 0:
                pg_session.commit()
                print(f"  ✓ {count} stocks migrés...")
                
        except Exception as e:
            errors += 1
            print(f"  ❌ Erreur stock: {e}")
            pg_session.rollback()
    
    pg_session.commit()
    print(f"✅ {count} stocks migrés ({errors} erreurs)")
    return count

def migrate_prices():
    print("\n💰 Migration des prix...")
    cursor = sqlite_conn.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='prices'")
    if not cursor.fetchone():
        print("⚠️  Table 'prices' non trouvée dans SQLite, ignorée")
        return 0
    
    cursor.execute("SELECT * FROM prices")
    prices = cursor.fetchall()
    
    if not prices:
        print("ℹ️  Aucun prix à migrer")
        return 0
    
    count = 0
    errors = 0
    
    for price_row in prices:
        try:
            price_dict = dict(price_row)
            
            # Gérer les dates
            date_value = price_dict.get('date')
            if date_value:
                if isinstance(date_value, str):
                    try:
                        date_value = datetime.fromisoformat(date_value.replace('Z', '+00:00'))
                    except:
                        date_value = datetime.now()
                elif isinstance(date_value, (int, float)):
                    date_value = datetime.fromtimestamp(date_value)
            
            price = Price(
                id=price_dict.get('id'),
                product_id=price_dict.get('product_id'),
                zone_id=price_dict.get('zone_id'),
                price=float(price_dict.get('price', 0)),
                date=date_value,
                notes=clean_value(price_dict.get('notes', '')),
                created_by=price_dict.get('created_by')
            )
            
            pg_session.add(price)
            count += 1
            
            if count % 50 == 0:
                pg_session.commit()
                print(f"  ✓ {count} prix migrés...")
                
        except Exception as e:
            errors += 1
            print(f"  ❌ Erreur prix: {e}")
            pg_session.rollback()
    
    pg_session.commit()
    print(f"✅ {count} prix migrés ({errors} erreurs)")
    return count

# ============================================
# 4. EXÉCUTION DE LA MIGRATION
# ============================================

print("\n" + "=" * 60)
print("🚀 DÉBUT DE LA MIGRATION")
print("=" * 60)

try:
    # Vider les tables PostgreSQL avant migration (optionnel)
    print("\n🧹 Nettoyage des tables PostgreSQL existantes...")
    pg_session.query(Price).delete()
    pg_session.query(Stock).delete()
    pg_session.query(Zone).delete()
    pg_session.query(Product).delete()
    pg_session.query(User).delete()
    pg_session.commit()
    print("✅ Tables PostgreSQL vidées")

    # Migration dans l'ordre (respecter les clés étrangères)
    total_users = migrate_users()
    total_products = migrate_products()
    total_zones = migrate_zones()
    total_stocks = migrate_stocks()
    total_prices = migrate_prices()
    
    print("\n" + "=" * 60)
    print("🎉 MIGRATION TERMINÉE AVEC SUCCÈS !")
    print("=" * 60)
    
    # Vérification finale
    print("\n📊 RÉCAPITULATIF FINAL:")
    print(f"   - Utilisateurs: {total_users}")
    print(f"   - Produits: {total_products}")
    print(f"   - Zones: {total_zones}")
    print(f"   - Stocks: {total_stocks}")
    print(f"   - Prix: {total_prices}")
    
    # Vérification croisée avec PostgreSQL
    print("\n🔍 VÉRIFICATION DANS POSTGRESQL:")
    tables_to_check = [
        ("users", User),
        ("products", Product),
        ("zones", Zone),
        ("stocks", Stock),
        ("prices", Price)
    ]
    
    for table_name, model in tables_to_check:
        count = pg_session.query(model).count()
        print(f"   - {table_name}: {count} enregistrements")
    
except Exception as e:
    print(f"\n❌ ERREUR PENDANT LA MIGRATION: {e}")
    pg_session.rollback()
    import traceback
    traceback.print_exc()
    
finally:
    # Fermeture des connexions
    sqlite_conn.close()
    pg_session.close()
    print("\n🔒 Connexions fermées")
    print("=" * 60)