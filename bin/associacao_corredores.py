#!/usr/bin/env python3
"""Associação entre cobertura da amostragem e taxa de sinistros nos corredores federais.

Mede a associação bivariada e condicionada entre a cobertura de contagem de tráfego
(C = `anos_utilizaveis`) e a taxa de sinistros (R) no painel dos dez maiores
corredores federais do Brasil (5 km, 10 km e 20 km), respondendo ao item R2-01
do parecer 02 do trabalho `next-generation-road-safety`.

1. **O que mede**:
   - Correlação de Pearson bivariada e parcial (controlando por `log(AADT médio)`).
   - Correlação de Spearman (postos) bivariada e parcial (controlando por postos de
     `log(AADT médio)`), robusta à assimetria severa da taxa de acidentes.
   - Moran bivariado (esda.Moran_BV) na ordem (taxa, cobertura), com matriz de
     vizinhança linear idêntica à de `bin/moran_corredores.py`, tanto bivariado
     quanto sobre os resíduos OLS de taxa e cobertura sobre `log(AADT médio)`.
   - Avaliação para taxa bruta (`taxa_por_100M_veic_km`) e para a taxa suavizada por
     Bayes Empírico (EB global de Marshall, método dos momentos), que controla a
     heterocedasticidade decorrente de extensões ou volumes distintos.
   - Estratificação por volume: tercis de `aadt_medio` calculados por tamanho de
     faixa via `statistics.quantiles(aadt, n=3)`, testando a estabilidade da
     associação dentro de classes homogêneas de tráfego.

2. **Por que**:
   O revisor R2 apontou duas explicações alternativas ao Moran bivariado negativo
   (I_BV = -0,276 a 10 km; r = -0,392):
   (a) Efeito de volume: relação sublinear volume x acidentes (safety in numbers)
       que derrubaria a taxa por veic-km nos locais com mais tráfego, onde a cobertura
       também costuma ser maior;
   (b) Efeito de precisão amostral: faixas com menor número de anos monitorados
       possuem estimativas de taxa com maior variância, gerando valores extremos.
   Controlando simultaneamente por `log(AADT médio)` e substituindo a taxa bruta
   pela taxa EB, este script afere se a associação negativa sobrevive ou se é
   explicada por esses dois mecanismos.

3. **Amostra**:
   Idêntica ao recorte `sem_piso` de `bin/moran_corredores.py`: por tamanho de faixa
   (5 km, 10 km, 20 km), entram todas as faixas com `exposicao_veic_km > 0`.
   O recorte `anos_completos` não entra porque nele `anos_utilizaveis` é constante
   (= 8), o que torna a correlação e o Moran bivariado indefinidos por construção
   (variância nula da cobertura).

4. **O que NÃO decide**:
   Este script NÃO infere causalidade nem decide isoladamente se existe ou não
   viés de seleção no programa de contagens. Imprime e grava os coeficientes,
   p-valores analíticos (t de Student com gl corrigidos) e p-valores simulados
   (Moran_BV). A interpretação substantiva obedece ao critério fixado a priori
   no plano de análise (PLAN.md / METODO-ESPACIAL.md).

Uso:
    ~/.venvs/geo/bin/python bin/associacao_corredores.py [--painel CAMINHO] [--saida CAMINHO]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import pathlib
import statistics
import sys
import warnings
from typing import Dict, List, Optional, Tuple

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_PAINEL = ROOT / "build" / "painel_corredores.csv"
DEFAULT_SAIDA = (
    ROOT
    / "bases"
    / "prf-acidentes"
    / "resultados"
    / "associacao_condicionada_corredores.csv"
)

TAMANHOS = (5, 10, 20)
ESTRATOS = ("todos", "aadt_tercil_1", "aadt_tercil_2", "aadt_tercil_3")
TAXAS = ("bruta", "eb")
PERMUTACOES = 9999


# ==============================================================================
# Funções puras stdlib-only
# ==============================================================================

def aadt_medio(linha: dict) -> float:
    """Calcula o AADT médio estimado de uma faixa do painel.

    Fórmula: exposicao_veic_km / (365 * km_com_exposicao * anos_utilizaveis).
    """
    exp = float(linha["exposicao_veic_km"])
    km = float(linha["km_com_exposicao"])
    anos = float(linha["anos_utilizaveis"])
    denom = 365.0 * km * anos
    if denom <= 0:
        return float("nan")
    return exp / denom


def taxa_eb(sinistros: List[float | int], exposicoes: List[float]) -> List[float]:
    """Suavização Bayesiana Empírica global de Marshall (método dos momentos).

    Retorna a taxa suavizada na unidade natural (eventos por unidade de exposição,
    isto é, sinistros por veic-km).

    Fórmulas (Marshall, 1991):
        r_i = y_i / e_i
        m = Σy / Σe
        s² = Σe_i(r_i - m)² / Σe
        ē = média(e)
        φ = max(0, s² - m / ē)
        w_i = φ / (φ + m / e_i)
        eb_i = w_i * r_i + (1 - w_i) * m
    """
    n = len(sinistros)
    if n == 0:
        return []
    y_sum = float(sum(sinistros))
    e_sum = float(sum(exposicoes))
    if e_sum <= 0:
        return [0.0] * n

    m = y_sum / e_sum
    r = [float(y) / float(e) if float(e) > 0 else m for y, e in zip(sinistros, exposicoes)]
    s2 = sum(float(e) * (ri - m) ** 2 for e, ri in zip(exposicoes, r)) / e_sum
    e_bar = e_sum / n
    r_var_right = m / e_bar if e_bar > 0 else 0.0
    phi = max(0.0, s2 - r_var_right)

    if phi == 0.0:
        return [m] * n

    res = []
    for ri, e in zip(r, exposicoes):
        fe = float(e)
        denom = phi + m / fe if fe > 0 else 0.0
        w = phi / denom if denom > 0 else 0.0
        res.append(w * ri + (1.0 - w) * m)
    return res


def postos(v: List[float]) -> List[float]:
    """Calcula postos médios 1-based (fractional ranking em caso de empates)."""
    n = len(v)
    if n == 0:
        return []
    ordenados = sorted(enumerate(v), key=lambda x: x[1])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j < n and ordenados[j][1] == ordenados[i][1]:
            j += 1
        posto_medio = (i + 1 + j) / 2.0
        for k in range(i, j):
            ranks[ordenados[k][0]] = posto_medio
        i = j
    return ranks


def residuos(y: List[float], x: List[float]) -> List[float]:
    """Calcula os resíduos da regressão linear simples de y sobre x (OLS).

    y - (slope * x + intercept).
    """
    try:
        reg = statistics.linear_regression(x, y)
        slope = reg.slope
        intercept = reg.intercept
        return [float(yi) - (slope * float(xi) + intercept) for yi, xi in zip(y, x)]
    except statistics.StatisticsError:
        return [float("nan")] * len(y)


def pearson(x: List[float], y: List[float]) -> float:
    """Correlação linear de Pearson entre x e y."""
    try:
        return float(statistics.correlation(x, y))
    except (statistics.StatisticsError, ZeroDivisionError):
        return float("nan")


def correlacao_parcial(x: List[float], y: List[float], z: List[float]) -> float:
    """Correlação parcial entre x e y controlando linearmente por z."""
    rx = residuos(x, z)
    ry = residuos(y, z)
    return pearson(rx, ry)


def tercis(valores: list, key=None) -> Tuple[list, list, list]:
    """Particiona a coleção em três tercis usando statistics.quantiles(n=3).

    Cortes: q1, q2 = statistics.quantiles(valores, n=3).
    Estrato 1: <= q1
    Estrato 2: (q1, q2]
    Estrato 3: > q2
    """
    if len(valores) < 2:
        return list(valores), [], []
    nums = [key(v) if key else v for v in valores]
    q1, q2 = statistics.quantiles(nums, n=3)
    t1 = [v for v, num in zip(valores, nums) if num <= q1]
    t2 = [v for v, num in zip(valores, nums) if q1 < num <= q2]
    t3 = [v for v, num in zip(valores, nums) if num > q2]
    return t1, t2, t3


def carregar_painel(path: pathlib.Path | str) -> List[dict]:
    """Lê o painel de corredores (CSV) tipando as colunas numéricas essenciais."""
    with open(path, newline="", encoding="utf-8") as f:
        linhas = list(csv.DictReader(f))
    for l in linhas:
        l["tamanho_km"] = int(l["tamanho_km"])
        l["km_inicial"] = int(l["km_inicial"])
        l["sinistros"] = int(l["sinistros"])
        l["exposicao_veic_km"] = float(l["exposicao_veic_km"])
        l["km_com_exposicao"] = float(l["km_com_exposicao"])
        l["anos_utilizaveis"] = int(l["anos_utilizaveis"])
        l["taxa_por_100M_veic_km"] = (
            float(l["taxa_por_100M_veic_km"])
            if l["taxa_por_100M_veic_km"] not in (None, "")
            else None
        )
    return linhas


# ==============================================================================
# Funções com imports lazy (scipy.stats, esda, libpysal, moran_corredores)
# ==============================================================================

def p_valor_t(r: float, n: int, k: int = 0) -> float:
    """Calcula o p-valor bicaudal da correlação r via t de Student com gl = n - 2 - k."""
    if math.isnan(r):
        return float("nan")
    df = n - 2 - k
    if df <= 0:
        return float("nan")
    if abs(r) >= 1.0:
        return 0.0
    import scipy.stats  # lazy import

    t = r * math.sqrt(df / (1.0 - r * r))
    return float(2.0 * scipy.stats.t.sf(abs(t), df))


def calcular_moran_bv(
    R: List[float],
    C: List[float],
    amostra: List[dict],
    tamanho: int,
    controle: str,
    log_aadt: Optional[List[float]] = None,
) -> Tuple[float, float, float]:
    """Calcula o Moran bivariado esda.Moran_BV(R, C, w) ou sobre os resíduos OLS.

    Argumentos:
        R: variável de taxa (bruta ou EB)
        C: variável de cobertura (anos_utilizaveis)
        amostra: linhas do painel na mesma ordem de R e C
        tamanho: tamanho da faixa em km
        controle: 'nenhum' ou 'log_aadt'
        log_aadt: valores de log(AADT médio) quando controle='log_aadt'

    Retorna: (I, p_sim, z_sim).
    """
    import esda  # lazy import
    import numpy as np  # lazy import

    bin_dir = str(pathlib.Path(__file__).resolve().parent)
    if bin_dir not in sys.path:
        sys.path.insert(0, bin_dir)
    from moran_corredores import montar_vizinhanca  # lazy import

    w, _ = montar_vizinhanca(amostra, tamanho)
    w.transform = "r"

    if controle == "log_aadt":
        if log_aadt is None:
            raise ValueError("log_aadt é obrigatório para controle='log_aadt'")
        res_R = residuos(R, log_aadt)
        res_C = residuos(C, log_aadt)
        arr_R = np.array(res_R, dtype=float)
        arr_C = np.array(res_C, dtype=float)
    else:
        arr_R = np.array(R, dtype=float)
        arr_C = np.array(C, dtype=float)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        mbv = esda.Moran_BV(arr_R, arr_C, w, transformation="r", permutations=PERMUTACOES)
    return float(mbv.I), float(mbv.p_sim), float(mbv.z_sim)


def calcular_sha256(path: pathlib.Path) -> str:
    """Calcula o sha256 do arquivo informado."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def gerar_prov(painel_path: pathlib.Path, script_rel: str) -> dict:
    """Gera o dicionário de proveniência do resultado."""
    from datetime import datetime, timezone
    import esda  # lazy import
    import libpysal  # lazy import
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
        "permutacoes": PERMUTACOES,
        "versoes": {
            "esda": getattr(esda, "__version__", "desconhecida"),
            "libpysal": getattr(libpysal, "__version__", "desconhecida"),
            "scipy": getattr(scipy, "__version__", "desconhecida"),
        },
        "aviso_reprodutibilidade": (
            "esda.Moran_BV não aceita semente; p_sim e z_sim variam ligeiramente "
            "entre execuções por simulação Monte Carlo. O valor I do Moran e as "
            "correlações de Pearson e Spearman são determinísticos."
        ),
    }


# ==============================================================================
# Execução principal
# ==============================================================================

def processar_painel(painel_path: pathlib.Path) -> List[dict]:
    """Processa o painel gerando as 72 linhas de resultado (24 por tamanho)."""
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

        # Calcula AADT e log_aadt para todas as faixas
        for l in amostra:
            l["aadt"] = aadt_medio(l)
            l["log_aadt"] = math.log(l["aadt"]) if l["aadt"] > 0 else float("nan")

        sinistros_todos = [l["sinistros"] for l in amostra]
        exposicoes_todos = [l["exposicao_veic_km"] for l in amostra]
        # Estimador EB calculado sobre toda a amostra do tamanho
        eb_taxas_raw = taxa_eb(sinistros_todos, exposicoes_todos)
        for l, ebr in zip(amostra, eb_taxas_raw):
            l["taxa_eb_100M"] = ebr * 1e8

        # Partição por tercis de AADT
        t1, t2, t3 = tercis(amostra, key=lambda l: l["aadt"])
        estratos_dict = {
            "todos": amostra,
            "aadt_tercil_1": t1,
            "aadt_tercil_2": t2,
            "aadt_tercil_3": t3,
        }

        # Laço determinístico de combinações conforme decisão 7
        for estrato_nome in ESTRATOS:
            subamostra = estratos_dict[estrato_nome]
            n_sub = len(subamostra)
            aadts_sub = [l["aadt"] for l in subamostra]
            aadt_min_val = min(aadts_sub) if aadts_sub else float("nan")
            aadt_max_val = max(aadts_sub) if aadts_sub else float("nan")

            C_sub = [float(l["anos_utilizaveis"]) for l in subamostra]
            c_constante = bool(len(set(C_sub)) <= 1)

            for taxa_nome in TAXAS:
                if taxa_nome == "bruta":
                    R_sub = [float(l["taxa_por_100M_veic_km"]) for l in subamostra]
                else:
                    R_sub = [float(l["taxa_eb_100M"]) for l in subamostra]

                log_aadt_sub = [l["log_aadt"] for l in subamostra]

                if estrato_nome == "todos":
                    medidas_lista = ("pearson", "spearman", "moran_bv")
                else:
                    medidas_lista = ("pearson", "spearman")

                for medida_nome in medidas_lista:
                    if estrato_nome == "todos":
                        controles_lista = ("nenhum", "log_aadt")
                    else:
                        controles_lista = ("nenhum",)

                    for controle_nome in controles_lista:
                        if c_constante:
                            resultados.append({
                                "tamanho_km": tamanho,
                                "estrato": estrato_nome,
                                "aadt_min": aadt_min_val,
                                "aadt_max": aadt_max_val,
                                "taxa": taxa_nome,
                                "medida": medida_nome,
                                "controle": controle_nome,
                                "n": n_sub,
                                "valor": "",
                                "p_valor": "",
                                "z_sim": "",
                                "nota": "cobertura_constante",
                            })
                            continue

                        k = 1 if controle_nome == "log_aadt" else 0

                        if medida_nome == "pearson":
                            if controle_nome == "nenhum":
                                r = pearson(C_sub, R_sub)
                            else:
                                r = correlacao_parcial(C_sub, R_sub, log_aadt_sub)
                            p = p_valor_t(r, n_sub, k=k)
                            resultados.append({
                                "tamanho_km": tamanho,
                                "estrato": estrato_nome,
                                "aadt_min": aadt_min_val,
                                "aadt_max": aadt_max_val,
                                "taxa": taxa_nome,
                                "medida": medida_nome,
                                "controle": controle_nome,
                                "n": n_sub,
                                "valor": r,
                                "p_valor": p,
                                "z_sim": "",
                                "nota": "",
                            })

                        elif medida_nome == "spearman":
                            pC = postos(C_sub)
                            pR = postos(R_sub)
                            if controle_nome == "nenhum":
                                r = pearson(pC, pR)
                            else:
                                pZ = postos(log_aadt_sub)
                                r = correlacao_parcial(pC, pR, pZ)
                            p = p_valor_t(r, n_sub, k=k)
                            resultados.append({
                                "tamanho_km": tamanho,
                                "estrato": estrato_nome,
                                "aadt_min": aadt_min_val,
                                "aadt_max": aadt_max_val,
                                "taxa": taxa_nome,
                                "medida": medida_nome,
                                "controle": controle_nome,
                                "n": n_sub,
                                "valor": r,
                                "p_valor": p,
                                "z_sim": "",
                                "nota": "",
                            })

                        elif medida_nome == "moran_bv":
                            I_val, p_sim, z_sim = calcular_moran_bv(
                                R_sub,
                                C_sub,
                                subamostra,
                                tamanho,
                                controle=controle_nome,
                                log_aadt=log_aadt_sub,
                            )
                            resultados.append({
                                "tamanho_km": tamanho,
                                "estrato": estrato_nome,
                                "aadt_min": aadt_min_val,
                                "aadt_max": aadt_max_val,
                                "taxa": taxa_nome,
                                "medida": medida_nome,
                                "controle": controle_nome,
                                "n": n_sub,
                                "valor": I_val,
                                "p_valor": p_sim,
                                "z_sim": z_sim,
                                "nota": "",
                            })

    return resultados


def imprimir_tabela_resumo(resultados: List[dict]) -> None:
    """Imprime uma tabela final por tamanho: bivariada x parcial, bruta x EB."""
    print("\n" + "=" * 80)
    print("RESUMO: ASSOCIAÇÃO COBERTURA x TAXA (CONDICIONADA A VOLUME E PRECISÃO)")
    print("=" * 80)

    for tamanho in TAMANHOS:
        sub = [r for r in resultados if r["tamanho_km"] == tamanho and r["estrato"] == "todos"]
        if not sub:
            continue
        n_faixas = sub[0]["n"]
        print(f"\n--- Faixa de {tamanho} km (n = {n_faixas} faixas) ---")
        print(f"{'Medida':<10} | {'Taxa':<7} | {'Bivariada (nenhum)':<28} | {'Parcial (log_aadt)':<28}")
        print("-" * 80)

        for medida in ("pearson", "spearman", "moran_bv"):
            simb = "r" if medida != "moran_bv" else "I"
            for taxa in ("bruta", "eb"):
                r_biv = next(
                    r for r in sub if r["medida"] == medida and r["taxa"] == taxa and r["controle"] == "nenhum"
                )
                r_parc = next(
                    r for r in sub if r["medida"] == medida and r["taxa"] == taxa and r["controle"] == "log_aadt"
                )

                txt_biv = f"{simb} = {float(r_biv['valor']):+.4f} (p = {float(r_biv['p_valor']):.4e})"
                txt_parc = f"{simb} = {float(r_parc['valor']):+.4f} (p = {float(r_parc['p_valor']):.4e})"
                print(f"{medida:<10} | {taxa:<7} | {txt_biv:<28} | {txt_parc:<28}")

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

    campos = [
        "tamanho_km",
        "estrato",
        "aadt_min",
        "aadt_max",
        "taxa",
        "medida",
        "controle",
        "n",
        "valor",
        "p_valor",
        "z_sim",
        "nota",
    ]

    with open(args.saida, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        writer.writerows(resultados)

    print(f"OK: {len(resultados)} linhas gravadas em {args.saida}")

    prov_path = args.saida.with_name(args.saida.stem + ".prov.json")
    script_rel = "bin/associacao_corredores.py"
    prov_dict = gerar_prov(args.painel, script_rel)
    with open(prov_path, "w", encoding="utf-8") as f:
        json.dump(prov_dict, f, indent=2, ensure_ascii=False)
    print(f"OK: Proveniência gravada em {prov_path}")

    imprimir_tabela_resumo(resultados)
    return 0


if __name__ == "__main__":
    sys.exit(main())
