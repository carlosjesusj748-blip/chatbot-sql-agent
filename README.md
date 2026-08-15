# Chatbot SQL Agent 🤖

Assistente Especialista em Dados com Text-to-SQL powered by **Gemini + LangChain**.

## O que faz?

Recebe perguntas em linguagem natural e retorna:
1. **Resumo da Base** — tabelas e variáveis utilizadas
2. **Lógica Aplicada** — filtros e agregações explicados
3. **SQL Otimizado** — query pronta para execução
4. **Resultado** — dados retornados pela consulta

## Stack

- **LLM:** Google Gemini 2.0 Flash
- **Framework:** LangChain SQL Agent
- **Banco:** SQLite (dados de vendas de exemplo)
- **Interface:** Streamlit
- **Deploy:** Render

## Rodar Localmente

```bash
# 1. Instalar dependências
pip install -r requirements.txt

# 2. Criar banco de dados de teste
python setup_database.py

# 3. Configurar API Key do Gemini
# Obtenha em: https://aistudio.google.com/app/apikey
export GOOGLE_API_KEY="sua-chave-aqui"

# 4. Rodar o app
streamlit run app.py
```

## Deploy no Render

1. Conecte este repositório no [Render](https://render.com)
2. Crie um **Web Service** apontando para este repo
3. Configure:
   - **Build Command:** `pip install -r requirements.txt && python setup_database.py`
   - **Start Command:** `streamlit run app.py --server.port $PORT --server.address 0.0.0.0 --server.headless true`
4. Adicione a variável de ambiente `GOOGLE_API_KEY`
5. Deploy!

## Estrutura

```
chatbot-sql-agent/
├── app.py              # Interface Streamlit
├── agent.py            # LangChain SQL Agent + Gemini
├── setup_database.py   # Cria banco SQLite com dados de teste
├── requirements.txt    # Dependências Python
├── render.yaml         # Config de deploy no Render
└── README.md
```
