#!/usr/bin/env python3
"""Precisão amostral por classe de cobertura e associação nos corredores federais.

Avalia o efeito da precisão amostral na associação entre a cobertura de contagem de
tráfego (C = `anos_utilizaveis`) e a taxa de sinistros (R) no painel dos dez maiores
corredores federais do Brasil (5 km, 10 km e 20 km), respondendo diretamente ao
item R2-01 (b) do parecer 02 do trabalho `next-generation-road-safety`.

1. **O que mede**:
   - Estratificação das faixas por classe de cobertura temporal (anos 1–3, 4–6, 7–9)
     e por número individual de anos utilizáveis (1 a 8).
   - Estatísticas de dispersão por estrato: média, mediana, variância amostral (n-1),
     desvio padrão, coeficiente de variação (CV), distância interquartil (DIQ),
     exposição mediana (veic-km), variância de Poisson esperada (com taxa comum do
     estrato) e a razão entre a variância observada e a esperada sob Poisson.
   - Testes de homogeneidade de variância e gradiente de dispersão no estrato 'todos':
     teste de Brown-Forsythe (Levene centrado na mediana) entre as 3 classes e entre
     os 8 valores individuais de anos; e correlação de postos de Spearman entre a
     cobertura C e o desvio absoluto em torno da mediana |r_i - mediana(r)|.
   - Associação C x R dentro de cada classe de cobertura e no agregado ('todos'):
     correlação de Pearson, correlação de Spearman (postos médios) e correlação
     linear ponderada de Pearson (pesos w_i = e_i, proporcional ao inverso da
     variância de amostragem de Poisson), com inferência via n_eff de Kish.

2. **Por que (R2-01 b e o limite do EB)**:
   O parecer R2 apontou que faixas com menor número de anos monitorados teriam
   estimativas de taxa com maior variância amostral, produzindo valores extremos e
   gerando espuriamente a associação negativa com a cobertura.
   A rodada de controle via Empirical Bayes (EB global de Marshall) não foi capaz
   de testar adequadamente essa hipótese porque o peso EB w_i mediano no painel é
   0,980–0,995 (exposição elevada diante da variância entre faixas), de modo que a
   taxa EB é praticamente idêntica à taxa bruta.
   Este script testa a hipótese diretamente: (i) verificando se a dispersão da
   taxa de fato decresce com o aumento de anos; (ii) quantificando o excesso de
   dispersão observada frente ao ruído puro de Poisson; e (iii) testando se a
   associação C x R sobrevive à ponderação por exposição e dentro de estratos com
   cobertura homogênea.

3. **Amostra**:
   Idêntica à amostra do recorte `sem_piso`: por tamanho de faixa (5 km, 10 km,
   20 km), entram todas as faixas com `exposicao_veic_km > 0`. A taxa analisada
   é a taxa bruta (`taxa_por_100M_veic_km`), já que o estimador EB coincide
   numericamente com a taxa bruta na precisão relevante.

4. **O que NÃO decide**:
   Este script NÃO infere causalidade nem decide isoladamente se a maior dispersão
   em faixas pouco monitoradas decorre unicamente de imprecisão estatística ou de
   diferenças substantivas de geometria/infraestrutura dessas vias. Da mesma forma,
   a persistência da associação negativa após a ponderação por exposição não
   identifica a causa subjacente da correlação. A leitura dos resultados segue
   estritamente o critério pré-registrado em PLAN.md e METODO-ESPACIAL.md.

Uso:
    ~/.venvs/geo/bin/python bin/precisao_corredores.py [--painel CAMINHO] [--saida CAMINHO]
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import pathlib
import statistics
import sys
from typing import Dict, List, Optional, Tuple

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_PAINEL = ROOT / "build" / "painel_corredores.csv"
DEFAULT_SAIDA = (
    ROOT
    / "bases"
    / "prf-acidentes"
    / "resultados"
    / "precisao_amostral_corredores.csv"
)

TAMANHOS = (5, 10, 20)
CLASSES = ("anos_1_3", "anos_4_6", "anos_7_9")
ANOS_INDIVIDUAIS = tuple(f"anos_{i}" for i in range(1, 9))
ESTRATOS_DISPERSAO = CLASSES + ANOS_INDIVIDUAIS  # 11 estratos
ESTRATOS_ASSOCIACAO = ("todos",) + CLASSES  # 4 estratos

MEDIDAS_DISPERSAO = (
    "media",
    "mediana",
    "variancia",
    "dp",
    "cv",
    "diq",
    "exposicao_mediana",
    "variancia_poisson_esperada",
    "razao_var_obs_poisson",
)

MEDIDAS_TESTE_DISPERSAO = (
    "brown_forsythe_classes",
    "brown_forsythe_anos",
    "spearman_c_desvio_abs",
)

MEDIDAS_ASSOCIACAO = (
    "pearson",
    "spearman",
    "pearson_ponderado",
)

CAMPOS = [
    "tamanho_km",
    "bloco",
    "estrato",
    "medida",
    "n",
    "n_valores_c",
    "valor",
    "p_valor",
    "nota",
]

# Reutiliza funções de bin/associacao_corredores.py via importlib por caminho
_CAMINHO_ASSOC = pathlib.Path(__file__).resolve().parent / "associacao_corredores.py"
_spec = importlib.util.spec_from_file_location("associacao_corredores", _CAMINHO_ASSOC)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Não foi possível carregar {_CAMINHO_ASSOC}")
_mod_assoc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod_assoc)

carregar_painel = _mod_assoc.carregar_painel
pearson = _mod_assoc.pearson
postos = _mod_assoc.postos
p_valor_t = _mod_assoc.p_valor_t
calcular_sha256 = _mod_assoc.calcular_sha256


# ==============================================================================
# Funções puras stdlib-only
# ==============================================================================

def classe_anos(c: int | float) -> str:
    """Mapeia o número de anos com contagem utilizável para o estrato de classe.

    1–3 anos -> 'anos_1_3'
    4–6 anos -> 'anos_4_6'
    7–9 anos -> 'anos_7_9'
    """
    ci = int(c)
    if 1 <= ci <= 3:
        return "anos_1_3"
    elif 4 <= ci <= 6:
        return "anos_4_6"
    elif 7 <= ci <= 9:
        return "anos_7_9"
    raise ValueError(f"Anos {c} fora do intervalo esperado (1..9)")


def dispersao(
    taxas: List[float],
    sinistros: List[float | int],
    exposicoes: List[float],
) -> dict:
    """Calcula as 9 estatísticas de dispersão e variância de Poisson do estrato.

    Retorna um dicionário com:
        - media
        - mediana
        - variancia (amostral, n-1)
        - dp
        - cv (dp / media)
        - diq (Q3 - Q1 via statistics.quantiles)
        - exposicao_mediana
        - variancia_poisson_esperada (média de 1e8 * M / e_i, com M = 1e8 * Σy / Σe)
        - razao_var_obs_poisson (variancia / variancia_poisson_esperada)
    """
    n = len(taxas)
    if n < 2:
        return {
            "media": None,
            "mediana": None,
            "variancia": None,
            "dp": None,
            "cv": None,
            "diq": None,
            "exposicao_mediana": None,
            "variancia_poisson_esperada": None,
            "razao_var_obs_poisson": None,
        }

    media = float(statistics.mean(taxas))
    mediana = float(statistics.median(taxas))
    variancia = float(statistics.variance(taxas))
    dp = float(statistics.stdev(taxas))
    cv = float(dp / media) if media != 0 else float("nan")

    qs = statistics.quantiles(taxas, n=4)
    diq = float(qs[2] - qs[0])
    exposicao_mediana = float(statistics.median(exposicoes))

    sum_y = sum(sinistros)
    sum_e = sum(exposicoes)
    if sum_e > 0:
        M = 1e8 * float(sum_y) / float(sum_e)
        var_p_i = [1e8 * M / float(e) for e in exposicoes]
        var_poisson_esp = float(statistics.mean(var_p_i))
    else:
        var_poisson_esp = 0.0

    razao = float(variancia / var_poisson_esp) if var_poisson_esp > 0 else float("nan")

    return {
        "media": media,
        "mediana": mediana,
        "variancia": variancia,
        "dp": dp,
        "cv": cv,
        "diq": diq,
        "exposicao_mediana": exposicao_mediana,
        "variancia_poisson_esperada": var_poisson_esp,
        "razao_var_obs_poisson": razao,
    }


def brown_forsythe_F(grupos: List[List[float]]) -> Tuple[float, int, int]:
    """Calcula a estatística F do teste de Brown-Forsythe (Levene na mediana).

    Retorna: (F, gl1, gl2).
    """
    k = len(grupos)
    N = sum(len(g) for g in grupos)
    gl1 = k - 1
    gl2 = N - k
    if k < 2 or gl2 <= 0:
        return float("nan"), gl1, gl2

    z = [[abs(float(x) - float(statistics.median(g))) for x in g] for g in grupos]
    z_bar_i = [sum(zg) / len(zg) if len(zg) > 0 else 0.0 for zg in z]
    z_bar_all = sum(sum(zg) for zg in z) / N

    ss_between = sum(len(zg) * (zb - z_bar_all) ** 2 for zg, zb in zip(z, z_bar_i))
    ss_within = sum(sum((x - zb) ** 2 for x in zg) for zg, zb in zip(z, z_bar_i))

    if ss_between == 0.0:
        return 0.0, gl1, gl2
    if ss_within <= 0.0:
        return float("nan"), gl1, gl2

    ms_between = ss_between / gl1
    ms_within = ss_within / gl2
    F = ms_between / ms_within
    return float(F), gl1, gl2


def pearson_ponderado(x: List[float], y: List[float], w: List[float]) -> float:
    """Correlação linear ponderada de Pearson entre x e y com pesos w."""
    if len(x) != len(y) or len(x) != len(w) or len(x) < 2:
        return float("nan")
    sum_w = sum(w)
    if sum_w <= 0:
        return float("nan")

    # Médias ponderadas
    x_bar = sum(wi * xi for wi, xi in zip(w, x)) / sum_w
    y_bar = sum(wi * yi for wi, yi in zip(w, y)) / sum_w

    # Covariância e variâncias ponderadas
    cov_xy = sum(wi * (xi - x_bar) * (yi - y_bar) for wi, xi, yi in zip(w, x, y))
    var_x = sum(wi * (xi - x_bar) ** 2 for wi, xi in zip(w, x))
    var_y = sum(wi * (yi - y_bar) ** 2 for wi, yi in zip(w, y))

    denom = math.sqrt(var_x * var_y)
    if denom <= 0:
        return float("nan")
    return float(cov_xy / denom)


def n_eff_kish(w: List[float]) -> float:
    """Calcula o tamanho amostral efetivo de Kish: (Σw)² / Σw²."""
    sum_w = sum(w)
    sum_w2 = sum(wi * wi for wi in w)
    if sum_w2 <= 0:
        return 0.0
    return (sum_w * sum_w) / sum_w2


# ==============================================================================
# Funções com imports lazy (scipy.stats)
# ==============================================================================

def p_brown_forsythe(F: float, gl1: int, gl2: int) -> float:
    """Calcula o p-valor da estatística F de Brown-Forsythe via scipy.stats.f.sf."""
    if math.isnan(F) or gl1 <= 0 or gl2 <= 0:
        return float("nan")
    import scipy.stats  # lazy import

    return float(scipy.stats.f.sf(F, gl1, gl2))


def gerar_prov(painel_path: pathlib.Path, script_rel: str) -> dict:
    """Gera o dicionário de proveniência do resultado."""
    from datetime import datetime, timezone
    import scipy  # lazy import

    sha = calcular_sha256(painel_path)
    return {
        "script": script_rel,
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "painel_caminho": str(painel_path),
        "painel_sha256": sha,
        "sha256": sha,
        "painel": {
            "caminho": str(painel_path),
            "sha256": sha,
        },
        "versoes": {
            "scipy": getattr(scipy, "__version__", "desconhecida"),
        },
        "definicao_classes": {
            "anos_1_3": [1, 2, 3],
            "anos_4_6": [4, 5, 6],
            "anos_7_9": [7, 8, 9],
        },
    }


# ==============================================================================
# Execução principal
# ==============================================================================

def processar_painel(painel_path: pathlib.Path | str) -> List[dict]:
    """Processa o painel gerando as 342 linhas de precisão amostral (114 por tamanho)."""
    linhas = carregar_painel(painel_path)
    resultados = []

    for tamanho in TAMANHOS:
        # Amostra sem_piso: exposicao_veic_km > 0
        amostra = [
            l
            for l in linhas
            if l["tamanho_km"] == tamanho and l["exposicao_veic_km"] > 0
        ]
        n_amostra = len(amostra)
        if n_amostra == 0:
            continue

        R_todos = [float(l["taxa_por_100M_veic_km"]) for l in amostra]
        C_todos = [float(l["anos_utilizaveis"]) for l in amostra]
        n_c_todos = len(set(C_todos))

        # ----------------------------------------------------------------------
        # Bloco 1: dispersao (11 estratos x 9 medidas = 99 linhas)
        # ----------------------------------------------------------------------
        subamostras_disp: Dict[str, List[dict]] = {}
        for c_nome in CLASSES:
            subamostras_disp[c_nome] = [
                l for l in amostra if classe_anos(l["anos_utilizaveis"]) == c_nome
            ]
        for i in range(1, 9):
            subamostras_disp[f"anos_{i}"] = [
                l for l in amostra if int(l["anos_utilizaveis"]) == i
            ]

        for estrato_nome in ESTRATOS_DISPERSAO:
            sub = subamostras_disp[estrato_nome]
            n_sub = len(sub)
            c_sub = [float(l["anos_utilizaveis"]) for l in sub]
            n_c_sub = len(set(c_sub))

            if n_sub < 2:
                for med in MEDIDAS_DISPERSAO:
                    resultados.append({
                        "tamanho_km": tamanho,
                        "bloco": "dispersao",
                        "estrato": estrato_nome,
                        "medida": med,
                        "n": n_sub,
                        "n_valores_c": n_c_sub,
                        "valor": "",
                        "p_valor": "",
                        "nota": "n_insuficiente",
                    })
            else:
                taxas_sub = [float(l["taxa_por_100M_veic_km"]) for l in sub]
                sinistros_sub = [int(l["sinistros"]) for l in sub]
                exposicoes_sub = [float(l["exposicao_veic_km"]) for l in sub]
                estats = dispersao(taxas_sub, sinistros_sub, exposicoes_sub)

                for med in MEDIDAS_DISPERSAO:
                    v = estats[med]
                    v_str = (
                        ""
                        if v is None or math.isnan(v)
                        else repr(v)
                    )
                    resultados.append({
                        "tamanho_km": tamanho,
                        "bloco": "dispersao",
                        "estrato": estrato_nome,
                        "medida": med,
                        "n": n_sub,
                        "n_valores_c": n_c_sub,
                        "valor": v_str,
                        "p_valor": "",
                        "nota": "",
                    })

        # ----------------------------------------------------------------------
        # Bloco 2: teste_dispersao (estrato 'todos', 3 medidas = 3 linhas)
        # ----------------------------------------------------------------------
        # 1. brown_forsythe_classes
        g_classes = [
            [float(l["taxa_por_100M_veic_km"]) for l in amostra if classe_anos(l["anos_utilizaveis"]) == c]
            for c in CLASSES
        ]
        F_cls, gl1_cls, gl2_cls = brown_forsythe_F(g_classes)
        p_cls = p_brown_forsythe(F_cls, gl1_cls, gl2_cls)
        resultados.append({
            "tamanho_km": tamanho,
            "bloco": "teste_dispersao",
            "estrato": "todos",
            "medida": "brown_forsythe_classes",
            "n": n_amostra,
            "n_valores_c": n_c_todos,
            "valor": repr(F_cls) if not math.isnan(F_cls) else "",
            "p_valor": repr(p_cls) if not math.isnan(p_cls) else "",
            "nota": f"gl={gl1_cls},{gl2_cls}",
        })

        # 2. brown_forsythe_anos
        g_anos = [
            [float(l["taxa_por_100M_veic_km"]) for l in amostra if int(l["anos_utilizaveis"]) == i]
            for i in range(1, 9)
        ]
        F_anos, gl1_anos, gl2_anos = brown_forsythe_F(g_anos)
        p_anos = p_brown_forsythe(F_anos, gl1_anos, gl2_anos)
        resultados.append({
            "tamanho_km": tamanho,
            "bloco": "teste_dispersao",
            "estrato": "todos",
            "medida": "brown_forsythe_anos",
            "n": n_amostra,
            "n_valores_c": n_c_todos,
            "valor": repr(F_anos) if not math.isnan(F_anos) else "",
            "p_valor": repr(p_anos) if not math.isnan(p_anos) else "",
            "nota": f"gl={gl1_anos},{gl2_anos}",
        })

        # 3. spearman_c_desvio_abs
        mediana_r = statistics.median(R_todos)
        desvios_abs = [abs(ri - mediana_r) for ri in R_todos]
        pC_todos = postos(C_todos)
        pD_todos = postos(desvios_abs)
        r_spearman_desv = pearson(pC_todos, pD_todos)
        p_spearman_desv = p_valor_t(r_spearman_desv, n_amostra, k=0)
        resultados.append({
            "tamanho_km": tamanho,
            "bloco": "teste_dispersao",
            "estrato": "todos",
            "medida": "spearman_c_desvio_abs",
            "n": n_amostra,
            "n_valores_c": n_c_todos,
            "valor": repr(r_spearman_desv) if not math.isnan(r_spearman_desv) else "",
            "p_valor": repr(p_spearman_desv) if not math.isnan(p_spearman_desv) else "",
            "nota": "",
        })

        # ----------------------------------------------------------------------
        # Bloco 3: associacao (4 estratos x 3 medidas = 12 linhas)
        # ----------------------------------------------------------------------
        subamostras_assoc: Dict[str, List[dict]] = {
            "todos": amostra,
        }
        for c_nome in CLASSES:
            subamostras_assoc[c_nome] = subamostras_disp[c_nome]

        for estrato_nome in ESTRATOS_ASSOCIACAO:
            sub = subamostras_assoc[estrato_nome]
            n_sub = len(sub)
            c_sub = [float(l["anos_utilizaveis"]) for l in sub]
            r_sub = [float(l["taxa_por_100M_veic_km"]) for l in sub]
            w_sub = [float(l["exposicao_veic_km"]) for l in sub]
            n_c_sub = len(set(c_sub))

            c_constante = bool(n_c_sub <= 1)

            for med in MEDIDAS_ASSOCIACAO:
                if c_constante:
                    resultados.append({
                        "tamanho_km": tamanho,
                        "bloco": "associacao",
                        "estrato": estrato_nome,
                        "medida": med,
                        "n": n_sub,
                        "n_valores_c": n_c_sub,
                        "valor": "",
                        "p_valor": "",
                        "nota": "cobertura_constante",
                    })
                    continue

                if med == "pearson":
                    r = pearson(c_sub, r_sub)
                    p = p_valor_t(r, n_sub, k=0)
                elif med == "spearman":
                    pC = postos(c_sub)
                    pR = postos(r_sub)
                    r = pearson(pC, pR)
                    p = p_valor_t(r, n_sub, k=0)
                elif med == "pearson_ponderado":
                    r = pearson_ponderado(c_sub, r_sub, w_sub)
                    neff = int(math.floor(n_eff_kish(w_sub)))
                    p = p_valor_t(r, neff, k=0)
                else:
                    raise ValueError(f"Medida desconhecida: {med}")

                v_str = repr(r) if not math.isnan(r) else ""
                p_str = repr(p) if not math.isnan(p) else ""

                resultados.append({
                    "tamanho_km": tamanho,
                    "bloco": "associacao",
                    "estrato": estrato_nome,
                    "medida": med,
                    "n": n_sub,
                    "n_valores_c": n_c_sub,
                    "valor": v_str,
                    "p_valor": p_str,
                    "nota": "",
                })

    return resultados


def imprimir_tabela_resumo(resultados: List[dict]) -> None:
    """Imprime um resumo por tamanho conforme o plano de precisão amostral."""
    print("\n" + "=" * 80)
    print("RESUMO: PRECISÃO AMOSTRAL E ASSOCIAÇÃO COBERTURA x TAXA")
    print("=" * 80)

    for tamanho in TAMANHOS:
        sub_tam = [r for r in resultados if r["tamanho_km"] == tamanho]
        if not sub_tam:
            continue
        n_faixas = next(r["n"] for r in sub_tam if r["bloco"] == "teste_dispersao")
        print(f"\n--- Faixa de {tamanho} km (n = {n_faixas} faixas) ---")

        # 1. Variância e razão por classe
        print("\n  1. Dispersão por classe de cobertura:")
        print(f"     {'Classe':<10} | {'n':<6} | {'Variância':<12} | {'DIQ':<10} | {'Var Poisson':<12} | {'Razão Obs/Esp':<12}")
        print("     " + "-" * 72)
        for c_nome in CLASSES:
            sub_c = [r for r in sub_tam if r["bloco"] == "dispersao" and r["estrato"] == c_nome]
            if not sub_c:
                continue
            n_c = sub_c[0]["n"]
            var_val = next(float(r["valor"]) for r in sub_c if r["medida"] == "variancia")
            diq_val = next(float(r["valor"]) for r in sub_c if r["medida"] == "diq")
            vp_val = next(float(r["valor"]) for r in sub_c if r["medida"] == "variancia_poisson_esperada")
            rz_val = next(float(r["valor"]) for r in sub_c if r["medida"] == "razao_var_obs_poisson")
            print(f"     {c_nome:<10} | {n_c:<6} | {var_val:<12.1f} | {diq_val:<10.1f} | {vp_val:<12.1f} | {rz_val:<12.2f}")

        # 2. Testes de dispersão
        print("\n  2. Testes de dispersão (estrato 'todos'):")
        bf_c = next(r for r in sub_tam if r["medida"] == "brown_forsythe_classes")
        bf_a = next(r for r in sub_tam if r["medida"] == "brown_forsythe_anos")
        sp_d = next(r for r in sub_tam if r["medida"] == "spearman_c_desvio_abs")
        print(f"     Brown-Forsythe (classes): F = {float(bf_c['valor']):.2f}, p = {float(bf_c['p_valor']):.4e} ({bf_c['nota']})")
        print(f"     Brown-Forsythe (anos):    F = {float(bf_a['valor']):.2f}, p = {float(bf_a['p_valor']):.4e} ({bf_a['nota']})")
        print(f"     Spearman (C x |r-med|):   r = {float(sp_d['valor']):+.4f}, p = {float(sp_d['p_valor']):.4e}")

        # 3. Pearson x Ponderado por estrato
        print("\n  3. Associação Cobertura x Taxa (Pearson x Ponderado):")
        print(f"     {'Estrato':<10} | {'n':<6} | {'n_c':<4} | {'Pearson (r)':<20} | {'Spearman (r)':<20} | {'Pearson Pond (r)':<20}")
        print("     " + "-" * 90)
        for estrato_nome in ESTRATOS_ASSOCIACAO:
            sub_a = [r for r in sub_tam if r["bloco"] == "associacao" and r["estrato"] == estrato_nome]
            if not sub_a:
                continue
            n_est = sub_a[0]["n"]
            nc_est = sub_a[0]["n_valores_c"]
            r_pea = next(r for r in sub_a if r["medida"] == "pearson")
            r_spe = next(r for r in sub_a if r["medida"] == "spearman")
            r_pnd = next(r for r in sub_a if r["medida"] == "pearson_ponderado")

            txt_pea = f"{float(r_pea['valor']):+.4f} (p={float(r_pea['p_valor']):.2e})" if r_pea["valor"] else r_pea["nota"]
            txt_spe = f"{float(r_spe['valor']):+.4f} (p={float(r_spe['p_valor']):.2e})" if r_spe["valor"] else r_spe["nota"]
            txt_pnd = f"{float(r_pnd['valor']):+.4f} (p={float(r_pnd['p_valor']):.2e})" if r_pnd["valor"] else r_pnd["nota"]

            print(f"     {estrato_nome:<10} | {n_est:<6} | {nc_est:<4} | {txt_pea:<20} | {txt_spe:<20} | {txt_pnd:<20}")

    print("\n" + "=" * 80)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--painel", type=pathlib.Path, default=DEFAULT_PAINEL)
    ap.add_argument("--saida", type=pathlib.Path, default=DEFAULT_SAIDA)
    args = ap.parse_args()

    if not args.painel.exists():
        sys.exit(f"ERRO: Painel não encontrado em {args.painel}")

    # Cria diretório de saída se faltar
    args.saida.parent.mkdir(parents=True, exist_ok=True)

    print(f"Processando painel {args.painel}...")
    resultados = processar_painel(args.painel)

    with open(args.saida, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS)
        writer.writeheader()
        writer.writerows(resultados)

    print(f"OK: {len(resultados)} linhas gravadas em {args.saida}")

    prov_path = args.saida.with_name(args.saida.stem + ".prov.json")
    script_rel = "bin/precisao_corredores.py"
    prov_dict = gerar_prov(args.painel, script_rel)
    with open(prov_path, "w", encoding="utf-8") as f:
        json.dump(prov_dict, f, indent=2, ensure_ascii=False)
    print(f"OK: Proveniência gravada em {prov_path}")

    imprimir_tabela_resumo(resultados)
    return 0


if __name__ == "__main__":
    sys.exit(main())
