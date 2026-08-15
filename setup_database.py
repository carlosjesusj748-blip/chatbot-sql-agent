"""
setup_database.py
-----------------
Cria o banco de dados SQLite 'vendas.db' com tabelas de exemplo
para testes do Assistente Especialista em Dados (Text-to-SQL).

Tabelas criadas:
  - clientes (id, nome, estado, segmento)
  - produtos (id, nome, categoria, preco_unitario)
  - vendas   (id, cliente_id, produto_id, quantidade, valor_total, data_venda)
"""

import sqlite3
import random
from datetime import datetime, timedelta

DB_PATH = "vendas.db"


def criar_banco():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # ── Tabela: clientes ──────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            estado TEXT NOT NULL,
            segmento TEXT NOT NULL
        )
    """)

    # ── Tabela: produtos ──────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            categoria TEXT NOT NULL,
            preco_unitario REAL NOT NULL
        )
    """)

    # ── Tabela: vendas ────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vendas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL,
            produto_id INTEGER NOT NULL,
            quantidade INTEGER NOT NULL,
            valor_total REAL NOT NULL,
            data_venda TEXT NOT NULL,
            FOREIGN KEY (cliente_id) REFERENCES clientes(id),
            FOREIGN KEY (produto_id) REFERENCES produtos(id)
        )
    """)

    # ── Dados: Clientes ───────────────────────────────────────────────
    nomes = [
        "Ana Silva", "Bruno Costa", "Carla Mendes", "Diego Oliveira",
        "Elena Souza", "Felipe Ramos", "Gabriela Lima", "Hugo Almeida",
        "Isabela Ferreira", "João Santos", "Karen Ribeiro", "Lucas Pereira",
        "Marina Barbosa", "Nelson Araújo", "Olívia Cardoso", "Paulo Neves",
        "Queila Martins", "Rafael Teixeira", "Sandra Rocha", "Thiago Borges",
        "Úrsula Dias", "Vinícius Lopes", "Wanda Correia", "Xavier Moura",
        "Yasmin Gomes", "Zeca Pinheiro", "Amanda Torres", "Bernardo Farias",
        "Cecília Duarte", "Daniel Vieira", "Estela Monteiro", "Fábio Cunha",
        "Glória Freitas", "Heitor Campos", "Irene Batista", "Júlio Rezende",
        "Lara Nogueira", "Marcos Sampaio", "Natália Guedes", "Oscar Machado",
        "Priscila Assis", "Quintino Braz", "Renata Carneiro", "Sérgio Leal",
        "Tatiana Mesquita", "Ulisses Rangel", "Vera Aguiar", "Walter Soares",
        "Ximena Queiroz", "Yuri Dantas"
    ]
    estados = ["SP", "RJ", "MG", "BA", "RS", "PR", "PE", "CE", "PA", "GO",
               "SC", "MA", "AM", "ES", "PB", "RN", "MT", "MS", "DF", "SE"]
    segmentos = ["Varejo", "Atacado", "Corporativo", "E-commerce"]

    clientes_data = []
    for nome in nomes:
        clientes_data.append((nome, random.choice(estados), random.choice(segmentos)))

    cursor.executemany(
        "INSERT INTO clientes (nome, estado, segmento) VALUES (?, ?, ?)",
        clientes_data
    )

    # ── Dados: Produtos ───────────────────────────────────────────────
    produtos_data = [
        ("Notebook Pro 15", "Eletrônicos", 4299.90),
        ("Mouse Wireless", "Eletrônicos", 89.90),
        ("Teclado Mecânico RGB", "Eletrônicos", 349.90),
        ("Monitor 27'' 4K", "Eletrônicos", 2199.90),
        ("Webcam HD", "Eletrônicos", 199.90),
        ("Headset Gamer", "Eletrônicos", 279.90),
        ("Cadeira Ergonômica", "Móveis", 1899.90),
        ("Mesa L 1.60m", "Móveis", 799.90),
        ("Estante Organizadora", "Móveis", 459.90),
        ("Gaveteiro Móvel", "Móveis", 329.90),
        ("Papel A4 (500fls)", "Escritório", 29.90),
        ("Caneta Esferográfica (cx)", "Escritório", 18.90),
        ("Grampeador Metal", "Escritório", 34.90),
        ("Agenda 2026", "Escritório", 49.90),
        ("Post-it Colorido", "Escritório", 12.90),
        ("Impressora Laser", "Eletrônicos", 1599.90),
        ("SSD 1TB NVMe", "Eletrônicos", 499.90),
        ("Hub USB-C 7 portas", "Eletrônicos", 159.90),
        ("Suporte Notebook", "Móveis", 129.90),
        ("Luminária LED Desk", "Móveis", 189.90),
        ("Mochila Executiva", "Acessórios", 249.90),
        ("Capa para Notebook", "Acessórios", 79.90),
        ("Mousepad XL", "Acessórios", 59.90),
        ("Cabo HDMI 2m", "Acessórios", 39.90),
        ("Carregador Universal", "Acessórios", 119.90),
        ("Software Antivírus (1 ano)", "Software", 99.90),
        ("Licença Office 365", "Software", 359.90),
        ("VPN Premium (1 ano)", "Software", 199.90),
        ("Cloud Storage 1TB", "Software", 149.90),
        ("Curso Online Python", "Software", 89.90),
    ]

    cursor.executemany(
        "INSERT INTO produtos (nome, categoria, preco_unitario) VALUES (?, ?, ?)",
        produtos_data
    )

    # ── Dados: Vendas ─────────────────────────────────────────────────
    num_clientes = len(nomes)
    num_produtos = len(produtos_data)
    vendas_data = []

    # Gerar 200 vendas nos últimos 12 meses
    data_base = datetime(2026, 8, 15)
    for _ in range(200):
        cliente_id = random.randint(1, num_clientes)
        produto_id = random.randint(1, num_produtos)
        quantidade = random.randint(1, 20)
        preco = produtos_data[produto_id - 1][2]
        valor_total = round(preco * quantidade, 2)
        dias_atras = random.randint(0, 365)
        data_venda = (data_base - timedelta(days=dias_atras)).strftime("%Y-%m-%d")
        vendas_data.append((cliente_id, produto_id, quantidade, valor_total, data_venda))

    cursor.executemany(
        "INSERT INTO vendas (cliente_id, produto_id, quantidade, valor_total, data_venda) VALUES (?, ?, ?, ?, ?)",
        vendas_data
    )

    conn.commit()

    # ── Verificação ───────────────────────────────────────────────────
    for tabela in ["clientes", "produtos", "vendas"]:
        count = cursor.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
        print(f"[OK] Tabela '{tabela}': {count} registros")

    conn.close()
    print(f"\n[SUCESSO] Banco '{DB_PATH}' criado com sucesso!")


if __name__ == "__main__":
    criar_banco()
