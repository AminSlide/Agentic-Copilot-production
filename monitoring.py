"""Monitoring du systeme multi-agents.

Trois niveaux :
1. Traces detaillees (optionnel) : LangSmith, active par variables d'environnement
   LANGSMITH_TRACING=true et LANGSMITH_API_KEY=... -> chaque appel LLM / outil visible.
2. Metriques par execution : un callback LangChain collecte latence, tokens,
   appels d'outils et erreurs, puis ecrit une ligne JSON dans runs.jsonl.
3. Alertes : des seuils simples signalent les executions anormales.

Le callback est passe a graph.invoke(config={"callbacks": [monitor]}) et se
propage automatiquement a tous les noeuds, agents et outils.
"""
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler

LOG_PATH = Path(__file__).parent / "runs.jsonl"

# Seuils d'alerte
SEUIL_LATENCE_S = 60
SEUIL_TAUX_ERREUR_SQL = 0.3


class RunMonitor(BaseCallbackHandler):
    """Collecte les metriques d'une execution du graphe."""

    def __init__(self):
        self.t0 = time.perf_counter()
        self._starts: dict[UUID, float] = {}
        self.llm_calls = 0
        self.llm_latency_s = 0.0
        self.tokens_in = 0
        self.tokens_out = 0
        self.tool_calls: list[dict] = []

    # ---------------------------------------------------------------- LLM
    def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
        self._starts[run_id] = time.perf_counter()

    def on_llm_start(self, serialized, prompts, *, run_id, **kwargs):
        self._starts[run_id] = time.perf_counter()

    def on_llm_end(self, response, *, run_id, **kwargs):
        self.llm_calls += 1
        self.llm_latency_s += time.perf_counter() - self._starts.pop(run_id, time.perf_counter())
        try:
            usage = response.generations[0][0].message.usage_metadata or {}
            self.tokens_in += usage.get("input_tokens", 0)
            self.tokens_out += usage.get("output_tokens", 0)
        except (AttributeError, IndexError):
            pass

    # ---------------------------------------------------------------- outils
    def on_tool_start(self, serialized, input_str, *, run_id, **kwargs):
        self._starts[run_id] = time.perf_counter()
        self._starts[(run_id, "name")] = (serialized or {}).get("name") or kwargs.get("name", "?")

    def on_tool_end(self, output, *, run_id, **kwargs):
        texte = getattr(output, "content", output)
        self._record_tool(run_id, erreur=str(texte).startswith("ERREUR"))

    def on_tool_error(self, error, *, run_id, **kwargs):
        self._record_tool(run_id, erreur=True)

    def _record_tool(self, run_id, erreur: bool):
        duree = time.perf_counter() - self._starts.pop(run_id, time.perf_counter())
        nom = self._starts.pop((run_id, "name"), "?")
        self.tool_calls.append({"tool": nom, "duree_s": round(duree, 3), "erreur": erreur})

    # ---------------------------------------------------------------- synthese
    def summary(self, question: str, etat: dict) -> dict:
        trajectoire = [m.name for m in etat["messages"] if getattr(m, "name", None)]
        sql = [c for c in self.tool_calls if c["tool"] == "run_sql"]
        erreurs_sql = sum(c["erreur"] for c in sql)
        final = etat["messages"][-1].content if etat["messages"] else ""
        run = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "question": question,
            "trajectoire": trajectoire,
            "etapes_superviseur": etat.get("etapes", 0),
            "latence_totale_s": round(time.perf_counter() - self.t0, 2),
            "latence_llm_s": round(self.llm_latency_s, 2),
            "appels_llm": self.llm_calls,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "appels_outils": len(self.tool_calls),
            "requetes_sql": len(sql),
            "erreurs_sql": erreurs_sql,
            "termine_par_redacteur": bool(trajectoire) and trajectoire[-1] == "agent_redacteur",
            "preuves_insuffisantes": "insuffisant" in final.lower(),
        }
        run["alertes"] = alertes(run)
        return run


def alertes(run: dict) -> list[str]:
    """Regles simples pour signaler une execution anormale."""
    from graph import MAX_ETAPES

    out = []
    if run["latence_totale_s"] > SEUIL_LATENCE_S:
        out.append(f"latence elevee ({run['latence_totale_s']} s)")
    if run["requetes_sql"] and run["erreurs_sql"] / run["requetes_sql"] > SEUIL_TAUX_ERREUR_SQL:
        out.append(f"taux d'erreur SQL eleve ({run['erreurs_sql']}/{run['requetes_sql']})")
    if run["etapes_superviseur"] >= MAX_ETAPES:
        out.append("limite d'etapes atteinte (boucle probable)")
    if not run["termine_par_redacteur"]:
        out.append("execution terminee sans diagnostic")
    return out


def log_run(run: dict, path: Path = LOG_PATH) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(run, ensure_ascii=False) + "\n")


def load_runs(path: Path = LOG_PATH) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def rapport(runs: list[dict]) -> dict:
    """Agregats pour le suivi dans le temps (affiches dans Streamlit ou en console)."""
    if not runs:
        return {}
    lat = sorted(r["latence_totale_s"] for r in runs)
    pct = lambda p: lat[round((len(lat) - 1) * p)]
    sql = sum(r["requetes_sql"] for r in runs)
    routage: dict[str, int] = {}
    for r in runs:
        for agent in r["trajectoire"]:
            routage[agent] = routage.get(agent, 0) + 1
    return {
        "executions": len(runs),
        "taux_diagnostic": round(sum(r["termine_par_redacteur"] for r in runs) / len(runs), 2),
        "latence_p50_s": pct(0.5),
        "latence_p95_s": pct(0.95),
        "tokens_moyens": round(sum(r["tokens_in"] + r["tokens_out"] for r in runs) / len(runs)),
        "taux_erreur_sql": round(sum(r["erreurs_sql"] for r in runs) / sql, 2) if sql else 0.0,
        "executions_avec_alerte": sum(bool(r["alertes"]) for r in runs),
        "appels_par_agent": routage,
    }


if __name__ == "__main__":
    print(json.dumps(rapport(load_runs()), indent=2, ensure_ascii=False))
