from __future__ import annotations

import time

import pandas as pd
import streamlit as st

import api_client as api

st.set_page_config(page_title="Dettaglio Job", layout="wide")
st.title("Dettaglio Job")

try:
    jobs = api.list_jobs()
except Exception as exc:
    st.error(f"Backend irraggiungibile: {exc}")
    st.stop()

if not jobs:
    st.info("Nessun job presente.")
    st.stop()

options = {f"#{j['id']} — {j['name']} ({j['status']})": j["id"] for j in jobs}
label = st.selectbox("Seleziona job", list(options.keys()))
job_id = options[label]

auto = st.checkbox("Auto-refresh ogni 3s", value=False)

stats = api.job_stats(job_id)

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Stato", stats["status"])
c2.metric("Siti totali", stats["total_sites"])
c3.metric("Fatti", stats["done"])
c4.metric("Falliti", stats["failed"])
c5.metric("Email", stats["emails_total"])

done = stats["done"] + stats["failed"] + stats["skipped"]
progress = done / stats["total_sites"] if stats["total_sites"] else 0
st.progress(progress, text=f"{done}/{stats['total_sites']} siti processati")

st.markdown("### Controlli")
b1, b2, b3, b4, b5, b6 = st.columns(6)
with b1:
    if st.button("Pausa", use_container_width=True):
        api.pause_job(job_id)
        st.rerun()
with b2:
    if st.button("Riprendi", use_container_width=True):
        api.resume_job(job_id)
        st.rerun()
with b3:
    if st.button("Stop", use_container_width=True):
        api.stop_job(job_id)
        st.rerun()
with b4:
    if st.button("Retry falliti", use_container_width=True):
        api.retry_failed(job_id)
        st.rerun()
with b5:
    csv_bytes = None
    try:
        csv_bytes = api.fetch_csv(job_id)
    except Exception:
        pass
    st.download_button(
        "Scarica CSV",
        data=csv_bytes or b"",
        file_name=f"job_{job_id}_emails.csv",
        mime="text/csv",
        disabled=csv_bytes is None,
        use_container_width=True,
    )
with b6:
    if st.button("Elimina", type="secondary", use_container_width=True):
        if st.session_state.get(f"confirm_del_{job_id}"):
            api.delete_job(job_id)
            st.success("Job eliminato")
            st.session_state.pop(f"confirm_del_{job_id}")
            time.sleep(1)
            st.rerun()
        else:
            st.session_state[f"confirm_del_{job_id}"] = True
            st.warning("Ri-clicca per confermare eliminazione")

st.markdown("### Siti")
status_filter = st.selectbox(
    "Filtra per stato", ["(tutti)", "pending", "running", "done", "failed", "skipped"]
)
status = None if status_filter == "(tutti)" else status_filter
sites = api.list_sites(job_id, status=status, limit=1000)
if sites:
    df = pd.DataFrame(sites)
    df = df[["id", "url", "status", "emails_found", "attempts", "error", "finished_at"]]
    st.dataframe(df, use_container_width=True, hide_index=True, height=400)
else:
    st.info("Nessun sito in questo filtro.")

if auto:
    time.sleep(3)
    st.rerun()
