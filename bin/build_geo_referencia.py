#!/usr/bin/env python3
"""Carrega as camadas de referência geoespacial (malha municipal + SNV) no PostGIS.

Duas fontes, endpoints verificados em 2026-09-07:

1. **Malha municipal de MG (IBGE via IPEA/geobr)** — GPKG legacy v1.7.0. A
   URL de download é resolvida a partir do metadado
   `https://www.ipea.gov.br/geobr/metadata/metadata_1.7.0_gpkg.csv` (a mesma
   cadeia que o plugin `gisbr` usa, ver `gisbr/core/constants.py` em
   `~/projects/gisbr`), filtrando `geo=municipality`, `year=2024`,
   `code=31` (MG), não-simplificado.
2. **SNV do DNIT** — WFS `https://geoservicos.inde.gov.br/geoserver/DNIT/ows`,
   `typeName=DNIT:snv_202507a`, filtrado NA ORIGEM por `CQL_FILTER=sg_uf='MG'`
   (945 trechos em MG contra 7.626 no Brasil inteiro, medido em 2026-09-07) —
   nunca baixa o país inteiro para filtrar depois.

O PostGIS é um ARTEFATO, exatamente como em `bin/build_geo_prf.py`: a fonte
de verdade é `raw/geo-referencia/*` (sha256 conferido contra
`raw/geo-referencia/manifest.json`) mais este script. Se o PostGIS e o `raw/`
discordarem, o `raw/` está certo e este script tem bug.

Este script **é dono de duas tabelas só**: `geo.municipios_mg` e
`geo.dnit_snv_mg`. Cria o schema `geo` se ainda não existir, mas **NUNCA** o
dropa. Só essas duas tabelas são dropadas e recriadas a cada execução.

Guardas duras (erro, nunca aviso):
  - download idempotente com sha256 no manifest; hash divergente da fonte é
    erro duro (ver `baixar_idempotente`);
  - `geo.municipios_mg` tem que ter exatamente 853 linhas (contagem do IBGE
    para MG, estável desde 1997);
  - `geo.dnit_snv_mg` tem mais de zero linhas e **todas** com `sg_uf='MG'`
    (confere depois do filtro CQL — filtro de servidor que não filtra de
    verdade é modo de falha conhecido);
  - geometrias inválidas (`ST_IsValid`) são contadas e falham o build; NÃO
    são consertadas com `ST_MakeValid` por conta própria (mudaria área e
    vizinhança sem decisão humana);
  - SRID gravado em `geometry_columns` tem que ser 4326 nas duas tabelas.

`geopandas`/`shapely` só são importados dentro das funções que carregam
geometria (`carregar_municipios`, `carregar_snv`, `build`) — as funções puras
de montagem de URL (`montar_url_snv_mg`, `resolver_url_gpkg_municipio_mg`) e
de download não dependem deles, para que a parte "sem banco" da suíte rode
com o `python3` do sistema (sem o venv `~/.venvs/geo`).

Uso:
    ~/.venvs/geo/bin/python bin/build_geo_referencia.py
"""
import argparse
import csv
import hashlib
import io
import json
import pathlib
import sys
from datetime import datetime, timezone
from urllib.parse import urlencode

import psycopg2
import psycopg2.extras
import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin"))

from build_geo_prf import resolver_dsn  # noqa: E402 — mesma resolução de DSN

RAW_DIR = ROOT / "raw" / "geo-referencia"
DEFAULT_MANIFEST_PATH = RAW_DIR / "manifest.json"

# --- Fonte 1: malha municipal (IBGE via IPEA/geobr, GPKG legacy v1.7.0) ----

GEOBR_METADATA_URL = "https://www.ipea.gov.br/geobr/metadata/metadata_1.7.0_gpkg.csv"
GEOBR_GEO = "municipality"
GEOBR_ANO = "2024"
GEOBR_CODE_UF = "31"  # Minas Gerais

# --- Fonte 2: SNV do DNIT (WFS via geoservicos.inde.gov.br) ----------------

WFS_ENDPOINT = "https://geoservicos.inde.gov.br/geoserver/DNIT/ows"
WFS_TYPE_NAME = "DNIT:snv_202507a"
WFS_SRS = "EPSG:4674"

UF_ALVO = "MG"

#: Contagem de municípios de MG — estável desde 1997. Divergir significa que
#: a malha mudou (fusão/criação de município) ou o download veio truncado.
MUNICIPIOS_MG_ESPERADO = 853

DDL = """
CREATE SCHEMA IF NOT EXISTS geo;

DROP TABLE IF EXISTS geo.municipios_mg;
CREATE TABLE geo.municipios_mg (
    code_muni integer PRIMARY KEY,
    name_muni text NOT NULL,
    geom geometry(MultiPolygon, 4326) NOT NULL
);
CREATE INDEX ON geo.municipios_mg USING GIST (geom);

DROP TABLE IF EXISTS geo.dnit_snv_mg;
CREATE TABLE geo.dnit_snv_mg (
    vl_br text,
    ds_jurisdi text,
    vl_extensa double precision,
    ds_superfi text,
    geom geometry(MultiLineString, 4326) NOT NULL
);
CREATE INDEX ON geo.dnit_snv_mg USING GIST (geom);
"""


def montar_url_snv_mg() -> str:
    """URL do WFS GetFeature do SNV, filtrada NA ORIGEM por `sg_uf='MG'`.

    O filtro é `CQL_FILTER`, aplicado pelo próprio GeoServer — a
    alternativa (baixar o Brasil inteiro e filtrar depois) traria os 7.626
    trechos nacionais em vez dos 945 de MG (medido em 2026-09-07).
    """
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeName": WFS_TYPE_NAME,
        "outputFormat": "application/json",
        "srsName": WFS_SRS,
        "CQL_FILTER": f"sg_uf='{UF_ALVO}'",
    }
    return f"{WFS_ENDPOINT}?{urlencode(params)}"


def resolver_url_gpkg_municipio_mg(metadata_csv_texto: str) -> str:
    """Resolve, a partir do TEXTO do metadado v1.7.0 do geobr, a URL do GPKG
    de municípios de MG em 2024 (não-simplificado).

    Recebe o texto (não a URL) de propósito, para ser testável sem rede —
    quem baixa o metadado de verdade é `baixar_fontes()`, abaixo. Colunas do
    CSV confirmadas em 2026-09-07: `geo,year,code,download_path,code_abbrev`.
    """
    leitor = csv.DictReader(io.StringIO(metadata_csv_texto))
    candidatos = [
        linha
        for linha in leitor
        if linha.get("geo") == GEOBR_GEO
        and linha.get("year") == GEOBR_ANO
        and linha.get("code") == GEOBR_CODE_UF
        and "simplified" not in (linha.get("download_path") or "")
    ]
    if len(candidatos) != 1:
        raise SystemExit(
            f"ERRO: esperava exatamente 1 linha no metadado do geobr para "
            f"geo={GEOBR_GEO!r} year={GEOBR_ANO!r} code={GEOBR_CODE_UF!r} "
            f"não-simplificada; encontrei {len(candidatos)}. O layout do "
            f"metadado pode ter mudado — não adivinhe, confira manualmente."
        )
    return candidatos[0]["download_path"]


def sha256_of(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _ler_manifest(manifest_path: pathlib.Path) -> dict:
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"slug": "geo-referencia", "arquivos": {}}


def _gravar_manifest(manifest_path: pathlib.Path, manifest: dict) -> None:
    """Escrita atômica (tmp + replace), mesma disciplina de candidatas.json."""
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = manifest_path.with_name(manifest_path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    tmp.replace(manifest_path)


def baixar_idempotente(
    url: str,
    destino: pathlib.Path,
    manifest: dict,
    chave: str,
    metadata_extra: dict | None = None,
    timeout: int = 120,
) -> None:
    """Baixa `url` para `destino`, registrando `url`/`sha256`/`baixado_em` em
    `manifest["arquivos"][chave]` (mutado in-place; quem grava em disco é o
    chamador, via `_gravar_manifest`).

    Idempotente: se `destino` já existe e o sha256 bate com o valor gravado
    no manifest para `chave`, NÃO baixa de novo. Senão (arquivo ausente, ou
    presente mas com hash divergente do manifest), baixa — e se o hash
    recém-baixado divergir do que já estava gravado no manifest para essa
    chave, é ERRO DURO (a fonte mudou embaixo do pé sem ninguém decidir isso
    conscientemente; a mensagem cita os dois hashes). Sem registro anterior
    no manifest (primeiro download), o hash recém-baixado vira a baseline.
    """
    registro_anterior = manifest.get("arquivos", {}).get(chave)
    sha_esperado = registro_anterior.get("sha256") if registro_anterior else None

    if destino.exists() and sha_esperado is not None:
        sha_local = sha256_of(destino)
        if sha_local == sha_esperado:
            print(f"OK (cache): {chave} já em disco, sha256 confere com o manifest ({sha_local}).")
            return
        print(
            f"AVISO: {chave} em disco não bate com o manifest "
            f"(esperado {sha_esperado}, encontrado {sha_local}) — baixando de novo para confirmar."
        )

    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_name(destino.name + ".tmp")
    with requests.get(url, stream=True, timeout=timeout) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
    sha_novo = sha256_of(tmp)

    if sha_esperado is not None and sha_novo != sha_esperado:
        tmp.unlink(missing_ok=True)
        raise SystemExit(
            f"ERRO DURO: {chave} mudou na fonte sem aviso — hash gravado no "
            f"manifest é {sha_esperado}, hash baixado agora é {sha_novo} "
            f"(url: {url}). É exatamente isso que a proveniência existe "
            f"para pegar; não sobrescrevo o manifest sozinho — revise a "
            f"mudança antes de aceitar o novo hash."
        )

    tmp.replace(destino)
    try:
        arquivo_local = str(destino.relative_to(ROOT))
    except ValueError:
        # destino fora da árvore do repo (ex.: tmp_path de teste) — grava o
        # caminho absoluto em vez de forçar uma relação que não existe.
        arquivo_local = str(destino)
    manifest.setdefault("arquivos", {})[chave] = {
        "url": url,
        "arquivo_local": arquivo_local,
        "sha256": sha_novo,
        "baixado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **(metadata_extra or {}),
    }
    print(f"OK (baixado): {chave} -> {destino} sha256={sha_novo}")


def baixar_fontes(
    manifest_path: pathlib.Path = DEFAULT_MANIFEST_PATH,
    raw_dir: pathlib.Path = RAW_DIR,
) -> tuple[pathlib.Path, pathlib.Path]:
    """Garante os dois brutos em `raw_dir`, atualiza e grava o manifest.

    Retorna (caminho_gpkg_municipios, caminho_geojson_snv).
    """
    manifest = _ler_manifest(manifest_path)

    resp = requests.get(GEOBR_METADATA_URL, timeout=60)
    resp.raise_for_status()
    url_gpkg = resolver_url_gpkg_municipio_mg(resp.text)
    gpkg_local = raw_dir / pathlib.Path(url_gpkg).name
    baixar_idempotente(
        url_gpkg,
        gpkg_local,
        manifest,
        "municipios_mg_2024",
        metadata_extra={
            "fonte": "IBGE via IPEA/geobr (metadata v1.7.0, GPKG legacy)",
            "geo": GEOBR_GEO,
            "ano": GEOBR_ANO,
            "code_uf": GEOBR_CODE_UF,
        },
    )

    url_snv = montar_url_snv_mg()
    snv_local = raw_dir / "dnit_snv_mg_202507a.geojson"
    baixar_idempotente(
        url_snv,
        snv_local,
        manifest,
        "dnit_snv_mg",
        metadata_extra={
            "fonte": "DNIT/SNV via WFS INDE (geoservicos.inde.gov.br)",
            "type_name": WFS_TYPE_NAME,
            "versao_snv": "202507a",
        },
    )

    _gravar_manifest(manifest_path, manifest)
    return gpkg_local, snv_local


def carregar_municipios(cur, gpkg_path: pathlib.Path) -> int:
    """Lê o GPKG de municípios, valida e insere em `geo.municipios_mg`.

    Precisa do venv `~/.venvs/geo` (geopandas/shapely) — import lazy.
    """
    import geopandas as gpd
    from shapely.geometry import MultiPolygon

    gdf = gpd.read_file(gpkg_path)
    if gdf.crs is None:
        raise SystemExit(f"ERRO: {gpkg_path} não tem CRS definido — não dá para confiar no ST_Transform.")
    gdf = gdf.to_crs(4326)

    n = len(gdf)
    if n != MUNICIPIOS_MG_ESPERADO:
        raise SystemExit(
            f"ERRO: geo.municipios_mg teria {n} município(s), esperado "
            f"{MUNICIPIOS_MG_ESPERADO} (contagem do IBGE para MG, estável "
            f"desde 1997) — a malha mudou ou o download veio truncado."
        )

    invalidas = int((~gdf.geometry.is_valid).sum())
    if invalidas:
        raise SystemExit(
            f"ERRO: {invalidas} geometria(s) inválida(s) em geo.municipios_mg "
            f"(ST_IsValid) — não conserto com ST_MakeValid por conta própria, "
            f"isso mudaria área e vizinhança sem decisão humana."
        )

    def para_multipolygon(geom):
        if geom.geom_type == "Polygon":
            return MultiPolygon([geom])
        return geom

    linhas = [
        (
            int(row["code_muni"]),
            row["name_muni"],
            psycopg2.Binary(para_multipolygon(row.geometry).wkb),
        )
        for _, row in gdf.iterrows()
    ]

    psycopg2.extras.execute_batch(
        cur,
        "INSERT INTO geo.municipios_mg (code_muni, name_muni, geom) "
        "VALUES (%s, %s, ST_SetSRID(ST_GeomFromWKB(%s), 4326))",
        linhas,
        page_size=500,
    )
    return n


def carregar_snv(cur, geojson_path: pathlib.Path) -> int:
    """Lê o GeoJSON do SNV, valida e insere em `geo.dnit_snv_mg`.

    Precisa do venv `~/.venvs/geo` (geopandas/shapely) — import lazy.
    """
    import geopandas as gpd
    from shapely.geometry import MultiLineString

    gdf = gpd.read_file(geojson_path)
    if gdf.crs is None:
        raise SystemExit(f"ERRO: {geojson_path} não tem CRS definido — não dá para confiar no ST_Transform.")
    gdf = gdf.to_crs(4326)

    n = len(gdf)
    if n == 0:
        raise SystemExit(
            "ERRO: geo.dnit_snv_mg ficaria com 0 linhas — o CQL_FILTER na origem não trouxe nada."
        )

    if "sg_uf" not in gdf.columns:
        raise SystemExit(
            "ERRO: coluna sg_uf ausente no GeoJSON do SNV — não dá para confirmar que o filtro pegou."
        )
    fora_de_mg = int((gdf["sg_uf"] != UF_ALVO).sum())
    if fora_de_mg:
        raise SystemExit(
            f"ERRO: {fora_de_mg} trecho(s) do SNV vieram com sg_uf != 'MG' mesmo "
            f"com CQL_FILTER=sg_uf='MG' na origem — filtro de servidor que "
            f"silenciosamente não filtra é modo de falha conhecido."
        )

    invalidas = int((~gdf.geometry.is_valid).sum())
    if invalidas:
        raise SystemExit(
            f"ERRO: {invalidas} geometria(s) inválida(s) em geo.dnit_snv_mg "
            f"(ST_IsValid) — não conserto com ST_MakeValid por conta própria."
        )

    def para_multilinestring(geom):
        if geom.geom_type == "LineString":
            return MultiLineString([geom])
        return geom

    linhas = [
        (
            row.get("vl_br"),
            row.get("ds_jurisdi"),
            float(row["vl_extensa"]) if row.get("vl_extensa") is not None else None,
            row.get("ds_superfi"),
            psycopg2.Binary(para_multilinestring(row.geometry).wkb),
        )
        for _, row in gdf.iterrows()
    ]

    psycopg2.extras.execute_batch(
        cur,
        "INSERT INTO geo.dnit_snv_mg (vl_br, ds_jurisdi, vl_extensa, ds_superfi, geom) "
        "VALUES (%s, %s, %s, %s, ST_SetSRID(ST_GeomFromWKB(%s), 4326))",
        linhas,
        page_size=500,
    )
    return n


def build(
    dsn: str,
    manifest_path: pathlib.Path = DEFAULT_MANIFEST_PATH,
    raw_dir: pathlib.Path = RAW_DIR,
) -> None:
    gpkg_path, snv_path = baixar_fontes(manifest_path=manifest_path, raw_dir=raw_dir)

    try:
        con = psycopg2.connect(dsn)
    except psycopg2.OperationalError as exc:
        raise SystemExit(f"Não foi possível conectar ao PostGIS com o DSN resolvido: {exc}")

    try:
        con.autocommit = False
        with con.cursor() as cur:
            cur.execute(DDL)
            n_mun = carregar_municipios(cur, gpkg_path)
            n_snv = carregar_snv(cur, snv_path)
        con.commit()

        with con.cursor() as cur:
            cur.execute(
                "SELECT f_table_name, srid FROM geometry_columns "
                "WHERE f_table_schema = 'geo' AND f_table_name IN ('municipios_mg', 'dnit_snv_mg')"
            )
            srids = dict(cur.fetchall())
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

    for tabela in ("municipios_mg", "dnit_snv_mg"):
        if srids.get(tabela) != 4326:
            raise SystemExit(
                f"ERRO: geometry_columns registra SRID {srids.get(tabela)!r} para "
                f"geo.{tabela}, esperado 4326."
            )

    print(f"OK: geo.municipios_mg = {n_mun} linhas (esperado {MUNICIPIOS_MG_ESPERADO})")
    print(f"OK: geo.dnit_snv_mg = {n_snv} linhas, todas com sg_uf='MG'")
    print(f"OK: SRID 4326 confirmado em geometry_columns para as duas tabelas.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dsn", default=None, help="DSN do PostGIS (sobrepõe env e pg.env)")
    ap.add_argument("--manifest", type=pathlib.Path, default=DEFAULT_MANIFEST_PATH)
    ap.add_argument("--raw-dir", type=pathlib.Path, default=RAW_DIR)
    args = ap.parse_args()

    dsn = resolver_dsn(args.dsn)
    build(dsn, manifest_path=args.manifest, raw_dir=args.raw_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
