# migrate_clean.py
import sqlite3
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker
from models import Base, User, Product, Zone, Stock, Price
import os
from datetime import datetime

# ============================================
# CONFIGURATION
# ============================================
SQLITE_PATH = "agriculture.db"
POSTGRES_URL = "postgresql://agrisuivi_admin:7w4TAfaflBx84orEne0tiMuqFCqy72lq@dpg-d6gtcd9drdic73cd8n30-a.frankfurt-postgres.render.com/agrisuivi_production?sslmode=require"

print("=" * 60)
print("🔄 MIGRATION PROPRE SQLITE → POSTGRESQL")
print("=" * 60)

# ============================================
# 1. CONNEXION À SQLITE
# ============================================
print(f"\n📂 Connexion à SQLite: {SQLITE_PATH}")
sqlite_conn = sqlite3.connect(SQLITE_PATH)
sqlite_conn.row_factory = sqlite3.Row
cursor = sqlite_conn.cursor()

# Récupérer les données SQLite
print("📊 Récupération des données SQLite...")

def get_sqlite_data(table_name):
    cursor.execute(f"SELECT * FROM {table_name}")
    return [dict(row) for row in cursor.fetchall()]

users_data = get_sqlite_data("users")
products_data = get_sqlite_data("products")
zones_data = get_sqlite_data("zones")
stocks_data = get_sqlite_data("stocks")
prices_data = get_sqlite_data("prices")

print(f"   - Utilisateurs: {len(users_data)}")
print(f"   - Produits: {len(products_data)}")
print(f"   - Zones: {len(zones_data)}")
print(f"   - Stocks: {len(stocks_data)}")
print(f"   - Prix: {len(prices_data)}")

# ============================================
# 2. CONNEXION À POSTGRESQL ET NETTOYAGE
# ============================================
print(f"\n🐘 Connexion à PostgreSQL...")
engine = create_engine(POSTGRES_URL, echo=False)

# Supprimer et recréer les tables
print("🧹 Nettoyage des tables PostgreSQL...")
Base.metadata.drop_all(bind=engine)  # Supprime toutes les tables
print("✅ Tables supprimées")

print("🏗️  Création des tables PostgreSQL...")
Base.metadata.create_all(bind=engine)  # Recrée les tables
print("✅ Tables créées")

Session = sessionmaker(bind=engine)
db = Session()

# ============================================
# 3. FONCTIONS DE MIGRATION
# ============================================

def migrate_without_ids(table_data, model, db_session):
    """Migre les données sans forcer les IDs, laisse la base générer les nouveaux IDs"""
    count = 0
    for item in table_data:
        try:
            # Créer une copie sans l'ID
            item_copy = item.copy()
            if 'id' in item_copy:
                del item_copy['id']  # Enlève l'ID pour que PostgreSQL en génère un nouveau
            
            # Créer l'objet avec les données sans ID
            obj = model(**item_copy)
            db_session.add(obj)
            count += 1
            
            if count % 50 == 0:
                db_session.commit()
                print(f"  ✓ {count}...")
                
        except Exception as e:
            print(f"  ❌ Erreur: {e}")
            db_session.rollback()
    
    db_session.commit()
    return count

def migrate_with_ids(table_data, model, db_session):
    """Migre les données en conservant les IDs (pour les tables sans contraintes d'auto-incrément)"""
    count = 0
    for item in table_data:
        try:
            obj = model(**item)
            db_session.add(obj)
            count += 1
            
            if count % 50 == 0:
                db_session.commit()
                print(f"  ✓ {count}...")
                
        except Exception as e:
            print(f"  ❌ Erreur: {e}")
            db_session.rollback()
    
    db_session.commit()
    return count

# ============================================
# 4. EXÉCUTION DE LA MIGRATION
# ============================================
print("\n🚀 DÉBUT DE LA MIGRATION")

try:
    # 1. Migrer les utilisateurs SANS leurs IDs (laisse la base générer)
    print("\n👤 Migration des utilisateurs...")
    user_count = 0
    for user_data in users_data:
        try:
            # Ne pas inclure l'ID, laisser PostgreSQL le générer
            user = User(
                username=user_data['username'],
                email=user_data['email'],
                hashed_password=user_data['hashed_password'],
                is_active=user_data['is_active'],
                is_admin=user_data['is_admin'],
                created_at=user_data.get('created_at', datetime.now())
            )
            db.add(user)
            user_count += 1
            
            if user_count % 50 == 0:
                db.commit()
                print(f"  ✓ {user_count} utilisateurs...")
        except Exception as e:
            print(f"  ❌ Erreur: {e}")
            db.rollback()
    db.commit()
    print(f"✅ {user_count} utilisateurs migrés (avec nouveaux IDs)")
    
    # 2. Récupérer la correspondance des IDs (ancien → nouveau)
    print("\n🔗 Établissement de la correspondance des IDs...")
    new_users = db.query(User).all()
    user_id_map = {}
    
    # Créer un mapping basé sur des identifiants uniques (email)
    for old_user in users_data:
        for new_user in new_users:
            if old_user['email'] == new_user.email:
                user_id_map[old_user['id']] = new_user.id
                break
    
    print(f"   {len(user_id_map)} correspondances trouvées")
    
    # 3. Migrer les produits (peuvent garder leurs IDs, pas de conflit)
    print("\n📦 Migration des produits...")
    product_count = 0
    for prod_data in products_data:
        try:
            # Garder l'ID original des produits
            prod_data_copy = prod_data.copy()
            db.add(Product(**prod_data_copy))
            product_count += 1
        except Exception as e:
            print(f"  ❌ Erreur: {e}")
    db.commit()
    print(f"✅ {product_count} produits migrés")
    
    # 4. Migrer les zones (peuvent garder leurs IDs)
    print("\n📍 Migration des zones...")
    zone_count = 0
    for zone_data in zones_data:
        try:
            zone_data_copy = zone_data.copy()
            db.add(Zone(**zone_data_copy))
            zone_count += 1
        except Exception as e:
            print(f"  ❌ Erreur: {e}")
    db.commit()
    print(f"✅ {zone_count} zones migrées")
    
    # 5. Migrer les stocks avec mise à jour des created_by
    print("\n📊 Migration des stocks...")
    stock_count = 0
    for stock_data in stocks_data:
        try:
            # Mettre à jour created_by avec le nouvel ID utilisateur
            if stock_data['created_by'] in user_id_map:
                stock_data['created_by'] = user_id_map[stock_data['created_by']]
            
            # Gérer la date
            if 'date' in stock_data and stock_data['date']:
                if isinstance(stock_data['date'], str):
                    stock_data['date'] = datetime.fromisoformat(stock_data['date'])
            
            stock_data_copy = stock_data.copy()
            db.add(Stock(**stock_data_copy))
            stock_count += 1
        except Exception as e:
            print(f"  ❌ Erreur stock: {e}")
    db.commit()
    print(f"✅ {stock_count} stocks migrés")
    
    # 6. Migrer les prix avec mise à jour des created_by
    print("\n💰 Migration des prix...")
    price_count = 0
    for price_data in prices_data:
        try:
            # Mettre à jour created_by avec le nouvel ID utilisateur
            if price_data['created_by'] in user_id_map:
                price_data['created_by'] = user_id_map[price_data['created_by']]
            
            # Gérer la date
            if 'date' in price_data and price_data['date']:
                if isinstance(price_data['date'], str):
                    price_data['date'] = datetime.fromisoformat(price_data['date'])
            
            price_data_copy = price_data.copy()
            db.add(Price(**price_data_copy))
            price_count += 1
        except Exception as e:
            print(f"  ❌ Erreur prix: {e}")
    db.commit()
    print(f"✅ {price_count} prix migrés")
    
    print("\n" + "=" * 60)
    print("🎉 MIGRATION TERMINÉE AVEC SUCCÈS !")
    print("=" * 60)
    
    # Vérification finale
    print("\n📊 RÉCAPITULATIF:")
    print(f"   - Utilisateurs: {db.query(User).count()}")
    print(f"   - Produits: {db.query(Product).count()}")
    print(f"   - Zones: {db.query(Zone).count()}")
    print(f"   - Stocks: {db.query(Stock).count()}")
    print(f"   - Prix: {db.query(Price).count()}")

except Exception as e:
    print(f"\n❌ ERREUR: {e}")
    db.rollback()
    import traceback
    traceback.print_exc()

finally:
    db.close()
    sqlite_conn.close()
    print("\n🔒 Connexions fermées")