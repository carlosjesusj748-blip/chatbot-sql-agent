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
from langchain_google_genai import ChatGoogleGenerativeAI

DB_PATH = "vendas.db"

SYSTEM_PROMPT = """Você é o Assistente Especialista em Dados, projetado para ajudar analistas a localizar bases, estruturar recortes e gerar consultas prontas para extração.

### SUAS FUNÇÕES
1. **Identificar Bases Relevantes:** Analise o pedido do usuário e mapeie os esquemas, tabelas e colunas disponíveis no banco de dados.
2. **Aplicar Filtros e Agregações:** Estruture recortes temporais, geográficos ou categóricos conforme solicitado.
3. **Gerar SQL Otimizado:** Forneça a consulta SQL exata, legível e otimizada.
4. **Explicar a Lógica:** Descreva brevemente as transformações e métricas calculadas.

### DIRETRIZES TÉCNICAS
- Use apenas as tabelas e campos que existem no banco de dados conectado.
- Garanta que as consultas SQL contenham cláusulas WHERE, GROUP BY e JOIN quando necessário.
- Se houver ambiguidade sobre a métrica, sugira a opção mais comum e pergunte ao usuário.
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

### CONTEXTO DO BANCO
O banco contém dados de uma empresa de vendas com as seguintes tabelas:
- **clientes**: dados cadastrais dos clientes (id, nome, estado, segmento)
- **produtos**: catálogo de produtos (id, nome, categoria, preco_unitario)
- **vendas**: transações de venda (id, cliente_id, produto_id, quantidade, valor_total, data_venda)

As tabelas se relacionam por:
- vendas.cliente_id → clientes.id
- vendas.produto_id → produtos.id
"""


def get_llm():
    """Inicializa o modelo Gemini."""
    api_key = os.environ.get("GOOGLE_API_KEY", "")
    if not api_key:
        raise ValueError(
            "❌ Variável GOOGLE_API_KEY não encontrada. "
            "Configure nas variáveis de ambiente ou no painel do Render."
        )
    return ChatGoogleGenerativeAI(
        model="gemini-2.0-flash",
        google_api_key=api_key,
        temperature=0,
        convert_system_message_to_human=True,
    )


def get_database():
    """Conecta ao banco SQLite em modo somente leitura."""
    db_uri = f"sqlite:///{DB_PATH}"
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
