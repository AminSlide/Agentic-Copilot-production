"""Orchestration multi-agents avec LangGraph (pattern superviseur).

            +-------------+
   question |             |---> agent_data  (SQL) ----+
   -------> | superviseur |---> agent_docs  (RAG) ----+--> retour au superviseur
            |             |---> agent_redacteur ------> FIN
            +-------------+
"""
from typing import Annotated, Literal, TypedDict

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

from config import get_llm
from tools import get_schema, run_sql, search_sop

MAX_ETAPES = 6  # garde-fou anti-boucle infinie


# ------------------------------------------------------------------ etat partage
class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]  # historique, on ajoute sans ecraser
    next: str
    etapes: int


# ------------------------------------------------------------------ superviseur
class Routage(BaseModel):
    """Sortie structuree du superviseur : evite les reponses floues."""
    next: Literal["agent_data", "agent_docs", "agent_redacteur"] = Field(
        description="Prochain agent a appeler")
    raison: str = Field(description="Justification courte du choix")


PROMPT_SUPERVISEUR = """Tu coordonnes une equipe d'agents qui diagnostique des retards de production.
- agent_data : interroge la base de production (OF, incidents machine, stocks, qualite).
- agent_docs : cherche dans les procedures internes (SOP) les regles et actions recommandees.
- agent_redacteur : redige le diagnostic final. A appeler UNIQUEMENT quand on a
  a la fois les faits chiffres (agent_data) et les procedures pertinentes (agent_docs).
Regarde ce qui a deja ete obtenu dans la conversation et choisis l'etape suivante."""


def superviseur(state: State) -> dict:
    if state.get("etapes", 0) >= MAX_ETAPES:
        return {"next": "agent_redacteur"}
    routeur = get_llm().with_structured_output(Routage)
    decision = routeur.invoke([SystemMessage(PROMPT_SUPERVISEUR)] + state["messages"])
    return {"next": decision.next, "etapes": state.get("etapes", 0) + 1}


# ------------------------------------------------------------------ agents specialises
PROMPT_DATA = """Tu es un analyste data d'usine pharmaceutique.
Appelle toujours get_schema avant d'ecrire du SQL. N'ecris que des SELECT.
Si une requete echoue, lis l'erreur et corrige-la.
Pour un OF en retard, verifie : incidents sur sa machine autour de la date prevue,
stock des matieres de son produit (table nomenclature) vs seuil, resultat du controle qualite.
Termine par un resume factuel avec les chiffres trouves."""

PROMPT_DOCS = """Tu es un expert des procedures internes.
Utilise search_sop pour trouver les procedures liees aux faits deja identifies.
Resume uniquement ce que disent les documents et cite toujours la source entre crochets."""

PROMPT_REDACTEUR = """Tu rediges un diagnostic pour le responsable de ligne.
Format :
1. Cause probable
2. Preuves (chiffres issus des donnees)
3. Actions recommandees (issues des procedures, avec la source)
N'invente rien : chaque affirmation doit venir des messages precedents.
Si les preuves sont insuffisantes, dis-le clairement."""


def _agent_node(name: str, agent):
    """Lance un agent ReAct et ne remonte que sa conclusion dans l'etat partage."""
    def node(state: State) -> dict:
        result = agent.invoke({"messages": state["messages"]})
        conclusion = result["messages"][-1].content
        return {"messages": [AIMessage(content=conclusion, name=name)]}
    return node


def redacteur(state: State) -> dict:
    reponse = get_llm().invoke([SystemMessage(PROMPT_REDACTEUR)] + state["messages"])
    return {"messages": [AIMessage(content=reponse.content, name="agent_redacteur")]}


# ------------------------------------------------------------------ construction du graphe
def build_graph():
    llm = get_llm()
    agent_data = create_agent(llm, tools=[get_schema, run_sql], system_prompt=PROMPT_DATA)
    agent_docs = create_agent(llm, tools=[search_sop], system_prompt=PROMPT_DOCS)

    g = StateGraph(State)
    g.add_node("superviseur", superviseur)
    g.add_node("agent_data", _agent_node("agent_data", agent_data))
    g.add_node("agent_docs", _agent_node("agent_docs", agent_docs))
    g.add_node("agent_redacteur", redacteur)

    g.add_edge(START, "superviseur")
    g.add_conditional_edges("superviseur", lambda s: s["next"],
                            ["agent_data", "agent_docs", "agent_redacteur"])
    g.add_edge("agent_data", "superviseur")
    g.add_edge("agent_docs", "superviseur")
    g.add_edge("agent_redacteur", END)
    return g.compile()


def diagnostiquer(question: str, monitorer: bool = True) -> dict:
    """Point d'entree : renvoie l'etat final (messages de chaque agent + trajectoire).

    Avec monitorer=True, un callback collecte latence, tokens et erreurs d'outils,
    ecrit une ligne dans runs.jsonl et ajoute les metriques dans etat["metriques"].
    """
    from monitoring import RunMonitor, log_run

    graph = build_graph()
    config = {"recursion_limit": 25}
    monitor = RunMonitor() if monitorer else None
    if monitor:
        config["callbacks"] = [monitor]
    etat = graph.invoke({"messages": [HumanMessage(question)], "etapes": 0}, config=config)
    if monitor:
        run = monitor.summary(question, etat)
        log_run(run)
        etat["metriques"] = run
    return etat


if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "Pourquoi l'OF 1042 est-il en retard ?"
    etat = diagnostiquer(q)
    for m in etat["messages"]:
        print(f"\n=== {getattr(m, 'name', None) or 'question'} ===\n{m.content}")
    print("\n=== metriques ===")
    for k, v in etat["metriques"].items():
        print(f"{k:24} {v}")
