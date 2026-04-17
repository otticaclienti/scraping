from __future__ import annotations

import streamlit as st

import api_client as api

st.set_page_config(page_title="Nuovo Job", layout="wide")
st.title("Nuovo Job")

with st.form("new_job"):
    name = st.text_input("Nome job", value="Scraping batch")

    col1, col2 = st.columns(2)
    with col1:
        uploaded = st.file_uploader(
            "Lista URL (CSV/TXT, un URL per riga)", type=["txt", "csv"]
        )
    with col2:
        urls_text = st.text_area(
            "Oppure incolla URL qui (uno per riga)",
            height=200,
            placeholder="https://example.com\nhttps://altro.it",
        )

    st.markdown("### Configurazione crawler")
    c1, c2, c3 = st.columns(3)
    with c1:
        concurrency = st.slider("Concorrenza (richieste parallele)", 5, 200, 50, 5)
        timeout = st.slider("Timeout per pagina (s)", 5, 60, 15)
    with c2:
        max_pages = st.slider("Pagine max per sito", 1, 30, 8)
        max_attempts = st.slider("Tentativi max per pagina", 1, 5, 2)
    with c3:
        render_js = st.checkbox(
            "Fallback JS con Playwright (più email, più lento)", value=True
        )
        verify_mx = st.checkbox("Verifica MX record (più lento)", value=False)
        follow_sitemap = st.checkbox("Parsa sitemap.xml", value=True)

    user_agent = st.text_input("User-Agent (lascia vuoto per default)", value="")

    submitted = st.form_submit_button("Avvia job", type="primary")

if submitted:
    if not uploaded and not urls_text.strip():
        st.error("Carica un file o incolla almeno un URL")
    else:
        config = {
            "concurrency": concurrency,
            "timeout_seconds": timeout,
            "max_pages_per_site": max_pages,
            "max_attempts": max_attempts,
            "render_js_fallback": render_js,
            "verify_mx": verify_mx,
            "follow_sitemap": follow_sitemap,
            "user_agent": user_agent or None,
        }
        try:
            file_bytes = uploaded.read() if uploaded else None
            filename = uploaded.name if uploaded else None
            result = api.create_job(
                name=name,
                config=config,
                urls_text=urls_text,
                file_bytes=file_bytes,
                filename=filename,
            )
            st.success(
                f"Job #{result['id']} creato con {result['total_sites']} URL. Vai su **Dettaglio Job**."
            )
        except Exception as exc:
            st.error(f"Errore: {exc}")
