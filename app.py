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
    st.markdown(
        '<span class="status-badge status-online">● Conectado ao BigQuery (Base dos Dados)</span>',
        unsafe_allow_html=True,
    )

    # Status da API Key
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        try:
            api_key = st.secrets.get("GROQ_API_KEY", "")
        except:
            pass

    if api_key:
        st.markdown(
            '<span class="status-badge status-online">● Groq Conectado</span>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<span class="status-badge status-offline">● API Key Ausente</span>',
            unsafe_allow_html=True,
        )
        st.markdown("---")
        manual_key = st.text_input(
            "🔑 Cole sua Groq API Key:",
            type="password",
            help="Obtenha em: https://console.groq.com/keys",
        )
        if manual_key:
            os.environ["GROQ_API_KEY"] = manual_key
            st.success("✅ API Key configurada!")
            st.rerun()

    st.markdown("---")

    # Info do banco
    st.markdown('<div class="sidebar-card">', unsafe_allow_html=True)
    st.markdown("#### 📊 BigQuery / Base dos Dados")
    st.markdown("O assistente agora está conectado ao catálogo público da Base dos Dados via Google BigQuery.")
    st.markdown("Você pode explorar dados de IBGE, TSE, INEP, entre outros.")
    st.markdown("</div>", unsafe_allow_html=True)

    # Exemplos de perguntas
    st.markdown('<div class="sidebar-card">', unsafe_allow_html=True)
    st.markdown("#### 💡 Exemplos de Perguntas")
    st.markdown("""
- Qual a população dos municípios de SP em 2022 segundo o IBGE?
- Mostre os 5 municípios com maior PIB per capita no último ano disponível.
- Qual a taxa de desemprego atual do Brasil segundo a PNAD?
- Quantos votos o candidato X teve em SP nas últimas eleições?
- Mostre as 5 escolas com melhor nota do ENEM no Ceará.
    """)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("---")
    st.caption("Assistente Especialista em Dados v1.0")
    st.caption("Powered by Groq (LLaMA 3) + LangChain")


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

# Função auxiliar para renderizar a resposta rica
def render_message(msg_content):
    if isinstance(msg_content, str):
        st.markdown(msg_content)
    elif isinstance(msg_content, dict):
        if "error" in msg_content:
            st.error(msg_content["error"])
            if "sql" in msg_content:
                with st.expander("Ver SQL Gerado"):
                    st.code(msg_content["sql"], language="sql")
        else:
            # 1. Análise
            st.markdown(msg_content.get("analysis", ""))
            
            # 2. Código SQL (Oculto)
            with st.expander("💻 Ver Código SQL"):
                st.code(msg_content.get("sql", ""), language="sql")
            
            # 3. Tabela de Dados Interativa
            st.markdown("### 🗂️ Dados Extraídos")
            df = msg_content.get("dataframe")
            st.dataframe(df, use_container_width=True)
            
            # Botão de Download CSV
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Baixar Dados (CSV)",
                data=csv,
                file_name="dados_extracao.csv",
                mime="text/csv",
            )
            
            # 4. Gráfico (se aplicável)
            chart = msg_content.get("chart_config", {})
            chart_type = chart.get("type", "none")
            if chart_type in ["bar", "line"]:
                st.markdown(f"### 📊 Visualização Gráfica")
                st.caption(chart.get("reason", ""))
                try:
                    if chart_type == "bar":
                        st.bar_chart(df, x=chart.get("x_col"), y=chart.get("y_col"))
                    elif chart_type == "line":
                        st.line_chart(df, x=chart.get("x_col"), y=chart.get("y_col"))
                except Exception as e:
                    st.warning(f"Não foi possível desenhar o gráfico: {e}")

# Exibir mensagens anteriores
for message in st.session_state.messages:
    with st.chat_message(message["role"], avatar="🤖" if message["role"] == "assistant" else "👤"):
        render_message(message["content"])

# ── Input do Usuário ──────────────────────────────────────────────────
if prompt := st.chat_input("Digite sua pergunta sobre os dados..."):
    # Adicionar mensagem do usuário
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)

    # Gerar resposta
    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("🔄 Analisando sua pergunta, processando SQL e gerando insights..."):
            try:
                from agent import ask
                response = ask(prompt)
            except ValueError as ve:
                response = {"error": str(ve)}
            except Exception as e:
                response = {"error": f"❌ **Erro inesperado:** {str(e)}\n\nVerifique se a API Key da Groq está configurada corretamente."}

        render_message(response)

    # Salvar resposta no histórico
    st.session_state.messages.append({"role": "assistant", "content": response})
