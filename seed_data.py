# seed_data.py
from database import SessionLocal
import models
from datetime import datetime, timedelta
import random

db = SessionLocal()

print("🌱 Ajout des données de test...")

# 1. VIDER LES ANCIENNES DONNÉES (optionnel - décommente si besoin)
# db.query(models.Price).delete()
# db.query(models.Stock).delete()
# db.query(models.Product).delete()
# db.query(models.Zone).delete()
# db.commit()

# 2. PRODUITS (10 produits)
produits = [
    {"name": "Maïs", "category": "Céréale", "unit": "kg", "description": "Maïs blanc local"},
    {"name": "Riz", "category": "Céréale", "unit": "sac", "description": "Riz long grain"},
    {"name": "Tomate", "category": "Légume", "unit": "kg", "description": "Tomate fraîche"},
    {"name": "Manioc", "category": "Tubercule", "unit": "kg", "description": "Manioc doux"},
    {"name": "Haricot", "category": "Légumineuse", "unit": "kg", "description": "Haricot blanc"},
    {"name": "Arachide", "category": "Olèagineux", "unit": "kg", "description": "Arachide décortiquée"},
    {"name": "Igname", "category": "Tubercule", "unit": "kg", "description": "Igname de Parakou"},
    {"name": "Mil", "category": "Céréale", "unit": "kg", "description": "Mil local"},
    {"name": "Sorgho", "category": "Céréale", "unit": "kg", "description": "Sorgho rouge"},
    {"name": "Piment", "category": "Épice", "unit": "kg", "description": "Piment frais"},
]

produits_crees = []
for p in produits:
    # Vérifier si le produit existe déjà
    existing = db.query(models.Product).filter(models.Product.name == p["name"]).first()
    if not existing:
        produit = models.Product(**p)
        db.add(produit)
        db.flush()
        produits_crees.append(produit)
        print(f"  ✅ Produit ajouté: {p['name']}")
    else:
        produits_crees.append(existing)
        print(f"  ⏩ Produit existant: {p['name']}")

db.commit()

# 3. ZONES (10 zones)
zones = [
    {"name": "Marché Dantokpa", "type": "Marché", "department": "Littoral", "city": "Cotonou"},
    {"name": "Marché Arzèkè", "type": "Marché", "department": "Ouémé", "city": "Porto-Novo"},
    {"name": "Dépôt de Parakou", "type": "Dépôt", "department": "Borgou", "city": "Parakou"},
    {"name": "Marché de Bohicon", "type": "Marché", "department": "Zou", "city": "Bohicon"},
    {"name": "Marché de Natitingou", "type": "Marché", "department": "Atacora", "city": "Natitingou"},
    {"name": "Dépôt de Lokossa", "type": "Dépôt", "department": "Mono", "city": "Lokossa"},
    {"name": "Marché de Kandi", "type": "Marché", "department": "Alibori", "city": "Kandi"},
    {"name": "Marché de Savè", "type": "Marché", "department": "Collines", "city": "Savè"},
    {"name": "Dépôt d'Abomey", "type": "Dépôt", "department": "Zou", "city": "Abomey"},
    {"name": "Marché de Ouidah", "type": "Marché", "department": "Atlantique", "city": "Ouidah"},
]

zones_crees = []
for z in zones:
    existing = db.query(models.Zone).filter(models.Zone.name == z["name"]).first()
    if not existing:
        zone = models.Zone(**z)
        db.add(zone)
        db.flush()
        zones_crees.append(zone)
        print(f"  ✅ Zone ajoutée: {z['name']}")
    else:
        zones_crees.append(existing)
        print(f"  ⏩ Zone existante: {z['name']}")

db.commit()

# 4. STOCKS (30 entrées pour avoir des données variées)
print("\n📦 Ajout des stocks...")
for i in range(30):
    produit = random.choice(produits_crees)
    zone = random.choice(zones_crees)
    
    # Quantités variées (certaines faibles pour les alertes)
    if i < 5:
        quantity = random.uniform(10, 50)  # Stocks très faibles
    elif i < 10:
        quantity = random.uniform(51, 99)  # Stocks faibles
    else:
        quantity = random.uniform(100, 5000)  # Stocks normals
    
    stock = models.Stock(
        product_id=produit.id,
        zone_id=zone.id,
        quantity=round(quantity, 2),
        date=datetime.now() - timedelta(days=random.randint(0, 30)),
        notes=f"Stock test {i+1}"
    )
    db.add(stock)

db.commit()
print(f"  ✅ {30} stocks ajoutés")

# 5. PRIX (40 entrées pour l'évolution)
print("\n💰 Ajout des prix...")
for i in range(40):
    produit = random.choice(produits_crees)
    zone = random.choice(zones_crees)
    
    # Prix avec tendance (certains produits augmentent)
    if produit.name == "Maïs":
        # Le maïs augmente progressivement
        base_price = 500 + i * 10
    elif produit.name == "Riz":
        # Le riz est stable
        base_price = 7500
    elif produit.name == "Tomate":
        # La tomate varie beaucoup
        base_price = random.choice([250, 300, 350, 400, 450, 500])
    else:
        base_price = random.uniform(200, 2000)
    
    price = models.Price(
        product_id=produit.id,
        zone_id=zone.id,
        price=round(base_price, 0),
        date=datetime.now() - timedelta(days=i),  # Un prix par jour
        notes=f"Prix test {i+1}"
    )
    db.add(price)

db.commit()
print(f"  ✅ {40} prix ajoutés")

# 6. AJOUTER QUELQUES PRIX RÉCENTS POUR LE GRAPHE D'ÉVOLUTION
print("\n📈 Ajout des prix récents (7 derniers jours)...")
for i in range(7):
    date = datetime.now() - timedelta(days=i)
    for produit in random.sample(produits_crees, 5):  # 5 produits aléatoires
        zone = random.choice(zones_crees)
        # Prix avec légère variation
        variation = random.uniform(-50, 50)
        price = models.Price(
            product_id=produit.id,
            zone_id=zone.id,
            price=round(500 + i*20 + variation, 0),  # Tendance à la hausse
            date=date,
            notes=f"Prix du {date.strftime('%d/%m/%Y')}"
        )
        db.add(price)

db.commit()
print(f"  ✅ Prix récents ajoutés")

print("\n" + "="*50)
print("🎉 DONNÉES DE TEST AJOUTÉES AVEC SUCCÈS !")
print("="*50)
print(f"📊 RÉSUMÉ:")
print(f"   - Produits: {db.query(models.Product).count()}")
print(f"   - Zones: {db.query(models.Zone).count()}")
print(f"   - Stocks: {db.query(models.Stock).count()}")
print(f"   - Prix: {db.query(models.Price).count()}")
print("="*50)

db.close()