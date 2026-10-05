#!/usr/bin/env python3
"""Ingerir a PRF (Minas Gerais, 2017+) na tabela `geo.prf_acidentes_mg` do PostGIS.

O PostGIS é um ARTEFATO, exatamente como `build/dados.db` e como o schema
`dados` construído por `bin/build_pg.py` — nunca fonte de verdade. A fonte de
verdade continua sendo `raw/prf-acidentes/*.zip` (conferido por sha256 contra
`bases/prf-acidentes/manifest.json`) e este script versionado. Se o PostGIS e
o `raw/` discordarem algum dia, o `raw/` está certo e este script tem bug.

Este script **é dono de duas tabelas**: `geo.prf_acidentes_mg` (recorte MG,
inalterada por esta extensão) e `geo.prf_acidentes_corredores` (recorte
nacional dos dez corredores por veículo-km/dia — ver
`bases/prf-acidentes/METODO-ESPACIAL.md`, "A lógica foi invertida": BR-101,
116, 163, 153, 364, 381, 050, 376, 158, 135, todas as UFs, 2017-2025). Ele
cria o schema `geo` se ainda não existir (`CREATE SCHEMA IF NOT EXISTS geo`),
mas **NUNCA** o dropa — `bin/build_pg.py` também não toca em `geo`, e este
script segue a mesma regra. Só as duas tabelas próprias são dropadas e
recriadas a cada execução, cada uma pela sua própria função (`build` para
`prf_acidentes_mg`, `build_corredores` para `prf_acidentes_corredores`).

`geo.prf_acidentes_corredores` usa a caixa envolvente do BRASIL CONTINENTAL
(`LAT_MIN_BR`/`LAT_MAX_BR`/`LON_MIN_BR`/`LON_MAX_BR`), não a de MG — a de MG
rejeitaria qualquer ponto fora do estado, que é exatamente o recorte que essa
tabela precisa aceitar. Além da quarentena de coordenada (mesmos dois motivos
de `prf_acidentes_mg`, adaptado: `coord_ilegivel`/`fora_da_caixa_brasil`, em
`build/quarentena_geo_prf_corredores.csv`), há uma terceira exclusão só
nesta tabela: coordenada em **grau inteiro** (`lat_bruta`/`lon_bruta` sem "."
nem ",", ex. "-19" em vez de "-19,78561818" — precisão de ~100 km). Isso
passa no `parse_coord` e cai dentro da caixa, então não é pego pela
quarentena de coordenada; é contado e excluído à parte
(`total_grau_inteiro`), nunca misturado com `coord_ilegivel`/
`fora_da_caixa_brasil` — é um problema diferente (precisão, não legibilidade
nem geografia).

Reusa `bin/extrai_prf_acidentes.py:registros(ano)` — o leitor único da PRF,
que já aplica todas as guardas duras (sha256, encoding, layout, datas,
vocabulário, inteiros) e já emite `latitude`/`longitude` como string. Este
script não reimplementa nenhuma dessas guardas; ele só filtra (MG, >=2017),
converte coordenada e escreve no PostGIS.

Comportamento:

1. Uma safra por vez (2017..2026, na ordem do manifest), streaming — nunca
   materializa os ~89 mil registros do recorte em uma lista.
2. Filtra `uf == 'MG'` e `ano >= 2017`.
3. Converte `latitude`/`longitude` (string, separador decimal variável — ver
   `parse_coord`) e valida a caixa envolvente de MG (`dentro_de_mg`).
   Registro cuja coordenada não passa vai para quarentena
   (`build/quarentena_geo_prf_mg.csv`), nunca para o banco e nunca em
   silêncio.
4. Insere em lotes com `psycopg2.extras.execute_batch`.
5. Se a quarentena passar de 1% dos registros lidos, falha (exit != 0)
   dizendo o percentual — sinal de que o layout mudou, não de que o dado
   piorou sozinho.

Uso:
    python3 bin/build_geo_prf.py
"""
import argparse
import csv
import os
import pathlib
import sys

import psycopg2
import psycopg2.extras

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin"))

from extrai_prf_acidentes import registros  # noqa: E402

PG_ENV_PATH = pathlib.Path.home() / ".config" / "dados" / "pg.env"
DEFAULT_MANIFEST_PATH = ROOT / "bases" / "prf-acidentes" / "manifest.json"
DEFAULT_QUARENTENA_PATH = ROOT / "build" / "quarentena_geo_prf_mg.csv"
DEFAULT_QUARENTENA_CORREDORES_PATH = ROOT / "build" / "quarentena_geo_prf_corredores.csv"
DEFAULT_INVENTARIO_CORREDORES_PATH = ROOT / "build" / "inventario_corredores.csv"

ANO_MIN = 2017
UF_ALVO = "MG"

#: Recorte nacional: dez corredores (BR) x TODAS as UFs x 2017-2025 — mesmos
#: anos do recorte VMDa (bin/extrai_pnct_vmda.py), não o ANO_MIN em diante
#: sem teto que a tabela MG usa.
ANO_MIN_CORREDORES = 2017
ANO_MAX_CORREDORES = 2025

#: Os dez corredores federais por veículo-km/dia medidos em 2024 — mesma
#: lista de `bin/extrai_pnct_vmda.py::BRS_CORREDORES`, ver
#: `bases/prf-acidentes/METODO-ESPACIAL.md`, "A lógica foi invertida".
BRS_CORREDORES = (
    "101", "116", "163", "153", "364", "381", "050", "376", "158", "135",
)

#: Caixa envolvente de Minas Gerais COM FOLGA — não é a fronteira real do
#: estado (isso exigiria a malha municipal do IBGE, que este repo ainda não
#: tem). Serve só para pegar coordenada visivelmente errada (grau inteiro,
#: separador perdido, sinal/hemisfério trocado), não para validar geografia.
LAT_MIN_MG = -23.2
LAT_MAX_MG = -14.0
LON_MIN_MG = -51.3
LON_MAX_MG = -39.6

#: Caixa envolvente do BRASIL CONTINENTAL COM FOLGA — não é a fronteira real
#: do país (isso exigiria a malha do IBGE), e é maior que a caixa de MG
#: acima: usada só por `geo.prf_acidentes_corredores` (recorte nacional),
#: nunca por `geo.prf_acidentes_mg`. Serve para pegar coordenada visivelmente
#: errada (sinal/hemisfério trocado, separador perdido), não para validar
#: geografia fina.
LAT_MIN_BR = -34.0
LAT_MAX_BR = 5.5
LON_MIN_BR = -74.0
LON_MAX_BR = -34.0

COLUNAS_TABELA = [
    "id", "ano", "data_inversa", "horario", "uf", "br", "km", "municipio",
    "causa_acidente", "tipo_acidente", "classificacao_acidente", "fase_dia",
    "condicao_metereologica", "tipo_pista", "tracado_via", "uso_solo",
    "pessoas", "mortos", "feridos_leves", "feridos_graves", "ilesos",
    "veiculos", "lat_bruta", "lon_bruta",
]

DDL = """
CREATE SCHEMA IF NOT EXISTS geo;

DROP TABLE IF EXISTS geo.prf_acidentes_mg;

CREATE TABLE geo.prf_acidentes_mg (
    id text,
    ano integer NOT NULL,
    data_inversa text,
    horario text,
    uf text,
    br text,
    km text,
    municipio text,
    causa_acidente text,
    tipo_acidente text,
    classificacao_acidente text,
    fase_dia text,
    condicao_metereologica text,
    tipo_pista text,
    tracado_via text,
    uso_solo text,
    pessoas integer,
    mortos integer,
    feridos_leves integer,
    feridos_graves integer,
    ilesos integer,
    veiculos integer,
    lat_bruta text,
    lon_bruta text,
    geom geometry(Point, 4326)
);

CREATE INDEX ON geo.prf_acidentes_mg USING GIST (geom);
CREATE INDEX ON geo.prf_acidentes_mg (ano);
"""

SQL_INSERT = f"""
INSERT INTO geo.prf_acidentes_mg (
    {', '.join(COLUNAS_TABELA)}, geom
) VALUES (
    {', '.join(['%s'] * len(COLUNAS_TABELA))},
    ST_SetSRID(ST_MakePoint(%s, %s), 4326)
)
"""

#: Mesmas colunas de geo.prf_acidentes_mg (ver COLUNAS_TABELA acima) —
#: `geo.prf_acidentes_corredores` é a tabela irmã do recorte nacional.
DDL_CORREDORES = """
CREATE SCHEMA IF NOT EXISTS geo;

DROP TABLE IF EXISTS geo.prf_acidentes_corredores;

CREATE TABLE geo.prf_acidentes_corredores (
    id text,
    ano integer NOT NULL,
    data_inversa text,
    horario text,
    uf text,
    br text,
    km text,
    municipio text,
    causa_acidente text,
    tipo_acidente text,
    classificacao_acidente text,
    fase_dia text,
    condicao_metereologica text,
    tipo_pista text,
    tracado_via text,
    uso_solo text,
    pessoas integer,
    mortos integer,
    feridos_leves integer,
    feridos_graves integer,
    ilesos integer,
    veiculos integer,
    lat_bruta text,
    lon_bruta text,
    geom geometry(Point, 4326)
);

CREATE INDEX ON geo.prf_acidentes_corredores USING GIST (geom);
CREATE INDEX ON geo.prf_acidentes_corredores (ano);
CREATE INDEX ON geo.prf_acidentes_corredores (br);
"""

SQL_INSERT_CORREDORES = f"""
INSERT INTO geo.prf_acidentes_corredores (
    {', '.join(COLUNAS_TABELA)}, geom
) VALUES (
    {', '.join(['%s'] * len(COLUNAS_TABELA))},
    ST_SetSRID(ST_MakePoint(%s, %s), 4326)
)
"""


def parse_coord(texto: str) -> float | None:
    """Converte uma string de coordenada da PRF para float.

    `strip`, remove aspas, troca ',' por '.' (o separador decimal muda de
    safra: ponto em 2024, vírgula nas outras nove — um `.replace(",", ".")`
    simples cobre as duas formas), e converte com `float()`.

    Não tenta "corrigir" nada: uma coordenada com separador perdido
    (ex.: "-19843262") vira um número absurdo e falha depois na caixa de
    `dentro_de_mg`, não aqui. Falhou o parse em si (string vazia, não
    numérica) → `None`.
    """
    if texto is None:
        return None
    s = texto.strip().strip('"').strip("'")
    if not s:
        return None
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def dentro_de_mg(lat: float, lon: float) -> bool:
    """Caixa envolvente de MG com folga (ver constantes no topo do módulo).

    Não é a fronteira real do estado — é só um filtro grosseiro contra
    coordenada visivelmente errada.
    """
    return LAT_MIN_MG <= lat <= LAT_MAX_MG and LON_MIN_MG <= lon <= LON_MAX_MG


def dentro_do_brasil(lat: float, lon: float) -> bool:
    """Caixa envolvente do Brasil continental com folga (ver constantes no
    topo do módulo). Usada só pelo recorte nacional (`prf_acidentes_corredores`);
    não é a fronteira real do país — é só um filtro grosseiro contra
    coordenada visivelmente errada."""
    return LAT_MIN_BR <= lat <= LAT_MAX_BR and LON_MIN_BR <= lon <= LON_MAX_BR


def eh_grau_inteiro(texto: str) -> bool:
    """True se a coordenada bruta não tem NENHUM separador decimal ('.' nem
    ',') — ex.: '-19' em vez de '-19,78561818'. Precisão de grau inteiro é
    ~100 km: passa no `parse_coord` (`float('-19')` funciona) e cai dentro
    da caixa envolvente, então NÃO é pego pela quarentena de coordenada.
    É um problema diferente (precisão, não legibilidade nem geografia) —
    por isso é contado e excluído à parte, nunca misturado com
    `coord_ilegivel`/`fora_da_caixa_brasil`. String vazia ou None não conta
    (isso já vira `coord_ilegivel` via `parse_coord`)."""
    if texto is None:
        return False
    s = texto.strip().strip('"').strip("'")
    if not s:
        return False
    return "." not in s and "," not in s


def normalizar_br(valor: str) -> str:
    """Mesma convenção de `bin/extrai_pnct_vmda.py::normalizar_br` e
    `bin/mede_cobertura_vmda.py::normalizar_br`: zero-pad a 3 dígitos só
    quando o valor é só dígitos — a PRF grava `br` como '40', '116', '381'
    (sem padding). Usada só para CASAR contra `BRS_CORREDORES`; o valor
    gravado na tabela continua o bruto (mesma coluna `br` de
    `geo.prf_acidentes_mg`, sem normalização — MG nunca precisou disso)."""
    s = str(valor).strip().strip('"')
    return s.zfill(3) if s.isdigit() else s


def resolver_dsn(dsn_cli: str | None = None) -> str:
    """Mesma resolução de bin/build_pg.py: --dsn > DADOS_PG_DSN do ambiente > pg.env."""
    if dsn_cli:
        return dsn_cli
    dsn_env = os.environ.get("DADOS_PG_DSN")
    if dsn_env:
        return dsn_env
    if not PG_ENV_PATH.exists():
        raise SystemExit(
            f"Sem DSN do PostGIS: variável de ambiente DADOS_PG_DSN não está "
            f"definida, e o arquivo de credenciais não existe em "
            f"{PG_ENV_PATH}. Crie esse arquivo (chmod 600) com as chaves "
            f"PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE/DADOS_PG_DSN."
        )
    valores = {}
    for linha in PG_ENV_PATH.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#"):
            continue
        chave, _, valor = linha.partition("=")
        valores[chave.strip()] = valor.strip()
    dsn = valores.get("DADOS_PG_DSN")
    if not dsn:
        raise SystemExit(f"{PG_ENV_PATH} existe mas não tem a chave DADOS_PG_DSN.")
    return dsn


def _linha_para_tabela(rec: dict) -> tuple:
    return tuple(rec.get(col) for col in COLUNAS_TABELA)


def build(
    dsn: str,
    manifest_path: pathlib.Path,
    quarentena_path: pathlib.Path,
    raw_dir: pathlib.Path | None = None,
) -> None:
    import json

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    anos = sorted(
        item["ano"] for item in manifest.get("arquivos", []) if item["ano"] >= ANO_MIN
    )
    if not anos:
        raise SystemExit(f"ERRO: nenhuma safra >= {ANO_MIN} em {manifest_path}")

    try:
        pg_con = psycopg2.connect(dsn)
    except psycopg2.OperationalError as exc:
        raise SystemExit(f"Não foi possível conectar ao PostGIS com o DSN resolvido: {exc}")

    quarentena_path.parent.mkdir(parents=True, exist_ok=True)

    total_lidos = 0
    total_inseridos = 0
    motivos_quarentena: dict = {}

    try:
        pg_con.autocommit = False
        with pg_con.cursor() as cur:
            cur.execute(DDL)

            with open(quarentena_path, "w", encoding="utf-8", newline="") as qf:
                colunas_quarentena = None
                qwriter = None
                lote: list = []

                for ano in anos:
                    for rec in registros(ano, raw_dir=raw_dir, manifest_path=manifest_path):
                        if rec["uf"] != UF_ALVO:
                            continue
                        total_lidos += 1

                        lat_bruta = rec.get("latitude", "")
                        lon_bruta = rec.get("longitude", "")
                        lat = parse_coord(lat_bruta)
                        lon = parse_coord(lon_bruta)

                        motivo = None
                        if lat is None or lon is None:
                            motivo = "coord_ilegivel"
                        elif not dentro_de_mg(lat, lon):
                            motivo = "fora_da_caixa_mg"

                        if motivo is not None:
                            motivos_quarentena[motivo] = motivos_quarentena.get(motivo, 0) + 1
                            linha_q = dict(rec)
                            linha_q["motivo"] = motivo
                            if qwriter is None:
                                colunas_quarentena = list(linha_q.keys())
                                qwriter = csv.DictWriter(qf, fieldnames=colunas_quarentena)
                                qwriter.writeheader()
                            qwriter.writerow(linha_q)
                            continue

                        rec_tabela = dict(rec)
                        rec_tabela["lat_bruta"] = lat_bruta
                        rec_tabela["lon_bruta"] = lon_bruta
                        linha = _linha_para_tabela(rec_tabela) + (lon, lat)
                        lote.append(linha)
                        total_inseridos += 1

                        if len(lote) >= 5000:
                            psycopg2.extras.execute_batch(cur, SQL_INSERT, lote, page_size=1000)
                            lote.clear()

                if lote:
                    psycopg2.extras.execute_batch(cur, SQL_INSERT, lote, page_size=1000)

        pg_con.commit()
    except Exception:
        pg_con.rollback()
        raise
    finally:
        pg_con.close()

    total_quarentena = sum(motivos_quarentena.values())
    pct_quarentena = (total_quarentena / total_lidos * 100.0) if total_lidos else 0.0

    print(f"OK: geo.prf_acidentes_mg = {total_inseridos} linhas inseridas (lidos: {total_lidos})")
    for motivo in sorted(motivos_quarentena):
        print(f"  quarentena[{motivo}] = {motivos_quarentena[motivo]}")
    print(f"  quarentena total = {total_quarentena} ({pct_quarentena:.4f}% dos lidos)")

    if pct_quarentena > 1.0:
        raise SystemExit(
            f"ERRO: quarentena de coordenada passou de 1% dos registros lidos "
            f"({pct_quarentena:.4f}%, {total_quarentena}/{total_lidos}) — o "
            f"layout pode ter mudado, isto precisa de revisão humana antes de "
            f"seguir."
        )


def build_corredores(
    dsn: str,
    manifest_path: pathlib.Path,
    quarentena_path: pathlib.Path,
    inventario_path: pathlib.Path,
    raw_dir: pathlib.Path | None = None,
) -> None:
    """Ingere `geo.prf_acidentes_corredores`: as dez BRs de BRS_CORREDORES,
    todas as UFs, 2017-2025 (ANO_MIN_CORREDORES..ANO_MAX_CORREDORES) —
    streaming, uma safra por vez, reusando o mesmo leitor único
    `extrai_prf_acidentes.registros(ano)` de `build()`. Nunca toca em
    `geo.prf_acidentes_mg` nem no schema `geo` inteiro (só
    `CREATE SCHEMA IF NOT EXISTS`, nunca DROP)."""
    import json

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    anos = sorted(
        item["ano"]
        for item in manifest.get("arquivos", [])
        if ANO_MIN_CORREDORES <= item["ano"] <= ANO_MAX_CORREDORES
    )
    if not anos:
        raise SystemExit(
            f"ERRO: nenhuma safra em [{ANO_MIN_CORREDORES}, {ANO_MAX_CORREDORES}] em {manifest_path}"
        )

    try:
        pg_con = psycopg2.connect(dsn)
    except psycopg2.OperationalError as exc:
        raise SystemExit(f"Não foi possível conectar ao PostGIS com o DSN resolvido: {exc}")

    quarentena_path.parent.mkdir(parents=True, exist_ok=True)
    inventario_path.parent.mkdir(parents=True, exist_ok=True)

    total_lidos = 0
    total_inseridos = 0
    total_grau_inteiro = 0
    motivos_quarentena: dict = {}
    por_br_ano: dict = {}  # (br, ano) -> sinistros ingeridos
    por_ano: dict = {}  # ano -> sinistros ingeridos (todas as BRs)
    ufs_por_br: dict = {}  # br -> set de UFs vistas (independe de quarentena)

    try:
        pg_con.autocommit = False
        with pg_con.cursor() as cur:
            cur.execute(DDL_CORREDORES)

            with open(quarentena_path, "w", encoding="utf-8", newline="") as qf:
                colunas_quarentena = None
                qwriter = None
                lote: list = []

                for ano in anos:
                    for rec in registros(ano, raw_dir=raw_dir, manifest_path=manifest_path):
                        br = normalizar_br(rec["br"])
                        if br not in BRS_CORREDORES:
                            continue
                        total_lidos += 1
                        ufs_por_br.setdefault(br, set()).add(rec["uf"])

                        lat_bruta = rec.get("latitude", "")
                        lon_bruta = rec.get("longitude", "")

                        if eh_grau_inteiro(lat_bruta) or eh_grau_inteiro(lon_bruta):
                            total_grau_inteiro += 1
                            continue

                        lat = parse_coord(lat_bruta)
                        lon = parse_coord(lon_bruta)

                        motivo = None
                        if lat is None or lon is None:
                            motivo = "coord_ilegivel"
                        elif not dentro_do_brasil(lat, lon):
                            motivo = "fora_da_caixa_brasil"

                        if motivo is not None:
                            motivos_quarentena[motivo] = motivos_quarentena.get(motivo, 0) + 1
                            linha_q = dict(rec)
                            linha_q["motivo"] = motivo
                            if qwriter is None:
                                colunas_quarentena = list(linha_q.keys())
                                qwriter = csv.DictWriter(qf, fieldnames=colunas_quarentena)
                                qwriter.writeheader()
                            qwriter.writerow(linha_q)
                            continue

                        rec_tabela = dict(rec)
                        rec_tabela["lat_bruta"] = lat_bruta
                        rec_tabela["lon_bruta"] = lon_bruta
                        linha = _linha_para_tabela(rec_tabela) + (lon, lat)
                        lote.append(linha)
                        total_inseridos += 1
                        por_br_ano[(br, ano)] = por_br_ano.get((br, ano), 0) + 1
                        por_ano[ano] = por_ano.get(ano, 0) + 1

                        if len(lote) >= 5000:
                            psycopg2.extras.execute_batch(cur, SQL_INSERT_CORREDORES, lote, page_size=1000)
                            lote.clear()

                if lote:
                    psycopg2.extras.execute_batch(cur, SQL_INSERT_CORREDORES, lote, page_size=1000)

        pg_con.commit()
    except Exception:
        pg_con.rollback()
        raise
    finally:
        pg_con.close()

    total_quarentena = sum(motivos_quarentena.values())
    pct_quarentena = (total_quarentena / total_lidos * 100.0) if total_lidos else 0.0

    print(
        f"OK: geo.prf_acidentes_corredores = {total_inseridos} linhas inseridas "
        f"(lidos: {total_lidos})"
    )
    for motivo in sorted(motivos_quarentena):
        print(f"  quarentena[{motivo}] = {motivos_quarentena[motivo]}")
    print(f"  quarentena total = {total_quarentena} ({pct_quarentena:.4f}% dos lidos)")
    print(f"  grau_inteiro excluído (à parte, não é quarentena) = {total_grau_inteiro}")

    # -- inventário: build/inventario_corredores.csv -----------------------
    colunas_inventario = ["tipo", "br", "ano", "motivo", "valor", "detalhe"]
    linhas_inventario = [colunas_inventario]

    print("Sinistros ingeridos por BR e por ano:")
    for br in BRS_CORREDORES:
        for ano in anos:
            n = por_br_ano.get((br, ano), 0)
            linhas_inventario.append(["sinistros_ingeridos", br, str(ano), "", str(n), ""])
        total_br = sum(por_br_ano.get((br, ano), 0) for ano in anos)
        print(f"  BR-{br}: {total_br} sinistros ingeridos (2017-2025)")

    print("Total ingerido por ano (todas as BRs):")
    for ano in anos:
        n = por_ano.get(ano, 0)
        linhas_inventario.append(["total_ano", "", str(ano), "", str(n), ""])
        print(f"  {ano}: {n}")

    for motivo in sorted(motivos_quarentena):
        linhas_inventario.append(["quarentena", "", "", motivo, str(motivos_quarentena[motivo]), ""])

    linhas_inventario.append(["grau_inteiro_excluido", "", "", "", str(total_grau_inteiro), ""])

    print("UFs atravessadas por corredor:")
    for br in BRS_CORREDORES:
        ufs = sorted(ufs_por_br.get(br, set()))
        linhas_inventario.append(["ufs_atravessadas", br, "", "", str(len(ufs)), ",".join(ufs)])
        print(f"  BR-{br}: {len(ufs)} UFs ({','.join(ufs)})")

    with open(inventario_path, "w", encoding="utf-8", newline="") as invf:
        csv.writer(invf).writerows(linhas_inventario)
    print(f"OK: inventário gravado em {inventario_path}")

    if pct_quarentena > 1.0:
        raise SystemExit(
            f"ERRO: quarentena de coordenada (geo.prf_acidentes_corredores) passou "
            f"de 1% dos registros lidos ({pct_quarentena:.4f}%, "
            f"{total_quarentena}/{total_lidos}) — o layout pode ter mudado, isto "
            f"precisa de revisão humana antes de seguir."
        )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dsn", default=None, help="DSN do PostGIS (sobrepõe env e pg.env)")
    ap.add_argument("--manifest", type=pathlib.Path, default=DEFAULT_MANIFEST_PATH)
    ap.add_argument("--raw-dir", type=pathlib.Path, default=None)
    ap.add_argument("--quarentena", type=pathlib.Path, default=DEFAULT_QUARENTENA_PATH)
    ap.add_argument(
        "--quarentena-corredores", type=pathlib.Path, default=DEFAULT_QUARENTENA_CORREDORES_PATH
    )
    ap.add_argument("--inventario", type=pathlib.Path, default=DEFAULT_INVENTARIO_CORREDORES_PATH)
    args = ap.parse_args()

    dsn = resolver_dsn(args.dsn)
    build(dsn, args.manifest, args.quarentena, raw_dir=args.raw_dir)
    build_corredores(
        dsn, args.manifest, args.quarentena_corredores, args.inventario, raw_dir=args.raw_dir
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
