# Copilote multi-agents pour l'analyse des retards de production

Système multi-agents (LangGraph) qui répond à des questions du type
« Pourquoi l'OF 1042 est-il en retard ? » sur une usine pharmaceutique simulée,
en croisant les données de production (SQL) et les procédures internes (RAG).

## Architecture

```
question ──> SUPERVISEUR ──> agent_data  (get_schema, run_sql)  ──┐
                 ▲     └───> agent_docs  (search_sop = RAG)    ──┤
                 └──────────────────────────────────────────────┘
                 └───> agent_redacteur ──> diagnostic final ──> FIN
```

| Composant | Rôle | Choix technique |
|---|---|---|
| Superviseur | Décide du prochain agent | Sortie structurée Pydantic (`Routage`) |
| agent_data | Text-to-SQL sur la base | Agent ReAct, outils `get_schema` + `run_sql` |
| agent_docs | Recherche dans les SOP | RAG : chunking 400/80, embeddings, top-k=3 |
| agent_redacteur | Diagnostic cause / preuves / actions | Prompt strict, interdiction d'inventer |
| État partagé | Messages de chaque agent | `TypedDict` + reducer `add_messages` |

## Garde-fous
- SQL en lecture seule (regex SELECT + connexion SQLite `mode=ro`) et limite de 50 lignes
- Les erreurs SQL sont renvoyées à l'agent qui corrige sa requête
- `MAX_ETAPES` et `recursion_limit` contre les boucles infinies
- Température 0, citations de sources obligatoires

## Évaluation
Les causes de retard sont injectées dans `data.py` (panne machine, rupture de stock,
non-conformité qualité), on connaît donc la vérité terrain. `evaluate.py` mesure :
- la **trajectoire** (les bons agents ont-ils été appelés, dans le bon ordre ?)
- la **justesse** du diagnostic final

## Lancer
```bash
pip install -r requirements.txt
export OPENAI_API_KEY=...            # ou LLM_MODEL=mistralai:... / ollama:...
python data.py                       # génère usine.db
python graph.py "Pourquoi l'OF 1043 est-il en retard ?"
python evaluate.py
streamlit run app.py
```

## Pistes d'amélioration
- Exécuter agent_data et agent_docs en parallèle pour réduire la latence
- Recherche hybride (BM25 + vecteurs) et reranking sur les SOP
- Validation humaine (`interrupt` LangGraph) avant toute action réelle
- Traçage de chaque étape avec LangSmith
- En production : brancher sur les vraies sources (MES, ERP) via Databricks
