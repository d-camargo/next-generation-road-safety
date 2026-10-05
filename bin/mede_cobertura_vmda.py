#!/usr/bin/env python3
"""Mede a cobertura espacial do VMDa (PNCT/DNIT) sobre os sinistros da PRF em MG.

Para cada ano de 2017 a 2025, cruza `geo.prf_acidentes_mg` (PostGIS) com
`bases/pnct-vmda/series/vmda_mg_por_trecho_2017_2025.csv` pela chave BR + km
(não pelo id do trecho — ver `bases/prf-acidentes/METODO-ESPACIAL.md`,
"A chave de junção é BR + km, não o id do trecho"), e imprime, por ano:

  1. sinistros da PRF em MG naquele ano (contagem bruta);
  2. quantos, dos sinistros SEM coordenada em grau inteiro (ver abaixo), caem
     dentro de uma faixa [km_inicial, km_final] de um trecho VMDa da MESMA BR
     naquele ano **que tem denominador utilizável** (`dentro_com_volume`);
  3. quantos caem dentro de uma faixa que existe mas não tem volume
     utilizável (`dentro_sem_volume`), e quantos não caem em faixa nenhuma
     (`fora_de_qualquer_faixa`) — ver "O defeito da medição antiga" abaixo;
  4. extensão total (km) coberta pelo VMDa naquele ano em MG, e a mesma
     extensão quebrada por jurisdição — `km_federal`, `km_indefinida`,
     `km_outras` (estadual + municipal) — ver "Jurisdição" abaixo;
  5. quantas BRs distintas aparecem nos sinistros e quantas no VMDa.

⚠️ **Jurisdição (2026-09-08):** a PRF policia só a malha federal, mas o VMDa
recente traz trecho estadual e municipal misturado (ver
`bases/prf-acidentes/METODO-ESPACIAL.md`, "Jurisdição: o denominador não
pode ser mais largo que o numerador"). `pct_sem_denominador` (coluna antiga,
mantida) não filtra por jurisdição — mede perda contra TODO trecho no VMDa,
federal ou não. `pct_sem_denominador_federal` (nova) mede a mesma perda
considerando denominador válido **só** faixa com `jurisdicao == 'federal'` e
`tem_denominador`. As duas ficam lado a lado de propósito: a diferença entre
elas é o tamanho do problema, não um número que substitui o outro.
`indefinida` (malha sem jurisdição declarada, ~9.400 km/ano em MG em 2018 e
2020) NUNCA conta como federal em `pct_sem_denominador_federal`.

⚠️ Normalização obrigatória nos dois lados, senão a medida sai errada em
silêncio: a PRF grava `br` como `'40'`, `'116'`, `'381'` — zero-padding para
3 dígitos; o VMDa já vem majoritariamente zero-padded, mas normaliza
incondicionalmente também (mesma função usada nas duas pontas). O `km` da
PRF é texto com VÍRGULA decimal (`'20,2'`) — `str.replace(',', '.')` antes de
`float()`.

⚠️ Exclui os 53 registros (na tabela inteira, 2017-2026) com coordenada em
grau inteiro (`lat_bruta` OU `lon_bruta` sem `.` nem `,` — precisão de
~100 km, já sabidamente fora do município que declaram) do denominador usado
nos itens 2/3 — são contados à parte e reportados, porque a junção por br+km
não usa a coordenada e por isso não muda com ou sem eles, mas eles têm que
sair do recorte pensando na análise espacial (que sim, usa a coordenada).

## O defeito da medição antiga (corrigido em 2026-09-08)

A versão anterior contava um sinistro como "dentro da cobertura" se ele caísse
em **qualquer** faixa de km do VMDa daquele ano — inclusive faixa **sem
estimativa de volume** (`vmda_total` vazio ou 0, ou `classificacao` em
`{'Não Simulável', 'Travessia - Não Simulável', 'Não Pavimentada'}`, que juntas
não têm volume utilizável). Isso superestimava a cobertura: cair na faixa não
significa ter denominador, que é a única coisa que interessa para uma taxa.

O viés é desigual entre anos, e por isso a tabela antiga sugeria variação
temporal que era artefato da medida: 2017 aparecia com a menor perda porque é
o único ano com `origem_km='oficial'` (faixas do trecho-pai do SNV, largura
média 21,4 km, que ladrilham a rodovia inteira por construção), enquanto os
demais usam `origem_km='estimado'` (sub-link, 14 a 19 km, com vãos entre
faixas) — comparar os dois `origem_km` é comparar medidas diferentes.

Um sinistro só conta como coberto (`dentro_com_volume`) quando cai numa faixa
que tem denominador:

    vmda_total > 0  E  classificacao NÃO em
      {'Não Simulável', 'Travessia - Não Simulável', 'Não Pavimentada'}

`pct_sem_denominador` = (`dentro_sem_volume` + `fora_de_qualquer_faixa`) /
`sinistros_considerados` — é esse o número que a análise precisa, não o
`pct_fora` antigo (que só contava `fora_de_qualquer_faixa`).

2021 não tem par de km no VMDa (`origem_km='indisponivel_2021'`) — nenhum
sinistro cai em faixa nenhuma nesse ano, por construção. **Isso é reportado
como indisponível, não "consertado"**: a coluna `origem_km` carrega a razão.

Saída: tabela impressa e `build/cobertura_vmda_mg.csv`.

Uso:
    python3 bin/mede_cobertura_vmda.py [--vmda-csv CAMINHO] [--dsn DSN] [--saida CAMINHO]
"""
from __future__ import annotations

import argparse
import csv
import pathlib
import sys
from typing import Dict, List, Optional, Tuple

import psycopg2
import psycopg2.extras

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin"))

from build_geo_prf import resolver_dsn  # noqa: E402 — mesma resolução de DSN

DEFAULT_VMDA_CSV = ROOT / "bases" / "pnct-vmda" / "series" / "vmda_mg_por_trecho_2017_2025.csv"
DEFAULT_SAIDA = ROOT / "build" / "cobertura_vmda_mg.csv"

ANOS = list(range(2017, 2026))


def normalizar_br(valor: str) -> str:
    """Mesma convenção de `bin/extrai_pnct_vmda.py::normalizar_br`: zero-pad
    a 3 dígitos só quando o valor é só dígitos."""
    s = str(valor).strip()
    return s.zfill(3) if s.isdigit() else s


def parse_km_prf(km_texto: str) -> Optional[float]:
    """`km` da PRF é texto com vírgula decimal ('20,2'). `.replace` simples,
    sem tentar adivinhar nada — mesma disciplina de `build_geo_prf.py::parse_coord`."""
    if km_texto is None:
        return None
    s = str(km_texto).strip()
    if not s:
        return None
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def eh_grau_inteiro(lat_bruta: Optional[str], lon_bruta: Optional[str]) -> bool:
    """lat_bruta OU lon_bruta sem '.' nem ',' — coordenada em grau inteiro
    (precisão de ~100 km)."""
    def sem_separador(v):
        v = (v or "").strip()
        return bool(v) and "." not in v and "," not in v
    return sem_separador(lat_bruta) or sem_separador(lon_bruta)


# Classificações sem volume utilizável mesmo quando `vmda_total` vier
# preenchido — ver "O defeito da medição antiga" no docstring do módulo.
CLASSIFICACOES_SEM_VOLUME = {"Não Simulável", "Travessia - Não Simulável", "Não Pavimentada"}


def tem_denominador(vmda_total: str, classificacao: str) -> bool:
    """`vmda_total > 0` E `classificacao` fora do conjunto sem volume
    utilizável — a regra do conserto (ver docstring do módulo)."""
    try:
        v = float(vmda_total) if vmda_total else 0.0
    except ValueError:
        v = 0.0
    return v > 0 and (classificacao or "").strip() not in CLASSIFICACOES_SEM_VOLUME


def carregar_faixas_vmda(
    vmda_csv: pathlib.Path, so_federal: bool = False
) -> Dict[int, Dict[str, List[Tuple[float, float, bool]]]]:
    """{ano -> {br -> [(km_min, km_max, tem_denominador), ...]}}, só das
    linhas com km_inicial E km_final preenchidos (2021 não tem nenhuma; um
    bloco de 2017 também não — ver FONTE.md da base).

    `so_federal=True` restringe às linhas com `jurisdicao == 'federal'` — é
    o denominador que a PRF de fato policia (ver METODO-ESPACIAL.md,
    "Jurisdição: o denominador não pode ser mais largo que o numerador").
    `indefinida` NUNCA entra nesse filtro por suposição."""
    faixas: Dict[int, Dict[str, List[Tuple[float, float, bool]]]] = {ano: {} for ano in ANOS}
    with open(vmda_csv, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ano = int(row["ano"])
            if ano not in faixas:
                continue
            if so_federal and row.get("jurisdicao") != "federal":
                continue
            ki, kf = row["km_inicial"], row["km_final"]
            if not ki or not kf:
                continue
            br = normalizar_br(row["br"])
            lo, hi = float(ki), float(kf)
            if lo > hi:
                lo, hi = hi, lo
            com_volume = tem_denominador(row["vmda_total"], row["classificacao"])
            faixas[ano].setdefault(br, []).append((lo, hi, com_volume))
    return faixas


def carregar_origem_km(vmda_csv: pathlib.Path) -> Dict[int, str]:
    """{ano -> origem_km}. Homogêneo dentro de cada ano nesta série (medido);
    se algum dia deixar de ser, junta os valores para não esconder o fato."""
    valores: Dict[int, set] = {ano: set() for ano in ANOS}
    with open(vmda_csv, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ano = int(row["ano"])
            if ano not in valores:
                continue
            valores[ano].add(row["origem_km"])
    return {ano: "+".join(sorted(v)) if v else "" for ano, v in valores.items()}


def carregar_extensao_e_brs_vmda(vmda_csv: pathlib.Path) -> Dict[int, Tuple[float, int, set]]:
    """{ano -> (extensao_total_km, linhas_sem_extensao, brs_distintos)}."""
    resultado: Dict[int, Tuple[float, int, set]] = {
        ano: [0.0, 0, set()] for ano in ANOS
    }
    with open(vmda_csv, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ano = int(row["ano"])
            if ano not in resultado:
                continue
            acc = resultado[ano]
            if row["extensao_km"]:
                acc[0] += float(row["extensao_km"])
            else:
                acc[1] += 1
            acc[2].add(normalizar_br(row["br"]))
    return {ano: (v[0], v[1], v[2]) for ano, v in resultado.items()}


def carregar_km_por_jurisdicao(vmda_csv: pathlib.Path) -> Dict[int, Dict[str, float]]:
    """{ano -> {'federal': km, 'indefinida': km, 'outras': km}}, somando
    `extensao_km` por `jurisdicao` (`outras` = estadual + municipal).
    `indefinida` fica separada, nunca somada a `federal` — ver
    `normalizar_jurisdicao` em `bin/extrai_pnct_vmda.py`."""
    resultado: Dict[int, Dict[str, float]] = {
        ano: {"federal": 0.0, "indefinida": 0.0, "outras": 0.0} for ano in ANOS
    }
    with open(vmda_csv, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ano = int(row["ano"])
            if ano not in resultado:
                continue
            if not row["extensao_km"]:
                continue
            km = float(row["extensao_km"])
            jurisdicao = row.get("jurisdicao", "indefinida")
            if jurisdicao == "federal":
                resultado[ano]["federal"] += km
            elif jurisdicao in ("estadual", "municipal"):
                resultado[ano]["outras"] += km
            else:
                resultado[ano]["indefinida"] += km
    return resultado


def status_cobertura(br: str, km: float, faixas_ano: Dict[str, List[Tuple[float, float, bool]]]) -> str:
    """'com_volume' se cair em alguma faixa com denominador utilizável;
    'sem_volume' se cair em faixa nenhuma (com denominador), mas em pelo
    menos uma sem; 'fora' se não cair em faixa nenhuma. Se o km cair em mais
    de uma faixa sobreposta, basta uma com volume para contar como coberto —
    há denominador disponível naquele ponto."""
    achou_sem_volume = False
    for lo, hi, com_volume in faixas_ano.get(br, ()):
        if lo <= km <= hi:
            if com_volume:
                return "com_volume"
            achou_sem_volume = True
    return "sem_volume" if achou_sem_volume else "fora"


def medir(vmda_csv: pathlib.Path, dsn: str) -> List[dict]:
    faixas = carregar_faixas_vmda(vmda_csv)
    faixas_federal = carregar_faixas_vmda(vmda_csv, so_federal=True)
    extensao_brs = carregar_extensao_e_brs_vmda(vmda_csv)
    origem_km = carregar_origem_km(vmda_csv)
    km_jurisdicao = carregar_km_por_jurisdicao(vmda_csv)

    con = psycopg2.connect(dsn)
    try:
        with con.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT ano, br, km, lat_bruta, lon_bruta FROM geo.prf_acidentes_mg")
            todas = cur.fetchall()
    finally:
        con.close()

    por_ano: Dict[int, list] = {ano: [] for ano in ANOS}
    for rec in todas:
        if rec["ano"] in por_ano:
            por_ano[rec["ano"]].append(rec)

    linhas = []
    for ano in ANOS:
        registros = por_ano[ano]
        sinistros_ano = len(registros)

        n_excluidos = 0
        dentro_com_volume = 0
        dentro_sem_volume = 0
        fora_de_qualquer_faixa = 0
        dentro_com_volume_federal = 0
        brs_sinistros = set()
        for r in registros:
            if eh_grau_inteiro(r["lat_bruta"], r["lon_bruta"]):
                n_excluidos += 1
                continue
            br = normalizar_br(r["br"])
            km = parse_km_prf(r["km"])
            brs_sinistros.add(br)
            status = status_cobertura(br, km, faixas.get(ano, {})) if km is not None else "fora"
            if status == "com_volume":
                dentro_com_volume += 1
            elif status == "sem_volume":
                dentro_sem_volume += 1
            else:
                fora_de_qualquer_faixa += 1

            status_federal = (
                status_cobertura(br, km, faixas_federal.get(ano, {})) if km is not None else "fora"
            )
            if status_federal == "com_volume":
                dentro_com_volume_federal += 1

        base = dentro_com_volume + dentro_sem_volume + fora_de_qualquer_faixa
        sem_denominador = dentro_sem_volume + fora_de_qualquer_faixa
        pct_sem_denominador = (sem_denominador / base * 100.0) if base else 0.0
        sem_denominador_federal = base - dentro_com_volume_federal
        pct_sem_denominador_federal = (sem_denominador_federal / base * 100.0) if base else 0.0
        ext_total, ext_sem, brs_vmda = extensao_brs[ano]
        km_jur = km_jurisdicao[ano]

        linhas.append({
            "ano": ano,
            "sinistros_ano": sinistros_ano,
            "excluidos_grau_inteiro": n_excluidos,
            "sinistros_considerados": base,
            "dentro_com_volume": dentro_com_volume,
            "dentro_sem_volume": dentro_sem_volume,
            "fora_de_qualquer_faixa": fora_de_qualquer_faixa,
            "pct_sem_denominador": round(pct_sem_denominador, 2),
            "pct_sem_denominador_federal": round(pct_sem_denominador_federal, 2),
            "origem_km": origem_km.get(ano, ""),
            "extensao_vmda_km": round(ext_total, 1),
            "km_federal": round(km_jur["federal"], 1),
            "km_indefinida": round(km_jur["indefinida"], 1),
            "km_outras": round(km_jur["outras"], 1),
            "trechos_vmda_sem_extensao": ext_sem,
            "brs_sinistros": len(brs_sinistros),
            "brs_vmda": len(brs_vmda),
        })

    return linhas


def imprimir_tabela(linhas: List[dict]) -> None:
    cols = [
        "ano", "sinistros_ano", "excluidos_grau_inteiro", "sinistros_considerados",
        "dentro_com_volume", "dentro_sem_volume", "fora_de_qualquer_faixa",
        "pct_sem_denominador", "pct_sem_denominador_federal", "origem_km",
        "extensao_vmda_km", "km_federal", "km_indefinida", "km_outras",
        "brs_sinistros", "brs_vmda",
    ]
    largura = {c: max(len(c), *(len(str(l[c])) for l in linhas)) for c in cols}
    cab = " | ".join(c.ljust(largura[c]) for c in cols)
    print(cab)
    print("-+-".join("-" * largura[c] for c in cols))
    for l in linhas:
        print(" | ".join(str(l[c]).ljust(largura[c]) for c in cols))

    total_excluidos = sum(l["excluidos_grau_inteiro"] for l in linhas)
    print(f"\nTotal de registros excluídos por coordenada em grau inteiro (2017-2025): {total_excluidos}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vmda-csv", type=pathlib.Path, default=DEFAULT_VMDA_CSV)
    ap.add_argument("--dsn", default=None)
    ap.add_argument("--saida", type=pathlib.Path, default=DEFAULT_SAIDA)
    args = ap.parse_args()

    dsn = resolver_dsn(args.dsn)
    linhas = medir(args.vmda_csv, dsn)

    imprimir_tabela(linhas)

    args.saida.parent.mkdir(parents=True, exist_ok=True)
    with open(args.saida, "w", newline="", encoding="utf-8") as f:
        campos = list(linhas[0].keys())
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows(linhas)
    print(f"\nOK: {args.saida} gravado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
