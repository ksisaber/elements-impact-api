"""
Elements Impact — Article Search API
Recherche d'articles scientifiques via OpenAlex (gratuit, sans clé)
"""


import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ══════════════════════════════════════════════════════════════════
# App setup
# ══════════════════════════════════════════════════════════════════

app = FastAPI(
    title="Elements Impact — Article Search API",
    description="Recherche d'articles scientifiques via OpenAlex",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

OPENALEX_BASE = "https://api.openalex.org"

# ══════════════════════════════════════════════════════════════════
# Schemas
# ══════════════════════════════════════════════════════════════════

class SearchInput(BaseModel):
    query: str
    max_results: int = 8

class Article(BaseModel):
    title: str
    authors: list[str]
    year: int | None
    doi: str | None
    abstract: str | None
    open_access_url: str | None
    cited_by_count: int

class SearchResponse(BaseModel):
    query_used: str
    total_found: int
    articles: list[Article]

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
        "endpoints": ["/health", "/search", "/docs"]
    }


@app.post("/search", response_model=SearchResponse)
async def search_articles(payload: SearchInput):
    """
    Recherche des articles scientifiques open access via OpenAlex.
    Aucune clé API requise.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{OPENALEX_BASE}/works",
            params={
                "search": payload.query,
                "filter": "is_oa:true,type:article",
                "sort": "cited_by_count:desc",
                "per-page": payload.max_results,
                "select": "title,authorships,publication_year,doi,abstract_inverted_index,open_access,cited_by_count",
                "mailto": "contact@elementsimpact.fr",
            },
            timeout=15.0
        )

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Erreur OpenAlex")

    data = resp.json()
    results = data.get("results", [])

    articles = []
    for r in results:
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
        ))

    return SearchResponse(
        query_used=payload.query,
        total_found=data.get("meta", {}).get("count", len(articles)),
        articles=articles,
    )


# ══════════════════════════════════════════════════════════════════
# Utils
# ══════════════════════════════════════════════════════════════════

def _reconstruct_abstract(inverted_index: dict | None) -> str | None:
    if not inverted_index:
        return None
    tokens = {}
    for word, positions in inverted_index.items():
        for pos in positions:
            tokens[pos] = word
    return " ".join(tokens[i] for i in sorted(tokens))
