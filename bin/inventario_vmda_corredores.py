#!/usr/bin/env python3
"""Inventário do VMDa (PNCT/DNIT) por corredor federal e ano — passo 3 do
plano de fechamento do VMDa nacional (ver `bases/pnct-vmda/FONTE.md`).

Lê `bases/pnct-vmda/series/vmda_corredores_por_trecho_2017_2025.csv` (as dez
BRs de `extrai_pnct_vmda.BRS_CORREDORES`, todas as UFs, 2017-2025) e, por
BR × ano, conta:

  - `trechos`: nº de linhas (sub-links) daquele BR naquele ano;
  - `extensao_km`: soma de `extensao_km` (a extensão do SUB-link — `vl_ext_estim`
    quando o layout do ano traz essa coluna, `vl_extensa` senão; ver
    `bases/pnct-vmda/FONTE.md`, "`extensao_km`: qual valor foi usado" — NUNCA
    `extensao_oficial_km`, que é o trecho-PAI repetido em cada sub-link e
    contaria a mesma extensão várias vezes);
  - `com_volume`: quantos desses trechos têm volume utilizável, na MESMA
    definição de `bin/mede_cobertura_vmda.py::tem_denominador` (duplicada
    aqui, não importada, para este script continuar stdlib-only — o módulo
    de cobertura carrega `psycopg2` para falar com o PostGIS, dependência que
    este inventário não precisa): `vmda_total > 0` E `classificacao` fora de
    `{'Não Simulável', 'Travessia - Não Simulável', 'Não Pavimentada'}`.

Grava `build/inventario_vmda_corredores.csv` (gitignored, reconstruível) e
imprime a mesma tabela no stdout.

Uso:
    python3 bin/inventario_vmda_corredores.py [--serie CAMINHO] [--saida CAMINHO]
"""
from __future__ import annotations

import argparse
import csv
import pathlib
from typing import Dict, Tuple

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_SERIE = ROOT / "bases" / "pnct-vmda" / "series" / "vmda_corredores_por_trecho_2017_2025.csv"
DEFAULT_SAIDA = ROOT / "build" / "inventario_vmda_corredores.csv"

# Mesmo conjunto de `bin/mede_cobertura_vmda.py::CLASSIFICACOES_SEM_VOLUME` —
# duplicado de propósito, ver docstring do módulo.
CLASSIFICACOES_SEM_VOLUME = {"Não Simulável", "Travessia - Não Simulável", "Não Pavimentada"}


def tem_denominador(vmda_total: str, classificacao: str) -> bool:
    """`vmda_total > 0` E `classificacao` fora do conjunto sem volume
    utilizável — mesma regra de `mede_cobertura_vmda.py::tem_denominador`."""
    try:
        v = float(vmda_total) if vmda_total else 0.0
    except ValueError:
        v = 0.0
    return v > 0 and (classificacao or "").strip() not in CLASSIFICACOES_SEM_VOLUME


def montar_inventario(serie_path: pathlib.Path) -> Dict[Tuple[str, int], Dict[str, float]]:
    """{(br, ano) -> {"trechos": int, "extensao_km": float, "com_volume": int}}."""
    inventario: Dict[Tuple[str, int], Dict[str, float]] = {}
    with serie_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            chave = (row["br"], int(row["ano"]))
            item = inventario.setdefault(chave, {"trechos": 0, "extensao_km": 0.0, "com_volume": 0})
            item["trechos"] += 1
            if row["extensao_km"]:
                item["extensao_km"] += float(row["extensao_km"])
            if tem_denominador(row["vmda_total"], row["classificacao"]):
                item["com_volume"] += 1
    return inventario


def gravar_e_imprimir(inventario: Dict[Tuple[str, int], Dict[str, float]], saida_path: pathlib.Path) -> None:
    linhas = [["br", "ano", "trechos", "extensao_km", "com_volume"]]
    for (br, ano) in sorted(inventario, key=lambda k: (k[0], k[1])):
        item = inventario[(br, ano)]
        linhas.append([
            br, str(ano), str(item["trechos"]),
            f"{item['extensao_km']:.3f}", str(item["com_volume"]),
        ])

    saida_path.parent.mkdir(parents=True, exist_ok=True)
    with open(saida_path, "w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(linhas)

    largura = {"br": 4, "ano": 6, "trechos": 8, "extensao_km": 14, "com_volume": 11}
    cabecalho = (
        f"{'br':<{largura['br']}}{'ano':<{largura['ano']}}{'trechos':>{largura['trechos']}}"
        f"{'extensao_km':>{largura['extensao_km']}}{'com_volume':>{largura['com_volume']}}"
    )
    print(cabecalho)
    for (br, ano) in sorted(inventario, key=lambda k: (k[0], k[1])):
        item = inventario[(br, ano)]
        print(
            f"{br:<{largura['br']}}{ano:<{largura['ano']}}{item['trechos']:>{largura['trechos']},d}"
            f"{item['extensao_km']:>{largura['extensao_km']},.3f}"
            f"{item['com_volume']:>{largura['com_volume']},d}"
        )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--serie", type=pathlib.Path, default=DEFAULT_SERIE)
    ap.add_argument("--saida", type=pathlib.Path, default=DEFAULT_SAIDA)
    args = ap.parse_args()

    if not args.serie.exists():
        raise SystemExit(f"ERRO: {args.serie} não existe — rode bin/extrai_pnct_vmda.py antes.")

    inventario = montar_inventario(args.serie)
    gravar_e_imprimir(inventario, args.saida)
    print(f"\nOK: {args.saida} gerado ({len(inventario)} linhas BR x ano).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
