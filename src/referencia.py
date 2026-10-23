"""Seção 2: medição de referência com o SonarQube (servidor no Docker, scanner sob demanda)."""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import pandas as pd
import requests

from . import config as C

# Métricas por arquivo coletadas da API (qualifier FIL)
METRICAS = ["ncloc", "functions", "complexity", "comment_lines", "comment_lines_density",
            "duplicated_lines", "duplicated_lines_density", "sqale_index", "sqale_debt_ratio"]

SONAR_DIR = C.RAW_DIR / "sonar"
BINARIOS_VAZIOS = C.RAW_DIR / "sonar_binarios_vazios"   # sonar.java.binaries: métricas não dependem de bytecode
REDE_DOCKER = "tcc-storch-experiment_default"           # rede criada pelo docker-compose
SONAR_URL_INTERNA = "http://tcc-sonarqube:9000"          # como o scanner enxerga o servidor dentro da rede
IMAGEM_SCANNER = "sonarsource/sonar-scanner-cli"


# ---------------------------------------------------------------------------
# Configuração (.env)
# ---------------------------------------------------------------------------
def ler_env(caminho: Path = C.RAIZ / ".env") -> dict:
    env = {}
    if caminho.exists():
        for linha in caminho.read_text().splitlines():
            linha = linha.strip()
            if linha and not linha.startswith("#") and "=" in linha:
                k, v = linha.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


class Sonar:
    def __init__(self, url: str, token: str):
        self.url = url.rstrip("/")
        self.sessao = requests.Session()
        self.sessao.auth = (token, "")   # token como usuário, senha vazia (aceito por todas as versões)

    def get(self, rota: str, **params) -> dict:
        r = self.sessao.get(f"{self.url}/{rota}", params=params, timeout=60)
        r.raise_for_status()
        return r.json() if r.headers.get("content-type", "").startswith("application/json") else {"texto": r.text}

    # 2.1 ---------------------------------------------------------------
    def estado(self) -> dict:
        status = self.get("api/system/status")
        versao = self.sessao.get(f"{self.url}/api/server/version", timeout=30).text.strip()
        autenticado = self.get("api/authentication/validate").get("valid", False)
        return {"status": status.get("status"), "versao_servidor": versao, "token_valido": autenticado}

    # 2.3 ---------------------------------------------------------------
    def esperar_tarefa(self, task_id: str, timeout_s: int = 3600, intervalo_s: int = 5) -> dict:
        inicio = time.time()
        while True:
            tarefa = self.get("api/ce/task", id=task_id)["task"]
            if tarefa["status"] in ("SUCCESS", "FAILED", "CANCELED"):
                return tarefa
            if time.time() - inicio > timeout_s:
                raise TimeoutError(f"Tarefa {task_id} não terminou em {timeout_s}s (status {tarefa['status']}).")
            time.sleep(intervalo_s)

    # 2.4 ---------------------------------------------------------------
    def medidas_por_arquivo(self, project_key: str) -> list[dict]:
        componentes, pagina = [], 1
        while True:
            dados = self.get("api/measures/component_tree", component=project_key, qualifiers="FIL",
                             metricKeys=",".join(METRICAS), ps=500, p=pagina)
            componentes += dados["components"]
            if pagina * 500 >= dados["paging"]["total"]:
                return componentes
            pagina += 1


def digest_imagem(imagem: str) -> str | None:
    r = subprocess.run(["docker", "image", "inspect", imagem, "--format", "{{index .RepoDigests 0}}"],
                       capture_output=True, text=True)
    return r.stdout.strip() or None


# ---------------------------------------------------------------------------
# 2.2 Análise de um repositório
# ---------------------------------------------------------------------------
def _exclusoes(linguagem: str) -> str:
    dirs = sorted({d for _, nomes in C.DIRETORIOS_EXCLUIDOS for d in nomes})
    padroes = [f"**/{d}/**" for d in dirs]
    if linguagem == "java":
        padroes += ["**/*Test.java", "**/*Tests.java", "**/*IT.java"]
    else:
        padroes += ["**/test_*.py", "**/*_test.py", "**/conftest.py"]
    return ",".join(padroes)


def comando_scanner(projeto: str, linguagem: str, token: str) -> list[str]:
    repo = (C.REPOS_DIR / projeto).resolve()
    BINARIOS_VAZIOS.mkdir(parents=True, exist_ok=True)
    props = {
        "sonar.projectKey": f"tcc-{projeto}",
        "sonar.projectName": f"TCC {projeto}",
        "sonar.sources": ".",
        "sonar.inclusions": "**/*.py" if linguagem == "python" else "**/*.java",
        "sonar.exclusions": _exclusoes(linguagem),
        "sonar.scm.disabled": "true",          # clone raso: sem blame
        "sonar.sourceEncoding": "UTF-8",
    }
    if linguagem == "java":
        props["sonar.java.binaries"] = "/tmp/binarios_vazios"
    else:
        props["sonar.python.version"] = "3.12"
    return [
        "docker", "run", "--rm",
        "--network", REDE_DOCKER,
        "-e", f"SONAR_HOST_URL={SONAR_URL_INTERNA}",
        "-e", f"SONAR_TOKEN={token}",
        "-e", "SONAR_SCANNER_JAVA_OPTS=-Xmx3g",
        "-e", "SONAR_SCANNER_OPTS=-Xmx3g",
        "-v", f"{repo}:/usr/src",
        "-v", f"{BINARIOS_VAZIOS.resolve()}:/tmp/binarios_vazios",
        IMAGEM_SCANNER,
        *[f"-D{k}={v}" for k, v in props.items()],
    ]


def analisar(projeto: str, linguagem: str, token: str) -> dict:
    """Roda o scanner e devolve o ID da tarefa de processamento no servidor."""
    inicio = time.time()
    r = subprocess.run(comando_scanner(projeto, linguagem, token), capture_output=True, text=True)
    log = C.RAW_DIR / "sonar" / f"scanner_{projeto}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(r.stdout + "\n" + r.stderr)
    if r.returncode != 0:
        raise RuntimeError(f"Scanner falhou em {projeto} (código {r.returncode}). Veja {log}.")
    relatorio = (C.REPOS_DIR / projeto / ".scannerwork" / "report-task.txt").read_text()
    props = dict(l.split("=", 1) for l in relatorio.splitlines() if "=" in l)
    return {"projeto": projeto, "task_id": props["ceTaskId"], "duracao_scanner_s": round(time.time() - inicio, 1)}


# ---------------------------------------------------------------------------
# 2.4 Coleta e conversão para tabela
# ---------------------------------------------------------------------------
def salvar_bruto(projeto: str, componentes: list[dict]) -> Path:
    SONAR_DIR.mkdir(parents=True, exist_ok=True)
    caminho = SONAR_DIR / f"{projeto}_component_tree.json"
    caminho.write_text(json.dumps(componentes, ensure_ascii=False, indent=1))
    return caminho


def tabela_medidas(projeto: str, componentes: list[dict]) -> pd.DataFrame:
    linhas = []
    for c in componentes:
        linha = {"projeto": projeto, "caminho": c["path"]}
        for m in c.get("measures", []):
            linha[m["metric"]] = float(m["value"]) if "value" in m else None
        linhas.append(linha)
    df = pd.DataFrame(linhas)
    for m in METRICAS:
        if m not in df.columns:
            df[m] = None
    return df[["projeto", "caminho", *METRICAS]]
