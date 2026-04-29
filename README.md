# Elements Impact — Article Search API

API FastAPI pour le moteur de recherche d'articles scientifiques d'Éléments Impact.

## Endpoints

| Méthode | Route | Description |
|---|---|---|
| GET | `/health` | Healthcheck (utilisé par Coolify) |
| GET | `/docs` | Swagger UI interactif |
| POST | `/predictors` | Génère les prédicteurs Margolis + requêtes de recherche |
| POST | `/search` | Recherche d'articles via OpenAlex |
| POST | `/effect-size` | Extrait la taille d'effet depuis un abstract |

---

## Variables d'environnement

| Variable | Requis | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | Clé API Anthropic |
| `OPENALEX_EMAIL` | ❌ | Email pour le pool poli OpenAlex (optionnel) |

---

## Lancer en local

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
uvicorn main:app --reload
# → http://localhost:8000/docs
```

## Lancer avec Docker

```bash
docker build -t elements-impact-api .
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=sk-ant-... elements-impact-api
```

---

## Déploiement sur Coolify

1. Crée un compte sur https://app.coolify.io
2. New Resource → Application → Public Git Repo
3. Colle l'URL du repo GitHub
4. Coolify détecte le `Dockerfile` automatiquement
5. Dans **Environment Variables** : ajoute `ANTHROPIC_API_KEY`
6. Port : `8000`
7. **Deploy** → Coolify génère une URL HTTPS automatiquement

---

## Exemple d'utilisation

### POST /predictors
```json
{
  "title": "Programme de mentorat scolaire",
  "description": "Accompagnement individualisé de jeunes en décrochage scolaire par des mentors bénévoles",
  "target_group": "adolescents 13-18 ans en décrochage",
  "intervention_type": "mentorat"
}
```

### POST /search
```json
{
  "title": "Programme de mentorat scolaire",
  "description": "Accompagnement individualisé de jeunes en décrochage scolaire",
  "target_group": "adolescents en décrochage"
}
```

### POST /effect-size
```json
{
  "project_description": "Programme de mentorat scolaire pour adolescents",
  "title": "Effects of mentoring on academic achievement",
  "abstract": "This RCT evaluated a school-based mentoring program... Cohen's d = 0.42 (p < 0.01)..."
}
```
