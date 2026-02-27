🚀 **PROJET 1 - Structure complète avec FastAPI + Jinja2**

Voici l'architecture complète qu'on va mettre en place :





projet1/

│

├── main.py                 # Point d'entrée de l'app

├── database.py             # Connexion BD et sessions

├── models.py               # Modèles SQLAlchemy

├── schemas.py              # Schémas Pydantic (validation)

│

├── routers/                # Routes organisées

│   ├── auth.py            # Authentification

│   ├── products.py        # CRUD produits

│   ├── zones.py           # CRUD zones

│   ├── stocks.py          # CRUD stocks

│   └── prices.py          # CRUD prix

│

├── templates/              # Fichiers HTML (Jinja2)

│   ├── base.html          # Template de base

│   ├── index.html         # Accueil

│   ├── products/

│   │   ├── list.html

│   │   └── form.html

│   ├── stocks/

│   │   ├── list.html

│   │   └── form.html

│   └── dashboard.html      # Statistiques

│

├── static/                 # Fichiers statiques

│   ├── css/

│   │   └── style.css

│   └── js/

│       └── main.js

│

└── requirements.txt        # Dépendances





📦 **1. Commençons par installer les dépendances**

Crée un fichier requirements.txt :



fastapi==0.104.1

uvicorn\[standard]==0.24.0

sqlalchemy==2.0.23

jinja2==3.1.2

python-multipart==0.0.6

passlib\[bcrypt]==1.7.4

python-jose\[cryptography]==3.3.0

python-dotenv==1.0.0

Installe tout :



**bash**

pip install -r requirements.txt

Frontend	HTML5, CSS3, Bootstrap 5, JavaScript, Chart.js, Font Awesome
Backend	Python 3.11, FastAPI, Jinja2
Base de données	SQLAlchemy, SQLite
Communication	Jinja2 (templates), API REST