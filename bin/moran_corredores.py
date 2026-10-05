#!/usr/bin/env python3
"""Moran global e LISA sobre o painel dos dez corredores federais.

Lê `build/painel_corredores.csv` (gerado por `bin/painel_corredores.py`,
já com numerador e denominador somados sobre o MESMO conjunto de
`anos_utilizaveis` por faixa — ver docstring daquele script) e, para cada
tamanho de faixa (5, 10, 20 km) e cada recorte de exposição/cobertura
(sem piso, p10, p25, **anos_completos**), calcula:

1. **Vizinhança**: faixas adjacentes dentro do mesmo `(br, uf)` — a unidade é
   linear (sequência de km ao longo da rodovia), não geometria de polígono.
   Os pesos são montados à mão a partir da posição `km_inicial` de cada
   faixa: duas faixas do mesmo `(br, uf)` são vizinhas se
   `km_inicial(j) == km_inicial(i) + tamanho`. `libpysal.weights.W` recebe
   esse dicionário pronto e faz só a padronização por linha
   (`transformation='r'`). Ilhas (faixa sem vizinho — extremidade de
   corredor, ou faixa isolada por um piso de exposição que removeu a
   vizinha) são contadas e reportadas, **nunca removidas**.
2. **Moran global**, 9.999 permutações, TRÊS versões:
   - `esda.Moran` sobre `taxa_por_100M_veic_km` (taxa bruta, agora alinhada);
   - `esda.Moran_Rate` sobre `(sinistros, exposicao_veic_km)` — ajuste
     bayesiano empírico de Assunção-Reis, o tratamento padrão para taxa com
     denominador heterogêneo;
   - `esda.Moran` sobre `anos_utilizaveis` (contínua) — **o teste que decide
     se o resultado da rodada anterior era artefato da cobertura do VMDa**:
     se a cobertura em si é espacialmente autocorrelacionada, qualquer
     padrão visto numa taxa não alinhada é candidato a estar medindo
     estrutura da cobertura, não do risco.
3. **LISA**: `esda.Moran_Local_Rate`, 9.999 permutações, com correção FDR
   (`esda.fdr`) para multiplicidade. Contagem de clusters significativos a
   5% antes e depois do FDR, por quadrante (alto-alto, baixo-baixo,
   alto-baixo, baixo-alto — esquema GeoDa: `geoda_quads=True`).

O recorte **`anos_completos`** (só faixas com os 8 anos de `anos_utilizaveis`)
é o controle sem desalinhamento possível por construção: toda faixa nesse
recorte soma numerador e denominador sobre os mesmos 8 anos, sempre.

⚠️ Faixa com `exposicao_veic_km == 0` (sem nenhum ano de volume utilizável)
não entra em nenhuma combinação — taxa é indefinida (0/0) e `Moran_Rate` não
tem base válida. A contagem de faixas excluídas por isso é impressa e faz
parte do `n` reportado.

⚠️ Este script NÃO decide se há ou não concentração espacial. Imprime `I`,
`E[I]`, `p_sim`, `z` e as contagens de cluster — quem interpreta é o Diego.
Se o Moran da taxa bruta e o do `Moran_Rate` divergirem em sinal ou em
significância (um cruza p<0,05 e o outro não), isso é destacado explicitamente
como divergência, nunca resolvido escolhendo um dos dois.

Grava `build/moran_corredores.csv` (uma linha por tamanho×recorte×versão) e
`build/lisa_corredores.csv` (classificação por faixa, no recorte de
referência **10 km / anos_completos**).

Uso:
    ~/.venvs/geo/bin/python bin/moran_corredores.py [--painel CAMINHO]
"""
from __future__ import annotations

import argparse
import csv
import pathlib
import sys
import warnings
from collections import defaultdict
from typing import Dict, List, Tuple

import esda
import libpysal
import numpy as np
import scipy.stats

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_PAINEL = ROOT / "build" / "painel_corredores.csv"
SAIDA_MORAN = ROOT / "build" / "moran_corredores.csv"
SAIDA_LISA = ROOT / "build" / "lisa_corredores.csv"

TAMANHOS = (5, 10, 20)
# "anos_completos" não é piso de exposição — é o recorte de robustez sem
# desalinhamento possível por construção (só faixas com os 8 anos de
# anos_utilizaveis). Fica na mesma lista para reaproveitar o laço de
# combinações e a tabela final.
PISOS = ("sem_piso", "p10", "p25", "anos_completos")
PERMUTACOES = 9999
ALPHA = 0.05
ANOS_ANALISE_N = 8  # tamanho de ANOS_ANALISE em bin/painel_corredores.py
VMDA_SUSPEITO = 2000.0  # veículos/dia — piso abaixo do qual o VMDa implícito é suspeito
# Recorte de referência do LISA: 10 km / anos_completos — o controle sem
# desalinhamento possível (spec "alinhar numerador e denominador").
RECORTE_REFERENCIA = (10, "anos_completos")

QUADRANTE_GEODA = {1: "alto-alto", 2: "baixo-baixo", 3: "baixo-alto", 4: "alto-baixo"}


def carregar_painel(path: pathlib.Path) -> List[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        linhas = list(csv.DictReader(f))
    for l in linhas:
        l["tamanho_km"] = int(l["tamanho_km"])
        l["km_inicial"] = int(l["km_inicial"])
        l["sinistros"] = int(l["sinistros"])
        l["exposicao_veic_km"] = float(l["exposicao_veic_km"])
        l["anos_utilizaveis"] = int(l["anos_utilizaveis"])
        l["taxa_por_100M_veic_km"] = (
            float(l["taxa_por_100M_veic_km"]) if l["taxa_por_100M_veic_km"] not in (None, "") else None
        )
    return linhas


def percentil(valores: List[float], p: float) -> float:
    return float(np.percentile(np.array(valores), p))


def montar_vizinhanca(amostra: List[dict], tamanho: int) -> libpysal.weights.W:
    """Vizinhança linear dentro de (br, uf): duas faixas são vizinhas se a
    posição km_inicial da segunda é exatamente km_inicial da primeira +
    tamanho. amostra já vem na ordem de índice 0..n-1 usada pelos arrays do
    Moran."""
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
    # remove duplicatas preservando determinismo
    neighbors = {k: sorted(set(v)) for k, v in neighbors.items()}

    with warnings.catch_warnings(record=True) as avisos:
        warnings.simplefilter("always")
        w = libpysal.weights.W(neighbors, silence_warnings=False)
    return w, avisos


def rodar_combinacao(amostra: List[dict], tamanho: int, piso: str) -> dict:
    w, avisos = montar_vizinhanca(amostra, tamanho)
    w.transform = "r"
    n = w.n
    ilhas = len(w.islands)

    taxa = np.array([l["taxa_por_100M_veic_km"] for l in amostra])
    sinistros = np.array([l["sinistros"] for l in amostra], dtype=float)
    exposicao = np.array([l["exposicao_veic_km"] for l in amostra], dtype=float)
    anos_utilizaveis = np.array([l["anos_utilizaveis"] for l in amostra], dtype=float)

    moran_bruta = esda.Moran(taxa, w, transformation="r", permutations=PERMUTACOES)
    moran_rate = esda.Moran_Rate(sinistros, exposicao, w, transformation="r", permutations=PERMUTACOES)
    # Terceira variável: anos_utilizaveis como contínua. Se a cobertura do
    # VMDa for espacialmente autocorrelacionada, isso é evidência de que um
    # padrão visto só na taxa não alinhada (rodada anterior) media estrutura
    # da cobertura, não do risco — ver docstring do módulo.
    #
    # ⚠️ No recorte `anos_completos`, anos_utilizaveis é CONSTANTE (=8) por
    # construção — variância zero. esda.Moran divide por soma de quadrados
    # zero e devolve I=NaN; a permutação compara NaN>=NaN (sempre False),
    # o que produziria um p_sim=0.0001 numericamente "significativo" mas
    # vazio de sentido. Detecta isso explicitamente e reporta NaN também no
    # p_sim/z_sim, em vez de deixar o artefato passar como se fosse achado.
    anos_constante = bool(np.std(anos_utilizaveis) == 0)
    if anos_constante:
        moran_anos = None
        moran_bv = None
        pearson_r = float("nan")
        pearson_p = float("nan")
    else:
        moran_anos = esda.Moran(anos_utilizaveis, w, transformation="r", permutations=PERMUTACOES)
        moran_bv = esda.Moran_BV(taxa, anos_utilizaveis, w, transformation="r", permutations=PERMUTACOES)
        pr, pp = scipy.stats.pearsonr(anos_utilizaveis, taxa)
        pearson_r = float(pr)
        pearson_p = float(pp)

    # Ilhas têm seI_sim == 0 (lag sempre 0), então z_sim vira 0/0 = NaN por
    # construção — esperado, documentado aqui, e sem efeito no que este
    # script reporta (p_sim, não z_sim, é o que decide significância do
    # LISA). Suprime só esse RuntimeWarning numérico, nunca o aviso de
    # ilha do libpysal, que é capturado acima e vai para o relatório.
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="invalid value encountered in divide", category=RuntimeWarning)
        lisa = esda.Moran_Local_Rate(
            sinistros, exposicao, w, transformation="r", permutations=PERMUTACOES,
            geoda_quads=True, seed=12345,
        )

    sig_antes = lisa.p_sim < ALPHA
    cutoff_fdr = esda.fdr(lisa.p_sim, ALPHA)
    sig_depois = lisa.p_sim < cutoff_fdr

    contagem_antes = defaultdict(int)
    contagem_depois = defaultdict(int)
    for q, sa, sd in zip(lisa.q, sig_antes, sig_depois):
        rotulo = QUADRANTE_GEODA[int(q)]
        if sa:
            contagem_antes[rotulo] += 1
        if sd:
            contagem_depois[rotulo] += 1

    return {
        "n": n,
        "ilhas": ilhas,
        "avisos_libpysal": "; ".join(str(a.message) for a in avisos),
        "moran_bruta_I": moran_bruta.I,
        "moran_bruta_EI": moran_bruta.EI,
        "moran_bruta_p_sim": moran_bruta.p_sim,
        "moran_bruta_z_sim": moran_bruta.z_sim,
        "moran_rate_I": moran_rate.I,
        "moran_rate_EI": moran_rate.EI,
        "moran_rate_p_sim": moran_rate.p_sim,
        "moran_rate_z_sim": moran_rate.z_sim,
        "moran_anos_I": moran_anos.I if moran_anos is not None else float("nan"),
        "moran_anos_EI": moran_anos.EI if moran_anos is not None else float("nan"),
        "moran_anos_p_sim": moran_anos.p_sim if moran_anos is not None else float("nan"),
        "moran_anos_z_sim": moran_anos.z_sim if moran_anos is not None else float("nan"),
        "moran_anos_constante": anos_constante,
        "moran_bv_I": moran_bv.I if moran_bv is not None else float("nan"),
        "moran_bv_p_sim": moran_bv.p_sim if moran_bv is not None else float("nan"),
        "moran_bv_z_sim": moran_bv.z_sim if moran_bv is not None else float("nan"),
        "pearson_r": pearson_r,
        "pearson_p": pearson_p,
        "fdr_cutoff": cutoff_fdr,
        "lisa_alto_alto_antes": contagem_antes["alto-alto"],
        "lisa_baixo_baixo_antes": contagem_antes["baixo-baixo"],
        "lisa_alto_baixo_antes": contagem_antes["alto-baixo"],
        "lisa_baixo_alto_antes": contagem_antes["baixo-alto"],
        "lisa_alto_alto_depois": contagem_depois["alto-alto"],
        "lisa_baixo_baixo_depois": contagem_depois["baixo-baixo"],
        "lisa_alto_baixo_depois": contagem_depois["alto-baixo"],
        "lisa_baixo_alto_depois": contagem_depois["baixo-alto"],
        "_lisa_obj": lisa,
        "_w": w,
    }


def gravar_lisa_referencia(
    amostra: List[dict], resultado: dict, tamanho: int, saida: pathlib.Path
) -> None:
    lisa = resultado["_lisa_obj"]
    cutoff_fdr = resultado["fdr_cutoff"]
    campos = [
        "br", "uf", "km_inicial", "sinistros", "exposicao", "taxa",
        "anos_utilizaveis", "quadrante", "p_valor", "significativo_fdr",
    ]
    with open(saida, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        for l, q, p in zip(amostra, lisa.q, lisa.p_sim):
            w.writerow({
                "br": l["br"], "uf": l["uf"], "km_inicial": l["km_inicial"],
                "sinistros": l["sinistros"], "exposicao": l["exposicao_veic_km"],
                "taxa": l["taxa_por_100M_veic_km"],
                "anos_utilizaveis": l["anos_utilizaveis"],
                "quadrante": QUADRANTE_GEODA[int(q)],
                "p_valor": p,
                "significativo_fdr": bool(p < cutoff_fdr),
            })
    print(f"OK: {saida} gravado ({len(amostra)} linhas).")

    # Passo 4 da spec: para cada cluster alto-alto sobrevivente ao FDR, o
    # VMDa médio implícito é a conta inversa que denunciou o defeito da
    # spec anterior — vira verificação permanente aqui.
    print(
        "\n=== Clusters alto-alto sobreviventes ao FDR "
        f"({tamanho}km / {RECORTE_REFERENCIA[1]}) — VMDa médio implícito ==="
    )
    algum_cluster = False
    for l, q, p in zip(amostra, lisa.q, lisa.p_sim):
        if QUADRANTE_GEODA[int(q)] != "alto-alto" or not (p < cutoff_fdr):
            continue
        algum_cluster = True
        anos = l["anos_utilizaveis"]
        vmda_implicito = (
            l["exposicao_veic_km"] / (tamanho * 365.0 * anos) if anos > 0 else float("nan")
        )
        suspeita = " ⚠️ SUSPEITO (<2.000 veic/dia)" if vmda_implicito < VMDA_SUSPEITO else ""
        print(
            f"  BR-{l['br']}/{l['uf']} km {l['km_inicial']}-{l['km_inicial'] + tamanho}: "
            f"sinistros={l['sinistros']} exposicao_veic_km={l['exposicao_veic_km']:,.0f} "
            f"anos_utilizaveis={anos} taxa={l['taxa_por_100M_veic_km']:.2f} "
            f"VMDa_implicito={vmda_implicito:,.1f} veic/dia p_sim={p:.4f}{suspeita}"
        )
    if not algum_cluster:
        print(f"  nenhum cluster alto-alto sobreviveu ao FDR em {tamanho}km / {RECORTE_REFERENCIA[1]}.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--painel", type=pathlib.Path, default=DEFAULT_PAINEL)
    args = ap.parse_args()

    linhas = carregar_painel(args.painel)

    resultados_para_csv = []
    resultado_referencia = None
    amostra_referencia = None

    for tamanho in TAMANHOS:
        do_tamanho = [l for l in linhas if l["tamanho_km"] == tamanho]
        base = [l for l in do_tamanho if l["exposicao_veic_km"] > 0]
        excluidas_zero = len(do_tamanho) - len(base)
        exposicoes_base = [l["exposicao_veic_km"] for l in base]
        p10 = percentil(exposicoes_base, 10)
        p25 = percentil(exposicoes_base, 25)

        print(f"\n=== Tamanho {tamanho} km ===")
        print(f"Faixas no painel: {len(do_tamanho)}; excluídas por exposição zero: {excluidas_zero}; base: {len(base)}")
        print(f"Piso p10 = {p10:,.0f} veic-km; piso p25 = {p25:,.0f} veic-km")

        for piso in PISOS:
            if piso == "sem_piso":
                amostra = base
            elif piso == "p10":
                amostra = [l for l in base if l["exposicao_veic_km"] >= p10]
            elif piso == "p25":
                amostra = [l for l in base if l["exposicao_veic_km"] >= p25]
            else:  # anos_completos — recorte de robustez sem desalinhamento possível
                amostra = [l for l in base if l["anos_utilizaveis"] == ANOS_ANALISE_N]

            resultado = rodar_combinacao(amostra, tamanho, piso)
            if resultado["moran_anos_constante"]:
                trecho_anos = "anos_utilizaveis: CONSTANTE nesta amostra (Moran indefinido por construção — recorte anos_completos)"
            else:
                trecho_anos = (
                    f"anos_utilizaveis: I={resultado['moran_anos_I']:.4f} "
                    f"p_sim={resultado['moran_anos_p_sim']:.4f} z={resultado['moran_anos_z_sim']:.3f}"
                )
            print(
                f"[{tamanho}km / {piso}] n={resultado['n']} ilhas={resultado['ilhas']} | "
                f"bruta: I={resultado['moran_bruta_I']:.4f} p_sim={resultado['moran_bruta_p_sim']:.4f} "
                f"z={resultado['moran_bruta_z_sim']:.3f} | "
                f"rate: I={resultado['moran_rate_I']:.4f} p_sim={resultado['moran_rate_p_sim']:.4f} "
                f"z={resultado['moran_rate_z_sim']:.3f} | "
                f"{trecho_anos}"
            )
            if resultado["avisos_libpysal"]:
                print(f"  aviso libpysal: {resultado['avisos_libpysal']}")

            linha_csv = {
                "tamanho_km": tamanho, "piso": piso,
                "n": resultado["n"], "ilhas": resultado["ilhas"],
                "moran_bruta_I": resultado["moran_bruta_I"],
                "moran_bruta_EI": resultado["moran_bruta_EI"],
                "moran_bruta_p_sim": resultado["moran_bruta_p_sim"],
                "moran_bruta_z_sim": resultado["moran_bruta_z_sim"],
                "moran_rate_I": resultado["moran_rate_I"],
                "moran_rate_EI": resultado["moran_rate_EI"],
                "moran_rate_p_sim": resultado["moran_rate_p_sim"],
                "moran_rate_z_sim": resultado["moran_rate_z_sim"],
                "moran_anos_I": resultado["moran_anos_I"],
                "moran_anos_EI": resultado["moran_anos_EI"],
                "moran_anos_p_sim": resultado["moran_anos_p_sim"],
                "moran_anos_z_sim": resultado["moran_anos_z_sim"],
                "moran_anos_constante": resultado["moran_anos_constante"],
                "moran_bv_I": resultado["moran_bv_I"],
                "moran_bv_p_sim": resultado["moran_bv_p_sim"],
                "moran_bv_z_sim": resultado["moran_bv_z_sim"],
                "pearson_r": resultado["pearson_r"],
                "pearson_p": resultado["pearson_p"],
                "fdr_cutoff": resultado["fdr_cutoff"],
                "lisa_alto_alto_antes": resultado["lisa_alto_alto_antes"],
                "lisa_baixo_baixo_antes": resultado["lisa_baixo_baixo_antes"],
                "lisa_alto_baixo_antes": resultado["lisa_alto_baixo_antes"],
                "lisa_baixo_alto_antes": resultado["lisa_baixo_alto_antes"],
                "lisa_alto_alto_depois": resultado["lisa_alto_alto_depois"],
                "lisa_baixo_baixo_depois": resultado["lisa_baixo_baixo_depois"],
                "lisa_alto_baixo_depois": resultado["lisa_alto_baixo_depois"],
                "lisa_baixo_alto_depois": resultado["lisa_baixo_alto_depois"],
            }
            resultados_para_csv.append(linha_csv)

            if (tamanho, piso) == RECORTE_REFERENCIA:
                resultado_referencia = resultado
                amostra_referencia = amostra

    args.painel.parent.mkdir(parents=True, exist_ok=True)
    campos = list(resultados_para_csv[0].keys())
    with open(SAIDA_MORAN, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows(resultados_para_csv)
    print(f"\nOK: {SAIDA_MORAN} gravado ({len(resultados_para_csv)} linhas).")

    gravar_lisa_referencia(amostra_referencia, resultado_referencia, RECORTE_REFERENCIA[0], SAIDA_LISA)

    print("\n=== Tabela final (tamanho × recorte: I/p da taxa bruta, do Moran_Rate, de anos_utilizaveis, e clusters LISA) ===")
    cab = (
        f"{'tamanho':>7} | {'recorte':>13} | {'n':>5} | {'ilhas':>5} | "
        f"{'I_bruta':>9} | {'p_bruta':>8} | {'I_rate':>9} | {'p_rate':>8} | "
        f"{'I_anos':>9} | {'p_anos':>8} | {'AA_antes':>8} | {'AA_depois':>9} | divergência"
    )
    print(cab)
    print("-" * len(cab))
    for r in resultados_para_csv:
        sig_bruta = r["moran_bruta_p_sim"] < ALPHA
        sig_rate = r["moran_rate_p_sim"] < ALPHA
        sinal_diverge = (r["moran_bruta_I"] > 0) != (r["moran_rate_I"] > 0)
        sig_diverge = sig_bruta != sig_rate
        marca = "SIM" if (sinal_diverge or sig_diverge) else ""
        if r["moran_anos_constante"]:
            col_i_anos, col_p_anos = "const", "const"
        else:
            col_i_anos, col_p_anos = f"{r['moran_anos_I']:.4f}", f"{r['moran_anos_p_sim']:.4f}"
        print(
            f"{r['tamanho_km']:>7} | {r['piso']:>13} | {r['n']:>5} | {r['ilhas']:>5} | "
            f"{r['moran_bruta_I']:>9.4f} | {r['moran_bruta_p_sim']:>8.4f} | "
            f"{r['moran_rate_I']:>9.4f} | {r['moran_rate_p_sim']:>8.4f} | "
            f"{col_i_anos:>9} | {col_p_anos:>8} | "
            f"{r['lisa_alto_alto_antes']:>8} | {r['lisa_alto_alto_depois']:>9} | {marca}"
        )

    divergentes = [
        r for r in resultados_para_csv
        if ((r["moran_bruta_I"] > 0) != (r["moran_rate_I"] > 0))
        or ((r["moran_bruta_p_sim"] < ALPHA) != (r["moran_rate_p_sim"] < ALPHA))
    ]
    if divergentes:
        print(
            f"\n⚠️ DIVERGÊNCIA entre taxa bruta e Moran_Rate em {len(divergentes)} "
            f"combinação(ões) de tamanho×piso (sinal ou significância a 5% não coincidem) "
            f"— ver coluna 'divergência' acima e {SAIDA_MORAN}. Isso não é resolvido aqui: "
            f"padrão que só aparece na taxa bruta é candidato a artefato de denominador pequeno."
        )
    else:
        print("\nSem divergência de sinal ou significância a 5% entre taxa bruta e Moran_Rate em nenhuma combinação.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
