# Documentation API - Projet 1 (AgriSuivi Bénin)

## Informations générales

- **Base URL** : `http://[IP_DU_PC1]:8000`
- **Documentation Swagger** : `http://[IP_DU_PC1]:8000/docs`
- **Format des données** : JSON

## Authentification

Tous les endpoints API nécessitent un token JWT.

### 1. Obtenir un token
```bash
POST /token
Content-Type: application/x-www-form-urlencoded

username=votre@email.com&password=votre_mot_de_passe

Réponse :
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...(votre token)",
  "token_type": "bearer"
}



2. Utiliser le token
Ajoutez ce header à chaque requête :
 Authorization: Bearer eyJhbGciOiJIUzI1NiIs...



Endpoints disponibles
Méthode	Endpoint	Description
GET	/api/products	Liste tous les produits
GET	/api/zones	Liste toutes les zones
GET	/api/stocks	Liste tous les stocks
GET	/api/prices	Liste tous les prix
GET	/api/stats	Statistiques globales


Exemples
Récupérer les produits
#bash
curl -X GET http://localhost:8000/api/products \
  -H "Authorization: Bearer VOTRE_TOKEN"


Voir les stocks faibles
#python
import requests

token = "VOTRE_TOKEN"
headers = {"Authorization": f"Bearer {token}"}

stocks = requests.get("http://localhost:8000/api/stocks", headers=headers).json()

alerte = [s for s in stocks if s['quantity'] < 100]
print("⚠️ Stocks faibles:", alerte)