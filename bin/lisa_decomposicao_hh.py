#!/usr/bin/env python3
"""Decomposição da queda de clusters alto-alto (HH) no LISA a 10 km.

No LISA (esda.Moran_Local_Rate, 9.999 permutações, seed=12345, FDR a 5%) das
faixas de 10 km dos corredores federais, o painel completo (sem_piso, n = 2.329)
apresenta 3 clusters alto-alto (HH) pós-FDR, enquanto o painel balanceado
(anos_completos, n = 1.851) apresenta 0 clusters HH.

Este script investiga quanto dessa queda decorre de:
  (a) exclusão dos 478 bins sem os 8 anos completos de contagem;
  (b) cobertura incompleta do tráfego no próprio bin.

Quatro cenários avaliados (todos em faixas de 10 km):
  - C1 `completo`: amostra sem_piso (2.329), matriz W linear sobre os 2.329,
    FDR com m = 2.329.
  - C2 `completo_so_balanceados_fdr_completo`: o mesmo LISA de C1 e o mesmo
    corte FDR de C1, contabilizando apenas os bins balanceados (anos == 8).
  - C3 `completo_restrito_1851`: o mesmo LISA de C1 (W completa de 2.329),
    restrito aos 1.851 bins balanceados, com corte FDR recalculado sobre esses
    1.851 p-valores (m = 1.851).
  - C4 `balanceado`: amostra balanceada (1.851), matriz W linear reconstruída
    exclusivamente sobre os 1.851 bins, FDR recalculado com m = 1.851.

Decomposição sequencial da queda de HH pós-FDR:
  queda_total = HH(C1) - HH(C4)
  efeito_cobertura_do_bin = HH(C1) - HH(C2)  # Cobertura do próprio bin (b)
  efeito_multiplicidade  = HH(C2) - HH(C3)  # Troca de m=2329 por 1851 no FDR (a1)
  efeito_vizinhanca      = HH(C3) - HH(C4)  # Remoção dos 478 da W e referência (a2)
  Identidade: efeito_cobertura_do_bin + efeito_multiplicidade + efeito_vizinhanca == queda_total

Sensibilidade à semente:
  Avaliada nas sementes 12345 (referência pré-registrada), 1, 2, 3 e 4.

Uso:
  ~/.venvs/geo/bin/python bin/lisa_decomposicao_hh.py [--painel CAMINHO] [--saida CAMINHO]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import pathlib
import sys
import warnings
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Sequence, Tuple

# Constantes e caminhos padrão do projeto
ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_PAINEL = ROOT / "build" / "painel_corredores.csv"
DEFAULT_SAIDA = (
    ROOT / "bases" / "prf-acidentes" / "resultados" / "lisa_decomposicao_queda_hh.csv"
)

SEMENTE_REFERENCIA = 12345
SEMENTES = (12345, 1, 2, 3, 4)
ALPHA = 0.05
PERMUTACOES = 9999
TAMANHO_KM = 10
VMDA_SUSPEITO = 2000.0

QUADRANTE_GEODA = {1: "alto-alto", 2: "baixo-baixo", 3: "baixo-alto", 4: "alto-baixo"}

CAMPOS_CSV = [
    "bloco",
    "semente",
    "cenario",
    "n",
    "n_testes_fdr",
    "ilhas",
    "fdr_cutoff",
    "hh_antes",
    "bb_antes",
    "ab_antes",
    "ba_antes",
    "hh_depois",
    "bb_depois",
    "ab_depois",
    "ba_depois",
    "hh_c1",
    "hh_c2",
    "hh_c3",
    "hh_c4",
    "efeito_cobertura_do_bin",
    "efeito_multiplicidade",
    "efeito_vizinhanca",
    "queda_total",
    "br",
    "uf",
    "km_inicial",
    "km_final",
    "sinistros",
    "exposicao_veic_km",
    "km_com_exposicao",
    "anos_utilizaveis",
    "anos_lista",
    "taxa_por_100M_veic_km",
    "pertence_balanceado",
    "quadrante",
    "p_sim",
    "significativo_fdr",
    "vmda_implicito",
    "vmda_implicito_km_exposicao",
    "vmda_suspeito",
]

# Valores de partida extraídos de build/moran_corredores.csv para validação
# cruzada estrita de C1 (sem_piso, 10 km) e C4 (anos_completos, 10 km) na semente 12345:
ESPERADO_C1_12345 = {
    "n": 2329,
    "ilhas": 2,
    "fdr_cutoff": 0.00045083726921425505,
    "hh_antes": 96,
    "bb_antes": 267,
    "ab_antes": 1,
    "ba_antes": 13,
    "hh_depois": 3,
    "bb_depois": 17,
    "ab_depois": 1,
    "ba_depois": 0,
}

ESPERADO_C4_12345 = {
    "n": 1851,
    "ilhas": 18,
    "fdr_cutoff": 0.0014316585629389521,
    "hh_antes": 70,
    "bb_antes": 202,
    "ab_antes": 15,
    "ba_antes": 13,
    "hh_depois": 0,
    "bb_depois": 38,
    "ab_depois": 14,
    "ba_depois": 1,
}


# ============================================================================
# Funções puras stdlib no topo (testáveis sem dependências externas)
# ============================================================================


def corte_fdr(pvalores: Sequence[float], alpha: float = 0.05) -> float:
    """Calcula o corte de p-valor para controle de FDR (Benjamini-Hochberg).

    Reimplementação exata do comportamento de `esda.fdr`:
    Ordena p decrescente; para k = n...1, compara p_sort[i] < k * alpha / n.
    Retorna o primeiro corte que satisfaz a condição; se nenhum satisfizer,
    retorna a cota conservadora de Bonferroni (alpha / n).
    """
    n = len(pvalores)
    if n == 0:
        return 0.0
    p_sort = sorted(pvalores, reverse=True)
    for i, p in enumerate(p_sort):
        k = n - i
        p_fdr = k * alpha / n
        if p < p_fdr:
            return float(p_fdr)
    return float(alpha / n)


def vmda_implicito(exposicao: float, km: float, anos: float) -> float:
    """Calcula o VMDa médio implícito: exposicao / (km * 365 * anos)."""
    if km <= 0 or anos <= 0:
        return float("nan")
    return float(exposicao) / (float(km) * 365.0 * float(anos))


def contar_quadrantes(
    quadrantes: Sequence[int],
    p_valores: Sequence[float],
    cutoff_fdr: float,
    alpha: float = 0.05,
    indices: Sequence[int] | None = None,
) -> dict[str, int]:
    """Conta faixas significativas por quadrante GeoDa antes e depois do FDR.

    Quadrantes GeoDa:
      1: alto-alto (HH)
      2: baixo-baixo (BB)
      3: baixo-alto (BA)
      4: alto-baixo (AB)
    """
    contagens = {
        "hh_antes": 0,
        "bb_antes": 0,
        "ab_antes": 0,
        "ba_antes": 0,
        "hh_depois": 0,
        "bb_depois": 0,
        "ab_depois": 0,
        "ba_depois": 0,
    }
    alvos = indices if indices is not None else range(len(quadrantes))
    for idx in alvos:
        q = int(quadrantes[idx])
        p = float(p_valores[idx])
        sa = p < alpha
        sd = p < cutoff_fdr
        if q == 1:
            if sa:
                contagens["hh_antes"] += 1
            if sd:
                contagens["hh_depois"] += 1
        elif q == 2:
            if sa:
                contagens["bb_antes"] += 1
            if sd:
                contagens["bb_depois"] += 1
        elif q == 3:
            if sa:
                contagens["ba_antes"] += 1
            if sd:
                contagens["ba_depois"] += 1
        elif q == 4:
            if sa:
                contagens["ab_antes"] += 1
            if sd:
                contagens["ab_depois"] += 1
    return contagens


def decompor(hh_c1: int, hh_c2: int, hh_c3: int, hh_c4: int) -> dict[str, int]:
    """Decomposição sequencial da queda de HH pós-FDR entre C1 e C4."""
    efeito_cobertura = hh_c1 - hh_c2
    efeito_multiplicidade = hh_c2 - hh_c3
    efeito_vizinhanca = hh_c3 - hh_c4
    queda_total = hh_c1 - hh_c4
    assert (
        efeito_cobertura + efeito_multiplicidade + efeito_vizinhanca
    ) == queda_total, (
        f"Identidade violada: {efeito_cobertura} + {efeito_multiplicidade} + "
        f"{efeito_vizinhanca} != {queda_total}"
    )
    return {
        "hh_c1": hh_c1,
        "hh_c2": hh_c2,
        "hh_c3": hh_c3,
        "hh_c4": hh_c4,
        "efeito_cobertura_do_bin": efeito_cobertura,
        "efeito_multiplicidade": efeito_multiplicidade,
        "efeito_vizinhanca": efeito_vizinhanca,
        "queda_total": queda_total,
    }


def calcular_sha256(caminho: pathlib.Path) -> str:
    """Calcula o hash SHA256 de um arquivo."""
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def carregar_painel_10km(caminho: pathlib.Path) -> List[dict]:
    """Carrega o painel filtrando tamanho 10 km e exposicao > 0."""
    with open(caminho, newline="", encoding="utf-8") as f:
        linhas = list(csv.DictReader(f))
    amostra = []
    for l in linhas:
        if l.get("tamanho_km") != "10":
            continue
        exp = float(l["exposicao_veic_km"])
        if exp <= 0:
            continue
        d = dict(l)
        d["tamanho_km"] = 10
        d["km_inicial"] = int(l["km_inicial"])
        d["km_final"] = int(l["km_final"])
        d["sinistros"] = int(l["sinistros"])
        d["exposicao_veic_km"] = exp
        d["km_com_exposicao"] = float(l["km_com_exposicao"])
        d["anos_utilizaveis"] = int(l["anos_utilizaveis"])
        d["taxa_por_100M_veic_km"] = float(l["taxa_por_100M_veic_km"])
        amostra.append(d)
    return amostra


# ============================================================================
# Funções com dependências geo/espaciais (imports lazy)
# ============================================================================


def montar_vizinhanca(amostra: List[dict], tamanho: int = TAMANHO_KM):
    """Monta a matriz de contiguidade linear W dentro de (br, uf)."""
    import libpysal  # lazy import

    por_br_uf: Dict[Tuple[str, str], List[Tuple[int, int]]] = defaultdict(list)
    for idx, l in enumerate(amostra):
        por_br_uf[(l["br"], l["uf"])].append((l["km_inicial"], idx))

    neighbors: Dict[int, List[int]] = {idx: [] for idx in range(len(amostra))}
    for chave, itens in por_br_uf.items():
        itens.sort()
        posicao_para_idx = {km: idx for km, idx in itens}
        for km, idx in itens:
            vizinho_km = km + tamanho
            if vizinho_km in posicao_para_idx:
                idx_vizinho = posicao_para_idx[vizinho_km]
                neighbors[idx].append(idx_vizinho)
                neighbors[idx_vizinho].append(idx)
    neighbors = {k: sorted(set(v)) for k, v in neighbors.items()}

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        w = libpysal.weights.W(neighbors, silence_warnings=True)
    w.transform = "r"
    return w


def executar_analise(painel_path: pathlib.Path) -> Tuple[List[dict], dict]:
    """Executa os cenários C1-C4 em todas as sementes e constrói as tabelas."""
    import esda  # lazy import
    import numpy as np  # lazy import

    amostra_c1 = carregar_painel_10km(painel_path)
    idx_balanceados = [
        i for i, l in enumerate(amostra_c1) if l["anos_utilizaveis"] == 8
    ]
    amostra_c4 = [amostra_c1[i] for i in idx_balanceados]

    w_c1 = montar_vizinhanca(amostra_c1, TAMANHO_KM)
    w_c4 = montar_vizinhanca(amostra_c4, TAMANHO_KM)

    sin_c1 = np.array([float(l["sinistros"]) for l in amostra_c1], dtype=float)
    exp_c1 = np.array([float(l["exposicao_veic_km"]) for l in amostra_c1], dtype=float)

    sin_c4 = np.array([float(l["sinistros"]) for l in amostra_c4], dtype=float)
    exp_c4 = np.array([float(l["exposicao_veic_km"]) for l in amostra_c4], dtype=float)

    linhas_cenarios: List[dict] = []
    linhas_decomposicao: List[dict] = []

    # Estruturas para registrar a execução de referência (semente 12345)
    dados_ref: Dict[str, Any] = {}

    for semente in SEMENTES:
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="invalid value encountered in divide",
                category=RuntimeWarning,
            )
            lisa1 = esda.Moran_Local_Rate(
                sin_c1,
                exp_c1,
                w_c1,
                transformation="r",
                permutations=PERMUTACOES,
                geoda_quads=True,
                seed=semente,
            )
            lisa4 = esda.Moran_Local_Rate(
                sin_c4,
                exp_c4,
                w_c4,
                transformation="r",
                permutations=PERMUTACOES,
                geoda_quads=True,
                seed=semente,
            )

        corte1 = corte_fdr(lisa1.p_sim, ALPHA)
        corte4 = corte_fdr(lisa4.p_sim, ALPHA)

        # Asserções duras de igualdade com esda.fdr nos cenários C1 e C4
        assert corte1 == esda.fdr(
            lisa1.p_sim, ALPHA
        ), f"corte_fdr != esda.fdr em C1 (seed {semente})"
        assert corte4 == esda.fdr(
            lisa4.p_sim, ALPHA
        ), f"corte_fdr != esda.fdr em C4 (seed {semente})"

        # C1: completo
        c1_contagens = contar_quadrantes(lisa1.q, lisa1.p_sim, corte1, alpha=ALPHA)
        res_c1 = {
            "semente": semente,
            "cenario": "completo",
            "n": len(amostra_c1),
            "n_testes_fdr": len(amostra_c1),
            "ilhas": len(w_c1.islands),
            "fdr_cutoff": corte1,
            **c1_contagens,
        }

        # C2: completo_so_balanceados_fdr_completo
        c2_contagens = contar_quadrantes(
            lisa1.q, lisa1.p_sim, corte1, alpha=ALPHA, indices=idx_balanceados
        )
        res_c2 = {
            "semente": semente,
            "cenario": "completo_so_balanceados_fdr_completo",
            "n": len(idx_balanceados),
            "n_testes_fdr": len(amostra_c1),
            "ilhas": len(w_c1.islands),
            "fdr_cutoff": corte1,
            **c2_contagens,
        }

        # C3: completo_restrito_1851
        p_bal = [float(lisa1.p_sim[i]) for i in idx_balanceados]
        corte3 = corte_fdr(p_bal, ALPHA)
        c3_contagens = contar_quadrantes(
            lisa1.q, lisa1.p_sim, corte3, alpha=ALPHA, indices=idx_balanceados
        )
        res_c3 = {
            "semente": semente,
            "cenario": "completo_restrito_1851",
            "n": len(idx_balanceados),
            "n_testes_fdr": len(idx_balanceados),
            "ilhas": len(w_c1.islands),
            "fdr_cutoff": corte3,
            **c3_contagens,
        }

        # C4: balanceado
        c4_contagens = contar_quadrantes(lisa4.q, lisa4.p_sim, corte4, alpha=ALPHA)
        res_c4 = {
            "semente": semente,
            "cenario": "balanceado",
            "n": len(amostra_c4),
            "n_testes_fdr": len(amostra_c4),
            "ilhas": len(w_c4.islands),
            "fdr_cutoff": corte4,
            **c4_contagens,
        }

        # Asserções duras de reprodução contra moran_corredores.csv na semente 12345
        if semente == SEMENTE_REFERENCIA:
            for k, val_esperado in ESPERADO_C1_12345.items():
                val_obtido = res_c1[k]
                if isinstance(val_esperado, float):
                    assert math.isclose(
                        val_obtido, val_esperado, rel_tol=1e-12
                    ), f"C1 12345 divergente em {k}: {val_obtido} != {val_esperado}"
                else:
                    assert (
                        val_obtido == val_esperado
                    ), f"C1 12345 divergente em {k}: {val_obtido} != {val_esperado}"

            for k, val_esperado in ESPERADO_C4_12345.items():
                val_obtido = res_c4[k]
                if isinstance(val_esperado, float):
                    assert math.isclose(
                        val_obtido, val_esperado, rel_tol=1e-12
                    ), f"C4 12345 divergente em {k}: {val_obtido} != {val_esperado}"
                else:
                    assert (
                        val_obtido == val_esperado
                    ), f"C4 12345 divergente em {k}: {val_obtido} != {val_esperado}"

            # Armazena objetos da referência para detalhamento dos sobreviventes
            dados_ref = {
                "lisa1": lisa1,
                "lisa4": lisa4,
                "corte1": corte1,
                "corte3": corte3,
                "corte4": corte4,
            }

        decomp = decompor(
            res_c1["hh_depois"],
            res_c2["hh_depois"],
            res_c3["hh_depois"],
            res_c4["hh_depois"],
        )

        linhas_cenarios.extend([res_c1, res_c2, res_c3, res_c4])
        linhas_decomposicao.append({"semente": semente, **decomp})

    # Bloco hh_sobrevivente: todo bin que é HH pós-FDR em qualquer cenário da semente 12345
    lisa1_ref = dados_ref["lisa1"]
    lisa4_ref = dados_ref["lisa4"]
    corte1_ref = dados_ref["corte1"]
    corte3_ref = dados_ref["corte3"]
    corte4_ref = dados_ref["corte4"]

    # Identifica índices no painel completo (amostra_c1)
    idx_sobreviventes_c1: List[int] = []
    for i, (q, p) in enumerate(zip(lisa1_ref.q, lisa1_ref.p_sim)):
        # Candidato se for HH pós-FDR em C1
        if int(q) == 1 and p < corte1_ref:
            idx_sobreviventes_c1.append(i)

    # Verifica se algum balanceado foi HH em C2, C3 ou C4 na semente 12345
    # (em 12345, sabemos que C2=0, C3=0, C4=0, mas o código avalia genericamente)
    for pos_bal, i_orig in enumerate(idx_balanceados):
        q1 = int(lisa1_ref.q[i_orig])
        p1 = float(lisa1_ref.p_sim[i_orig])
        q4 = int(lisa4_ref.q[pos_bal])
        p4 = float(lisa4_ref.p_sim[pos_bal])
        eh_hh_c2 = q1 == 1 and p1 < corte1_ref
        eh_hh_c3 = q1 == 1 and p1 < corte3_ref
        eh_hh_c4 = q4 == 1 and p4 < corte4_ref
        if (eh_hh_c2 or eh_hh_c3 or eh_hh_c4) and i_orig not in idx_sobreviventes_c1:
            idx_sobreviventes_c1.append(i_orig)

    idx_sobreviventes_c1.sort()

    linhas_sobreviventes: List[dict] = []
    # Mapeamento do índice em amostra_c1 para amostra_c4 (se balanceado)
    orig_para_bal = {i_orig: pos_bal for pos_bal, i_orig in enumerate(idx_balanceados)}

    for idx in idx_sobreviventes_c1:
        bin_info = amostra_c1[idx]
        anos = bin_info["anos_utilizaveis"]
        exp = bin_info["exposicao_veic_km"]
        km_exp = bin_info["km_com_exposicao"]
        eh_balanceado = anos == 8

        vmda_imp = vmda_implicito(exp, TAMANHO_KM, anos)
        vmda_imp_km_exp = vmda_implicito(exp, km_exp, anos)
        eh_suspeito = vmda_imp < VMDA_SUSPEITO

        # Em C1
        q_c1 = QUADRANTE_GEODA[int(lisa1_ref.q[idx])]
        p_c1 = float(lisa1_ref.p_sim[idx])
        linhas_sobreviventes.append(
            {
                "cenario": "completo",
                "br": bin_info["br"],
                "uf": bin_info["uf"],
                "km_inicial": bin_info["km_inicial"],
                "km_final": bin_info["km_final"],
                "sinistros": bin_info["sinistros"],
                "exposicao_veic_km": exp,
                "km_com_exposicao": km_exp,
                "anos_utilizaveis": anos,
                "anos_lista": bin_info["anos_lista"],
                "taxa_por_100M_veic_km": bin_info["taxa_por_100M_veic_km"],
                "pertence_balanceado": eh_balanceado,
                "quadrante": q_c1,
                "p_sim": p_c1,
                "fdr_cutoff": corte1_ref,
                "significativo_fdr": bool(q_c1 == "alto-alto" and p_c1 < corte1_ref),
                "vmda_implicito": vmda_imp,
                "vmda_implicito_km_exposicao": vmda_imp_km_exp,
                "vmda_suspeito": eh_suspeito,
            }
        )

        # Em C2
        linhas_sobreviventes.append(
            {
                "cenario": "completo_so_balanceados_fdr_completo",
                "br": bin_info["br"],
                "uf": bin_info["uf"],
                "km_inicial": bin_info["km_inicial"],
                "km_final": bin_info["km_final"],
                "sinistros": bin_info["sinistros"],
                "exposicao_veic_km": exp,
                "km_com_exposicao": km_exp,
                "anos_utilizaveis": anos,
                "anos_lista": bin_info["anos_lista"],
                "taxa_por_100M_veic_km": bin_info["taxa_por_100M_veic_km"],
                "pertence_balanceado": eh_balanceado,
                "quadrante": q_c1,
                "p_sim": p_c1,
                "fdr_cutoff": corte1_ref,
                "significativo_fdr": bool(
                    eh_balanceado and q_c1 == "alto-alto" and p_c1 < corte1_ref
                ),
                "vmda_implicito": vmda_imp,
                "vmda_implicito_km_exposicao": vmda_imp_km_exp,
                "vmda_suspeito": eh_suspeito,
            }
        )

        # Em C3
        linhas_sobreviventes.append(
            {
                "cenario": "completo_restrito_1851",
                "br": bin_info["br"],
                "uf": bin_info["uf"],
                "km_inicial": bin_info["km_inicial"],
                "km_final": bin_info["km_final"],
                "sinistros": bin_info["sinistros"],
                "exposicao_veic_km": exp,
                "km_com_exposicao": km_exp,
                "anos_utilizaveis": anos,
                "anos_lista": bin_info["anos_lista"],
                "taxa_por_100M_veic_km": bin_info["taxa_por_100M_veic_km"],
                "pertence_balanceado": eh_balanceado,
                "quadrante": q_c1,
                "p_sim": p_c1,
                "fdr_cutoff": corte3_ref,
                "significativo_fdr": bool(
                    eh_balanceado and q_c1 == "alto-alto" and p_c1 < corte3_ref
                ),
                "vmda_implicito": vmda_imp,
                "vmda_implicito_km_exposicao": vmda_imp_km_exp,
                "vmda_suspeito": eh_suspeito,
            }
        )

        # Em C4 (aparece apenas se for balanceado)
        if eh_balanceado:
            pos_c4 = orig_para_bal[idx]
            q_c4 = QUADRANTE_GEODA[int(lisa4_ref.q[pos_c4])]
            p_c4 = float(lisa4_ref.p_sim[pos_c4])
            linhas_sobreviventes.append(
                {
                    "cenario": "balanceado",
                    "br": bin_info["br"],
                    "uf": bin_info["uf"],
                    "km_inicial": bin_info["km_inicial"],
                    "km_final": bin_info["km_final"],
                    "sinistros": bin_info["sinistros"],
                    "exposicao_veic_km": exp,
                    "km_com_exposicao": km_exp,
                    "anos_utilizaveis": anos,
                    "anos_lista": bin_info["anos_lista"],
                    "taxa_por_100M_veic_km": bin_info["taxa_por_100M_veic_km"],
                    "pertence_balanceado": True,
                    "quadrante": q_c4,
                    "p_sim": p_c4,
                    "fdr_cutoff": corte4_ref,
                    "significativo_fdr": bool(
                        q_c4 == "alto-alto" and p_c4 < corte4_ref
                    ),
                    "vmda_implicito": vmda_imp,
                    "vmda_implicito_km_exposicao": vmda_imp_km_exp,
                    "vmda_suspeito": eh_suspeito,
                }
            )

    # Montagem de todas as linhas formatadas para o CSV
    linhas_finais_csv: List[Dict[str, str]] = []

    for c in linhas_cenarios:
        r = {k: "" for k in CAMPOS_CSV}
        r["bloco"] = "cenario"
        r["semente"] = str(c["semente"])
        r["cenario"] = str(c["cenario"])
        r["n"] = str(c["n"])
        r["n_testes_fdr"] = str(c["n_testes_fdr"])
        r["ilhas"] = str(c["ilhas"])
        r["fdr_cutoff"] = repr(c["fdr_cutoff"])
        r["hh_antes"] = str(c["hh_antes"])
        r["bb_antes"] = str(c["bb_antes"])
        r["ab_antes"] = str(c["ab_antes"])
        r["ba_antes"] = str(c["ba_antes"])
        r["hh_depois"] = str(c["hh_depois"])
        r["bb_depois"] = str(c["bb_depois"])
        r["ab_depois"] = str(c["ab_depois"])
        r["ba_depois"] = str(c["ba_depois"])
        linhas_finais_csv.append(r)

    for d in linhas_decomposicao:
        r = {k: "" for k in CAMPOS_CSV}
        r["bloco"] = "decomposicao"
        r["semente"] = str(d["semente"])
        r["hh_c1"] = str(d["hh_c1"])
        r["hh_c2"] = str(d["hh_c2"])
        r["hh_c3"] = str(d["hh_c3"])
        r["hh_c4"] = str(d["hh_c4"])
        r["efeito_cobertura_do_bin"] = str(d["efeito_cobertura_do_bin"])
        r["efeito_multiplicidade"] = str(d["efeito_multiplicidade"])
        r["efeito_vizinhanca"] = str(d["efeito_vizinhanca"])
        r["queda_total"] = str(d["queda_total"])
        linhas_finais_csv.append(r)

    for s in linhas_sobreviventes:
        r = {k: "" for k in CAMPOS_CSV}
        r["bloco"] = "hh_sobrevivente"
        r["cenario"] = str(s["cenario"])
        r["br"] = str(s["br"])
        r["uf"] = str(s["uf"])
        r["km_inicial"] = str(s["km_inicial"])
        r["km_final"] = str(s["km_final"])
        r["sinistros"] = str(s["sinistros"])
        r["exposicao_veic_km"] = repr(s["exposicao_veic_km"])
        r["km_com_exposicao"] = str(s["km_com_exposicao"])
        r["anos_utilizaveis"] = str(s["anos_utilizaveis"])
        r["anos_lista"] = str(s["anos_lista"])
        r["taxa_por_100M_veic_km"] = repr(s["taxa_por_100M_veic_km"])
        r["pertence_balanceado"] = str(s["pertence_balanceado"])
        r["quadrante"] = str(s["quadrante"])
        r["p_sim"] = repr(s["p_sim"])
        r["fdr_cutoff"] = repr(s["fdr_cutoff"])
        r["significativo_fdr"] = str(s["significativo_fdr"])
        r["vmda_implicito"] = repr(s["vmda_implicito"])
        r["vmda_implicito_km_exposicao"] = repr(s["vmda_implicito_km_exposicao"])
        r["vmda_suspeito"] = str(s["vmda_suspeito"])
        linhas_finais_csv.append(r)

    resumo_terminal = {
        "cenarios": linhas_cenarios,
        "decomposicao": linhas_decomposicao,
        "sobreviventes": linhas_sobreviventes,
    }
    return linhas_finais_csv, resumo_terminal


def gerar_prov(painel_path: pathlib.Path, csv_path: pathlib.Path) -> dict:
    """Gera o dicionário de proveniência com versões e sha256."""
    import esda  # lazy import
    import libpysal  # lazy import
    import numpy as np  # lazy import

    sha_painel = calcular_sha256(painel_path)
    sha_csv = calcular_sha256(csv_path)

    return {
        "script": "bin/lisa_decomposicao_hh.py",
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "painel_caminho": str(painel_path.resolve()),
        "painel_sha256": sha_painel,
        "painel": {
            "caminho": str(painel_path.resolve()),
            "sha256": sha_painel,
        },
        "csv_sha256": sha_csv,
        "sha256": sha_csv,
        "permutacoes": PERMUTACOES,
        "sementes": list(SEMENTES),
        "alpha": ALPHA,
        "versoes": {
            "esda": getattr(esda, "__version__", "desconhecida"),
            "libpysal": getattr(libpysal, "__version__", "desconhecida"),
            "numpy": getattr(np, "__version__", "desconhecida"),
        },
    }


def imprimir_relatorio(resumo: dict) -> None:
    """Imprime na saída padrão a tabela de cenários, decomposição e sobreviventes."""
    print("\n" + "=" * 90)
    print("DECOMPOSIÇÃO DA QUEDA DE HH NO LISA A 10 KM (C1 → C4)")
    print("=" * 90)

    print("\n--- 1. Cenários C1–C4 na semente de referência (12345) ---")
    print(
        f"{'Cenário':<38} | {'n':>4} | {'m_FDR':>5} | {'Corte FDR':>10} | "
        f"{'HH antes':>8} | {'HH pós-FDR':>10} | {'BB pós':>6} | {'AB pós':>6} | {'BA pós':>6}"
    )
    print("-" * 110)
    for c in resumo["cenarios"]:
        if c["semente"] == SEMENTE_REFERENCIA:
            print(
                f"{c['cenario']:<38} | {c['n']:>4} | {c['n_testes_fdr']:>5} | "
                f"{c['fdr_cutoff']:>10.6f} | {c['hh_antes']:>8} | {c['hh_depois']:>10} | "
                f"{c['bb_depois']:>6} | {c['ab_depois']:>6} | {c['ba_depois']:>6}"
            )

    print("\n--- 2. Decomposição da Queda por Semente ---")
    print(
        f"{'Semente':>7} | {'C1':>2} | {'C2':>2} | {'C3':>2} | {'C4':>2} | "
        f"{'Cobertura (bin)':>15} | {'Multiplicidade':>14} | {'Vizinhança':>11} | {'Queda Total':>11}"
    )
    print("-" * 90)
    for d in resumo["decomposicao"]:
        print(
            f"{d['semente']:>7} | {d['hh_c1']:>2} | {d['hh_c2']:>2} | {d['hh_c3']:>2} | {d['hh_c4']:>2} | "
            f"{d['efeito_cobertura_do_bin']:>15} | {d['efeito_multiplicidade']:>14} | "
            f"{d['efeito_vizinhanca']:>11} | {d['queda_total']:>11}"
        )

    print("\n--- 3. Bins Sobreviventes (HH pós-FDR na semente 12345) ---")
    for s in resumo["sobreviventes"]:
        if s["cenario"] == "completo":
            suspeita_str = (
                " ⚠️  VMDa SUSPEITO (<2.000)" if s["vmda_suspeito"] else ""
            )
            print(
                f"\n  • BR-{s['br']}/{s['uf']} km {s['km_inicial']}-{s['km_final']} "
                f"(anos={s['anos_utilizaveis']}, balanceado={s['pertence_balanceado']}):\n"
                f"    Sinistros={s['sinistros']}, Exposição={s['exposicao_veic_km']:,.0f} veic-km, "
                f"Taxa={s['taxa_por_100M_veic_km']:.2f}\n"
                f"    VMDa implícito (10 km)={s['vmda_implicito']:,.1f} veic/dia{suspeita_str}\n"
                f"    VMDa implícito ({s['km_com_exposicao']:.0f} km com exp)={s['vmda_implicito_km_exposicao']:,.1f} veic/dia\n"
                f"    p_sim={s['p_sim']:.6f}, FDR cutoff={s['fdr_cutoff']:.6f} "
                f"→ Significativo pós-FDR: {s['significativo_fdr']}"
            )
        else:
            print(
                f"    ↳ No cenário {s['cenario']}: "
                f"quadrante={s['quadrante']}, p_sim={s['p_sim']:.6f}, "
                f"FDR cutoff={s['fdr_cutoff']:.6f} → Significativo: {s['significativo_fdr']}"
            )
    print("=" * 90 + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--painel",
        type=pathlib.Path,
        default=DEFAULT_PAINEL,
        help="Caminho do painel de corredores (default: build/painel_corredores.csv)",
    )
    ap.add_argument(
        "--saida",
        type=pathlib.Path,
        default=DEFAULT_SAIDA,
        help="Caminho para gravação do CSV (default: bases/prf-acidentes/resultados/lisa_decomposicao_queda_hh.csv)",
    )
    args = ap.parse_args()

    if not args.painel.exists():
        print(f"ERRO: Arquivo do painel não encontrado: {args.painel}", file=sys.stderr)
        return 1

    print(f"Executando análise de decomposição LISA sobre {args.painel}...")
    linhas_csv, resumo = executar_analise(args.painel)

    args.saida.parent.mkdir(parents=True, exist_ok=True)
    with open(args.saida, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS_CSV)
        writer.writeheader()
        writer.writerows(linhas_csv)
    print(f"OK: CSV gravado em {args.saida} ({len(linhas_csv)} linhas).")

    # Geração do arquivo de proveniência .prov.json
    prov_dict = gerar_prov(args.painel, args.saida)
    prov_path = args.saida.with_suffix(".prov.json")
    with open(prov_path, "w", encoding="utf-8") as f:
        json.dump(prov_dict, f, indent=2, ensure_ascii=False)
    print(f"OK: Proveniência gravada em {prov_path}.")

    imprimir_relatorio(resumo)
    return 0


if __name__ == "__main__":
    sys.exit(main())
