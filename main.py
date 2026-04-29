"""
Elements Impact — Article Search API
Moteur de recherche d'articles scientifiques + extraction d'effect sizes
"""

import os
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from anthropic import Anthropic

# ══════════════════════════════════════════════════════════════════
# App setup
# ══════════════════════════════════════════════════════════════════

app = FastAPI(
    title="Elements Impact — Article Search API",
    description="Moteur de recherche d'articles scientifiques pour l'évaluation d'impact",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

anthropic = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

OPENALEX_BASE = "https://api.openalex.org"
OPENALEX_EMAIL = os.environ.get("OPENALEX_EMAIL", "contact@elementsimpact.fr")

# ══════════════════════════════════════════════════════════════════
# Schemas
# ══════════════════════════════════════════════════════════════════

class ProjectInput(BaseModel):
    title: str
    description: str
    target_group: str | None = None  # ex: "jeunes en décrochage scolaire"
    intervention_type: str | None = None  # ex: "mentorat", "formation"

class PredictorsResponse(BaseModel):
    predictors: list[str]
    search_queries: list[str]
    reasoning: str

class Article(BaseModel):
    title: str
    authors: list[str]
    year: int | None
    doi: str | None
    abstract: str | None
    open_access_url: str | None
    cited_by_count: int
    relevance_score: float | None

class SearchResponse(BaseModel):
    query_used: str
    articles: list[Article]
    total_found: int

class EffectSizeInput(BaseModel):
    project_description: str
    abstract: str
    title: str

class EffectSizeResponse(BaseModel):
    effect_size: str | None
    metric: str | None       # Cohen's d, Hedge's g, OR, etc.
    interpretation: str | None
    confidence: str          # high / medium / low
    excerpt: str | None

# ══════════════════════════════════════════════════════════════════
# Routes
# ══════════════════════════════════════════════════════════════════

@app.get("/health")
def health():
    return {"status": "ok", "service": "elements-impact-api"}


@app.get("/")
def root():
    return {
        "service": "Elements Impact Article Search API",
        "endpoints": ["/health", "/predictors", "/search", "/effect-size", "/docs"]
    }


@app.post("/predictors", response_model=PredictorsResponse)
async def get_predictors(project: ProjectInput):
    """
    À partir de la description d'un projet, retourne :
    - les prédicteurs Margolis pertinents
    - les requêtes de recherche suggérées pour OpenAlex
    """
    prompt = f"""Tu es un expert en évaluation d'impact social et en recherche scientifique.

Voici un projet :
- Titre : {project.title}
- Description : {project.description}
- Groupe cible : {project.target_group or "non précisé"}
- Type d'intervention : {project.intervention_type or "non précisé"}

Ta tâche :
1. Identifie 4 à 6 prédicteurs d'impact pertinents selon le cadre Margolis & Raven (outcomes mesurables, variables intermédiaires, mécanismes causaux).
2. Génère 3 requêtes de recherche en anglais optimisées pour OpenAlex (concises, avec termes MeSH ou keywords scientifiques).
3. Explique brièvement ton raisonnement.

Réponds UNIQUEMENT en JSON valide, sans markdown :
{{
  "predictors": ["...", "...", "..."],
  "search_queries": ["...", "...", "..."],
  "reasoning": "..."
}}"""

    message = anthropic.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )

    import json
    try:
        data = json.loads(message.content[0].text)
        return PredictorsResponse(**data)
    except Exception:
        raise HTTPException(status_code=500, detail="Erreur de parsing LLM")


@app.post("/search", response_model=SearchResponse)
async def search_articles(project: ProjectInput):
    """
    Recherche des articles scientifiques pertinents via OpenAlex
    en fonction de la description du projet.
    """
    # 1. Générer une query optimisée via LLM
    prompt = f"""Génère UNE requête de recherche scientifique en anglais pour OpenAlex.
Projet : {project.title} — {project.description}
Groupe cible : {project.target_group or "général"}

Règles : 2-5 mots-clés, termes académiques, pas d'opérateurs booléens complexes.
Réponds UNIQUEMENT avec la requête, rien d'autre."""

    message = anthropic.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=100,
        messages=[{"role": "user", "content": prompt}]
    )
    query = message.content[0].text.strip().strip('"')

    # 2. Appel OpenAlex
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{OPENALEX_BASE}/works",
            params={
                "search": query,
                "filter": "is_oa:true,type:article",
                "sort": "cited_by_count:desc",
                "per-page": 8,
                "select": "title,authorships,publication_year,doi,abstract_inverted_index,open_access,cited_by_count,relevance_score",
                "mailto": OPENALEX_EMAIL,
            },
            timeout=15.0
        )

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Erreur OpenAlex")

    data = resp.json()
    results = data.get("results", [])

    articles = []
    for r in results:
        # Reconstruit l'abstract depuis l'inverted index
        abstract = _reconstruct_abstract(r.get("abstract_inverted_index"))
        authors = [
            a["author"]["display_name"]
            for a in (r.get("authorships") or [])[:3]
            if a.get("author")
        ]
        articles.append(Article(
            title=r.get("title") or "",
            authors=authors,
            year=r.get("publication_year"),
            doi=r.get("doi"),
            abstract=abstract,
            open_access_url=r.get("open_access", {}).get("oa_url"),
            cited_by_count=r.get("cited_by_count", 0),
            relevance_score=r.get("relevance_score"),
        ))

    return SearchResponse(
        query_used=query,
        articles=articles,
        total_found=data.get("meta", {}).get("count", len(articles)),
    )


@app.post("/effect-size", response_model=EffectSizeResponse)
async def extract_effect_size(payload: EffectSizeInput):
    """
    Extrait la taille d'effet (Cohen's d, Hedge's g, OR…)
    depuis l'abstract d'un article, en contexte du projet.
    """
    prompt = f"""Tu es un expert en méta-analyse et en évaluation d'impact.

Projet évalué : {payload.project_description}

Article :
Titre : {payload.title}
Abstract : {payload.abstract}

Extrais la taille d'effet principale rapportée dans cet abstract.
Réponds UNIQUEMENT en JSON valide, sans markdown :
{{
  "effect_size": "0.45",
  "metric": "Cohen's d",
  "interpretation": "effet modéré, amélioration significative du score de lecture",
  "confidence": "high",
  "excerpt": "passage exact de l'abstract mentionnant l'effet"
}}

Si aucun effet n'est trouvé, mets null pour effect_size, metric, interpretation et excerpt, et "low" pour confidence."""

    message = anthropic.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}]
    )

    import json
    try:
        data = json.loads(message.content[0].text)
        return EffectSizeResponse(**data)
    except Exception:
        raise HTTPException(status_code=500, detail="Erreur de parsing LLM")


# ══════════════════════════════════════════════════════════════════
# Utils
# ══════════════════════════════════════════════════════════════════

def _reconstruct_abstract(inverted_index: dict | None) -> str | None:
    """Reconstruit un abstract depuis l'inverted index OpenAlex."""
    if not inverted_index:
        return None
    tokens = {}
    for word, positions in inverted_index.items():
        for pos in positions:
            tokens[pos] = word
    return " ".join(tokens[i] for i in sorted(tokens))
