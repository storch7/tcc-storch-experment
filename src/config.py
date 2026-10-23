"""Configuração central do experimento.

Toda regra que afeta quais dados entram no experimento fica aqui, em um só
lugar, para ser citada no Capítulo 5 e reproduzida por qualquer pessoa.
"""
from pathlib import Path

# ---------------------------------------------------------------------------
# Caminhos
# ---------------------------------------------------------------------------
RAIZ = Path(__file__).resolve().parents[1]
CONFIG_DIR = RAIZ / "config"
DATA_DIR = RAIZ / "data"
RAW_DIR = DATA_DIR / "raw"
REPOS_DIR = RAW_DIR / "repos"          # clones (ignorados pelo git)
PROCESSED_DIR = DATA_DIR / "processed"
OUTPUTS_DIR = DATA_DIR / "outputs"
FIGURAS_DIR = OUTPUTS_DIR / "figuras"

CORPUS_REPOS_CSV = CONFIG_DIR / "corpus_repos.csv"

# ---------------------------------------------------------------------------
# Reprodutibilidade
# ---------------------------------------------------------------------------
SEED = 42

# ---------------------------------------------------------------------------
# Regras de exclusão de arquivos (aplicadas nesta ordem; a primeira que casar
# define o motivo registrado no funil). Caminhos relativos à raiz do repositório,
# comparados em minúsculas e com "/" como separador.
# ---------------------------------------------------------------------------
EXTENSAO_POR_LINGUAGEM = {"python": ".py", "java": ".java"}

# (motivo, lista de trechos de diretório). Casa se algum segmento do caminho
# for exatamente um dos nomes listados.
DIRETORIOS_EXCLUIDOS = [
    ("teste", ["test", "tests", "testing", "test_utils", "testutils", "_testing", "it", "e2e", "test-harness"]),
    ("documentacao_exemplo", ["doc", "docs", "example", "examples", "sample", "samples", "demo"]),
    ("script_build_benchmark", ["scripts", "script", "benchmark", "benchmarks", "asv_bench", "ci", "build",
                                "dist", "buildtools", ".github", "tools"]),
    ("migracao_locale", ["migrations", "locale"]),
    ("vendor_gerado", ["vendor", "third_party", "_vendor", "generated", "gen"]),
]

# Arquivos de teste identificados pelo nome (mesmo fora de pastas de teste)
PADROES_NOME_TESTE = [
    r"^test_.*\.py$", r".*_test\.py$", r"^conftest\.py$",
    r".*Test\.java$", r".*Tests\.java$", r".*IT\.java$", r"^Test.*\.java$",
]

# Arquivos estruturais do pacote, sem lógica própria relevante
ARQUIVOS_ESTRUTURAIS = {"__init__.py", "package-info.java", "module-info.java", "setup.py", "conftest.py"}

# Tipos de arquivo excluídos porque as medidas do Q-Rapids não se aplicam
# (não há funções para medir complexidade por função).
TIPOS_EXCLUIDOS = {"sem_definicoes", "anotacao"}

# Além disso, qualquer arquivo com zero funções/métodos com corpo é excluído
# (motivo "sem_funcoes"): ex. interface Java sem default, classe só com atributos.


# ---------------------------------------------------------------------------
# Limite de tamanho (LOC não vazias). Definido no piloto; None = sem corte.
# ---------------------------------------------------------------------------
LOC_MIN = None
LOC_MAX = None

# ---------------------------------------------------------------------------
# Amostragem estratificada (repositório × tipo). Definido com o orientador.
# ---------------------------------------------------------------------------
K_POR_ESTRATO = None   # ex.: 20 -> até 20 arquivos por estrato
K_CANDIDATOS = [10, 20, 30, 50]  # cenários apresentados ao orientador
