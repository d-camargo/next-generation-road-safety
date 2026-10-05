#!/usr/bin/env python3
"""Gera GeoJSON das faixas do painel/LISA dos dez corredores, com geometria.

Entradas:
  - raw/geo-referencia/dnit_snv_corredores_202507a.geojson (SNV 202507a, as
    dez BRs do recorte, país inteiro — baixado do mesmo WFS INDE/DNIT do
    `build_geo_referencia.py`, CQL por vl_br);
  - build/painel_corredores.csv (bin/painel_corredores.py);
  - build/lisa_corredores.csv (bin/moran_corredores.py, recorte de
    referência 10 km / anos_completos).

Saídas (build/mapa/):
  - faixas_lisa_10km_anos_completos.geojson — uma feição por faixa do LISA,
    com quadrante/p_valor/significativo_fdr + taxa/sinistros/exposição;
  - faixas_painel_10km.geojson — todas as faixas de 10 km do painel (camada
    de contexto, sem classificação LISA).

Como a geometria é cortada: a faixa é um intervalo de quilometragem
[km_inicial, km_final) dentro de (br, uf); cada trecho do SNV cobre
[vl_km_inic, vl_km_fina]. A interseção em km é convertida em FRAÇÃO ao longo
da geometria do trecho ((km - lo)/(hi - lo)) e cortada com
`shapely.ops.substring`. ⚠️ Isso assume velocidade uniforme do marco
quilométrico ao longo do trecho (aproximação declarada) e que o trecho é
digitalizado no sentido do km crescente — verificado por encadeamento de
extremidades em amostra de MG (BR-040/050/116/381: 137 pares corretos,
0 invertidos, 2026-10-03).

Trechos sobrepostos em km (Contorno/Anel/Coinc reivindicando a mesma faixa):
varredura de intervalos com prioridade — Eixo Principal > Contorno > Anel >
demais; empatado, desc_coinc '-' antes de 'Coinc'; empatado, trecho mais
longo. Cada subintervalo de km é coberto por UM trecho só (sem geometria
duplicada).

A chave de junção é (br, uf, km), a mesma do painel — a quilometragem
reinicia em cada estado. `vl_br` do SNV e `br` do painel estão ambos com
zero-padding de 3 dígitos.

SF: EPSG:4674 (SIRGAS 2000), o mesmo do WFS.

Uso:
    ~/.venvs/geo/bin/python bin/gera_mapa_corredores.py
"""
from __future__ import annotations

import csv
import json
import pathlib
from collections import defaultdict

from shapely.geometry import LineString, MultiLineString, mapping
from shapely.ops import substring

ROOT = pathlib.Path(__file__).resolve().parent.parent
SNV = ROOT / "raw" / "geo-referencia" / "dnit_snv_corredores_202507a.geojson"
PAINEL = ROOT / "build" / "painel_corredores.csv"
LISA = ROOT / "build" / "lisa_corredores.csv"
SAIDA_DIR = ROOT / "build" / "mapa"

TAMANHO = 10  # km — o do recorte de referência do LISA e da camada de contexto

PRIORIDADE_TIPO = {"Eixo Principal": 0, "Contorno": 1, "Anel": 2}
PRIORIDADE_COINC = {"-": 0, "Coinc": 1}


def arredondar(coords, nd=6):
    if isinstance(coords[0], (int, float)):
        return [round(coords[0], nd), round(coords[1], nd)]
    return [arredondar(c, nd) for c in coords]


def cortar(geom: LineString | MultiLineString, frac0: float, frac1: float) -> list:
    """Corta `geom` entre as frações frac0..frac1 do comprimento total,
    tratando MultiLineString por comprimento acumulado na ordem digitalizada."""
    partes = list(geom.geoms) if geom.geom_type == "MultiLineString" else [geom]
    total = sum(p.length for p in partes)
    if total <= 0:
        return []
    d0, d1 = frac0 * total, frac1 * total
    pecas, acc = [], 0.0
    for p in partes:
        pl = p.length
        if pl <= 0:
            continue
        s, e = max(d0, acc), min(d1, acc + pl)
        if e - s > 1e-12:
            pecas.append(substring(p, s - acc, e - acc, normalized=False))
        acc += pl
    return [p for p in pecas if not p.is_empty]


def montar_trechos(snv_path: pathlib.Path) -> dict:
    """Agrupa trechos por (br, uf), ordenados por prioridade de cobertura."""
    feats = json.loads(snv_path.read_text(encoding="utf-8"))["features"]
    por_br_uf: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for f in feats:
        pr = f["properties"]
        lo, hi = float(pr["vl_km_inic"]), float(pr["vl_km_fina"])
        if hi <= lo:
            continue
        prio = (
            PRIORIDADE_TIPO.get(pr.get("nm_tipo_tr"), 3),
            PRIORIDADE_COINC.get(pr.get("desc_coinc"), 1),
            -(hi - lo),
            pr.get("vl_codigo", ""),
        )
        por_br_uf[(pr["vl_br"], pr["sg_uf"])].append(
            {"lo": lo, "hi": hi, "prio": prio, "geom": f["geometry"]}
        )
    for k in por_br_uf:
        por_br_uf[k].sort(key=lambda t: t["prio"])
    return por_br_uf


def cobrir_faixa(trechos: list[dict], f0: float, f1: float) -> list[dict]:
    """Varredura de intervalos: devolve [{'trecho': i, 'lo': km, 'hi': km}, ...]
    cobrindo [f0, f1) sem sobreposição, com o trecho de maior prioridade
    vencendo cada subintervalo de km."""
    coberto: list[tuple[float, float]] = []
    atrib: list[dict] = []
    for i, t in enumerate(trechos):
        lo, hi = max(t["lo"], f0), min(t["hi"], f1)
        if hi <= lo:
            continue
        rem = [(lo, hi)]
        for c0, c1 in coberto:
            novo = []
            for r0, r1 in rem:
                if c1 <= r0 or c0 >= r1:
                    novo.append((r0, r1))
                    continue
                if r0 < c0:
                    novo.append((r0, c0))
                if c1 < r1:
                    novo.append((c1, r1))
            rem = novo
        for r0, r1 in rem:
            atrib.append({"trecho": i, "lo": r0, "hi": r1})
            coberto.append((r0, r1))
    return atrib


def geometria_da_faixa(trechos: list[dict], f0: float, f1: float):
    atrib = sorted(cobrir_faixa(trechos, f0, f1), key=lambda a: a["lo"])
    pecas, km_coberto = [], 0.0
    for a in atrib:
        t = trechos[a["trecho"]]
        ext = t["hi"] - t["lo"]
        g = t["geom"]
        partes = g["coordinates"]
        comp_total = None
        # frações ao longo da geometria (na ordem digitalizada = km crescente)
        geom = (
            MultiLineString([LineString(p) for p in partes])
            if g["type"] == "MultiLineString"
            else LineString(partes)
        )
        frac0 = (a["lo"] - t["lo"]) / ext
        frac1 = (a["hi"] - t["lo"]) / ext
        pecas.extend(cortar(geom, frac0, frac1))
        km_coberto += a["hi"] - a["lo"]
    if not pecas:
        return None, 0.0
    if len(pecas) == 1:
        return pecas[0], km_coberto
    return MultiLineString(
        [p if p.geom_type == "LineString" else list(p.geoms) for p in pecas]
    ).buffer(0) if False else MultiLineString(
        [q for p in pecas for q in (list(p.geoms) if p.geom_type == "MultiLineString" else [p])]
    ), km_coberto


def feature(br, uf, linha, geom):
    propriedades = {
        "br": br,
        "br_rotulo": f"BR-{int(br)}",
        "uf": uf,
        "km_inicial": int(linha["km_inicial"]),
        "km_final": int(float(linha.get("km_final") or int(linha["km_inicial"]) + TAMANHO)),
        "sinistros": int(linha["sinistros"]),
        "exposicao_veic_km": round(float(linha.get("exposicao_veic_km") or linha.get("exposicao") or 0), 1),
        "taxa_por_100M_veic_km": round(float(linha["taxa"]), 6)
        if "taxa" in linha and linha["taxa"] not in ("", None)
        else None,
        "anos_utilizaveis": int(linha["anos_utilizaveis"]),
    }
    if "quadrante" in linha:
        propriedades["quadrante"] = linha["quadrante"]
        propriedades["p_valor"] = round(float(linha["p_valor"]), 5)
        propriedades["significativo_fdr"] = linha["significativo_fdr"] == "True"
    geo = mapping(geom)
    geo["coordinates"] = arredondar(geo["coordinates"])
    return {"type": "Feature", "properties": propriedades, "geometry": geo}


def gerar(trechos_por_br_uf, linhas, caminho, tem_lisa):
    feats, sem_geometria, km_esperado, km_obtido = [], [], 0.0, 0.0
    for linha in linhas:
        br, uf = linha["br"], linha["uf"]
        f0 = float(linha["km_inicial"])
        f1 = float(linha["km_final"]) if linha.get("km_final") else f0 + TAMANHO
        trechos = trechos_por_br_uf.get((br, uf), [])
        geom, km_cob = geometria_da_faixa(trechos, f0, f1)
        km_esperado += f1 - f0
        if geom is None or km_cob <= 0.01:
            sem_geometria.append((br, uf, linha["km_inicial"]))
            continue
        km_obtido += km_cob
        feats.append(feature(br, uf, linha, geom))
    fc = {
        "type": "FeatureCollection",
        "name": caminho.stem,
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::4674"}},
        "features": feats,
    }
    caminho.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
    print(f"\n{caminho.name}: {len(feats)} feições")
    if sem_geometria:
        print(f"  ⚠️ {len(sem_geometria)} faixas SEM geometria no SNV "
              f"(primeiras 10): {sem_geometria[:10]}")
    print(f"  cobertura de km: {km_obtido:,.1f} de {km_esperado:,.1f} "
          f"({100 * km_obtido / km_esperado:.1f}%)")


def main():
    SAIDA_DIR.mkdir(parents=True, exist_ok=True)
    trechos_por_br_uf = montar_trechos(SNV)

    with open(PAINEL, newline="", encoding="utf-8") as f:
        painel = [l for l in csv.DictReader(f) if int(l["tamanho_km"]) == TAMANHO]
    painel.sort(key=lambda l: (l["br"], l["uf"], int(l["km_inicial"])))
    print(f"painel 10 km: {len(painel)} faixas")

    gerar(trechos_por_br_uf, painel, SAIDA_DIR / "faixas_painel_10km.geojson", False)

    with open(LISA, newline="", encoding="utf-8") as f:
        lisa = [l for l in csv.DictReader(f) if int(l["km_inicial"]) % TAMANHO == 0]
    lisa.sort(key=lambda l: (l["br"], l["uf"], int(l["km_inicial"])))
    # junta taxa/exposição do painel (o LISA já traz sinistros/exposicao/taxa próprios)
    for l in lisa:
        l.setdefault("taxa", l.get("taxa", ""))
    print(f"LISA 10 km: {len(lisa)} faixas")
    gerar(trechos_por_br_uf, lisa, SAIDA_DIR / "faixas_lisa_10km_anos_completos.geojson", True)


if __name__ == "__main__":
    main()
