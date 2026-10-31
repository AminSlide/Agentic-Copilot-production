"""Interface Streamlit : lancer avec  streamlit run app.py"""
import streamlit as st

from data import DB_PATH, build
from graph import diagnostiquer

st.set_page_config(page_title="Copilote production", page_icon="🏭")
st.title("Copilote multi-agents : retards de production")

if not DB_PATH.exists():
    build()

question = st.text_input("Question", "Pourquoi l'OF 1042 est-il en retard ?")
if st.button("Diagnostiquer"):
    with st.spinner("Les agents travaillent..."):
        etat = diagnostiquer(question)
    st.subheader("Diagnostic")
    st.markdown(etat["messages"][-1].content)
    with st.expander("Trajectoire des agents"):
        for m in etat["messages"][1:-1]:
            st.markdown(f"**{m.name}**")
            st.text(m.content)
