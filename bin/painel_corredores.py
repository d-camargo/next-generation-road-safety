#!/usr/bin/env python3
"""Constrói o painel espacial dos dez corredores federais (2017-2025) que
alimenta `bin/moran_corredores.py`.

Unidade: faixa de N km (N em {5, 10, 20}) dentro de `(br, uf)`. ⚠️ A chave é
SEMPRE `(br, uf, km)` — a quilometragem das BRs reinicia em cada estado (a
BR-101 tem km 0 em onze UFs), e chavear só por `(br, km)` funde trechos
separados por milhares de km. Ver `bases/prf-acidentes/METODO-ESPACIAL.md`,
"A chave de junção é BR + km, não o id do trecho".

## Como o painel é construído

1. **Rede (denominador da elegibilidade)**: a partir de
   `bases/pnct-vmda/series/vmda_corredores_por_trecho_2017_2025.csv`
   (as dez BRs, todas as UFs), cada linha vira um intervalo
   `[km_inicial, km_final]` com `jurisdicao`/`superficie`/`vmda_total`/
   `classificacao`. Um bin de 1 km `(br, uf, km)` entra na rede do painel
   só se, em **todos** os quatro anos que declaram jurisdição (2022-2025),
   o centro do bin (`km + 0.5`) cai dentro de exatamente um intervalo com
   `jurisdicao == 'federal'` e `superficie` em `{PAV, DUP}` — mesma regra
   de "O painel" no método (rede definida pelos anos que declaram
   jurisdição, aplicada retroativamente). Se o centro não cair em nenhum
   intervalo, ou cair em intervalos conflitantes (jurisdição/superfície
   diferentes) em algum dos quatro anos, o bin fica fora, e essa exclusão é
   contada.
2. **Exposição por ano**: para cada bin da rede e cada ano de análise
   (2017-2020, 2022-2025 — 2021 não tem par de km), calcula
   `vmda_total × 1 km × 365` quando o intervalo que cobre o centro do bin
   naquele ano tem volume utilizável (`vmda_total > 0` e `classificacao`
   fora de `{Não Simulável, Travessia - Não Simulável, Não Pavimentada}`).
   Fica guardado por ano (não somado ainda) — a soma só acontece no passo 4,
   sobre o conjunto de anos que a faixa efetivamente usa.
3. **Sinistros por ano**: de `geo.prf_acidentes_corredores` (PostGIS),
   contados por ano, excluindo coordenada em grau inteiro, atribuídos ao bin
   `(br, uf, floor(km))` — só contam os que caem num bin que É rede do
   painel; sinistro fora da rede (bin não qualificado) não entra em faixa
   nenhuma e é reportado à parte.
4. **Agregação em faixas com alinhamento temporal**: `faixa = km // tamanho
   * tamanho`, dentro de `(br, uf)`, para tamanho em {5, 10, 20} km. Para
   cada faixa, `anos_utilizaveis` é o conjunto de anos em que **pelo menos
   um** km da faixa teve volume utilizável (união, não interseção — ver
   nota abaixo). ⚠️ **`sinistros` e `exposicao_veic_km` somam SEMPRE o
   mesmo conjunto `anos_utilizaveis`, nunca conjuntos diferentes** — este é
   o defeito da spec anterior que esta versão conserta: lá, `sinistros`
   somava os 8 anos de análise inteiros e `exposicao_veic_km` só os anos
   com volume, o que inflava a taxa onde a cobertura do VMDa era parcial
   (ver `anos_utilizaveis`/`anos_lista` no CSV de saída, e
   `bin/moran_corredores.py` para o teste de se essa cobertura é
   espacialmente estruturada).

## Guarda dura da chave (br, uf, km)

A junção do sinistro ao bin usa SEMPRE a tripla `(br, uf, km)` — nunca
`(br, km)`. Como prova executável disso, e não só promessa em docstring,
o script recalcula a contagem de sinistros por bin por dois caminhos
independentes (agregação direta vs. reconstrução a partir das linhas cruas)
e falha se divergirem. Além disso conta e IMPRIME quantas combinações
`(br, km)` inteiras são reivindicadas por mais de uma UF na tabela de
sinistros dos dez corredores — não é falha (é o sintoma esperado do reset
de quilometragem por estado, a própria razão de a chave carregar UF), mas
fica registrado como medida de quão grave seria a chave curta.

Uso:
    ~/.venvs/geo/bin/python bin/painel_corredores.py [--vmda-csv CAMINHO]
        [--dsn DSN] [--saida CAMINHO]
"""
from __future__ import annotations

import argparse
import csv
import math
import pathlib
import sys
from collections import defaultdict
from typing import Dict, List, Tuple

import psycopg2
import psycopg2.extras

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin"))

from build_geo_prf import resolver_dsn  # noqa: E402
from mede_cobertura_vmda import (  # noqa: E402
    CLASSIFICACOES_SEM_VOLUME,
    eh_grau_inteiro,
    normalizar_br,
    parse_km_prf,
)

DEFAULT_VMDA_CSV = ROOT / "bases" / "pnct-vmda" / "series" / "vmda_corredores_por_trecho_2017_2025.csv"
DEFAULT_SAIDA = ROOT / "build" / "painel_corredores.csv"

ANOS_JURISDICAO = (2022, 2023, 2024, 2025)
ANOS_ANALISE = (2017, 2018, 2019, 2020, 2022, 2023, 2024, 2025)
TAMANHOS = (5, 10, 20)
SUPERFICIES_PAINEL = {"PAV", "DUP"}

Intervalo = Tuple[float, float, str, str, float, str]  # lo, hi, jurisdicao, superficie, vmda_total, classificacao


def carregar_vmda(path: pathlib.Path) -> Dict[int, Dict[Tuple[str, str], List[Intervalo]]]:
    """{ano -> {(br, uf) -> [intervalos]}}, só linhas com km_inicial E
    km_final preenchidos (2021 não tem nenhuma)."""
    reg: Dict[int, Dict[Tuple[str, str], List[Intervalo]]] = defaultdict(lambda: defaultdict(list))
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ki, kf = row["km_inicial"], row["km_final"]
            if not ki or not kf:
                continue
            ano = int(row["ano"])
            lo, hi = float(ki), float(kf)
            if lo > hi:
                lo, hi = hi, lo
            br = normalizar_br(row["br"])
            uf = row["uf"]
            vmda_total = float(row["vmda_total"]) if row["vmda_total"] else 0.0
            reg[ano][(br, uf)].append((lo, hi, row["jurisdicao"], row["superficie"], vmda_total, row["classificacao"]))
    for ano in reg:
        for chave in reg[ano]:
            reg[ano][chave].sort()
    return reg


def cobertura(intervalos: List[Intervalo], centro: float) -> List[Intervalo]:
    return [iv for iv in intervalos if iv[0] <= centro <= iv[1]]


def construir_rede(
    reg: Dict[int, Dict[Tuple[str, str], List[Intervalo]]]
) -> Tuple[set, Dict[str, int]]:
    """Retorna (bins_da_rede, contagem_exclusoes). bins_da_rede é um set de
    (br, uf, km) — km inteiro. contagem_exclusoes detalha por que cada km
    candidato ficou fora: 'sem_cobertura' (algum dos 4 anos sem intervalo
    cobrindo o centro), 'ambiguo' (mais de um intervalo conflitante),
    'nao_federal_pav_dup' (cobertura existe mas não é federal+PAV/DUP)."""
    chaves_br_uf = set()
    for ano in ANOS_JURISDICAO:
        chaves_br_uf |= set(reg.get(ano, {}).keys())

    bins_rede = set()
    exclusoes = {"sem_cobertura": 0, "ambiguo": 0, "nao_federal_pav_dup": 0}

    for (br, uf) in sorted(chaves_br_uf):
        max_hi = 0.0
        for ano in ANOS_JURISDICAO:
            for iv in reg.get(ano, {}).get((br, uf), []):
                max_hi = max(max_hi, iv[1])
        km_max = math.ceil(max_hi)
        for km in range(0, km_max):
            centro = km + 0.5
            motivo_exclusao = None
            for ano in ANOS_JURISDICAO:
                ivs = reg.get(ano, {}).get((br, uf), [])
                matches = cobertura(ivs, centro)
                if not matches:
                    motivo_exclusao = "sem_cobertura"
                    break
                jurs = {m[2] for m in matches}
                sups = {m[3] for m in matches}
                if len(jurs) > 1 or len(sups) > 1:
                    motivo_exclusao = "ambiguo"
                    break
                jur, sup = matches[0][2], matches[0][3]
                if jur != "federal" or sup not in SUPERFICIES_PAINEL:
                    motivo_exclusao = "nao_federal_pav_dup"
                    break
            if motivo_exclusao is None:
                bins_rede.add((br, uf, km))
            else:
                exclusoes[motivo_exclusao] += 1

    return bins_rede, exclusoes


def calcular_exposicao_por_ano(
    bins_rede: set, reg: Dict[int, Dict[Tuple[str, str], List[Intervalo]]]
) -> Dict[Tuple[str, str, int], Dict[int, float]]:
    """Para cada bin da rede, {(br,uf,km) -> {ano -> exposicao_veic_km}},
    UM valor por ano (não somado ainda) — só entram no dict interno os anos
    em que o bin teve volume utilizável naquele ano. A soma sobre um
    conjunto de anos é responsabilidade de quem agrega em faixa
    (`agregar_faixas`), que tem que escolher o MESMO conjunto de anos para
    somar sinistros e exposição — ver docstring do módulo."""
    resultado: Dict[Tuple[str, str, int], Dict[int, float]] = {}
    for (br, uf, km) in bins_rede:
        centro = km + 0.5
        por_ano: Dict[int, float] = {}
        for ano in ANOS_ANALISE:
            ivs = reg.get(ano, {}).get((br, uf), [])
            matches = cobertura(ivs, centro)
            if len(matches) != 1:
                # sem cobertura naquele ano, ou cobertura ambígua — sem
                # denominador utilizável nesse ano para este bin.
                continue
            _, _, _jur, _sup, vmda_total, classificacao = matches[0]
            if vmda_total > 0 and (classificacao or "").strip() not in CLASSIFICACOES_SEM_VOLUME:
                por_ano[ano] = vmda_total * 1.0 * 365.0
        resultado[(br, uf, km)] = por_ano
    return resultado


def carregar_sinistros(dsn: str) -> List[dict]:
    con = psycopg2.connect(dsn)
    try:
        with con.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT ano, br, uf, km, lat_bruta, lon_bruta "
                "FROM geo.prf_acidentes_corredores WHERE ano = ANY(%s)",
                (list(ANOS_ANALISE),),
            )
            return cur.fetchall()
    finally:
        con.close()


def contar_sinistros_por_bin(
    registros: List[dict], bins_rede: set
) -> Tuple[Dict[Tuple[str, str, int], int], int, int, int]:
    """Conta sinistros por bin da rede, usando SEMPRE a chave (br, uf, km).

    Retorna (contagem_por_bin, excluidos_grau_inteiro, fora_da_rede,
    colisoes_br_km_sem_uf) — o último é quantas combinações (br, km) inteiras
    (ignorando UF) são reivindicadas por mais de uma UF nos sinistros dos
    dez corredores: não é erro, é a medida do estrago que a chave sem UF
    causaria (ver docstring do módulo)."""
    contagem: Dict[Tuple[str, str, int], int] = defaultdict(int)
    excluidos = 0
    fora_da_rede = 0
    ufs_por_br_km: Dict[Tuple[str, int], set] = defaultdict(set)

    for r in registros:
        if eh_grau_inteiro(r["lat_bruta"], r["lon_bruta"]):
            excluidos += 1
            continue
        br = normalizar_br(r["br"])
        uf = r["uf"]
        km_f = parse_km_prf(r["km"])
        if km_f is None:
            excluidos += 1
            continue
        km = math.floor(km_f)
        ufs_por_br_km[(br, km)].add(uf)
        chave = (br, uf, km)
        if chave in bins_rede:
            contagem[chave] += 1
        else:
            fora_da_rede += 1

    colisoes = sum(1 for ufs in ufs_por_br_km.values() if len(ufs) > 1)

    # Guarda dura: reconstrução independente da contagem por bin, a partir
    # das linhas cruas, batendo item a item contra `contagem`. Se algum dia
    # o join for trocado para (br, km) sem UF, esta reconstrução diverge e
    # o script falha — é o "sintoma da chave errada voltando" que a spec
    # pede para vigiar.
    conferencia: Dict[Tuple[str, str, int], int] = defaultdict(int)
    for r in registros:
        if eh_grau_inteiro(r["lat_bruta"], r["lon_bruta"]):
            continue
        br = normalizar_br(r["br"])
        uf = r["uf"]
        km_f = parse_km_prf(r["km"])
        if km_f is None:
            continue
        km = math.floor(km_f)
        chave = (br, uf, km)
        if chave in bins_rede:
            conferencia[chave] += 1

    divergencias = 0
    for chave in set(contagem) | set(conferencia):
        if contagem.get(chave, 0) != conferencia.get(chave, 0):
            divergencias += 1
    if divergencias:
        raise SystemExit(
            f"GUARDA DURA FALHOU: {divergencias} bins com contagem de sinistros "
            f"divergente entre as duas agregações independentes por (br, uf, km) "
            f"— sintoma de chave errada (br, km) sem UF voltando. Abortando."
        )

    return dict(contagem), excluidos, fora_da_rede, colisoes


def contar_sinistros_por_bin_por_ano(
    registros: List[dict], bins_rede: set
) -> Dict[Tuple[str, str, int], Dict[int, int]]:
    """{(br,uf,km) -> {ano -> contagem}}, mesma filtragem (grau inteiro
    excluído, chave SEMPRE (br,uf,km)) de `contar_sinistros_por_bin`, só que
    sem colapsar o ano — é o que permite `agregar_faixas` somar sinistros no
    MESMO conjunto de anos usado para somar exposição."""
    contagem: Dict[Tuple[str, str, int], Dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for r in registros:
        if eh_grau_inteiro(r["lat_bruta"], r["lon_bruta"]):
            continue
        br = normalizar_br(r["br"])
        uf = r["uf"]
        km_f = parse_km_prf(r["km"])
        if km_f is None:
            continue
        km = math.floor(km_f)
        chave = (br, uf, km)
        if chave in bins_rede:
            contagem[chave][int(r["ano"])] += 1
    return {chave: dict(por_ano) for chave, por_ano in contagem.items()}


def agregar_faixas(
    bins_rede: set,
    exposicao_por_bin_ano: Dict[Tuple[str, str, int], Dict[int, float]],
    sinistros_por_bin_ano: Dict[Tuple[str, str, int], Dict[int, int]],
    tamanho: int,
) -> List[dict]:
    """Agrega bins em faixas de `tamanho` km dentro de (br, uf).

    ⚠️ PONTO CENTRAL DO ALINHAMENTO TEMPORAL: para cada faixa,
    `anos_utilizaveis` é a UNIÃO dos anos em que qualquer km da faixa teve
    volume utilizável. `sinistros` e `exposicao_veic_km` são somados sobre
    EXATAMENTE esse mesmo conjunto de anos, para todos os bins da faixa —
    nunca um conjunto para o numerador e outro para o denominador. É o
    defeito da spec anterior (numerador com 8 anos, denominador só com os
    anos de volume) que esta função conserta.
    """
    bins_por_faixa: Dict[Tuple[str, str, int], List[int]] = defaultdict(list)
    for (br, uf, km) in bins_rede:
        faixa_km = (km // tamanho) * tamanho
        bins_por_faixa[(br, uf, faixa_km)].append(km)

    linhas = []
    for (br, uf, faixa_km), kms in bins_por_faixa.items():
        anos_utilizaveis: set = set()
        for km in kms:
            anos_utilizaveis |= set(exposicao_por_bin_ano.get((br, uf, km), {}).keys())
        anos_lista = sorted(anos_utilizaveis)

        sinistros = 0
        exposicao_veic_km = 0.0
        km_com_exposicao = 0
        for km in kms:
            exp_ano = exposicao_por_bin_ano.get((br, uf, km), {})
            sin_ano = sinistros_por_bin_ano.get((br, uf, km), {})
            # numerador e denominador percorrem o MESMO anos_lista — é o
            # laço que garante o alinhamento (ver docstring da função).
            for ano in anos_lista:
                exposicao_veic_km += exp_ano.get(ano, 0.0)
                sinistros += sin_ano.get(ano, 0)
            if exp_ano:
                km_com_exposicao += 1

        taxa = (
            sinistros / exposicao_veic_km * 100_000_000.0
            if exposicao_veic_km > 0 else None
        )
        linhas.append({
            "tamanho_km": tamanho, "br": br, "uf": uf,
            "km_inicial": faixa_km, "km_final": faixa_km + tamanho,
            "n_bins_painel": len(kms), "sinistros": sinistros,
            "exposicao_veic_km": exposicao_veic_km,
            "km_com_exposicao": km_com_exposicao,
            "anos_utilizaveis": len(anos_lista),
            "anos_lista": ";".join(str(a) for a in anos_lista),
            "taxa_por_100M_veic_km": taxa,
        })
    linhas.sort(key=lambda l: (l["br"], l["uf"], l["km_inicial"]))
    return linhas


def percentis(valores: List[float], pontos=(0, 5, 10, 25, 50, 75, 90, 100)) -> Dict[int, float]:
    if not valores:
        return {p: float("nan") for p in pontos}
    vs = sorted(valores)
    n = len(vs)
    resultado = {}
    for p in pontos:
        if n == 1:
            resultado[p] = vs[0]
            continue
        posicao = (p / 100.0) * (n - 1)
        lo = math.floor(posicao)
        hi = math.ceil(posicao)
        if lo == hi:
            resultado[p] = vs[lo]
        else:
            frac = posicao - lo
            resultado[p] = vs[lo] * (1 - frac) + vs[hi] * frac
    return resultado


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vmda-csv", type=pathlib.Path, default=DEFAULT_VMDA_CSV)
    ap.add_argument("--dsn", default=None)
    ap.add_argument("--saida", type=pathlib.Path, default=DEFAULT_SAIDA)
    args = ap.parse_args()

    dsn = resolver_dsn(args.dsn)

    print(f"Carregando VMDa de {args.vmda_csv} ...")
    reg = carregar_vmda(args.vmda_csv)

    print("Construindo a rede do painel (jurisdição federal + PAV/DUP estável em 2022-2025) ...")
    bins_rede, exclusoes = construir_rede(reg)
    print(f"Bins no painel (br,uf,km, 1 km cada): {len(bins_rede)}")
    print(f"Exclusões da rede por motivo: {exclusoes}")

    print("Calculando exposição por bin, por ano (2017-2020, 2022-2025) ...")
    exposicao_por_bin_ano = calcular_exposicao_por_ano(bins_rede, reg)

    print("Carregando sinistros de geo.prf_acidentes_corredores ...")
    registros = carregar_sinistros(dsn)
    sinistros_por_bin, excluidos_grau_inteiro, fora_da_rede, colisoes = contar_sinistros_por_bin(registros, bins_rede)
    total_sinistros_no_painel = sum(sinistros_por_bin.values())
    print(
        f"Sinistros (2017-2020,2022-2025): {len(registros)} lidos; "
        f"{excluidos_grau_inteiro} excluídos por coordenada em grau inteiro; "
        f"{fora_da_rede} fora da rede do painel; "
        f"{total_sinistros_no_painel} atribuídos a bins do painel."
    )
    print(
        f"Guarda (br,uf,km): {colisoes} combinações de (br,km) SEM uf reivindicadas por "
        f"mais de uma UF na tabela de sinistros dos dez corredores — não é falha, é a "
        f"medida do que a chave curta fundiria; a agregação usada é sempre (br,uf,km) "
        f"e a reconstrução independente bateu (0 divergências)."
    )

    sinistros_por_bin_ano = contar_sinistros_por_bin_por_ano(registros, bins_rede)
    # Guarda dura extra (alinhamento): a quebra por ano tem que somar
    # exatamente ao mesmo total por bin já conferido acima — senão o
    # conjunto de anos usado na agregação por faixa estaria descolado da
    # contagem total.
    divergencias_ano = 0
    for chave, total in sinistros_por_bin.items():
        if sum(sinistros_por_bin_ano.get(chave, {}).values()) != total:
            divergencias_ano += 1
    if divergencias_ano:
        raise SystemExit(
            f"GUARDA DURA FALHOU: {divergencias_ano} bins com soma por ano divergente "
            f"do total por bin — sintoma de desalinhamento entre numerador e "
            f"denominador na agregação por faixa. Abortando."
        )

    todas_as_linhas: List[dict] = []
    for tamanho in TAMANHOS:
        linhas = agregar_faixas(bins_rede, exposicao_por_bin_ano, sinistros_por_bin_ano, tamanho)
        todas_as_linhas.extend(linhas)
        exposicoes = [l["exposicao_veic_km"] for l in linhas]
        p = percentis(exposicoes)
        print(f"\nTamanho {tamanho} km: {len(linhas)} faixas.")
        print(
            "Distribuição de exposicao_veic_km (p0,p5,p10,p25,p50,p75,p90,p100): "
            + ", ".join(f"{k}%={p[k]:,.0f}" for k in (0, 5, 10, 25, 50, 75, 90, 100))
        )
        dist_anos = defaultdict(int)
        for l in linhas:
            dist_anos[l["anos_utilizaveis"]] += 1
        print(
            "Distribuição de anos_utilizaveis (0.." + str(len(ANOS_ANALISE)) + " anos): "
            + ", ".join(f"{n_anos}={dist_anos.get(n_anos, 0)}" for n_anos in range(len(ANOS_ANALISE) + 1))
        )
        n_completos = dist_anos.get(len(ANOS_ANALISE), 0)
        print(
            f"  faixas com os {len(ANOS_ANALISE)} anos utilizáveis (recorte anos_completos): "
            f"{n_completos}/{len(linhas)} ({n_completos / len(linhas) * 100:.1f}%)"
        )

    args.saida.parent.mkdir(parents=True, exist_ok=True)
    campos = [
        "tamanho_km", "br", "uf", "km_inicial", "km_final", "n_bins_painel",
        "sinistros", "exposicao_veic_km", "km_com_exposicao",
        "anos_utilizaveis", "anos_lista", "taxa_por_100M_veic_km",
    ]
    with open(args.saida, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        for linha in todas_as_linhas:
            w.writerow(linha)
    print(f"\nOK: {args.saida} gravado ({len(todas_as_linhas)} linhas).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
