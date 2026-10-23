"""Seção 2: indicador de manutenibilidade (IM) por arquivo segundo Q-Rapids e MeasureSoftGram.

As mesmas funções são usadas na Seção 7 sobre as medidas informadas pelos LLMs, para que
referência (SonarQube) e tratamento (LLM) cheguem ao IM pelo mesmo caminho.

Entrada de ambas as funções: complexity, functions, comment_lines_density (%),
duplicated_lines_density (%) e, no MSG com 4 medidas, sqale_debt_ratio (%).
"""
from __future__ import annotations

import math

import numpy as np

# MeasureSoftGram-Core, commit 02af9a9 (v1.5.5rc4). Ver decisão D10 no plano.
import core.aggregated_normalized_measures as _msg
from core.transformations import calculate_aggregated_weighted_value as _msg_agregar

# ---------------------------------------------------------------------------
# Q-Rapids, como implementado no notebook Analytics (fga-eps-mds/Analytics,
# internal_quality_analysis-sonarqube.ipynb): cada medida é a fração de arquivos
# que atende ao limite; para um único arquivo, vale 1 ou 0.
# ---------------------------------------------------------------------------
QRAPIDS_PESOS = {"complexidade": 0.33, "comentarios": 0.33, "duplicacao": 0.33}  # pm1, pm2, pm3 do notebook


def qrapids_medidas(complexity, functions, comment_lines_density, duplicated_lines_density) -> dict:
    return {
        "complexidade": float(functions > 0 and (complexity / functions) < 10),
        "comentarios": float(10 < comment_lines_density < 30),
        "duplicacao": float(duplicated_lines_density < 5),
    }


def qrapids_im(complexity, functions, comment_lines_density, duplicated_lines_density) -> float:
    m = qrapids_medidas(complexity, functions, comment_lines_density, duplicated_lines_density)
    return sum(m[k] * QRAPIDS_PESOS[k] for k in QRAPIDS_PESOS)


# ---------------------------------------------------------------------------
# MeasureSoftGram: funções de medida do MSG-Core com os limites da configuração
# padrão (staticfiles/default_pre_config.py) e agregação por norma ponderada.
# A função de alto nível calculate_measures() não aceita um único arquivo
# (converte a lista em escalar), por isso as funções de medida são chamadas diretamente.
# ---------------------------------------------------------------------------
MSG_LIMITES = {
    "non_complex_file_density": (0, 10),
    "commented_file_density": (10, 30),
    "duplication_absense": (0, 5),
    "technical_debt_ratio": (0, 20),
}
MSG_PESOS = {
    3: {"non_complex_file_density": 33, "commented_file_density": 33, "duplication_absense": 34},
    4: {"non_complex_file_density": 25, "commented_file_density": 25, "duplication_absense": 25,
        "technical_debt_ratio": 25},
}


def msg_medidas(complexity, functions, comment_lines_density, duplicated_lines_density,
                sqale_debt_ratio=None) -> dict:
    dados = {
        "complexity": [float(complexity)],
        "functions": [float(functions)],
        "comment_lines_density": [float(comment_lines_density)],
        "duplicated_lines_density": [float(duplicated_lines_density)],
    }
    medidas = {
        "non_complex_file_density": _msg.non_complex_files_density(dados, *MSG_LIMITES["non_complex_file_density"]),
        "commented_file_density": _msg.commented_files_density(dados, *MSG_LIMITES["commented_file_density"]),
        "duplication_absense": _msg.absence_of_duplications(dados, *MSG_LIMITES["duplication_absense"]),
    }
    if sqale_debt_ratio is not None and not (isinstance(sqale_debt_ratio, float) and math.isnan(sqale_debt_ratio)):
        medidas["technical_debt_ratio"] = _msg.technical_debt_ratio(
            {"sqale_debt_ratio": [float(sqale_debt_ratio)]}, *MSG_LIMITES["technical_debt_ratio"])
    return {k: float(v) for k, v in medidas.items()}


def msg_im(complexity, functions, comment_lines_density, duplicated_lines_density,
           sqale_debt_ratio=None, n_medidas: int = 3) -> float:
    medidas = msg_medidas(complexity, functions, comment_lines_density, duplicated_lines_density,
                          sqale_debt_ratio if n_medidas == 4 else None)
    pesos = MSG_PESOS[n_medidas]
    valores = np.array([medidas[k] for k in pesos])
    return float(_msg_agregar(valores, np.array(list(pesos.values()), dtype=float)))


def calcular_im(df, prefixo: str = "") -> "pd.DataFrame":
    """Acrescenta ao DataFrame as medidas e os IMs de Q-Rapids e MSG (3 e 4 medidas)."""
    import pandas as pd

    linhas = []
    for r in df.itertuples(index=False):
        args = (r.complexity, r.functions, r.comment_lines_density, r.duplicated_lines_density)
        q = qrapids_medidas(*args)
        sqale = getattr(r, "sqale_debt_ratio", None)
        m = msg_medidas(*args, sqale)
        linhas.append({
            f"{prefixo}qr_complexidade": q["complexidade"],
            f"{prefixo}qr_comentarios": q["comentarios"],
            f"{prefixo}qr_duplicacao": q["duplicacao"],
            f"{prefixo}im_qrapids": qrapids_im(*args),
            f"{prefixo}msg_complexidade": m["non_complex_file_density"],
            f"{prefixo}msg_comentarios": m["commented_file_density"],
            f"{prefixo}msg_duplicacao": m["duplication_absense"],
            f"{prefixo}msg_divida_tecnica": m.get("technical_debt_ratio"),
            f"{prefixo}im_msg3": msg_im(*args, n_medidas=3),
            f"{prefixo}im_msg4": msg_im(*args, sqale, n_medidas=4) if "technical_debt_ratio" in m else None,
        })
    return pd.concat([df.reset_index(drop=True), pd.DataFrame(linhas)], axis=1)
