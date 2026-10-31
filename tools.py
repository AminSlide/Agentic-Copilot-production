"""Outils mis a disposition des agents (tool calling).

Chaque fonction decoree avec @tool est decrite au LLM (nom, docstring,
parametres). Le LLM renvoie un appel structure, notre code l'execute.
"""
import re
import sqlite3
from pathlib import Path

from langchain_core.tools import tool
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import get_embeddings
from data import DB_PATH

SOP_DIR = Path(__file__).parent / "docs" / "sop"
MAX_ROWS = 50


# ---------------------------------------------------------------- outils SQL
@tool
def get_schema() -> str:
    """Renvoie le schema de la base de production (tables et colonnes).
    A appeler AVANT d'ecrire une requete SQL."""
    con = sqlite3.connect(DB_PATH)
    rows = con.execute("SELECT sql FROM sqlite_master WHERE type='table'").fetchall()
    con.close()
    return "\n\n".join(r[0] for r in rows)


@tool
def run_sql(query: str) -> str:
    """Execute une requete SQL SELECT en lecture seule sur la base de production
    et renvoie le resultat. Seules les requetes SELECT sont autorisees."""
    # Garde-fou 1 : lecture seule
    if not re.match(r"^\s*(SELECT|WITH)\b", query, re.IGNORECASE) or ";" in query.strip().rstrip(";"):
        return "ERREUR : seules les requetes SELECT simples sont autorisees."
    # Garde-fou 2 : connexion ouverte en mode read-only au niveau SQLite
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        cur = con.execute(query)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchmany(MAX_ROWS)  # Garde-fou 3 : limite de lignes
    except Exception as e:  # l'erreur est renvoyee a l'agent pour qu'il corrige sa requete
        return f"ERREUR SQL : {e}"
    finally:
        con.close()
    if not rows:
        return "Aucun resultat."
    lines = [" | ".join(cols)] + [" | ".join(str(v) for v in r) for r in rows]
    return "\n".join(lines)


# ---------------------------------------------------------------- outil RAG
_store = None


def _get_store() -> InMemoryVectorStore:
    """Indexation des SOP : chargement -> chunking -> embeddings -> vector store."""
    global _store
    if _store is None:
        splitter = RecursiveCharacterTextSplitter(chunk_size=400, chunk_overlap=80)
        texts, metas = [], []
        for path in sorted(SOP_DIR.glob("*.md")):
            for chunk in splitter.split_text(path.read_text(encoding="utf-8")):
                texts.append(chunk)
                metas.append({"source": path.name})
        _store = InMemoryVectorStore(get_embeddings())
        _store.add_texts(texts, metadatas=metas)
    return _store


@tool
def search_sop(question: str) -> str:
    """Recherche dans les procedures internes (SOP maintenance, qualite, supply)
    les passages pertinents pour une question. Renvoie les extraits avec leur source."""
    docs = _get_store().similarity_search(question, k=3)
    return "\n\n".join(f"[{d.metadata['source']}]\n{d.page_content}" for d in docs)
