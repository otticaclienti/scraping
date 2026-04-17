from __future__ import annotations

import pandas as pd
import streamlit as st

import api_client as api

st.set_page_config(page_title="Email", layout="wide")
st.title("Email raccolte")

try:
    jobs = api.list_jobs()
except Exception as exc:
    st.error(f"Backend irraggiungibile: {exc}")
    st.stop()

c1, c2, c3 = st.columns([2, 2, 1])
with c1:
    job_options = {"(tutti i job)": None} | {f"#{j['id']} — {j['name']}": j["id"] for j in jobs}
    job_label = st.selectbox("Job", list(job_options.keys()))
    job_filter = job_options[job_label]
with c2:
    search = st.text_input("Cerca", placeholder="@example.com oppure parola")
with c3:
    limit = st.selectbox("Limite", [100, 500, 1000, 5000], index=1)

try:
    counts = api.count_emails(job_filter)
    st.caption(f"Totale: {counts['total']}  —  Distinte: {counts['distinct']}")
except Exception:
    pass

emails = api.list_emails(job_id=job_filter, q=search or None, limit=limit)
if not emails:
    st.info("Nessuna email trovata.")
else:
    df = pd.DataFrame(emails)
    df = df[["email", "site_id", "job_id", "source_page", "found_at"]]
    st.dataframe(df, use_container_width=True, hide_index=True, height=600)

    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Scarica visualizzate (CSV)",
        data=csv,
        file_name="emails.csv",
        mime="text/csv",
    )
