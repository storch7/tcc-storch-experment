"""Seção 1 do notebook: corpus, funil de exclusão, classificação por tipo e amostragem."""
from __future__ import annotations

import ast
import sys

if sys.version_info < (3, 12):
    raise RuntimeError(
        f"Python {sys.version.split()[0]} detectado. Use Python 3.12+: versões anteriores do 'ast' "
        "não leem a sintaxe do Django 6.1/pandas 3 e excluem arquivos indevidamente (erro_parse)."
    )
import hashlib
import re
import subprocess
from pathlib import Path

import pandas as pd
import tree_sitter_java as tsjava
from tree_sitter import Language, Parser

from . import config as C

_JAVA = Parser(Language(tsjava.language()))
_PADROES_TESTE = [re.compile(p) for p in C.PADROES_NOME_TESTE]


# ---------------------------------------------------------------------------
# 1.1 Repositórios
# ---------------------------------------------------------------------------
def carregar_repos() -> pd.DataFrame:
    return pd.read_csv(C.CORPUS_REPOS_CSV)


def _git(*args, cwd=None) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def preparar_repositorio(projeto: str, url: str, release: str, commit: str) -> dict:
    """Clona o repositório na release fixada (se necessário) e confere o commit."""
    destino = C.REPOS_DIR / projeto
    if not destino.exists():
        C.REPOS_DIR.mkdir(parents=True, exist_ok=True)
        _git("clone", "--quiet", "--depth", "1", "--branch", release, url, str(destino))
    head = _git("rev-parse", "HEAD", cwd=destino)
    return {"projeto": projeto, "commit_esperado": commit, "commit_obtido": head, "confere": head == commit,
            "data_commit": _git("log", "-1", "--format=%cs", cwd=destino)}


# ---------------------------------------------------------------------------
# 1.2 Classificação por tipo
# ---------------------------------------------------------------------------
def classificar_python(fonte: str) -> dict:
    try:
        arvore = ast.parse(fonte)
    except SyntaxError:
        return {"tipo": "erro_parse", "n_funcoes": 0}
    classes = [n for n in arvore.body if isinstance(n, ast.ClassDef)]
    funcoes_modulo = [n for n in arvore.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    n_funcoes = sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) for n in ast.walk(arvore))
    if classes and not funcoes_modulo:
        tipo = "classe"
    elif funcoes_modulo and not classes:
        tipo = "modulo_funcoes"
    elif classes and funcoes_modulo:
        tipo = "misto"
    else:
        tipo = "sem_definicoes"
    return {"tipo": tipo, "n_funcoes": n_funcoes}


_TIPO_JAVA = {
    "class_declaration": "classe",
    "interface_declaration": "interface",
    "enum_declaration": "enum_record",
    "record_declaration": "enum_record",
    "annotation_type_declaration": "anotacao",
}


def classificar_java(fonte: str) -> dict:
    raiz = _JAVA.parse(fonte.encode("utf-8", errors="ignore")).root_node
    topo = [n for n in raiz.children if n.type in _TIPO_JAVA]
    if not topo:
        return {"tipo": "erro_parse" if raiz.has_error else "sem_definicoes", "n_funcoes": 0}
    principal = topo[0]
    # métodos/construtores com corpo em todo o arquivo (o que o Sonar conta em "functions")
    pilha, n_funcoes = [raiz], 0
    while pilha:
        no = pilha.pop()
        if no.type in ("method_declaration", "constructor_declaration", "compact_constructor_declaration"):
            if no.child_by_field_name("body") is not None:
                n_funcoes += 1
        pilha.extend(no.children)
    return {"tipo": _TIPO_JAVA[principal.type], "n_funcoes": n_funcoes}


def contar_loc(fonte: str) -> int:
    """Linhas não vazias (aproximação usada só para descrever o corpus; o ncloc oficial vem do Sonar)."""
    return sum(1 for linha in fonte.splitlines() if linha.strip())


# ---------------------------------------------------------------------------
# 1.3 Inventário com funil de exclusão
# ---------------------------------------------------------------------------
def _motivo_por_caminho(rel: str) -> str | None:
    segmentos = rel.lower().split("/")[:-1]
    nome = rel.split("/")[-1]
    if nome in C.ARQUIVOS_ESTRUTURAIS:
        return "arquivo_estrutural"
    if any(p.match(nome) for p in _PADROES_TESTE):
        return "teste"
    for motivo, nomes in C.DIRETORIOS_EXCLUIDOS:
        if any(seg in nomes for seg in segmentos):
            return motivo
    return None


def inventariar(projeto: str, linguagem: str) -> pd.DataFrame:
    """Lista todos os arquivos da linguagem do repositório e registra se foi excluído e por quê."""
    raiz = C.REPOS_DIR / projeto
    ext = C.EXTENSAO_POR_LINGUAGEM[linguagem]
    classificar = classificar_python if linguagem == "python" else classificar_java
    linhas = []
    for arq in sorted(raiz.rglob(f"*{ext}")):
        rel = arq.relative_to(raiz).as_posix()
        if rel.startswith(".git/"):
            continue
        fonte = arq.read_text(encoding="utf-8", errors="ignore")
        info = {"projeto": projeto, "linguagem": linguagem, "caminho": rel, "loc": contar_loc(fonte),
                "sha256": hashlib.sha256(fonte.encode("utf-8", errors="ignore")).hexdigest()}
        motivo = _motivo_por_caminho(rel)
        if motivo is None:
            info.update(classificar(fonte))
            if info["tipo"] == "erro_parse":
                motivo = "erro_parse"
            elif info["tipo"] in C.TIPOS_EXCLUIDOS:
                motivo = f"tipo_{info['tipo']}"
            elif info["n_funcoes"] == 0:
                motivo = "sem_funcoes"
            elif C.LOC_MIN is not None and info["loc"] < C.LOC_MIN:
                motivo = "loc_abaixo_minimo"
            elif C.LOC_MAX is not None and info["loc"] > C.LOC_MAX:
                motivo = "loc_acima_maximo"
        else:
            info.update({"tipo": None, "n_funcoes": None})
        info["motivo_exclusao"] = motivo
        info["elegivel"] = motivo is None
        linhas.append(info)
    return pd.DataFrame(linhas)


ORDEM_FUNIL = ["arquivo_estrutural", "teste", "documentacao_exemplo", "script_build_benchmark",
               "migracao_locale", "vendor_gerado", "erro_parse", "tipo_sem_definicoes", "tipo_anotacao",
               "sem_funcoes", "loc_abaixo_minimo", "loc_acima_maximo"]


def funil(inv: pd.DataFrame) -> pd.DataFrame:
    """Tabela: total encontrado, exclusões por motivo e elegíveis, por projeto."""
    tab = (inv.assign(motivo=inv["motivo_exclusao"].fillna("elegivel"))
              .pivot_table(index="motivo", columns="projeto", values="caminho", aggfunc="count", fill_value=0))
    ordem = ["elegivel"] + [m for m in ORDEM_FUNIL if m in tab.index]
    tab = tab.reindex(ordem).fillna(0).astype(int)
    tab.loc["total_encontrado"] = tab.sum()
    tab = tab.reindex(["total_encontrado"] + ORDEM_FUNIL + ["elegivel"]).dropna(how="all").fillna(0).astype(int)
    tab["total"] = tab.sum(axis=1)
    return tab


# ---------------------------------------------------------------------------
# 1.4 Amostragem estratificada (repositório × tipo)
# ---------------------------------------------------------------------------
def tamanho_amostra_por_k(eleg: pd.DataFrame, ks: list[int]) -> pd.DataFrame:
    estratos = eleg.groupby(["projeto", "tipo"]).size().rename("N")
    tab = estratos.to_frame()
    for k in ks:
        tab[f"k={k}"] = estratos.clip(upper=k)
    tab.loc[("TOTAL", ""), :] = tab.sum()
    return tab.astype(int)


def amostrar(eleg: pd.DataFrame, k: int, seed: int = C.SEED) -> pd.DataFrame:
    """Sorteia até k arquivos por estrato (projeto × tipo), de forma reprodutível."""
    partes = []
    for (projeto, tipo), grupo in eleg.sort_values("caminho").groupby(["projeto", "tipo"]):
        partes.append(grupo.sample(n=min(k, len(grupo)), random_state=seed))
    amostra = pd.concat(partes).sort_values(["projeto", "tipo", "caminho"]).reset_index(drop=True)
    amostra.insert(0, "arquivo_id", [f"f_{i:04d}" for i in range(1, len(amostra) + 1)])
    return amostra
