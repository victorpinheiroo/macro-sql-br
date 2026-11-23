"""Streamlit front end. Renders what the API returns; no logic of its own.

streamlit run app/streamlit_app.py      (API_URL defaults to http://localhost:8000)
"""

from __future__ import annotations

import os

import httpx
import streamlit as st

API = os.environ.get("API_URL", "http://localhost:8000")
PCT = {"ipca", "selic", "juro_real", "selic_meta", "answer"}
LEVEL = {"high": "alta", "medium": "média", "low": "baixa", "none": "—"}

st.set_page_config(page_title="Macro SQL BR", page_icon="📈", layout="centered")
st.title("Macro SQL BR")
st.caption(
    "Juros, inflação e Selic em linguagem natural. O modelo interpreta; "
    "a conta sai de uma camada de métricas governada."
)


@st.cache_data(ttl=300)
def metrics() -> list[dict]:
    return httpx.get(f"{API}/v1/metrics", timeout=10).json()["metrics"]


with st.sidebar:
    st.subheader("Catálogo")
    try:
        for m in metrics():
            st.markdown(
                f"**{m['label']}**  \n`{m['name']}` · último dado: {m['last_complete_ref_date']}"
            )
    except httpx.HTTPError:
        st.error(f"API indisponível em {API}")
    st.divider()
    st.caption("Exemplos")
    for ex in (
        "Quanto foi a inflação de 2024?",
        "Qual o juro real em 2023?",
        "Qual a meta Selic hoje?",
        "Qual mês de 2024 teve a maior inflação?",
    ):
        if st.button(ex, use_container_width=True):
            st.session_state.q = ex

q = st.text_input(
    "Pergunta", key="q", placeholder="Ex.: IPCA acumulado em 12 meses até junho de 2025"
)


def ask(question: str) -> dict | None:
    try:
        r = httpx.post(f"{API}/v1/ask", json={"question": question}, timeout=120)
    except httpx.HTTPError as e:
        st.error(f"Falha ao chamar a API: {e}")
        return None
    if r.status_code != 200:
        st.error(r.json().get("detail", r.text))
        return None
    return r.json()


if q:
    with st.spinner("Planejando e calculando..."):
        a = ask(q)
    if a:
        path = a["path"]
        if path in ("metrics", "free_sql"):
            for name, value in (a["values"] or {}).items():
                label = name if name != "answer" else "resposta"
                shown = f"{value:,.2f}%" if name in PCT and value is not None else value
                st.metric(label, shown)
            conf = a["confidence"]
            st.markdown(f"Confiança **{LEVEL[conf['level']]}** ({conf['score']:.2f})")
            for reason in conf["reasons"]:
                st.caption(f"• {reason}")
            if path == "free_sql":
                st.warning("Resposta fora do catálogo de métricas: SQL escrito pelo modelo.")
        elif path == "clarify":
            st.info(a["message"])
            for opt in a["options"]:
                if st.button(opt):
                    st.session_state.q = opt
                    st.rerun()
        else:
            st.info(a["message"])
        if a.get("plan"):
            st.caption(f"Plano: {a['plan']}")
        if a.get("sql"):
            with st.expander("SQL executado"):
                st.code(a["sql"], language="sql")
        st.caption(f"Modelo: {a['model']} · {a['latency_ms']} ms · dados até {a['data_as_of']}")
