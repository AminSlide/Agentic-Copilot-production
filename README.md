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

## Monitoring
Trois niveaux, dans `monitoring.py` :

| Niveau | Ce qui est suivi | Comment |
|---|---|---|
| Traces détaillées | Chaque appel LLM et outil, prompts et réponses | LangSmith, via `LANGSMITH_TRACING=true` et `LANGSMITH_API_KEY` |
| Métriques par exécution | Trajectoire, latence, tokens, appels d'outils, erreurs SQL | Callback LangChain propagé à tout le graphe, une ligne JSON par exécution dans `runs.jsonl` |
| Alertes | Latence > 60 s, taux d'erreur SQL > 30 %, limite d'étapes atteinte, exécution sans diagnostic | Règles dans `alertes()`, affichées dans Streamlit |

`python monitoring.py` affiche les agrégats (taux de diagnostic, latence p50/p95, tokens moyens,
taux d'erreur SQL, appels par agent). L'onglet **Monitoring** de l'app Streamlit montre les mêmes
indicateurs et les dernières exécutions.

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
