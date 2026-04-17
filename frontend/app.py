from __future__ import annotations

import streamlit as st

import api_client as api

st.set_page_config(page_title="Email Scraper", layout="wide", page_icon="@")

st.title("Email Scraper")
st.caption("Estrai email da liste di siti web — controllo completo via UI")

with st.sidebar:
    st.header("Stato servizio")
    try:
        jobs = api.list_jobs()
        st.success(f"Backend connesso ({len(jobs)} job)")
    except Exception as exc:
        st.error(f"Backend irraggiungibile: {exc}")
        st.stop()

st.subheader("Panoramica job")

if not jobs:
    st.info("Nessun job. Creane uno nella pagina **Nuovo Job**.")
else:
    import pandas as pd

    rows = []
    for j in jobs:
        try:
            stats = api.job_stats(j["id"])
        except Exception:
            stats = {}
        rows.append(
            {
                "ID": j["id"],
                "Nome": j["name"],
                "Stato": j["status"],
                "Siti": j["total_sites"],
                "Fatti": stats.get("done", 0),
                "Falliti": stats.get("failed", 0),
                "Email": stats.get("emails_total", 0),
                "Creato": j["created_at"][:19].replace("T", " "),
            }
        )
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

st.markdown(
    """
**Pagine disponibili (menu a sinistra):**
- **Nuovo Job** — carica una lista di URL e avvia il crawler
- **Dettaglio Job** — stato, controlli (pause/stop/resume/retry), lista siti
- **Email** — sfoglia, cerca, esporta in CSV
- **Blacklist** — domini da escludere
"""
)
