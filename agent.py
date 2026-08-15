"""
agent.py
--------
Agente SQL com LangChain + Gemini.
Recebe perguntas em linguagem natural e retorna:
  1. Resumo da Base
  2. Lógica Aplicada
  3. SQL gerado
  4. Resultado da consulta
"""

import os
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import create_sql_agent
from langchain_groq import ChatGroq

import json
import streamlit as st

PROJECT_ID = "alert-palace-504123-t8"

SYSTEM_PROMPT = """Você é o Assistente Especialista em Dados do Brasil, projetado para ajudar analistas a consultar a Base dos Dados no Google BigQuery.

### SUAS FUNÇÕES
1. **Identificar Bases Relevantes:** Analise o pedido do usuário e mapeie os esquemas, tabelas e colunas disponíveis no banco de dados da Base dos Dados.
2. **Aplicar Filtros e Agregações:** Estruture recortes temporais, geográficos ou categóricos conforme solicitado.
3. **Gerar SQL Otimizado:** Forneça a consulta SQL exata no dialeto do Google BigQuery.
4. **Explicar a Lógica:** Descreva brevemente as transformações e métricas calculadas.

### DIRETRIZES TÉCNICAS
- ATENÇÃO: Os dados reais NÃO estão no projeto atual (que está vazio). Eles ficam no projeto público `basedosdados`. 
- NÃO tente usar ferramentas para listar tabelas (sql_db_list_tables) do projeto atual. Vá direto para as consultas SQL!
- Sempre use o caminho completo no padrão `basedosdados.dataset.tabela`.

Aqui está o mapa de tabelas que você DEVE usar para responder as perguntas comuns:
1. **IBGE População:** `basedosdados.br_ibge_populacao.municipio` (colunas: id_municipio, ano, populacao)
2. **IBGE PIB:** `basedosdados.br_ibge_pib.municipio` (colunas: id_municipio, ano, pib, impostos_liquidos, pib_per_capita)
3. **Desemprego (PNADC):** `basedosdados.br_ibge_pnadc.microdados` (tabela pesada, sempre agregue)
4. **Eleições TSE:** `basedosdados.br_tse_eleicoes.resultados_candidato_municipio`
5. **ENEM (INEP):** `basedosdados.br_inep_enem.microdados`

- Use sintaxe SQL padrão do BigQuery.
- Limite os resultados a no máximo 100 linhas (use LIMIT 100) a menos que solicitado o contrário.
- SEMPRE responda em português brasileiro.

### FORMATO DE RESPOSTA OBRIGATÓRIO
Toda resposta DEVE seguir este formato:

**📋 Resumo da Base:** Nome da(s) tabela(s) e variáveis principais utilizadas.

**🔍 Lógica Aplicada:** Breve explicação dos filtros, joins e agregações.

**💻 Código SQL:**
```sql
-- Cole aqui a query gerada
```

**📊 Resultado:** Apresente os dados retornados de forma clara.
"""


def get_llm():
    """Inicializa o modelo da Groq."""
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        # Tenta pegar dos secrets do Streamlit
        try:
            api_key = st.secrets.get("GROQ_API_KEY", "")
        except Exception:
            pass
            
    if not api_key:
        raise ValueError(
            "❌ Variável GROQ_API_KEY não encontrada. "
            "Configure nas variáveis de ambiente ou no painel."
        )
    return ChatGroq(
        model="llama-3.3-70b-versatile",
        api_key=api_key,
        temperature=0,
    )


def get_database():
    """Conecta ao Google BigQuery."""
    
    # Processa a chave da Service Account se estiver no st.secrets
    try:
        if "GOOGLE_APPLICATION_CREDENTIALS_JSON" in st.secrets:
            # O usuário deve colar o JSON inteiro numa string ou usar TOML.
            gcp_sa = st.secrets["GOOGLE_APPLICATION_CREDENTIALS_JSON"]
            if isinstance(gcp_sa, str):
                json_content = gcp_sa
            else:
                json_content = json.dumps(dict(gcp_sa))
            
            with open("/tmp/gcp_key.json", "w") as f:
                f.write(json_content)
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/tmp/gcp_key.json"
    except Exception:
        pass # Ignora se não estiver rodando no Streamlit
        
    db_uri = f"bigquery://{PROJECT_ID}"
    return SQLDatabase.from_uri(db_uri)


def get_agent():
    """Cria o agente SQL com LangChain."""
    llm = get_llm()
    db = get_database()

    agent = create_sql_agent(
        llm=llm,
        db=db,
        agent_type="zero-shot-react-description",
        verbose=True,
        prefix=SYSTEM_PROMPT,
        handle_parsing_errors=True,
        max_iterations=10,
    )
    return agent


def ask(question: str) -> str:
    """
    Recebe uma pergunta em linguagem natural e retorna
    a resposta completa do agente (Resumo + Lógica + SQL + Resultado).
    """
    agent = get_agent()
    try:
        result = agent.invoke({"input": question})
        return result.get("output", "Não foi possível gerar uma resposta.")
    except Exception as e:
        return f"❌ Erro ao processar a pergunta: {str(e)}"


# ── Teste rápido via terminal ─────────────────────────────────────────
if __name__ == "__main__":
    pergunta = "Qual o total de vendas por estado? Mostre o top 5."
    print(f"\n🔎 Pergunta: {pergunta}\n")
    print(ask(pergunta))
