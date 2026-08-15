"""
app.py
------
Interface Streamlit do Assistente Especialista em Dados.
Chat interativo com histórico, sidebar informativa e formatação rica.
"""

import streamlit as st
import sqlite3
import os

# ── Configuração da Página ────────────────────────────────────────────
st.set_page_config(
    page_title="Assistente SQL | Especialista em Dados",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS Customizado ───────────────────────────────────────────────────
st.markdown("""
<style>
    /* Tema geral */
    .stApp {
        background: linear-gradient(135deg, #0f0f23 0%, #1a1a3e 50%, #0f0f23 100%);
    }

    /* Header customizado */
    .main-header {
        text-align: center;
        padding: 1.5rem 0 1rem;
    }
    .main-header h1 {
        background: linear-gradient(135deg, #818cf8, #6366f1, #a78bfa);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.2rem;
        font-weight: 800;
        margin-bottom: 0.3rem;
    }
    .main-header p {
        color: #a1a1aa;
        font-size: 0.95rem;
    }

    /* Cards da sidebar */
    .sidebar-card {
        background: rgba(99, 102, 241, 0.08);
        border: 1px solid rgba(99, 102, 241, 0.2);
        border-radius: 12px;
        padding: 1rem;
        margin-bottom: 0.8rem;
    }
    .sidebar-card h4 {
        color: #818cf8;
        margin: 0 0 0.5rem 0;
        font-size: 0.85rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .sidebar-card p, .sidebar-card li {
        color: #d4d4d8;
        font-size: 0.82rem;
        line-height: 1.5;
    }

    /* Status badge */
    .status-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 999px;
        font-size: 0.75rem;
        font-weight: 700;
    }
    .status-online {
        background: rgba(16, 185, 129, 0.15);
        color: #10b981;
        border: 1px solid rgba(16, 185, 129, 0.3);
    }
    .status-offline {
        background: rgba(239, 68, 68, 0.15);
        color: #ef4444;
        border: 1px solid rgba(239, 68, 68, 0.3);
    }

    /* Esconder elementos padrão do Streamlit */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    /* Chat input styling */
    .stChatInput > div {
        border-color: rgba(99, 102, 241, 0.3) !important;
    }
    .stChatInput > div:focus-within {
        border-color: #6366f1 !important;
        box-shadow: 0 0 0 1px #6366f1 !important;
    }
</style>
""", unsafe_allow_html=True)


# ── Sidebar ───────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🤖 Assistente SQL")
    st.markdown("---")

    # Status do banco
    db_exists = os.path.exists("vendas.db")
    if db_exists:
        st.markdown(
            '<span class="status-badge status-online">● Banco Conectado</span>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<span class="status-badge status-offline">● Banco Não Encontrado</span>',
            unsafe_allow_html=True,
        )

    # Status da API Key
    api_key = os.environ.get("GOOGLE_API_KEY", "")
    if api_key:
        st.markdown(
            '<span class="status-badge status-online">● Gemini Conectado</span>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<span class="status-badge status-offline">● API Key Ausente</span>',
            unsafe_allow_html=True,
        )
        st.markdown("---")
        manual_key = st.text_input(
            "🔑 Cole sua Google API Key:",
            type="password",
            help="Obtenha em: https://aistudio.google.com/app/apikey",
        )
        if manual_key:
            os.environ["GOOGLE_API_KEY"] = manual_key
            st.success("✅ API Key configurada!")
            st.rerun()

    st.markdown("---")

    # Info do banco
    if db_exists:
        st.markdown('<div class="sidebar-card">', unsafe_allow_html=True)
        st.markdown("#### 📊 Catálogo do Banco")
        try:
            conn = sqlite3.connect("vendas.db")
            cursor = conn.cursor()

            tabelas = cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()

            for (tabela,) in tabelas:
                colunas = cursor.execute(f"PRAGMA table_info({tabela})").fetchall()
                count = cursor.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
                col_names = [c[1] for c in colunas]

                st.markdown(f"**🗂️ {tabela}** ({count} registros)")
                st.caption(", ".join(col_names))

            conn.close()
        except Exception as e:
            st.error(f"Erro ao ler banco: {e}")
        st.markdown("</div>", unsafe_allow_html=True)

    # Exemplos de perguntas
    st.markdown('<div class="sidebar-card">', unsafe_allow_html=True)
    st.markdown("#### 💡 Exemplos de Perguntas")
    st.markdown("""
- Qual o total de vendas por estado?
- Top 5 produtos mais vendidos
- Qual cliente gerou mais receita?
- Vendas por categoria no último trimestre
- Ticket médio por segmento de cliente
    """)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("---")
    st.caption("Assistente Especialista em Dados v1.0")
    st.caption("Powered by Gemini + LangChain")


# ── Header Principal ──────────────────────────────────────────────────
st.markdown("""
<div class="main-header">
    <h1>🤖 Assistente Especialista em Dados</h1>
    <p>Pergunte em linguagem natural. Receba SQL otimizado e insights instantâneos.</p>
</div>
""", unsafe_allow_html=True)

# ── Histórico de Chat ─────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": (
                "👋 Olá! Sou o **Assistente Especialista em Dados**.\n\n"
                "Posso ajudar você a:\n"
                "- 🔍 **Identificar tabelas e colunas** relevantes\n"
                "- 🎯 **Aplicar filtros e agregações** (temporal, geográfico, categórico)\n"
                "- 💻 **Gerar SQL otimizado** pronto para execução\n"
                "- 📊 **Explicar a lógica** por trás das transformações\n\n"
                "Faça sua primeira pergunta!"
            ),
        }
    ]

# Exibir mensagens anteriores
for message in st.session_state.messages:
    with st.chat_message(message["role"], avatar="🤖" if message["role"] == "assistant" else "👤"):
        st.markdown(message["content"])

# ── Input do Usuário ──────────────────────────────────────────────────
if prompt := st.chat_input("Digite sua pergunta sobre os dados..."):
    # Adicionar mensagem do usuário
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)

    # Gerar resposta
    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("🔄 Analisando sua pergunta e gerando SQL..."):
            try:
                from agent import ask
                response = ask(prompt)
            except ValueError as ve:
                response = str(ve)
            except Exception as e:
                response = (
                    f"❌ **Erro inesperado:** {str(e)}\n\n"
                    "Verifique se a API Key do Gemini está configurada corretamente."
                )

        st.markdown(response)

    # Salvar resposta no histórico
    st.session_state.messages.append({"role": "assistant", "content": response})
