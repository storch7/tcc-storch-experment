# Experimento do TCC — Padrões de prompt e aferição de manutenibilidade por LLMs

Guilherme Storch · Orientação: Prof. Hilmer Rodrigues Neri · UnB/FCTE

Repositório do experimento controlado descrito no Capítulo 5 do TCC. Todos os dados
gerados ficam em `data/` (arquivos abertos, sem banco de dados), para que o estudo
possa ser reproduzido a partir deste repositório.

## Estrutura

```
config/corpus_repos.csv      repositórios do corpus, com release e commit fixados
src/config.py                todas as regras de seleção (exclusões, seed, k, LOC)
src/corpus.py                Seção 1: clone, inventário, classificação por tipo, funil, amostragem
notebooks/experimento_tcc.ipynb   notebook principal (seções 0 a 11)
data/raw/repos/              clones (ignorados pelo git; recriados pelo notebook)
data/processed/              tabelas intermediárias (inventario.csv, corpus_repos.csv, corpus.csv)
data/outputs/                tabelas e figuras usadas na monografia
```

## Como reproduzir

```bash
python3.12 -m venv .venv      # no Mac: brew install python@3.12
source .venv/bin/activate
pip install -r requirements.txt
jupyter lab notebooks/experimento_tcc.ipynb   # Run All
```

Requisitos: **Python 3.12+** (versões anteriores não leem a sintaxe do Django 6.1 e do
pandas 3, e o corpus muda), git e acesso ao GitHub (a Seção 1 clona os seis repositórios,
cerca de 1 GB). A partir da Seção 2: SonarQube local e `.env` (ver `.env.example`).

## SonarQube (a partir da Seção 2)

Requer Docker Desktop com pelo menos 4 GB de memória (Settings → Resources).

```bash
docker compose -f docker/docker-compose.yml up -d
```

1. Aguarde 1–2 minutos e abra http://localhost:9000 (admin / admin; troque a senha).
2. Gere um token: My Account → Security → Generate Token (tipo *Global Analysis Token*).
3. Copie `.env.example` para `.env` e preencha `SONAR_TOKEN`.

## Estado

| Seção | Situação |
|---|---|
| 0 Configuração | implementada |
| 1 Corpus e funil | implementada (k por estrato e corte de LOC pendentes) |
| 2 Referência SonarQube | em andamento (Docker criado) |
| 3–11 | a implementar |
