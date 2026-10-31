"""Choix du fournisseur de LLM, modifiable via variables d'environnement.

Exemples :
    LLM_MODEL=mistralai:mistral-large-latest   EMB_MODEL=mistralai:mistral-embed
    LLM_MODEL=openai:gpt-4o-mini               EMB_MODEL=openai:text-embedding-3-small
    LLM_MODEL=ollama:llama3.1                  EMB_MODEL=ollama:nomic-embed-text   (100 % local)
"""
import os

from langchain.chat_models import init_chat_model
from langchain.embeddings import init_embeddings

LLM_MODEL = os.getenv("LLM_MODEL", "openai:gpt-4o-mini")
EMB_MODEL = os.getenv("EMB_MODEL", "openai:text-embedding-3-small")


def get_llm():
    # temperature 0 : reponses stables et factuelles
    return init_chat_model(LLM_MODEL, temperature=0)


def get_embeddings():
    return init_embeddings(EMB_MODEL)
