"""Evaluation : on connait la vraie cause de chaque retard (injectee dans data.py).

On mesure deux choses :
- la trajectoire : est-ce que les bons agents ont ete appeles ?
- la reponse finale : est-ce que le diagnostic mentionne la bonne cause ?
"""
from data import CAUSES_CONNUES, build
from graph import diagnostiquer

MOTS_CLES = {
    "panne_machine": ["panne", "casse", "arret", "tambour", "m3"],
    "rupture_stock": ["stock", "rupture", "seuil", "enoxaparine"],
    "qualite": ["non conforme", "non-conform", "durete", "qualite"],
}


def evaluer():
    build()
    ok_cause = ok_traj = 0
    for of_id, cause in CAUSES_CONNUES.items():
        etat = diagnostiquer(f"Pourquoi l'OF {of_id} est-il en retard ?")
        agents = [m.name for m in etat["messages"] if getattr(m, "name", None)]
        final = etat["messages"][-1].content.lower()

        bonne_traj = "agent_data" in agents and agents[-1] == "agent_redacteur"
        bonne_cause = any(k in final for k in MOTS_CLES[cause])
        ok_traj += bonne_traj
        ok_cause += bonne_cause
        print(f"OF {of_id} | attendu={cause:14} | trajectoire={agents} | "
              f"cause OK={bonne_cause}")

    n = len(CAUSES_CONNUES)
    print(f"\nTrajectoires correctes : {ok_traj}/{n}")
    print(f"Causes correctes       : {ok_cause}/{n}")


if __name__ == "__main__":
    evaluer()
