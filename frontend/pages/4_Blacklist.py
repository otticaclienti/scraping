from __future__ import annotations

import pandas as pd
import streamlit as st

import api_client as api

st.set_page_config(page_title="Blacklist", layout="wide")
st.title("Blacklist domini")
st.caption("I domini in lista vengono saltati in tutti i job.")

with st.form("add_bl"):
    domain = st.text_input("Dominio da aggiungere", placeholder="esempio.com")
    if st.form_submit_button("Aggiungi"):
        try:
            api.add_blacklist(domain)
            st.success(f"Aggiunto: {domain}")
        except Exception as exc:
            st.error(f"Errore: {exc}")

items = api.list_blacklist()
if items:
    df = pd.DataFrame(items)
    st.dataframe(df, use_container_width=True, hide_index=True)

    to_remove = st.selectbox(
        "Rimuovi dominio", [""] + [i["domain"] for i in items]
    )
    if to_remove and st.button("Rimuovi"):
        api.remove_blacklist(to_remove)
        st.rerun()
else:
    st.info("Blacklist vuota.")
