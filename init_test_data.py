from database import SessionLocal
import models

db = SessionLocal()

# Ajouter des produits de test
produits = [
    {"name": "Maïs", "category": "Céréale", "unit": "kg"},
    {"name": "Riz", "category": "Céréale", "unit": "sac"},
    {"name": "Tomate", "category": "Légume", "unit": "kg"},
    {"name": "Manioc", "category": "Tubercule", "unit": "kg"},
]

for p in produits:
    produit = models.Product(**p)
    db.add(produit)

# Ajouter des zones de test
zones = [
    {"name": "Marché Dantokpa", "type": "Marché", "department": "Littoral", "city": "Cotonou"},
    {"name": "Marché Arzèkè", "type": "Marché", "department": "Ouémé", "city": "Porto-Novo"},
    {"name": "Dépôt de Parakou", "type": "Dépôt", "department": "Borgou", "city": "Parakou"},
]

for z in zones:
    zone = models.Zone(**z)
    db.add(zone)

db.commit()
print("✅ Données de test ajoutées avec succès !")
db.close()