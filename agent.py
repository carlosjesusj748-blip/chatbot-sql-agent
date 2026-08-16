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
import io
import time
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

SCOPE_CLASSIFIER_PROMPT = """Você é um assistente estrito que decide se a pergunta do usuário exige uma consulta a um banco de dados SQL estruturado com dados reais do Brasil (IBGE, etc) ou se é apenas uma conversa genérica/ajuda sobre outro assunto.
Pergunta: {question}
Responda APENAS "dados" se a pergunta exigir consulta ao banco de dados ou "conversa" caso contrário.
"""

ROUTER_PROMPT = """Você é um assistente de roteamento.
Classifique a pergunta do usuário em APENAS UM dos seguintes temas: economia, educacao, saude, trabalho, seguranca, geografia ou geral.
Responda APENAS com o nome do tema, sem pontuação ou explicação.
Pergunta: {question}
Tema:"""

TABLE_SCHEMAS_MAP = {
    "economia": "1. IBGE PIB: `basedosdados.br_ibge_pib.municipio`\n2. IBGE IPCA: `basedosdados.br_ibge_ipca.mes_brasil`",
    "educacao": "1. INEP Censo Escolar: `basedosdados.br_inep_censo_escolar.escola`",
    "saude": "1. SIM DataSUS (Mortalidade): `basedosdados.br_ms_sim.microdados` (colunas cruciais: ano, sigla_uf, id_municipio_ocorrencia, id_municipio_residencia, circunstancia_obito)",
    "trabalho": "1. Novo CAGED: `basedosdados.br_me_caged.microdados_movimentacao`\n2. RAIS: `basedosdados.br_me_rais.microdados_vinculos`",
    "seguranca": "1. ABSP Município: `basedosdados.br_fbsp_absp.municipio`\n2. ABSP UF: `basedosdados.br_fbsp_absp.uf`\n3. Ocorrências SP: `basedosdados.br_sp_gov_ssp.ocorrencias_registradas`",
    "geografia": "1. Municípios: `basedosdados.br_bd_diretorios_brasil.municipio`\n2. UF: `basedosdados.br_bd_diretorios_brasil.uf`\n3. Setor Censitário: `basedosdados.br_bd_diretorios_brasil.setor_censitario`",
    "geral": "1. IBGE População: `basedosdados.br_ibge_populacao.municipio`\n2. Eleições TSE: `basedosdados.br_tse_eleicoes.resultados_candidato_municipio`"
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
   - Chave: `id_municipio`
   - Métricas: `homicidio_doloso`, `latrocinio`

### REGRA DE FORMATAÇÃO DA SAÍDA
Sempre que gerar uma query SQL, você DEVE encapsulá-la em um bloco de código markdown ` ```sql ... ``` `. Nunca deixe a query solta no meio do texto ou responda apenas com texto.

### REGRA CRÍTICA — SCHEMA REAL VERIFICADO
Se o contexto abaixo contiver uma seção "SCHEMA REAL VERIFICADO NO BIGQUERY", ela é a fonte da verdade e tem prioridade sobre qualquer suposição. Use SOMENTE as tabelas e colunas ali listadas. NUNCA use uma tabela que não esteja explicitamente no mapa de tabelas fornecido — mesmo que você "lembre" de uma tabela parecida do treinamento, ela pode não existir neste projeto ou ter outro nome/schema.

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
O banco de dados retornou {linhas} linhas, listadas abaixo (limitado às primeiras 20 para contexto):
{data}

**Sua missão:**
1. Responda à pergunta do usuário de forma direta, clara e com um tom amigável. Fuja de respostas robóticas ou engessadas.
2. Destaque os principais insights dos dados (ex: quem lidera o ranking, valores discrepantes, tendências).
3. **Seja propositivo:** Sugira o que o usuário pode fazer com esses dados agora.
4. **Regra de Amostra:** Se o total de linhas retornadas ({linhas}) for menor que 30, adicione uma breve ressalva de que a amostra é pequena e os resultados devem ser interpretados com cautela.
5. Formate tudo em Markdown amigável (use negritos, listas, emojis para dar vida ao texto).
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


def _invocar_com_retry(chain, inputs: dict, max_tentativas: int = 4):
    """
    Invoca uma chain do LangChain com retry automático para o erro 429
    (rate limit de tokens/minuto da Groq). Extrai o tempo de espera sugerido
    pela própria API quando disponível ("try again in Xms/Xs"); caso não
    encontre, usa backoff exponencial. Outros tipos de erro sobem na hora.
    """
    espera_base = 1.0
    ultimo_erro = None
    for tentativa in range(max_tentativas):
        try:
            return chain.invoke(inputs)
        except Exception as e:
            ultimo_erro = e
            mensagem = str(e)
            eh_rate_limit = "rate_limit" in mensagem.lower() or "429" in mensagem
            if not eh_rate_limit or tentativa == max_tentativas - 1:
                raise

            espera = espera_base * (2 ** tentativa)
            match = re.search(r"try again in ([\d.]+)\s*(ms|s)", mensagem, re.IGNORECASE)
            if match:
                valor, unidade = float(match.group(1)), match.group(2).lower()
                espera = (valor / 1000 if unidade == "ms" else valor) + 0.3  # margem de segurança
            time.sleep(espera)
    raise ultimo_erro


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


def _extrair_from_where(sql: str):
    """Extrai o bloco bruto FROM...JOIN...WHERE (até GROUP BY/ORDER BY/LIMIT), preservando joins e aliases."""
    match = re.search(r"(FROM\s+.*?)(?:\bGROUP BY\b|\bORDER BY\b|\bLIMIT\b|$)", sql, re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else None


def _extrair_where(sql: str):
    """Extrai o texto da cláusula WHERE (até GROUP BY / ORDER BY / LIMIT ou o fim da query)."""
    match = re.search(r"WHERE\s+(.*?)(?:\bGROUP BY\b|\bORDER BY\b|\bLIMIT\b|$)", sql, re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else None


def _extrair_filtros_igualdade(where_clause: str):
    """
    Encontra filtros do tipo `coluna = 'valor'` dentro da cláusula WHERE.
    Mantém a referência qualificada (ex: 'm.circunstancia_obito') para reuso seguro
    em queries com JOIN, e também o nome puro da coluna (sem alias) para exibição.
    """
    if not where_clause:
        return []
    padrao = re.compile(r"([\w.]+)\s*=\s*'([^']*)'")
    encontrados = []
    for m in padrao.finditer(where_clause):
        coluna_qualificada = m.group(1)
        coluna_pura = coluna_qualificada.split(".")[-1]
        valor = m.group(2)
        encontrados.append((coluna_pura, coluna_qualificada, valor, m.group(0)))
    return encontrados


def _investigar_valores_reais(sql_query: str, max_colunas: int = 2) -> str:
    """
    Quando uma query roda sem erro mas volta com 0 linhas, investiga os valores
    reais de até `max_colunas` colunas usadas em filtros de igualdade (ex:
    circunstancia_obito = '3'), contando ocorrências dentro do MESMO recorte —
    reaproveitando o FROM/JOIN/WHERE originais e só neutralizando a condição
    suspeita (troca por TRUE), para não quebrar joins nem aliases.
    Retorna um texto pronto para o prompt de correção, ou "" se nada for encontrado.
    """
    from_where = _extrair_from_where(sql_query)
    where_clause = _extrair_where(sql_query)
    if not from_where or not where_clause:
        return ""

    # colunas "seguras" que raramente são a causa (já sabemos que existem e têm o valor certo)
    colunas_ignoradas = {"ano", "sigla_uf", "sigla"}
    filtros = [f for f in _extrair_filtros_igualdade(where_clause) if f[0].lower() not in colunas_ignoradas]
    if not filtros:
        return ""

    achados = []
    try:
        client = bigquery.Client(project=PROJECT_ID)
    except Exception:
        return ""

    for coluna_pura, coluna_qualificada, valor_usado, trecho_original in filtros[:max_colunas]:
        from_where_sem_essa_condicao = from_where.replace(trecho_original, "TRUE", 1)
        query_diagnostico = (
            f"SELECT {coluna_qualificada} AS valor, COUNT(*) AS total "
            f"{from_where_sem_essa_condicao} "
            f"GROUP BY valor ORDER BY total DESC LIMIT 10"
        )
        try:
            job_config = bigquery.QueryJobConfig(use_query_cache=True)
            resultado = client.query(query_diagnostico, job_config=job_config).result()
            valores = [(row["valor"], row["total"]) for row in resultado]
            if valores:
                achados.append(
                    f"- Coluna `{coluna_pura}` (você usou o valor '{valor_usado}', que não existe nesse recorte). "
                    f"Valores reais encontrados (valor, contagem): {valores}"
                )
        except Exception:
            continue  # se o diagnóstico falhar por qualquer motivo, apenas ignora essa coluna

    if not achados:
        return ""
    return (
        "\nInvestigação automática dos filtros — a query rodou sem erro de sintaxe mas "
        "retornou 0 linhas. Prováveis valores de filtro incorretos:\n" + "\n".join(achados) +
        "\nCorrija a query usando um dos valores reais listados acima (ou remova o filtro se não fizer sentido)."
    )


# Cache em memória: evita repetir a mesma consulta de metadados (INFORMATION_SCHEMA)
# várias vezes na mesma sessão do app.
_CACHE_SCHEMA_TABELAS = {}


def _extrair_tabelas_do_texto(texto: str) -> list:
    """Extrai todos os nomes de tabela no formato `projeto.dataset.tabela` de um texto."""
    return re.findall(r"`([\w]+\.[\w]+\.[\w]+)`", texto)


def _obter_colunas_tabela(tabela_completa: str) -> list:
    """
    Busca as colunas REAIS de uma tabela via INFORMATION_SCHEMA.COLUMNS do BigQuery
    (consulta de metadados, praticamente sem custo de processamento). Resultado fica
    em cache na sessão. Retorna [] se a tabela não existir ou a consulta falhar.
    """
    if tabela_completa in _CACHE_SCHEMA_TABELAS:
        return _CACHE_SCHEMA_TABELAS[tabela_completa]

    partes = tabela_completa.split(".")
    if len(partes) != 3:
        return []
    projeto, dataset, tabela = partes

    query = f"""
        SELECT column_name
        FROM `{projeto}.{dataset}`.INFORMATION_SCHEMA.COLUMNS
        WHERE table_name = '{tabela}'
        ORDER BY ordinal_position
    """
    try:
        client = bigquery.Client(project=PROJECT_ID)
        resultado = client.query(query).result()
        colunas = [row["column_name"] for row in resultado]
        _CACHE_SCHEMA_TABELAS[tabela_completa] = colunas
        return colunas
    except Exception:
        return []


def _enriquecer_contexto_com_schema_real(tabelas_contexto_texto: str, max_colunas_por_tabela: int = 35) -> str:
    """
    Acrescenta ao texto de contexto das tabelas a lista REAL de colunas de cada
    uma (via INFORMATION_SCHEMA), reduzindo a chance do LLM inventar nomes de
    coluna que não existem. Mantém o texto original intacto e só adiciona uma
    seção nova ao final. Trunca listas muito longas para economizar tokens
    (e, consequentemente, evitar bater no rate limit de tokens/minuto da Groq).
    """
    tabelas = _extrair_tabelas_do_texto(tabelas_contexto_texto)
    linhas_schema = []
    for tabela in tabelas:
        colunas = _obter_colunas_tabela(tabela)
        if not colunas:
            continue
        if len(colunas) > max_colunas_por_tabela:
            colunas_texto = ", ".join(colunas[:max_colunas_por_tabela]) + f", ... (+{len(colunas) - max_colunas_por_tabela} colunas)"
        else:
            colunas_texto = ", ".join(colunas)
        linhas_schema.append(f"- `{tabela}`: {colunas_texto}")
    if not linhas_schema:
        return tabelas_contexto_texto
    return (
        tabelas_contexto_texto
        + "\n\n### SCHEMA REAL VERIFICADO NO BIGQUERY (fonte da verdade — use SOMENTE estas colunas)\n"
        + "\n".join(linhas_schema)
    )


def _validar_tabelas_permitidas(sql: str, tabelas_permitidas: list):
    """
    Checagem rápida e sem custo: garante que a query só usa tabelas que estavam
    na lista de tabelas fornecida ao LLM. Se ele inventar uma tabela fora da
    lista, pegamos isso ANTES de gastar uma chamada de dry run/execução.
    """
    usadas = set(re.findall(r"`([\w]+\.[\w]+\.[\w]+)`", sql))
    nao_permitidas = usadas - set(tabelas_permitidas)
    if nao_permitidas:
        return False, (
            f"Você usou a(s) tabela(s) {sorted(nao_permitidas)}, que NÃO estão na lista de tabelas "
            f"permitidas para esta pergunta. Use exclusivamente uma destas: {sorted(set(tabelas_permitidas))}."
        )
    return True, ""


def _dataframe_para_texto(df: pd.DataFrame) -> str:
    """Converte o dataframe em texto para os prompts, sem depender de 'tabulate'."""
    try:
        return df.to_markdown()
    except ImportError:
        # 'tabulate' não instalado — cai para uma representação simples em texto
        return df.to_string()


def dataframe_para_xlsx(df: pd.DataFrame, estatisticas: str = None, sql: str = None) -> bytes:
    """
    Gera um arquivo .xlsx em memória (bytes), pronto para uso em
    st.download_button. Coloca os dados na aba 'Dados' e, se houver,
    o texto de estatísticas e a query SQL em abas separadas — assim o
    usuário baixa tudo junto em vez de só a tabela crua.
    """
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Dados", index=False)

        if estatisticas:
            pd.DataFrame({"Estatísticas": estatisticas.split("\n")}).to_excel(
                writer, sheet_name="Estatisticas", index=False
            )

        if sql:
            pd.DataFrame({"Query SQL": sql.split("\n")}).to_excel(
                writer, sheet_name="SQL", index=False
            )

        # Ajusta a largura das colunas na aba de dados para não ficar tudo cortado
        from openpyxl.utils import get_column_letter
        planilha = writer.sheets["Dados"]
        for i, col in enumerate(df.columns):
            largura = min(max(len(str(col)), df[col].astype(str).str.len().max() if len(df) else 0) + 2, 60)
            planilha.column_dimensions[get_column_letter(i + 1)].width = largura

    buffer.seek(0)
    return buffer.getvalue()


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


def buscar_tabelas_relevantes(pergunta_usuario: str, top_n: int = 3) -> list:
    """Busca tabelas no json de metadados baseado nas palavras da pergunta."""
    caminho_json = os.path.join(os.path.dirname(__file__), "tabelas_metadados.json")
    if not os.path.exists(caminho_json):
        return []
        
    try:
        with open(caminho_json, "r", encoding="utf-8") as f:
            todas_as_tabelas = json.load(f)
    except Exception:
        return []

    palavras_chave = pergunta_usuario.lower().split()
    tabelas_encontradas = []
    
    for tab in todas_as_tabelas:
        desc = tab.get('description', '')
        if not desc: continue
        texto_busca = f"{tab.get('dataset_id', '')} {tab.get('table_id', '')} {desc}".lower()
        
        score = sum(1 for palavra in palavras_chave if len(palavra) > 3 and palavra in texto_busca)
        if score > 0:
            tabelas_encontradas.append((score, tab))
            
    tabelas_encontradas.sort(key=lambda x: x[0], reverse=True)
    return [tab[1] for tab in tabelas_encontradas[:top_n]]


def ask(question: str) -> dict:
    """
    Nova arquitetura Chain:
    0.1 Classificação de Escopo
    0.2 Roteamento de Metadados
    1. Gera SQL
    2. Executa via Pandas
    3. Gera Análise Textual
    4. Gera Config de Gráfico
    """
    try:
        llm = get_llm()
        engine = get_engine()

        # 0.1 Classificação de Escopo (Guardião)
        prompt_scope = ChatPromptTemplate.from_template(SCOPE_CLASSIFIER_PROMPT)
        chain_scope = prompt_scope | llm | StrOutputParser()
        escopo = chain_scope.invoke({"question": question}).strip().lower()
        
        if "conversa" in escopo:
            prompt_conversa = ChatPromptTemplate.from_template("O usuário disse: {question}\nResponda de forma amigável e direta, e informe que você só faz consultas a dados estruturados.")
            chain_conversa = prompt_conversa | llm | StrOutputParser()
            resposta_conversa = chain_conversa.invoke({"question": question})
            return {
                "analysis": resposta_conversa,
                "sql": "-- Nenhuma query gerada. Pergunta classificada como conversa/meta.",
                "dataframe": pd.DataFrame(),
                "ml_config": ML_CONFIG_DEFAULTS,
                "estatisticas": None,
                "figura": None
            }

        # 0.2 Roteamento de Tema via Metadados (RAG Local)
        tabelas_rag = buscar_tabelas_relevantes(question)
        if tabelas_rag:
            contexto_prompt = ""
            for t in tabelas_rag:
                contexto_prompt += f"- Tabela: `basedosdados.{t.get('dataset_id', '')}.{t.get('table_id', '')}`\n  Descrição: {t.get('description', '')}\n\n"
            tabelas_contexto_base = BASE_TABLE + "\n" + contexto_prompt
        else:
            prompt_router = ChatPromptTemplate.from_template(ROUTER_PROMPT)
            chain_router = prompt_router | llm | StrOutputParser()
            tema = chain_router.invoke({"question": question}).strip().lower()
            if tema not in TABLE_SCHEMAS_MAP:
                tema = "geral"
            tabelas_contexto_base = BASE_TABLE + "\n" + TABLE_SCHEMAS_MAP[tema]

        tabelas_permitidas = _extrair_tabelas_do_texto(tabelas_contexto_base)
        tabelas_contexto = _enriquecer_contexto_com_schema_real(tabelas_contexto_base)

        # 1. Geração SQL + Execução, com loop de correção único.
        # Trata: tabela fora da lista permitida, erros de sintaxe/schema (dry run),
        # e queries válidas que rodam mas voltam com 0 linhas (filtro errado).
        max_tentativas = 4
        sql_query = ""
        erro_anterior = ""
        df = None

        for tentativa in range(max_tentativas):
            contexto_erro = (
                f"\nSua tentativa anterior teve um problema: {erro_anterior}\n"
                "Por favor, reescreva a query corrigindo o problema usando apenas as "
                "colunas do schema fornecido e evite repetir o mesmo erro."
                if erro_anterior else ""
            )

            prompt_sql = ChatPromptTemplate.from_template(SQL_PROMPT)
            chain_sql = prompt_sql | llm | StrOutputParser()
            resposta_llm = _invocar_com_retry(chain_sql, {
                "question": question,
                "tabelas_contexto": tabelas_contexto,
                "contexto_erro": contexto_erro
            })
            sql_query = extrair_sql(resposta_llm)

            if not sql_query:
                erro_anterior = "A resposta do modelo veio vazia."
                df = None
                continue

            # Checagem barata (sem custo de BigQuery): a query só pode usar tabelas
            # que estavam na lista fornecida — pega tabelas inventadas na hora, sem
            # gastar uma tentativa de dry run/execução com elas.
            tabelas_ok, msg_tabelas = _validar_tabelas_permitidas(sql_query, tabelas_permitidas)
            if not tabelas_ok:
                erro_anterior = msg_tabelas
                df = None
                continue

            sucesso, msg = validar_query_bigquery(sql_query)
            if not sucesso:
                erro_anterior = msg
                df = None
                continue

            try:
                df = pd.read_sql(sql_query, engine)
            except Exception as e:
                erro_anterior = str(e)
                df = None
                continue

            if df.empty:
                dica_investigacao = _investigar_valores_reais(sql_query)
                erro_anterior = (
                    "A query é sintaticamente válida e rodou sem erros, mas retornou 0 linhas. "
                    "Isso normalmente indica um valor de filtro incorreto (ex: um código categórico "
                    "que não existe de fato nos dados)." + dica_investigacao
                )
                continue  # tenta de novo já com a dica do que corrigir

            break  # sucesso: query válida e com resultados

        if df is None or df.empty:
            return {
                "error": (
                    f"**Não foi possível obter resultados após {max_tentativas} tentativas.**\n"
                    f"Último problema: {erro_anterior}\n\n"
                    f"**Última Query Gerada:**\n```sql\n{sql_query}\n```"
                ),
                "sql": sql_query,
            }

        # 3. Análise
        data_sample = _dataframe_para_texto(df.head(20))
        linhas_totais = len(df)
        prompt_analysis = ChatPromptTemplate.from_template(ANALYSIS_PROMPT)
        chain_analysis = prompt_analysis | llm | StrOutputParser()
        analysis = _invocar_com_retry(chain_analysis, {"question": question, "sql": sql_query, "data": data_sample, "linhas": linhas_totais})

        # 4. Machine Learning & Gráfico
        prompt_ml = ChatPromptTemplate.from_template(ML_PROMPT)
        chain_ml = prompt_ml | llm | StrOutputParser()
        ml_json_str = _invocar_com_retry(chain_ml, {"question": question, "data": data_sample})

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


def is_followup_analysis(prompt: str) -> bool:
    """Verifica se a pergunta do usuário é um pedido de nova análise/gráfico sobre os dados já extraídos."""
    try:
        llm = get_llm()
        prompt_router = ChatPromptTemplate.from_template(
            "O usuário enviou a mensagem: '{question}'. "
            "Isso é um pedido para reanalisar os dados recém extraídos (ex: 'agrupe por', 'faça um grafico', 'qual a media disso', etc) "
            "em vez de pedir dados de um novo assunto? "
            "Responda APENAS 'sim' ou 'nao'."
        )
        chain = prompt_router | llm | StrOutputParser()
        resp = _invocar_com_retry(chain, {"question": prompt}).strip().lower()
        return "sim" in resp
    except:
        return False


def analyze_cached(question: str, df: pd.DataFrame, sql_query: str) -> dict:
    """Faz a Análise IA e ML em cima de um dataframe cacheado, sem usar o BigQuery."""
    try:
        llm = get_llm()
        data_sample = _dataframe_para_texto(df.head(20))
        linhas_totais = len(df)
        
        prompt_analysis = ChatPromptTemplate.from_template(ANALYSIS_PROMPT)
        chain_analysis = prompt_analysis | llm | StrOutputParser()
        analysis = _invocar_com_retry(chain_analysis, {"question": question, "sql": sql_query, "data": data_sample, "linhas": linhas_totais})

        prompt_ml = ChatPromptTemplate.from_template(ML_PROMPT)
        chain_ml = prompt_ml | llm | StrOutputParser()
        ml_json_str = _invocar_com_retry(chain_ml, {"question": question, "data": data_sample})

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
            "sql": sql_query,
            "dataframe": df,
            "analysis": analysis,
            "ml_config": ml_config,
            "estatisticas": analise_ml["stats"],
            "figura": analise_ml["figura"],
        }
    except Exception as e:
        return {"error": f"❌ Erro ao processar dados cacheados: {str(e)}"}


if __name__ == "__main__":
    res = ask("Qual a população dos municípios de SP em 2022 segundo o IBGE?")
    print(res)