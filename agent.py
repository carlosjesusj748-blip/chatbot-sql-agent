"""
agent.py
--------
Agente SQL com LangChain + Groq.
Processo dividido em: Geração de SQL -> Execução Pandas -> Análise IA -> Gráfico IA.
"""

import os
import re
import json
import difflib
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from scipy import stats as scipy_stats
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sqlalchemy import create_engine
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from google.cloud import bigquery
from google.api_core.exceptions import BadRequest

PROJECT_ID = "alert-palace-504123-t8"

ROUTER_PROMPT = """Você é um assistente de roteamento.
Classifique a pergunta do usuário em APENAS UM dos seguintes temas: economia, educacao, saude, trabalho, seguranca, geografia ou geral.
Responda APENAS com o nome do tema, sem pontuação ou explicação.
Pergunta: {question}
Tema:"""

TABLE_SCHEMAS_MAP = {
    "economia": "1. IBGE PIB: `basedosdados.br_ibge_pib.municipio`\n2. IBGE IPCA: `basedosdados.br_ibge_ipca.mes_brasil`\n\nEXEMPLO DE QUERY:\n```sql\nSELECT m.nome, p.pib FROM `basedosdados.br_ibge_pib.municipio` p JOIN `basedosdados.br_bd_diretorios_brasil.municipio` m ON p.id_municipio = m.id_municipio WHERE p.ano = 2021 ORDER BY p.pib DESC LIMIT 10\n```",
    "educacao": "1. INEP Censo Escolar: `basedosdados.br_inep_censo_escolar.escola`\n\nEXEMPLO DE QUERY:\n```sql\nSELECT m.nome, COUNT(e.id_escola) as total_escolas FROM `basedosdados.br_inep_censo_escolar.escola` e JOIN `basedosdados.br_bd_diretorios_brasil.municipio` m ON e.id_municipio = m.id_municipio WHERE e.ano = 2023 AND e.sigla_uf = 'SP' GROUP BY m.nome ORDER BY total_escolas DESC LIMIT 10\n```",
    "saude": "1. SIM DataSUS (Mortalidade): `basedosdados.br_ms_sim.microdados` (colunas cruciais: ano, sigla_uf, id_municipio_ocorrencia, id_municipio_residencia, circunstancia_obito)\n\nEXEMPLO DE QUERY:\n```sql\nSELECT m.nome, COUNT(*) as total_obitos FROM `basedosdados.br_ms_sim.microdados` s JOIN `basedosdados.br_bd_diretorios_brasil.municipio` m ON s.id_municipio_ocorrencia = m.id_municipio WHERE s.ano = 2022 AND s.sigla_uf = 'SP' AND s.circunstancia_obito = '3' GROUP BY m.nome ORDER BY total_obitos DESC LIMIT 10\n```",
    "trabalho": "1. Novo CAGED: `basedosdados.br_me_caged.microdados_movimentacao`\n2. RAIS: `basedosdados.br_me_rais.microdados_vinculos`\n\nEXEMPLO DE QUERY:\n```sql\nSELECT m.nome, SUM(c.saldo_movimentacao) as saldo_empregos FROM `basedosdados.br_me_caged.microdados_movimentacao` c JOIN `basedosdados.br_bd_diretorios_brasil.municipio` m ON c.id_municipio = m.id_municipio WHERE c.ano = 2023 AND c.mes = 12 GROUP BY m.nome ORDER BY saldo_empregos DESC LIMIT 10\n```",
    "seguranca": "1. ABSP Município: `basedosdados.br_fbsp_absp.municipio`\n2. ABSP UF: `basedosdados.br_fbsp_absp.uf`\n3. Ocorrências SP: `basedosdados.br_sp_gov_ssp.ocorrencias_registradas`\n\nEXEMPLO DE QUERY (Municípios mais violentos):\n```sql\nWITH ano_recente AS (SELECT MAX(ano) as ano FROM `basedosdados.br_fbsp_absp.municipio` WHERE sigla_uf='BA') SELECT m.nome, SUM(f.quantidade_homicidio_doloso) as total_homicidios FROM `basedosdados.br_fbsp_absp.municipio` f JOIN ano_recente a ON f.ano = a.ano JOIN `basedosdados.br_bd_diretorios_brasil.municipio` m ON f.id_municipio = m.id_municipio WHERE f.sigla_uf = 'BA' GROUP BY m.nome ORDER BY total_homicidios DESC LIMIT 10\n```",
    "geografia": "1. Diretório Municípios: `basedosdados.br_bd_diretorios_brasil.municipio`\n2. Diretório UF: `basedosdados.br_bd_diretorios_brasil.uf`\n\nEXEMPLO DE QUERY:\n```sql\nSELECT m.nome, m.sigla_uf, u.regiao FROM `basedosdados.br_bd_diretorios_brasil.municipio` m JOIN `basedosdados.br_bd_diretorios_brasil.uf` u ON m.sigla_uf = u.sigla WHERE u.regiao = 'Nordeste'\n```",
    "geral": "1. Diretório Municípios: `basedosdados.br_bd_diretorios_brasil.municipio`\n2. IBGE População: `basedosdados.br_ibge_populacao.municipio`\n\nEXEMPLO DE QUERY:\n```sql\nWITH ano_recente AS (SELECT MAX(ano) as ano FROM `basedosdados.br_ibge_populacao.municipio`) SELECT m.nome, p.populacao FROM `basedosdados.br_ibge_populacao.municipio` p JOIN ano_recente a ON p.ano = a.ano JOIN `basedosdados.br_bd_diretorios_brasil.municipio` m ON p.id_municipio = m.id_municipio WHERE m.sigla_uf = 'SP' ORDER BY p.populacao DESC LIMIT 10\n```"
}

BASE_TABLE = "0. Diretório de Municípios: `basedosdados.br_bd_diretorios_brasil.municipio` (colunas: id_municipio, nome, sigla_uf). Diretório de UFs: `basedosdados.br_bd_diretorios_brasil.uf`. FAÇA JOIN com diretórios sempre que precisar dos nomes em texto em vez de IDs."

SQL_PROMPT = """Você é um Engenheiro e Analista de Dados especialista no ecossistema do BigQuery da "Base dos Dados".

### REGRAS CRÍTICAS DE SCHEMA E ESCOPO
1. ESCOPO GEOGRÁFICO:
   - Tabelas iniciadas por `br_sp_*` atendem EXCLUSIVAMENTE ao Estado de São Paulo.
   - Para analisar homicídios, mortalidade ou violência na Bahia ('BA'), em outros estados ou no Brasil como um todo, consulte SEMPRE:
     * `basedosdados.br_ms_sim.microdados` (Causa externa/homicídio: `circunstancia_obito = '3'`)
     * `basedosdados.br_fbsp_absp.municipio`
2. PADRÕES DE DIRETÓRIO:
   - Para enriquecer códigos de municípios (`id_municipio`) com nome e estado, use `basedosdados.br_bd_diretorios_brasil.municipio`.
   - Na tabela `br_bd_diretorios_brasil.municipio`, use os campos `id_municipio`, `nome` e `sigla_uf`.
   - Na tabela `br_bd_diretorios_brasil.uf`, o campo de identificação do estado é `sigla` (e não `sigla_uf`).
3. SINTAXE SQL:
   - Escreva sempre em padrão Google BigQuery (Standard SQL), envolvendo os caminhos das tabelas entre crases (`basedosdados.dataset.tabela`).
   - Evite `SELECT *`; selecione apenas as colunas necessárias e aplique `LIMIT` apropriado se não houver agregação.
   - NUNCA use funções de Machine Learning do BigQuery (como ML.KMEANS).
4. OTIMIZAÇÃO E CONTAGEM:
   - Sempre que consultar tabelas grandes como `br_ms_sim` ou censos, é OBRIGATÓRIO incluir um filtro de `ano` (ex: `ano = 2022`) na cláusula WHERE.
   - Nunca assuma a existência de uma coluna `id`. Se precisar contar o total de registros (linhas) de uma tabela e não tiver certeza da chave primária, utilize SEMPRE `COUNT(*)`.

### DICIONÁRIO DE DADOS OBRIGATÓRIO (ESQUEMAS)
Sempre que utilizar as tabelas abaixo, RESPEITE ESTRITAMENTE os nomes das colunas:
1. `basedosdados.br_ms_sim.microdados` (Mortalidade/DATASUS)
   - Chaves geográficas: OBRIGATÓRIO usar `id_municipio_ocorrencia` ou `id_municipio_residencia`. NUNCA use `id_municipio` nesta tabela.
   - Filtros: `ano`, `sigla_uf`, `circunstancia_obito` ('3' = homicídio/causa externa).
2. `basedosdados.br_bd_diretorios_brasil.municipio` (Diretório de Municípios)
   - Chave: `id_municipio`
   - Nomes: `nome`, `sigla_uf`
3. `basedosdados.br_fbsp_absp.municipio` (Segurança Pública/Anuário)
   - Chaves: `ano`, `sigla_uf`, `id_municipio`, `grupo`
   - ATENÇÃO: Todas as métricas usam o prefixo `quantidade_`. Os nomes corretos são:
     * `quantidade_homicidio_doloso` (homicídios dolosos)
     * `quantidade_mortes_violentas_intencionais` (MVI / CVLI total)
     * `quantidade_latrocinio` (latrocínio)
     * `quantidade_lesao_corporal_morte` (lesão corporal seguida de morte)
     * `quantidade_feminicidio` (feminicídio)
     * `quantidade_estupro` (estupro)
     * `quantidade_furto_veiculos`, `quantidade_roubo_veiculos`
     * `quantidade_mortes_intervencao_policial`
   - NUNCA use `homicidio_doloso` sem o prefixo `quantidade_`.

### REGRA DE FORMATAÇÃO DA SAÍDA
Sempre que gerar uma query SQL, você DEVE encapsulá-la em um bloco de código markdown ` ```sql ... ``` `. Nunca deixe a query solta no meio do texto ou responda apenas com texto.

Aqui está o mapa de tabelas que você DEVE usar para responder a pergunta:
{tabelas_contexto}

Pergunta do usuário: {question}
{contexto_erro}
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
  "ml_task": "kmeans" | "regression" | "correlation" | "summary" | "outliers" | "distribution" | "timeseries" | "none",
  "x_col": "nome_da_coluna_eixo_x_ou_alvo1",
  "y_col": "nome_da_coluna_eixo_y_ou_alvo2",
  "k": 3,
  "chart_type": "scatter" | "bar" | "line" | "histogram" | "box" | "heatmap" | "pie" | "none",
  "reason": "motivo resumido da escolha matemática"
}}
- Use "kmeans" para segmentação ou agrupamento numérico (escolha um valor para 'k' adequado, default 3; 'x_col' e 'y_col' são as duas dimensões usadas no agrupamento).
- Use "regression" para prever ou achar tendência/relação linear entre 'x_col' (variável independente) e 'y_col' (variável dependente).
- Use "correlation" para analisar a matriz de correlação de Pearson entre todas as colunas numéricas, quando a pergunta pedir correlações entre várias métricas.
- Use "summary" para estatísticas descritivas (média, mediana, desvio padrão, quartis, assimetria) de uma coluna numérica em 'x_col'.
- Use "outliers" para detectar valores atípicos (método IQR) em 'x_col'.
- Use "distribution" para analisar a distribuição (histograma, assimetria/curtose) de 'x_col'.
- Use "timeseries" quando houver uma coluna temporal/ano em 'x_col' e uma métrica numérica em 'y_col', para ver tendência ao longo do tempo (com média móvel).
- Se não houver pedido analítico complexo, retorne "ml_task": "none" e sugira apenas um "chart_type" comum (bar, line, scatter, pie) usando 'x_col'/'y_col' como eixos.
Retorne APENAS o JSON válido, sem tags markdown.
"""

# Valores default para garantir que o dict de ML sempre tenha todas as chaves
# esperadas pelo restante da aplicação, mesmo se o LLM devolver um JSON incompleto.
ML_CONFIG_DEFAULTS = {
    "ml_task": "none",
    "x_col": None,
    "y_col": None,
    "k": 3,
    "chart_type": "none",
    "reason": "",
}


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
        # llama-3.3-70b-versatile foi descontinuado pela Groq (aviso de
        # 17/06/2026). openai/gpt-oss-120b é o substituto recomendado.
        model="openai/gpt-oss-120b",
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
    except Exception as e:
        # Se as credenciais não puderem ser configuradas aqui, avisa em vez
        # de falhar silenciosamente — evita erros confusos de autenticação
        # mais adiante no BigQuery.
        st.warning(f"⚠️ Não foi possível configurar credenciais do GCP via secrets: {e}")

    db_uri = f"bigquery://{PROJECT_ID}"
    return create_engine(db_uri)


def extrair_sql(texto_llm):
    """Extrai apenas o bloco SQL da resposta do LLM (tolerante a variações de formatação)."""
    match = re.search(r"```sql\s*(.*?)\s*```", texto_llm, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    # fallback: tenta capturar qualquer bloco de código, mesmo sem a tag "sql"
    match = re.search(r"```\s*(.*?)\s*```", texto_llm, re.DOTALL)
    if match:
        return match.group(1).strip()
    return texto_llm.strip()


def validar_query_bigquery(query_sql):
    """
    Valida a sintaxe e o schema da query usando o Dry Run do BigQuery.
    Retorna (True, "Mensagem de sucesso/bytes") ou (False, "Mensagem de erro").
    """
    client = bigquery.Client(project=PROJECT_ID)
    job_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)

    try:
        query_job = client.query(query_sql, job_config=job_config)
        bytes_processados = query_job.total_bytes_processed
        mb_processados = bytes_processados / (1024 * 1024)
        return True, f"Query válida! Processaria {mb_processados:.2f} MB."
    except BadRequest as e:
        return False, e.message


def _dataframe_para_texto(df: pd.DataFrame) -> str:
    """Converte o dataframe em texto para os prompts, sem depender de 'tabulate'."""
    try:
        return df.to_markdown()
    except ImportError:
        # 'tabulate' não instalado — cai para uma representação simples em texto
        return df.to_string()


def _resolver_coluna(df: pd.DataFrame, nome_sugerido):
    """
    Resolve o nome de coluna sugerido pelo LLM contra as colunas reais do
    dataframe (o LLM pode errar maiúsculas/acentos/nome aproximado).
    Retorna o nome real da coluna ou None se não achar nada razoável.
    """
    if not nome_sugerido:
        return None
    if nome_sugerido in df.columns:
        return nome_sugerido
    # tenta case-insensitive
    lower_map = {c.lower(): c for c in df.columns}
    if isinstance(nome_sugerido, str) and nome_sugerido.lower() in lower_map:
        return lower_map[nome_sugerido.lower()]
    # tenta o mais parecido
    candidatos = difflib.get_close_matches(str(nome_sugerido), df.columns, n=1, cutoff=0.6)
    return candidatos[0] if candidatos else None


def _colunas_numericas(df: pd.DataFrame, limiar: float = 0.9):
    """
    Lista as colunas realmente numéricas do dataframe.
    Não confia só no dtype: colunas NUMERIC/INTEGER do BigQuery às vezes voltam
    como dtype 'object' (Decimal/int misturado). Por isso, para colunas não
    numéricas por dtype, tenta converter e só aceita se pelo menos `limiar`
    (90% por padrão) dos valores não nulos forem convertíveis — isso evita
    aceitar colunas de texto (ex: nomes de cidade) por engano.
    """
    numericas = []
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            numericas.append(col)
            continue
        serie = df[col]
        validos = serie.notna()
        if validos.sum() == 0:
            continue
        convertida = pd.to_numeric(serie, errors="coerce")
        taxa_sucesso = convertida[validos].notna().mean()
        if taxa_sucesso >= limiar:
            numericas.append(col)
    return numericas


def _serie_numerica(df: pd.DataFrame, col: str) -> pd.Series:
    """Converte uma coluna para numérico de fato (lida com Decimal/Int64/object do BigQuery)."""
    return pd.to_numeric(df[col], errors="coerce")


def _dados_numericos(df: pd.DataFrame, colunas: list) -> pd.DataFrame:
    """Devolve uma cópia do dataframe só com as colunas pedidas, já convertidas para numérico."""
    return pd.DataFrame({col: _serie_numerica(df, col) for col in colunas})


def _executar_summary(df: pd.DataFrame, x_col):
    """Estatística descritiva clássica de analista: média, mediana, desvio, quartis, assimetria/curtose."""
    numericas = _colunas_numericas(df)
    if x_col and x_col in numericas:
        colunas = [x_col]
    else:
        colunas = numericas
    if not colunas:
        return {"stats": "Não há colunas numéricas para resumir."}, None

    df_num = _dados_numericos(df, colunas)
    resumo = df_num.describe().T
    resumo["skew"] = df_num.skew()
    resumo["kurtosis"] = df_num.kurtosis()
    stats_texto = _dataframe_para_texto(resumo.round(2))

    fig = None
    if len(colunas) == 1:
        fig = px.histogram(df_num, x=colunas[0], marginal="box", title=f"Distribuição de {colunas[0]}")
    return {"stats": stats_texto}, fig


def _executar_outliers(df: pd.DataFrame, x_col):
    """Detecção de outliers pelo método IQR (Intervalo Interquartil), clássico em análise exploratória."""
    numericas = _colunas_numericas(df)
    col = x_col if x_col in numericas else (numericas[0] if numericas else None)
    if not col:
        return {"stats": "Não há coluna numérica para checar outliers."}, None

    serie = _serie_numerica(df, col).dropna()
    if serie.empty:
        return {"stats": f"A coluna `{col}` não tem valores numéricos válidos."}, None

    q1, q3 = serie.quantile(0.25), serie.quantile(0.75)
    iqr = q3 - q1
    limite_inf, limite_sup = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    outliers = serie[(serie < limite_inf) | (serie > limite_sup)]

    stats_texto = (
        f"**Coluna analisada:** `{col}`\n"
        f"- Q1: {q1:.2f} | Q3: {q3:.2f} | IQR: {iqr:.2f}\n"
        f"- Limites considerados normais: [{limite_inf:.2f}, {limite_sup:.2f}]\n"
        f"- **{len(outliers)} outlier(s)** encontrados de {len(serie)} linhas ({(len(outliers) / len(serie) * 100):.1f}%)"
    )
    fig = px.box(pd.DataFrame({col: serie}), y=col, points="outliers", title=f"Outliers em {col} (método IQR)")
    return {"stats": stats_texto}, fig


def _executar_distribution(df: pd.DataFrame, x_col):
    """Análise de distribuição de uma variável: histograma + medidas de forma."""
    numericas = _colunas_numericas(df)
    col = x_col if x_col in numericas else (numericas[0] if numericas else None)
    if not col:
        return {"stats": "Não há coluna numérica para analisar distribuição."}, None

    serie = _serie_numerica(df, col).dropna()
    if serie.empty:
        return {"stats": f"A coluna `{col}` não tem valores numéricos válidos."}, None

    stats_texto = (
        f"**Distribuição de `{col}`**\n"
        f"- Média: {serie.mean():.2f} | Mediana: {serie.median():.2f} | Desvio padrão: {serie.std():.2f}\n"
        f"- Assimetria (skew): {serie.skew():.2f} | Curtose: {serie.kurtosis():.2f}\n"
        f"- Mínimo: {serie.min():.2f} | Máximo: {serie.max():.2f}"
    )
    fig = px.histogram(pd.DataFrame({col: serie}), x=col, marginal="violin", title=f"Distribuição de {col}")
    return {"stats": stats_texto}, fig


def _executar_correlation(df: pd.DataFrame):
    """Matriz de correlação de Pearson entre todas as colunas numéricas."""
    numericas = _colunas_numericas(df)
    if len(numericas) < 2:
        return {"stats": "É preciso de pelo menos 2 colunas numéricas para calcular correlação."}, None

    df_num = _dados_numericos(df, numericas)
    corr = df_num.corr(method="pearson").round(2)
    stats_texto = _dataframe_para_texto(corr)
    fig = px.imshow(
        corr, text_auto=True, color_continuous_scale="RdBu_r", zmin=-1, zmax=1,
        title="Matriz de Correlação (Pearson)"
    )
    return {"stats": stats_texto}, fig


def _executar_regression(df: pd.DataFrame, x_col, y_col):
    """Regressão linear simples (mínimos quadrados) entre x_col e y_col."""
    numericas = _colunas_numericas(df)
    if x_col not in numericas or y_col not in numericas or x_col == y_col:
        return {"stats": "Colunas insuficientes/ inválidas para regressão linear."}, None

    dados = _dados_numericos(df, [x_col, y_col]).dropna()
    if len(dados) < 3:
        return {"stats": "Dados insuficientes para uma regressão confiável."}, None

    reg = scipy_stats.linregress(dados[x_col], dados[y_col])
    stats_texto = (
        f"**Regressão linear: `{y_col}` ~ `{x_col}`**\n"
        f"- Equação: y = {reg.slope:.4f}x + {reg.intercept:.4f}\n"
        f"- R² (qualidade do ajuste): {reg.rvalue ** 2:.4f}\n"
        f"- p-valor: {reg.pvalue:.4g} "
        f"({'estatisticamente significativo' if reg.pvalue < 0.05 else 'não significativo ao nível de 5%'})\n"
        f"- Erro padrão da inclinação: {reg.stderr:.4f}"
    )
    fig = px.scatter(dados, x=x_col, y=y_col, title=f"Regressão linear: {y_col} vs {x_col}")
    linha_x = np.array([dados[x_col].min(), dados[x_col].max()])
    linha_y = reg.slope * linha_x + reg.intercept
    fig.add_trace(go.Scatter(x=linha_x, y=linha_y, mode="lines", name="Reta de regressão"))
    return {"stats": stats_texto}, fig


def _executar_kmeans(df: pd.DataFrame, x_col, y_col, k):
    """Agrupamento K-Means em duas dimensões numéricas, com padronização (StandardScaler)."""
    numericas = _colunas_numericas(df)
    if x_col not in numericas or y_col not in numericas:
        return {"stats": "Colunas insuficientes/ inválidas para K-Means."}, None

    dados = _dados_numericos(df, [x_col, y_col]).dropna()
    k = max(2, min(int(k or 3), len(dados)))
    if len(dados) < k:
        return {"stats": "Poucos registros para o número de clusters pedido."}, None

    escala = StandardScaler().fit_transform(dados)
    modelo = KMeans(n_clusters=k, random_state=42, n_init=10)
    dados = dados.copy()
    dados["cluster"] = modelo.fit_predict(escala).astype(str)

    contagem = dados["cluster"].value_counts().sort_index()
    stats_texto = (
        f"**K-Means com k={k}** sobre `{x_col}` e `{y_col}`\n"
        + "\n".join(f"- Cluster {c}: {n} registros" for c, n in contagem.items())
    )
    fig = px.scatter(
        dados, x=x_col, y=y_col, color="cluster",
        title=f"K-Means (k={k}): {y_col} vs {x_col}"
    )
    return {"stats": stats_texto}, fig


def _executar_timeseries(df: pd.DataFrame, x_col, y_col):
    """Tendência ao longo do tempo, com média móvel simples (janela de 3 pontos)."""
    numericas = _colunas_numericas(df)
    if x_col not in df.columns or y_col not in numericas:
        return {"stats": "Colunas insuficientes/ inválidas para série temporal."}, None

    serie = df[[x_col]].copy()
    serie[y_col] = _serie_numerica(df, y_col)
    serie = serie.dropna().sort_values(x_col)
    if serie.empty:
        return {"stats": f"A coluna `{y_col}` não tem valores numéricos válidos."}, None
    serie["media_movel"] = serie[y_col].rolling(window=3, min_periods=1).mean()

    variacao = None
    if len(serie) >= 2 and serie[y_col].iloc[0] != 0:
        variacao = (serie[y_col].iloc[-1] - serie[y_col].iloc[0]) / abs(serie[y_col].iloc[0]) * 100

    stats_texto = (
        f"**Série temporal: `{y_col}` ao longo de `{x_col}`**\n"
        f"- Primeiro valor: {serie[y_col].iloc[0]:.2f} | Último valor: {serie[y_col].iloc[-1]:.2f}\n"
        + (f"- Variação no período: {variacao:.1f}%\n" if variacao is not None else "")
    )
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=serie[x_col], y=serie[y_col], mode="lines+markers", name=y_col))
    fig.add_trace(go.Scatter(x=serie[x_col], y=serie["media_movel"], mode="lines", name="Média móvel (3)"))
    fig.update_layout(title=f"Tendência de {y_col} ao longo de {x_col}")
    return {"stats": stats_texto}, fig


def _gerar_grafico_padrao(df: pd.DataFrame, chart_type, x_col, y_col):
    """Gráfico simples quando não há análise estatística pedida, só visualização direta dos dados."""
    if not chart_type or chart_type == "none":
        return None
    try:
        if chart_type == "scatter" and x_col and y_col:
            return px.scatter(df, x=x_col, y=y_col, title=f"{y_col} vs {x_col}")
        if chart_type == "bar" and x_col and y_col:
            return px.bar(df, x=x_col, y=y_col, title=f"{y_col} por {x_col}")
        if chart_type == "line" and x_col and y_col:
            return px.line(df, x=x_col, y=y_col, title=f"{y_col} ao longo de {x_col}")
        if chart_type == "histogram" and x_col:
            return px.histogram(df, x=x_col, title=f"Distribuição de {x_col}")
        if chart_type == "box" and x_col:
            return px.box(df, y=x_col, title=f"Boxplot de {x_col}")
        if chart_type == "pie" and x_col and y_col:
            return px.pie(df, names=x_col, values=y_col, title=f"{y_col} por {x_col}")
        if chart_type == "heatmap":
            numericas = _colunas_numericas(df)
            if len(numericas) >= 2:
                return px.imshow(df[numericas].corr().round(2), text_auto=True, title="Correlação")
    except Exception:
        return None
    return None


def executar_analise_ml(df: pd.DataFrame, ml_config: dict):
    """
    Roteia o ml_config sugerido pelo LLM para a função estatística correspondente
    e monta o gráfico (Plotly) associado. Nunca deixa o pipeline quebrar: em caso
    de erro/coluna inválida, devolve stats=None e figura=None.
    """
    ml_task = (ml_config or {}).get("ml_task", "none")
    chart_type = (ml_config or {}).get("chart_type", "none")
    x_col = _resolver_coluna(df, (ml_config or {}).get("x_col"))
    y_col = _resolver_coluna(df, (ml_config or {}).get("y_col"))
    k = (ml_config or {}).get("k", 3)

    try:
        if ml_task == "summary":
            resultado, fig = _executar_summary(df, x_col)
        elif ml_task == "outliers":
            resultado, fig = _executar_outliers(df, x_col)
        elif ml_task == "distribution":
            resultado, fig = _executar_distribution(df, x_col)
        elif ml_task == "correlation":
            resultado, fig = _executar_correlation(df)
        elif ml_task == "regression":
            resultado, fig = _executar_regression(df, x_col, y_col)
        elif ml_task == "kmeans":
            resultado, fig = _executar_kmeans(df, x_col, y_col, k)
        elif ml_task == "timeseries":
            resultado, fig = _executar_timeseries(df, x_col, y_col)
        else:
            resultado, fig = None, None

        # Se nenhuma análise estatística gerou gráfico, tenta o gráfico simples sugerido
        if fig is None:
            fig = _gerar_grafico_padrao(df, chart_type, x_col, y_col)

        return {"stats": resultado.get("stats") if resultado else None, "figura": fig}
    except Exception as e:
        return {"stats": f"⚠️ Não foi possível concluir a análise estatística: {e}", "figura": None}


def _diagnosticar_zero_resultados(sql_query: str, engine) -> str:
    """
    Quando uma query retorna 0 resultados, tenta diagnosticar qual filtro
    do WHERE é o responsável. Faz isso removendo cada condição AND uma por vez
    e verificando se o COUNT(*) resultante é > 0.
    Retorna uma string descritiva para injetar no contexto de erro do LLM.
    """
    try:
        # Extrair a parte do WHERE
        where_match = re.search(r'WHERE\s+(.*?)(?:GROUP BY|ORDER BY|LIMIT|$)', sql_query, re.DOTALL | re.IGNORECASE)
        if not where_match:
            return "Não foi possível identificar os filtros WHERE."

        where_clause = where_match.group(1).strip()

        # Separar as condições AND (simplificado)
        condicoes = re.split(r'\bAND\b', where_clause, flags=re.IGNORECASE)
        condicoes = [c.strip().rstrip(',') for c in condicoes if c.strip()]

        if len(condicoes) <= 1:
            return f"Há apenas um filtro: '{where_clause}'. Verifique se o valor dele existe na tabela."

        # Extrair a parte FROM...JOIN...WHERE (preservando aliases)
        from_match = re.search(r'(FROM\s+.*?)WHERE', sql_query, re.DOTALL | re.IGNORECASE)
        if not from_match:
            return "Não foi possível extrair o FROM/JOIN da query."

        from_clause = from_match.group(1).strip()

        diagnosticos = []
        for i, cond in enumerate(condicoes):
            # Remove a condição i e monta um COUNT(*) com as restantes
            filtros_restantes = [c for j, c in enumerate(condicoes) if j != i]
            novo_where = " AND ".join(filtros_restantes)
            query_teste = f"SELECT COUNT(*) AS total {from_clause} WHERE {novo_where}"

            try:
                resultado = pd.read_sql(query_teste, engine)
                total = resultado['total'].iloc[0] if not resultado.empty else 0
                diagnosticos.append(f"Sem o filtro '{cond.strip()}': {total} linhas")
            except Exception:
                diagnosticos.append(f"Sem o filtro '{cond.strip()}': [erro ao testar]")

        return " | ".join(diagnosticos)

    except Exception as e:
        return f"Erro ao diagnosticar: {str(e)}"


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

        # 1. Geração SQL com Loop de Validação + Execução Unificados
        max_tentativas = 4
        sql_query = ""
        erro_anterior = ""
        df = None

        for tentativa in range(max_tentativas):
            contexto_erro = (
                f"\nSua tentativa anterior falhou com este erro: {erro_anterior}\n"
                "Por favor, reescreva a query corrigindo o problema usando apenas as "
                "colunas do schema fornecido e evite o erro."
                if erro_anterior else ""
            )

            prompt_sql = ChatPromptTemplate.from_template(SQL_PROMPT)
            chain_sql = prompt_sql | llm | StrOutputParser()
            resposta_llm = chain_sql.invoke({
                "question": question,
                "tabelas_contexto": tabelas_contexto,
                "contexto_erro": contexto_erro
            })
            sql_query = extrair_sql(resposta_llm)

            if not sql_query:
                erro_anterior = "A resposta do modelo veio vazia."
                continue

            # Passo A: Dry Run (valida sintaxe e schema)
            valido, msg_validacao = validar_query_bigquery(sql_query)
            if not valido:
                erro_anterior = msg_validacao
                continue

            # Passo B: Execução real
            try:
                df = pd.read_sql(sql_query, engine)
            except Exception as e:
                erro_anterior = f"Erro de execução: {str(e)}"
                continue

            # Passo C: Verifica se retornou dados
            if df.empty:
                # Diagnóstico inteligente: tenta descobrir qual filtro zerou
                diagnostico = _diagnosticar_zero_resultados(sql_query, engine)
                erro_anterior = (
                    "A query é sintaticamente válida, mas retornou 0 resultados. "
                    f"Diagnóstico dos filtros: {diagnostico} "
                    "Reconsidere os filtros do WHERE. "
                    "DICA 1: Se usou circunstancia_obito = '3', troque por REGEXP_CONTAINS(causa_basica, r'^(X8[5-9]|X9[0-9]|Y0[0-9])'). "
                    "DICA 2: Se usou br_ms_sim.microdados e não deu resultado, tente a tabela `basedosdados.br_fbsp_absp.municipio` (use SUM sobre as colunas de métricas disponíveis). "
                    "DICA 3: Tente um ano anterior (2021, 2020) ou use uma subquery com MAX(ano) para achar o ano mais recente disponível."
                )
                df = None
                continue
            else:
                break  # Sucesso! Temos dados.

        # Se esgotou tentativas
        if df is None or df.empty:
            return {
                "error": (
                    f"**Falha ao obter dados válidos após {max_tentativas} tentativas.**\n"
                    f"Último problema: {erro_anterior}\n\n"
                    f"**Última Query Gerada:**\n```sql\n{sql_query}\n```"
                ),
                "sql": sql_query
            }

        # 3. Análise
        data_sample = _dataframe_para_texto(df.head(20))
        prompt_analysis = ChatPromptTemplate.from_template(ANALYSIS_PROMPT)
        chain_analysis = prompt_analysis | llm | StrOutputParser()
        analysis = chain_analysis.invoke({"question": question, "sql": sql_query, "data": data_sample})

        # 4. Machine Learning & Gráfico
        prompt_ml = ChatPromptTemplate.from_template(ML_PROMPT)
        chain_ml = prompt_ml | llm | StrOutputParser()
        ml_json_str = chain_ml.invoke({"question": question, "data": data_sample})

        ml_config = dict(ML_CONFIG_DEFAULTS)
        try:
            match = re.search(r'\{.*\}', ml_json_str, re.DOTALL)
            if match:
                parsed = json.loads(match.group())
                ml_config.update(parsed)
        except Exception:
            pass  # mantém os defaults em caso de JSON malformado

        # 5. Execução real da estatística/gráfico sugeridos pelo passo anterior
        analise_ml = executar_analise_ml(df, ml_config)

        return {
            "sql": sql_query,
            "dataframe": df,
            "analysis": analysis,
            "ml_config": ml_config,
            "estatisticas": analise_ml["stats"],   # texto em markdown com os resultados numéricos
            "figura": analise_ml["figura"],         # objeto plotly.graph_objects.Figure ou None
        }

    except Exception as e:
        return {"error": f"❌ Erro inesperado: {str(e)}"}


# ── Palavras-chave que indicam pedido de análise/follow-up ──────────
_KEYWORDS_ANALISE = [
    "kmeans", "k-means", "regressão", "regressao", "correlação", "correlacao",
    "sumarização", "sumarizacao", "resumo", "resumir", "summary",
    "outlier", "distribuição", "distribuicao", "histograma",
    "gráfico", "grafico", "plotar", "plottar", "chart",
    "tendência", "tendencia", "série temporal", "serie temporal",
    "agora faça", "agora faca", "agora mostre", "agora analise",
    "com esses dados", "desses dados", "dos mesmos dados",
    "mesma base", "mesma tabela", "mesmos dados",
    "refaça", "refaca", "repita", "de novo",
]


def is_followup_analysis(question: str) -> bool:
    """Detecta se a pergunta parece um pedido de análise/follow-up sobre dados já carregados."""
    q = question.lower()
    return any(kw in q for kw in _KEYWORDS_ANALISE)


def analyze_cached(question: str, df: pd.DataFrame, sql_original: str = "") -> dict:
    """
    Reutiliza um DataFrame já carregado (do cache da sessão) para gerar
    nova análise textual + ML/gráfico, SEM consultar o BigQuery novamente.
    Economiza tempo, custo e evita erros de SQL em perguntas de follow-up.
    """
    try:
        llm = get_llm()

        data_sample = _dataframe_para_texto(df.head(20))

        # Análise textual
        prompt_analysis = ChatPromptTemplate.from_template(ANALYSIS_PROMPT)
        chain_analysis = prompt_analysis | llm | StrOutputParser()
        analysis = chain_analysis.invoke({
            "question": question,
            "sql": sql_original or "(dados reutilizados da consulta anterior)",
            "data": data_sample
        })

        # ML & Gráfico
        prompt_ml = ChatPromptTemplate.from_template(ML_PROMPT)
        chain_ml = prompt_ml | llm | StrOutputParser()
        ml_json_str = chain_ml.invoke({"question": question, "data": data_sample})

        ml_config = dict(ML_CONFIG_DEFAULTS)
        try:
            match = re.search(r'\{.*\}', ml_json_str, re.DOTALL)
            if match:
                parsed = json.loads(match.group())
                ml_config.update(parsed)
        except Exception:
            pass

        analise_ml = executar_analise_ml(df, ml_config)

        return {
            "sql": sql_original or "(dados reutilizados do cache)",
            "dataframe": df,
            "analysis": analysis,
            "ml_config": ml_config,
            "estatisticas": analise_ml["stats"],
            "figura": analise_ml["figura"],
            "from_cache": True,
        }

    except Exception as e:
        return {"error": f"❌ Erro inesperado na análise em cache: {str(e)}"}


if __name__ == "__main__":
    res = ask("Qual a população dos municípios de SP em 2022 segundo o IBGE?")
    print(res)