"""
agent.py
--------
Agente SQL com LangChain + Groq.
Processo dividido em: Geração de SQL -> Execução Pandas -> Análise IA -> Gráfico IA.
"""

import os
import json
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

PROJECT_ID = "alert-palace-504123-t8"

ROUTER_PROMPT = """Você é um assistente de roteamento.
Classifique a pergunta do usuário em APENAS UM dos seguintes temas: economia, educacao, saude, trabalho, seguranca, geografia ou geral.
Responda APENAS com o nome do tema, sem pontuação ou explicação.
Pergunta: {question}
Tema:"""

TABLE_SCHEMAS_MAP = {
    "economia": "1. IBGE PIB: `basedosdados.br_ibge_pib.municipio`\n2. IBGE IPCA: `basedosdados.br_ibge_ipca.mes_brasil`",
    "educacao": "1. INEP Censo Escolar: `basedosdados.br_inep_censo_escolar.escola`",
    "saude": "1. SIM DataSUS (Mortalidade): `basedosdados.br_ms_datasus.sim`",
    "trabalho": "1. Novo CAGED: `basedosdados.br_me_caged.microdados_movimentacao`\n2. RAIS: `basedosdados.br_me_rais.microdados_vinculos`",
    "seguranca": "1. ABSP Município: `basedosdados.br_fbsp_absp.municipio`\n2. ABSP UF: `basedosdados.br_fbsp_absp.uf`\n3. Ocorrências SP: `basedosdados.br_sp_gov_ssp.ocorrencias_registradas`",
    "geografia": "1. Municípios: `basedosdados.br_bd_diretorios_brasil.municipio`\n2. UF: `basedosdados.br_bd_diretorios_brasil.uf`\n3. Setor Censitário: `basedosdados.br_bd_diretorios_brasil.setor_censitario`",
    "geral": "1. IBGE População: `basedosdados.br_ibge_populacao.municipio`\n2. Eleições TSE: `basedosdados.br_tse_eleicoes.resultados_candidato_municipio`"
}

BASE_TABLE = "0. Diretório de Municípios: `basedosdados.br_bd_diretorios_brasil.municipio` (colunas: id_municipio, nome, sigla_uf). Diretório de UFs: `basedosdados.br_bd_diretorios_brasil.uf`. FAÇA JOIN com diretórios sempre que precisar dos nomes em texto em vez de IDs."

SQL_PROMPT = """Você é um analista de dados especialista em Google BigQuery.
Gere APENAS o código SQL para responder à pergunta do usuário, sem NENHUM texto adicional, sem formatação markdown e sem crases (```). Apenas o SELECT válido.

### DIRETRIZES TÉCNICAS
- ATENÇÃO: Os dados reais estão no projeto público `basedosdados`. 
- Sempre use o caminho completo no padrão `basedosdados.dataset.tabela`.
- OBRIGATÓRIO: Você DEVE envolver o nome completo da tabela com crases (backticks) no FROM e JOIN. Exemplo: \`basedosdados.dataset.tabela\`

Aqui está o mapa de tabelas que você DEVE usar para responder a pergunta:
{tabelas_contexto}

- Limite os resultados a no máximo 100 linhas (use LIMIT 100) a menos que solicitado o contrário.
- **MUITO IMPORTANTE:** NUNCA use funções de Machine Learning do BigQuery (como ML.KMEANS, ML.LINEAR_REG). O Machine Learning será feito no Python! O seu SQL deve retornar apenas os DADOS BRUTOS (ex: SELECT populacao, pib FROM ...).
- **SINTAXE SQL:** No BigQuery, use sempre `=` para igualdade, NUNCA `==`. Exemplo correto: `WHERE sigla_uf = 'SP'`.

Pergunta do usuário: {question}
SQL:
"""

ANALYSIS_PROMPT = """Você é um analista de dados sênior brilhante, comunicativo e perspicaz.
O usuário fez a seguinte pergunta: "{question}"
Você gerou a seguinte consulta SQL:
```sql
{sql}
```
E o banco de dados retornou os seguintes dados (limitado às primeiras 20 linhas para contexto):
{data}

**Sua missão:**
1. Responda à pergunta do usuário de forma direta, clara e com um tom amigável. Fuja de respostas robóticas ou engessadas.
2. Destaque os principais insights dos dados (ex: quem lidera o ranking, valores discrepantes, tendências).
3. **Seja propositivo:** Sugira o que o usuário pode fazer com esses dados agora (ex: "Com esses dados, você pode criar um mapa de calor no QGIS", ou "Você pode exportar esse CSV e criar um dashboard no Power BI comparando X com Y").
4. Formate tudo em Markdown amigável (use negritos, listas, emojis para dar vida ao texto).
NÃO gere a tabela de dados no texto, pois o sistema já vai exibir a tabela real interativa logo abaixo da sua análise.
"""

ML_PROMPT = """Você é um Cientista de Dados (Data Scientist).
O usuário fez a pergunta: "{question}"
Os dados extraídos do banco têm as seguintes colunas e amostras:
{data}

Retorne um JSON sugerindo qual algoritmo matemático de Machine Learning ou Estatística deve ser rodado no Python antes de exibir a tabela. Use estritamente o formato abaixo e nenhuma outra palavra:
{{
  "ml_task": "kmeans" | "regression" | "correlation" | "summary" | "none",
  "x_col": "nome_da_coluna_eixo_x_ou_alvo1",
  "y_col": "nome_da_coluna_eixo_y_ou_alvo2",
  "k": 3, 
  "chart_type": "scatter" | "bar" | "line" | "none",
  "reason": "motivo resumido da escolha matemática"
}}
- Use "kmeans" para segmentação ou agrupamento numérico (escolha um valor para 'k' adequado, default 3).
- Use "regression" para prever ou achar tendência/relação entre 'x_col' e 'y_col'.
- Use "correlation" para analisar a matriz de correlação se a pergunta pedir correlações estatísticas entre todas as métricas.
- Use "summary" para sumarização ou análise descritiva simples.
- Se não houver pedido analítico complexo, retorne "ml_task": "none" e sugira um "chart_type" comum (bar, line).
Retorne APENAS o JSON válido, sem tags markdown.
"""


def get_llm():
    """Inicializa o modelo da Groq."""
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
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


def get_engine():
    """Conecta ao Google BigQuery via SQLAlchemy."""
    try:
        if "GOOGLE_APPLICATION_CREDENTIALS_JSON" in st.secrets:
            gcp_sa = st.secrets["GOOGLE_APPLICATION_CREDENTIALS_JSON"]
            if isinstance(gcp_sa, str):
                json_content = gcp_sa
            else:
                json_content = json.dumps(dict(gcp_sa))
            
            with open("/tmp/gcp_key.json", "w") as f:
                f.write(json_content)
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/tmp/gcp_key.json"
    except Exception:
        pass 
        
    db_uri = f"bigquery://{PROJECT_ID}"
    return create_engine(db_uri)


def ask(question: str) -> dict:
    """
    Nova arquitetura Chain:
    1. Gera SQL
    2. Executa via Pandas
    3. Gera Análise Textual
    4. Gera Config de Gráfico
    """
    try:
        llm = get_llm()
        engine = get_engine()
        
        # 0. Roteamento de Tema
        prompt_router = ChatPromptTemplate.from_template(ROUTER_PROMPT)
        chain_router = prompt_router | llm | StrOutputParser()
        tema = chain_router.invoke({"question": question}).strip().lower()
        
        # Validar o tema retornado
        if tema not in TABLE_SCHEMAS_MAP:
            tema = "geral"
            
        tabelas_contexto = BASE_TABLE + "\n" + TABLE_SCHEMAS_MAP[tema]
        
        # 1. Geração SQL
        prompt_sql = ChatPromptTemplate.from_template(SQL_PROMPT)
        chain_sql = prompt_sql | llm | StrOutputParser()
        sql_query = chain_sql.invoke({
            "question": question,
            "tabelas_contexto": tabelas_contexto
        })
        sql_query = sql_query.replace("```sql", "").replace("```", "").strip()
        
        # 2. Execução
        try:
            df = pd.read_sql(sql_query, engine)
        except Exception as e:
            return {"error": f"**Erro ao executar SQL no banco:** {str(e)}\n\n**Query Gerada:**\n```sql\n{sql_query}\n```"}
            
        if df.empty:
            return {"error": "A consulta retornou 0 resultados.", "sql": sql_query}
            
        # 3. Análise
        data_sample = df.head(20).to_markdown()
        prompt_analysis = ChatPromptTemplate.from_template(ANALYSIS_PROMPT)
        chain_analysis = prompt_analysis | llm | StrOutputParser()
        analysis = chain_analysis.invoke({"question": question, "sql": sql_query, "data": data_sample})
        
        # 4. Machine Learning & Gráfico
        prompt_ml = ChatPromptTemplate.from_template(ML_PROMPT)
        chain_ml = prompt_ml | llm | StrOutputParser()
        ml_json_str = chain_ml.invoke({"question": question, "data": data_sample})
        
        ml_config = {"ml_task": "none", "chart_type": "none"}
        try:
            import re
            match = re.search(r'\{.*\}', ml_json_str, re.DOTALL)
            if match:
                ml_config = json.loads(match.group())
        except Exception as e:
            pass # fallback silencioso
            
        return {
            "sql": sql_query,
            "dataframe": df,
            "analysis": analysis,
            "ml_config": ml_config
        }

    except Exception as e:
        return {"error": f"❌ Erro inesperado: {str(e)}"}


if __name__ == "__main__":
    res = ask("Qual a população dos municípios de SP em 2022 segundo o IBGE?")
    print(res)
