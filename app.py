"""Interface Streamlit : lancer avec  streamlit run app.py"""
import streamlit as st

from data import DB_PATH, build
from graph import diagnostiquer
from monitoring import load_runs, rapport

st.set_page_config(page_title="Copilote production", page_icon="🏭")
st.title("Copilote multi-agents : retards de production")

if not DB_PATH.exists():
    build()

onglet_diag, onglet_monitoring = st.tabs(["Diagnostic", "Monitoring"])

with onglet_diag:
    question = st.text_input("Question", "Pourquoi l'OF 1042 est-il en retard ?")
    if st.button("Diagnostiquer"):
        with st.spinner("Les agents travaillent..."):
            etat = diagnostiquer(question)
        st.subheader("Diagnostic")
        st.markdown(etat["messages"][-1].content)
        m = etat["metriques"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Latence", f"{m['latence_totale_s']} s")
        c2.metric("Tokens", m["tokens_in"] + m["tokens_out"])
        c3.metric("Requetes SQL", m["requetes_sql"])
        c4.metric("Erreurs SQL", m["erreurs_sql"])
        for alerte in m["alertes"]:
            st.warning(alerte)
        with st.expander("Trajectoire des agents"):
            for msg in etat["messages"][1:-1]:
                st.markdown(f"**{msg.name}**")
                st.text(msg.content)

with onglet_monitoring:
    runs = load_runs()
    if not runs:
        st.info("Aucune execution enregistree. Lance un diagnostic pour alimenter le suivi.")
    else:
        r = rapport(runs)
        c1, c2, c3 = st.columns(3)
        c1.metric("Executions", r["executions"])
        c2.metric("Taux de diagnostic", f"{r['taux_diagnostic']:.0%}")
        c3.metric("Taux d'erreur SQL", f"{r['taux_erreur_sql']:.0%}")
        c1.metric("Latence p50", f"{r['latence_p50_s']} s")
        c2.metric("Latence p95", f"{r['latence_p95_s']} s")
        c3.metric("Tokens moyens", r["tokens_moyens"])
        st.subheader("Appels par agent")
        st.bar_chart(r["appels_par_agent"])
        st.subheader("Dernieres executions")
        st.dataframe([{k: run[k] for k in ("timestamp", "question", "latence_totale_s",
                                           "erreurs_sql", "alertes")} for run in runs[-20:]])
