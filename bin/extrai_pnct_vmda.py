#!/usr/bin/env python3
"""Extrai o Volume Médio Diário Anual (VMDa) do PNCT/DNIT, recorte MG (2017-2025).

Baixa (idempotente, sha256 no manifest) as planilhas anuais do VMDa direto da
API do PNCT — `https://servicos.dnit.gov.br/dadospnct-api/api/v1/downloads/`
(`diretorios?path=...` para listar, `file?path=...` para baixar; o parâmetro
é `path`, não `filePath`) — e gera a série tidy
`bases/pnct-vmda/series/vmda_mg_por_trecho_2017_2025.csv`.

⚠️ O VMDa NÃO tem um layout único. Foram medidos, em 2026-09-07, **sete
cabeçalhos exatos distintos** ao longo de nove anos (2019==2020 idênticos,
2022==2023 idênticos; os outros cinco — 2017, 2018, 2021, 2024, 2025 — são
todos diferentes entre si), agrupados em três famílias estruturais descritas
no `FONTE.md` desta base. Cabeçalho que não casa com NENHUM dos sete
registrados em `LAYOUTS` é ERRO DURO, nunca aviso — mesma disciplina de
`extrai_prf_acidentes.py::_validar_cabecalho`.

Guardas duras (erro, nunca aviso):
  (a) sha256 de cada .xlsx baixado confere com o manifest; hash divergente
      do que já estava gravado é ERRO DURO (a fonte mudou sem avisar);
  (b) cabeçalho (normalizado: strip + sem acento + minúsculas) casa
      EXATAMENTE com um dos sete layouts conhecidos — nunca aproximado;
  (c) a planilha tem que ter exatamente UMA aba além de "Metadados" —
      mais de uma (ou nenhuma) é erro duro, não escolha a "mais provável";
  (d) para o layout de 2017, a soma das 20 colunas por categoria (metodologia
      PNCT, ver FONTE.md) tem que bater com as colunas 'VMDa_T' (Crescente +
      Decrescente) que a própria planilha já traz prontas — divergência acima
      de 1,0 veículo/dia é ERRO DURO (sinal de que a leitura por posição de
      coluna está errada, não que o dado piorou). Divergência entre 0,5 e 1,0
      é tolerada (ruído da fonte — medido em 2026-09-08: 1 linha em 2.031,
      diferença máxima 1,0; erro de coluna produz diferença na casa dos
      milhares, ver FONTE.md), mas **contada** e **impressa** no resumo final
      — nunca silenciada.

Não inventa equivalência entre layouts: onde um layout não trouxer uma coluna
(GEH em 2017/2018, km_inicial/km_final em 2021, versao_snv em 2021), o campo
correspondente da série tidy fica **vazio**, nunca extrapolado — ver
`origem_km`, que registra explicitamente qual par de colunas de km foi usado
em cada linha.

⚠️ Além do recorte MG (`vmda_mg_por_trecho_2017_2025.csv`), este script gera
uma segunda série, `vmda_corredores_por_trecho_2017_2025.csv`: mesmo
tratamento dos quatro layouts, mesmas guardas, mas o filtro de linha muda de
"uf == MG" para "br em BRS_CORREDORES, qualquer UF" — os dez corredores
federais por veículo-km/dia medidos em `bases/prf-acidentes/METODO-ESPACIAL.md`
("A lógica foi invertida"): 101, 116, 163, 153, 364, 381, 050, 376, 158, 135.
`ler_ano`/`_linha_2017`/`_linha_2021`/`_linha_padrao` recebem `ufs_alvo` e
`brs_alvo` (cada um `None` = sem filtro naquele eixo) em vez de um `UF_ALVO`
fixo — o recorte MG passa `ufs_alvo=("MG",)`, o recorte corredores passa
`brs_alvo=BRS_CORREDORES`. O comportamento padrão (MG) não muda.

Uso:
    python3 bin/extrai_pnct_vmda.py [--raw-dir CAMINHO] [--manifest CAMINHO]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import pathlib
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import openpyxl

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_RAW_DIR = ROOT / "raw" / "pnct-vmda"
DEFAULT_MANIFEST_PATH = ROOT / "bases" / "pnct-vmda" / "manifest.json"
DEFAULT_SERIES_DIR = ROOT / "bases" / "pnct-vmda" / "series"
DEFAULT_SERIES_PATH = DEFAULT_SERIES_DIR / "vmda_mg_por_trecho_2017_2025.csv"
DEFAULT_SERIES_PATH_CORREDORES = DEFAULT_SERIES_DIR / "vmda_corredores_por_trecho_2017_2025.csv"

ANOS = list(range(2017, 2026))  # 2017..2025, inclusive — escopo desta apuração
UF_ALVO = "MG"

#: Os dez corredores federais por veículo-km/dia medidos em 2024 — ver
#: `bases/prf-acidentes/METODO-ESPACIAL.md`, "A lógica foi invertida". Já no
#: formato de 3 dígitos que `normalizar_br` produz (zfill só quando o valor
#: é só dígitos), para casar direto contra `rec["br"]` sem reprocessar.
BRS_CORREDORES = (
    "101", "116", "163", "153", "364", "381", "050", "376", "158", "135",
)

API_BASE = "https://servicos.dnit.gov.br/dadospnct-api/api/v1/downloads"
DIRETORIO_VMDA = "Volume Médio Diário Anual (VMDa)"

CATEGORIAS_PADRAO = [
    "a_c", "b_c", "c_c", "d_c", "e_c", "f_c", "g_c", "h_c", "i_c", "j_c",
    "a_d", "b_d", "c_d", "d_d", "e_d", "f_d", "g_d", "h_d", "i_d", "j_d",
]
assert len(CATEGORIAS_PADRAO) == 20

CATEGORIAS_2021 = [
    "a_ab", "b_ab", "c_ab", "d_ab", "e_ab", "f_ab", "g_ab", "h_ab", "i_ab", "j_ab",
    "a_ba", "b_ba", "c_ba", "d_ba", "e_ba", "f_ba", "g_ba", "h_ba", "i_ba", "j_ba",
]
assert len(CATEGORIAS_2021) == 20


# --------------------------------------------------------------------------
# Os sete cabeçalhos exatos medidos em 2026-09-07 (normalizados: strip + sem
# acento + minúsculas). Ver bases/pnct-vmda/FONTE.md para a tabela completa
# dos quatro layouts (narrativa) e o detalhe de cada um destes sete
# cabeçalhos exatos (técnico).
# --------------------------------------------------------------------------

HEADER_2017 = (
    "id1", "ord", "length", "dir", "id_trecho_", "vl_br", "sg_uf", "nm_tipo_tr",
    "sg_tipo_tr", "desc_coinc", "vl_codigo", "ds_local_i", "ds_local_f",
    "vl_km_inic", "vl_km_fina", "vl_extensa", "ds_sup_fed", "ds_obra",
    "ds_coinc", "ds_tipo_ad", "ds_ato_leg", "est_coinc", "sup_est_co",
    "ds_jurisdi", "ds_superfi", "ds_legenda", "sg_legenda", "leg_multim",
    "versao_snv", "id_versao", "marcador",
    "vmda_a", "vmda_b", "vmda_c", "vmda_d", "vmda_e", "vmda_f", "vmda_g", "vmda_h", "vmda_i", "vmda_j",
    "vmda_a", "vmda_b", "vmda_c", "vmda_d", "vmda_e", "vmda_f", "vmda_g", "vmda_h", "vmda_i", "vmda_j",
    "vmda_p1p3", "vmda_o1", "vmda_c1", "vmda_c2", "vmda_s3", "vmda_s6", "vmda_se1", "vmda_m", "vmda_r1", "vmda_r2", "vmda_r4", "vmda_r5",
    "vmda_p1p3", "vmda_o1", "vmda_c1", "vmda_c2", "vmda_s3", "vmda_s6", "vmda_se1", "vmda_m", "vmda_r1", "vmda_r2", "vmda_r4", "vmda_r5",
    "vmda_p", "vmda_m", "vmda_2cb", "vmda_2c", "vmda_3c", "vmda_2dl", "vmda_3d4", "vmda_2s2", "vmda_2s3", "vmda_3s3", "vmda_3t4", "vmda_3m6", "vmda_z",
    "vmda_p", "vmda_m", "vmda_2cb", "vmda_2c", "vmda_3c", "vmda_2dl", "vmda_3d4", "vmda_2s2", "vmda_2s3", "vmda_3s3", "vmda_3t4", "vmda_3m6", "vmda_z",
    "vmda_t", "vmda_t", "referencial", "geh_t",
) + ("",) * 24  # colunas 105-128 da planilha, sem nome — sempre vazias

HEADER_2018 = (
    "id", "id_trecho_", "vl_br", "sg_uf", "nm_tipo_tr", "sg_tipo_tr", "desc_coinc",
    "vl_codigo", "ds_local_i", "ds_local_f", "vl_km_inic", "vl_km_fina", "vl_extensa",
    "vl_km_i_estim", "vl_km_f_estim", "vl_ext_estim", "ds_sup_fed", "ds_obra",
    "ds_coinc", "ds_tipo_ad", "ds_ato_leg", "est_coinc", "sup_est_co", "ds_jurisdi",
    "ds_superfi", "ds_legenda", "sg_legenda", "leg_multim", "versao_snv", "id_versao",
    "classificacao",
) + tuple(CATEGORIAS_PADRAO) + ("vmda_c", "vmda_d", "ns_c", "nc_d")

HEADER_2019_2020 = (
    "id", "id_trecho_", "vl_br", "sg_uf", "nm_tipo_tr", "sg_tipo_tr", "desc_coinc",
    "vl_codigo", "ds_local_i", "ds_local_f", "vl_km_inic", "vl_km_fina", "vl_extensa",
    "vl_km_i_estim", "vl_km_f_estim", "vl_ext_estim", "ds_sup_fed", "ds_obra",
    "ds_coinc", "ds_tipo_ad", "ds_ato_leg", "est_coinc", "sup_est_co", "ds_jurisdi",
    "ds_superfi", "ds_legenda", "sg_legenda", "leg_multim", "versao_snv", "id_versao",
    "classificacao", "geh",
) + tuple(CATEGORIAS_PADRAO) + ("vmda_c", "vmda_d", "ns_c", "ns_d")

HEADER_2022_2023 = (
    "id", "id_trecho_", "vl_br", "sg_uf", "nm_tipo_tr", "sg_tipo_tr", "desc_coinc",
    "vl_codigo", "ds_local_i", "ds_local_f", "vl_km_inic", "vl_km_fina", "vl_extensa",
    "vl_km_i_estim", "vl_km_f_estim", "vl_ext_estim", "ds_sup_fed", "ds_obra", "ul",
    "ds_coinc", "ds_tipo_ad", "ds_ato_leg", "est_coinc", "sup_est_co", "ds_jurisdi",
    "ds_superfi", "ds_legenda", "sg_legenda", "leg_multim", "versao_snv", "id_versao",
    "classificacao", "geh",
) + tuple(CATEGORIAS_PADRAO) + ("vmda_c", "vmda_d")

HEADER_2024 = (
    "id", "id_trecho_", "vl_br", "sg_uf", "nm_tipo_tr", "sg_tipo_tr", "desc_coinc",
    "vl_codigo", "ds_local_i", "ds_local_f", "vl_km_inic", "vl_km_fina", "vl_extensa",
    "vl_km_i_estim", "vl_km_f_estim", "vl_ext_estim", "ds_sup_fed", "ds_obra", "ul",
    "ds_coinc", "ds_tipo_ad", "ds_ato_leg", "est_coinc", "sup_est_co", "ds_jurisdi",
    "ds_superfi", "ds_legenda", "sg_legenda", "leg_multim", "versao_snv",
    "classificacao", "geh",
) + tuple(CATEGORIAS_PADRAO) + ("vmda_c", "vmda_d")

HEADER_2025 = (
    "id", "id_trecho_", "vl_br", "sg_uf", "nm_tipo_tr", "sg_tipo_tr", "desc_coinc",
    "vl_codigo", "ds_local_i", "ds_local_f", "vl_km_inic", "vl_km_fina", "vl_extensa",
    "km_i_estim", "km_f_estim", "ext_estim", "ds_sup_fed", "ds_obra", "ul",
    "ds_coinc", "ds_tipo_ad", "ds_ato_leg", "est_coinc", "sup_est_co", "ds_jurisdi",
    "ds_superfi", "ds_legenda", "sg_legenda", "leg_multim", "versao_snv", "id_versao",
    "classifica", "geh",
) + tuple(CATEGORIAS_PADRAO) + ("vmda_c", "vmda_d")

HEADER_2021 = (
    "id_pnct", "id_modelo", "codigo_br", "regiao", "uf", "extensao", "superficie",
    "codigo_snv-sre", "coinc_f1", "coinc_f2", "coinc_f3", "coinc_e", "jurisdicao",
    "tipo_link", "relevo_pre", "velocidade", "classificacao", "geh",
) + tuple(CATEGORIAS_2021) + ("vmda_ab", "vmda_ba", "vmda_total")

# {ano -> (header esperado, família, linha do cabeçalho na planilha [1-based])}
#
# `col_ext_estim` segue exatamente a mesma convenção já usada por
# `col_km_estim`: o VMDa também traz, a partir de 2018, um campo de extensão
# do SUB-link (mais fino que `vl_extensa`, que é a extensão do trecho-PAI do
# SNV repetida em cada sub-link — ver METODO-ESPACIAL.md, "Os dois erros de
# leitura da fonte"). Em 2025 essa coluna existe com o mesmo nome sem prefixo
# (`ext_estim`, medido: 1.133/1.133 linhas de MG preenchidas), do mesmo jeito
# que `vl_km_i_estim` vira `km_i_estim` nesse ano — por isso o valor por ano
# aqui é o nome exato da coluna, não um booleano.
LAYOUTS: Dict[int, Dict[str, Any]] = {
    2017: {"header": HEADER_2017, "familia": "2017", "linha_cabecalho": 2},
    2018: {
        "header": HEADER_2018, "familia": "padrao", "linha_cabecalho": 1,
        "col_km_estim": ("vl_km_i_estim", "vl_km_f_estim"), "col_geh": None,
        "col_classificacao": "classificacao", "col_versao_snv": "versao_snv",
        "col_ext_estim": "vl_ext_estim", "col_jurisdicao": "ds_jurisdi",
    },
    2019: {
        "header": HEADER_2019_2020, "familia": "padrao", "linha_cabecalho": 1,
        "col_km_estim": ("vl_km_i_estim", "vl_km_f_estim"), "col_geh": "geh",
        "col_classificacao": "classificacao", "col_versao_snv": "versao_snv",
        "col_ext_estim": "vl_ext_estim", "col_jurisdicao": "ds_jurisdi",
    },
    2020: {
        "header": HEADER_2019_2020, "familia": "padrao", "linha_cabecalho": 1,
        "col_km_estim": ("vl_km_i_estim", "vl_km_f_estim"), "col_geh": "geh",
        "col_classificacao": "classificacao", "col_versao_snv": "versao_snv",
        "col_ext_estim": "vl_ext_estim", "col_jurisdicao": "ds_jurisdi",
    },
    2021: {"header": HEADER_2021, "familia": "2021", "linha_cabecalho": 1},
    2022: {
        "header": HEADER_2022_2023, "familia": "padrao", "linha_cabecalho": 1,
        "col_km_estim": ("vl_km_i_estim", "vl_km_f_estim"), "col_geh": "geh",
        "col_classificacao": "classificacao", "col_versao_snv": "versao_snv",
        "col_ext_estim": "vl_ext_estim", "col_jurisdicao": "ds_jurisdi",
    },
    2023: {
        "header": HEADER_2022_2023, "familia": "padrao", "linha_cabecalho": 1,
        "col_km_estim": ("vl_km_i_estim", "vl_km_f_estim"), "col_geh": "geh",
        "col_classificacao": "classificacao", "col_versao_snv": "versao_snv",
        "col_ext_estim": "vl_ext_estim", "col_jurisdicao": "ds_jurisdi",
    },
    2024: {
        "header": HEADER_2024, "familia": "padrao", "linha_cabecalho": 1,
        "col_km_estim": ("vl_km_i_estim", "vl_km_f_estim"), "col_geh": "geh",
        "col_classificacao": "classificacao", "col_versao_snv": "versao_snv",
        "col_ext_estim": "vl_ext_estim", "col_jurisdicao": "ds_jurisdi",
    },
    2025: {
        "header": HEADER_2025, "familia": "padrao", "linha_cabecalho": 1,
        "col_km_estim": ("km_i_estim", "km_f_estim"), "col_geh": "geh",
        "col_classificacao": "classifica", "col_versao_snv": "versao_snv",
        # ⚠️ Achado em 2026-09-08, na execução da SPEC-serie-extensao-jurisdicao,
        # confirmado e corrigido em 2026-09-08 na SPEC-2025-e-hipotese: a
        # planilha de 2025 TEM uma coluna `ext_estim` (índice 15, header
        # normalizado) com dado preenchido em 100% das 1.133 linhas de MG —
        # equivalente a `vl_ext_estim`, só sem o prefixo `vl_` (mesmo padrão
        # já tratado acima em `col_km_estim` para `km_i_estim`/`km_f_estim`).
        # A sondagem anterior tinha procurado o nome exato `vl_km_i_estim` e
        # concluído (errado) que 2025 não tinha o campo; corrigido aqui.
        "col_ext_estim": "ext_estim", "col_jurisdicao": "ds_jurisdi",
    },
}

ESCOPO_SERIE = "vmda_bruto_2017_2025"
ESCOPO_SERIE_CORREDORES = "vmda_corredores_bruto_2017_2025"


def remover_acentos(txt: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", txt) if unicodedata.category(c) != "Mn"
    )


def normalizar_cel_cabecalho(valor: Any) -> str:
    if valor is None:
        return ""
    return remover_acentos(str(valor).strip().strip('"').strip("﻿")).lower()


def normalizar_jurisdicao(valor: Any) -> str:
    """Normaliza `jurisdicao_bruta` por PREFIXO, insensível a caixa:
    `FEDERAL-PAV`/`FEDERAL-PLA` (2018/2020) e `Federal` (2023-2025) caem
    ambos em `federal`; idem estadual/municipal. Vazio/None vira
    `indefinida`.

    ⚠️ `indefinida` NUNCA vira `federal` por suposição: em MG, 2018 e 2020
    têm ~9.400 km/ano sem valor nenhum de jurisdição (mais da metade da
    malha modelada nesses anos) — promovê-los a federal infla o denominador
    sem base. Ver METODO-ESPACIAL.md, "Jurisdição: o denominador não pode
    ser mais largo que o numerador"."""
    s = remover_acentos(str(valor or "").strip()).lower()
    if not s:
        return "indefinida"
    if s.startswith("federal"):
        return "federal"
    if s.startswith("estadual"):
        return "estadual"
    if s.startswith("municipal"):
        return "municipal"
    return "indefinida"


def normalizar_br(valor: Any) -> str:
    """Zero-padding para 3 dígitos — a mesma normalização que
    `bin/mede_cobertura_vmda.py` aplica ao lado da PRF. Aqui o valor já
    costuma vir com 3 dígitos ('040').

    Só faz zfill quando o valor é só dígitos: em 2021, `CODIGO_BR` traz
    placeholders não-numéricos ('-' para "Conector", '999'/'900' para
    trecho estadual/municipal sem BR federal — ver FONTE.md) que NÃO são
    código de rodovia e não podem virar algo como '-00' por zero-padding
    cego. Esses placeholders ficam como vieram (sem padding), documentados,
    nunca inventados como BR."""
    s = str(valor).strip().strip('"')
    return s.zfill(3) if s.isdigit() else s


def to_float(valor: Any) -> Optional[float]:
    """Converte célula numérica (ou vazia/traço) para float; None se não der."""
    if valor is None:
        return None
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    s = str(valor).strip()
    if not s or s == "-":
        return None
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def eh_numerico(valor: Any) -> bool:
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


def sha256_of(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------
# Download idempotente (API do PNCT)
# --------------------------------------------------------------------------

def montar_url_arquivo(ano: int) -> str:
    path = f"{DIRETORIO_VMDA}/{ano}/VMDa {ano}.xlsx"
    return f"{API_BASE}/file?path={urllib.parse.quote(path)}"


def _ler_manifest(manifest_path: pathlib.Path) -> dict:
    if manifest_path.exists():
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        "slug": "pnct-vmda",
        "nome": "Volume Médio Diário Anual (VMDa) do PNCT/DNIT",
        "autor": "DEPARTAMENTO NACIONAL DE INFRAESTRUTURA DE TRANSPORTES (DNIT)",
        "url": "https://servicos.dnit.gov.br/dnitcloud/index.php/s/pnct-dados-abertos",
        "periodicidade": "anual",
        "descricao": (
            "Volume Médio Diário Anual (VMDa) estimado/contado por trecho do "
            "SNV, publicado anualmente pelo Programa Nacional de Contagem de "
            "Tráfego (PNCT) do DNIT."
        ),
        "arquivos": [],
    }


def _gravar_manifest(manifest_path: pathlib.Path, manifest: dict) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = manifest_path.with_name(manifest_path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2, sort_keys=False)
        f.write("\n")
    tmp.replace(manifest_path)


def baixar_ano_idempotente(
    ano: int, raw_dir: pathlib.Path, manifest: dict, timeout: int = 120
) -> pathlib.Path:
    """Garante `raw_dir/VMDa_<ano>.xlsx` em disco, atualizando `manifest`
    (mutado in-place) com url/sha256/data_acesso. Idempotente: se o arquivo
    já existe em disco E confere com o sha256 já gravado no manifest para
    este ano, não baixa de novo. Hash divergente do que já estava gravado é
    ERRO DURO."""
    destino = raw_dir / f"VMDa_{ano}.xlsx"
    url = montar_url_arquivo(ano)

    arquivos = manifest.setdefault("arquivos", [])
    entrada = next((a for a in arquivos if a.get("ano") == ano), None)
    sha_esperado = entrada.get("sha256") if entrada else None

    if destino.exists() and sha_esperado:
        sha_local = sha256_of(destino)
        if sha_local == sha_esperado:
            print(f"OK (cache): VMDa {ano} já em disco, sha256 confere com o manifest.")
            return destino
        print(
            f"AVISO: VMDa {ano} em disco não bate com o manifest "
            f"(esperado {sha_esperado}, encontrado {sha_local}) — baixando de novo."
        )

    raw_dir.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_name(destino.name + ".tmp")
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            with open(tmp, "wb") as f:
                f.write(resp.read())
    except urllib.error.URLError as exc:
        raise SystemExit(f"ERRO: falha ao baixar VMDa {ano} de {url}: {exc}")

    sha_novo = sha256_of(tmp)
    if sha_esperado and sha_novo != sha_esperado:
        tmp.unlink(missing_ok=True)
        raise SystemExit(
            f"ERRO DURO: VMDa {ano} mudou na fonte sem aviso — hash gravado no "
            f"manifest é {sha_esperado}, hash baixado agora é {sha_novo} "
            f"(url: {url}). Não sobrescrevo o manifest sozinho — revise a "
            f"mudança antes de aceitar o novo hash."
        )

    tmp.replace(destino)
    tamanho = destino.stat().st_size
    registro = {
        "ano": ano,
        "url": url,
        "arquivo_local": str(destino.relative_to(ROOT)),
        "tamanho_bytes": tamanho,
        "sha256": sha_novo,
        "data_acesso": datetime.now(timezone.utc).date().isoformat(),
        "formato": "XLSX",
    }
    if entrada:
        entrada.update(registro)
    else:
        arquivos.append(registro)
    print(f"OK (baixado): VMDa {ano} -> {destino} sha256={sha_novo} ({tamanho} bytes)")
    return destino


# --------------------------------------------------------------------------
# Leitura + normalização de uma safra
# --------------------------------------------------------------------------

def detectar_aba_dados(wb, filepath: pathlib.Path) -> str:
    """A aba de dados é a única que não é 'Metadados'. Mais de uma (ou
    nenhuma) candidata é erro duro — não escolhe "a mais provável"."""
    candidatas = [nome for nome in wb.sheetnames if nome.strip().lower() != "metadados"]
    if len(candidatas) != 1:
        raise SystemExit(
            f"ERRO: {filepath} tem {len(candidatas)} aba(s) além de 'Metadados' "
            f"({candidatas}), esperava exatamente 1."
        )
    return candidatas[0]


def _validar_cabecalho(header_norm: Tuple[str, ...], ano: int, filepath: pathlib.Path) -> None:
    esperado = LAYOUTS[ano]["header"]
    if tuple(header_norm) != tuple(esperado):
        raise SystemExit(
            f"ERRO: cabeçalho de {filepath} (ano {ano}) não casa com NENHUM "
            f"layout conhecido do VMDa.\n"
            f"  Esperado ({len(esperado)} cols): {esperado}\n"
            f"  Obtido ({len(header_norm)} cols):   {tuple(header_norm)}"
        )


def _linha_padrao(
    row: Sequence[Any],
    idx: Dict[str, int],
    layout: dict,
    ufs_alvo: Optional[Sequence[str]] = (UF_ALVO,),
    brs_alvo: Optional[Sequence[str]] = None,
) -> Optional[Dict[str, Any]]:
    uf = row[idx["sg_uf"]]
    if ufs_alvo is not None and uf not in ufs_alvo:
        return None

    br = normalizar_br(row[idx["vl_br"]])
    if brs_alvo is not None and br not in brs_alvo:
        return None

    col_km_estim = layout["col_km_estim"]
    v_estim = row[idx[col_km_estim[0]]] if col_km_estim else None
    if col_km_estim and eh_numerico(v_estim):
        km_i = to_float(row[idx[col_km_estim[0]]])
        km_f = to_float(row[idx[col_km_estim[1]]])
        origem_km = "estimado"
    else:
        km_i = to_float(row[idx["vl_km_inic"]])
        km_f = to_float(row[idx["vl_km_fina"]])
        origem_km = "oficial"

    # `vl_extensa` é a extensão do trecho-PAI do SNV, repetida em cada
    # sub-link (ver METODO-ESPACIAL.md, "Os dois erros de leitura da fonte").
    # `col_ext_estim` (quando o layout do ano tiver) é a extensão do
    # sub-link — a que de fato corresponde à faixa [km_i, km_f] desta linha.
    col_ext_estim = layout.get("col_ext_estim")
    v_ext_estim = row[idx[col_ext_estim]] if col_ext_estim else None
    if col_ext_estim and eh_numerico(v_ext_estim):
        extensao = to_float(v_ext_estim)
        origem_extensao = "estimado"
    else:
        extensao = to_float(row[idx["vl_extensa"]])
        origem_extensao = "oficial"

    # `extensao_oficial_km` é SEMPRE `vl_extensa` (o trecho-PAI do SNV,
    # repetido em cada sub-link — ver FONTE.md), em todos os anos,
    # independente de qual valor `extensao_km`/`origem_extensao` usou. Existe
    # para deixar a armadilha (somar `vl_extensa` conta o mesmo trecho-pai
    # várias vezes) auditável no CSV versionado, não só na prosa do FONTE.md.
    extensao_oficial = to_float(row[idx["vl_extensa"]])

    superficie = row[idx["ds_superfi"]] or ""
    geh = (row[idx[layout["col_geh"]]] if layout["col_geh"] else "") or ""
    classificacao = row[idx[layout["col_classificacao"]]] if layout["col_classificacao"] else ""
    classificacao = classificacao or ""
    versao_snv = row[idx[layout["col_versao_snv"]]] if layout["col_versao_snv"] else ""
    versao_snv = versao_snv or ""

    col_jurisdicao = layout.get("col_jurisdicao")
    jurisdicao_bruta = (row[idx[col_jurisdicao]] if col_jurisdicao else "") or ""

    vals = [row[idx[c]] for c in CATEGORIAS_PADRAO]
    vmda_total = sum(float(v) for v in vals) if all(eh_numerico(v) for v in vals) else None

    return {
        "uf": uf, "br": br, "km_inicial": km_i, "km_final": km_f,
        "origem_km": origem_km, "extensao_km": extensao,
        "origem_extensao": origem_extensao, "extensao_oficial_km": extensao_oficial,
        "vmda_total": vmda_total,
        "superficie": str(superficie), "geh": str(geh), "classificacao": str(classificacao),
        "versao_snv": str(versao_snv), "jurisdicao_bruta": str(jurisdicao_bruta),
    }


def _linha_2017(
    row: Sequence[Any],
    filepath: pathlib.Path,
    ufs_alvo: Optional[Sequence[str]] = (UF_ALVO,),
    brs_alvo: Optional[Sequence[str]] = None,
    toleradas: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    uf = row[6]
    if ufs_alvo is not None and uf not in ufs_alvo:
        return None

    br = normalizar_br(row[5])
    if brs_alvo is not None and br not in brs_alvo:
        return None
    km_i = to_float(row[13])
    km_f = to_float(row[14])
    extensao = to_float(row[15])  # ~234 trechos nacionais (52 em MG) vêm sem
    # metadado de km/extensão neste arquivo — ver FONTE.md; ficam com
    # extensao_km/km_inicial/km_final vazios, nunca inventados.
    # 2017 não tem coluna de extensão "estimada" (par sub-link) nenhuma —
    # `vl_extensa` (trecho-pai) é o único valor disponível.
    origem_extensao = "oficial"
    jurisdicao_bruta = row[23] or ""
    superficie = row[24] or ""
    versao_snv = row[28] or ""

    pnct_c = row[31:41]
    pnct_d = row[41:51]
    vmda_total = None
    if all(eh_numerico(v) for v in pnct_c) and all(eh_numerico(v) for v in pnct_d):
        vmda_total = sum(float(v) for v in pnct_c) + sum(float(v) for v in pnct_d)
        t_c, t_d = row[101], row[102]
        if eh_numerico(t_c) and eh_numerico(t_d):
            referencia = float(t_c) + float(t_d)
            diff = abs(vmda_total - referencia)
            if diff > 1.0:
                raise SystemExit(
                    f"ERRO: {filepath}: soma das 20 colunas PNCT (Crescente+Decrescente) "
                    f"= {vmda_total}, diverge de VMDa_T (Crescente+Decrescente) = "
                    f"{referencia} (diff > 1.0) — a leitura por posição de coluna "
                    f"pode estar errada, revise antes de aceitar."
                )
            if diff > 0.5 and toleradas is not None:
                # Medido em 2026-09-08 (ver FONTE.md): das 2.031 linhas dos dez
                # corredores em 2017, só 1 diverge de VMDa_T, e a diferença
                # máxima é 1,0 — ruído da fonte (arredondamento/digitação),
                # não erro de leitura de coluna (erro de coluna produz
                # diferença na casa dos milhares, ver as famílias P1P3/O1/C1…
                # e P/2CB/2C… no FONTE.md). Tolerado, mas CONTADO — nunca
                # silenciado (ver bin/extrai_pnct_vmda.py, guarda (d)).
                toleradas.append({
                    "filepath": str(filepath),
                    "uf": row[6],
                    "br": normalizar_br(row[5]),
                    "vmda_total": vmda_total,
                    "referencia": referencia,
                    "diff": diff,
                })

    return {
        "uf": uf, "br": br, "km_inicial": km_i, "km_final": km_f,
        "origem_km": "oficial", "extensao_km": extensao,
        "origem_extensao": origem_extensao,
        # 2017 não tem par estimado nenhum: `extensao_km` já É `vl_extensa`
        # (o trecho-pai), então `extensao_oficial_km` é o mesmo valor.
        "extensao_oficial_km": extensao,
        "vmda_total": vmda_total,
        "superficie": str(superficie), "geh": "", "classificacao": "",
        "versao_snv": str(versao_snv), "jurisdicao_bruta": str(jurisdicao_bruta),
    }


def _linha_2021(
    row: Sequence[Any],
    idx: Dict[str, int],
    ufs_alvo: Optional[Sequence[str]] = (UF_ALVO,),
    brs_alvo: Optional[Sequence[str]] = None,
) -> Optional[Dict[str, Any]]:
    uf = row[idx["uf"]]
    if ufs_alvo is not None and uf not in ufs_alvo:
        return None

    br = normalizar_br(row[idx["codigo_br"]])
    if brs_alvo is not None and br not in brs_alvo:
        return None
    extensao = to_float(row[idx["extensao"]])
    superficie = row[idx["superficie"]] or ""
    geh = row[idx["geh"]] or ""
    classificacao = row[idx["classificacao"]] or ""
    jurisdicao_bruta = row[idx["jurisdicao"]] or ""

    vals = [row[idx[c]] for c in CATEGORIAS_2021]
    vmda_total = sum(float(v) for v in vals) if all(eh_numerico(v) for v in vals) else None

    return {
        "uf": uf, "br": br, "km_inicial": None, "km_final": None,
        "origem_km": "indisponivel_2021", "extensao_km": extensao,
        # 2021 só traz a extensão total do trecho (`EXTENSAO`), sem par
        # sub-link "estimado" — mesmo espírito de 2017. `extensao_km` já É
        # a extensão do trecho-pai, então `extensao_oficial_km` é o mesmo
        # valor.
        "origem_extensao": "oficial", "extensao_oficial_km": extensao,
        "vmda_total": vmda_total,
        "superficie": str(superficie), "geh": str(geh), "classificacao": str(classificacao),
        "versao_snv": "", "jurisdicao_bruta": str(jurisdicao_bruta),
    }


def ler_ano(
    ano: int,
    filepath: pathlib.Path,
    ufs_alvo: Optional[Sequence[str]] = (UF_ALVO,),
    brs_alvo: Optional[Sequence[str]] = None,
    toleradas: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Lê a planilha `filepath` (ano `ano`), valida o cabeçalho contra o
    layout conhecido daquele ano, e devolve as linhas que passam pelo
    filtro: `ufs_alvo` (`None` = todas as UFs) e `brs_alvo` (`None` = todas
    as BRs; valores já no formato de `normalizar_br`). O default
    (`ufs_alvo=("MG",)`, `brs_alvo=None`) reproduz o comportamento histórico
    (recorte MG, qualquer BR). `toleradas`, se passado, recebe um dict por
    linha de 2017 cuja soma das 20 colunas PNCT diverge de `VMDa_T` em mais
    de 0,5 e até 1,0 (tolerado, mas nunca silenciado — ver guarda (d) no
    docstring do módulo)."""
    layout = LAYOUTS[ano]
    wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
    try:
        aba = detectar_aba_dados(wb, filepath)
        ws = wb[aba]
        linha_cab = layout["linha_cabecalho"]
        header_raw = next(ws.iter_rows(min_row=linha_cab, max_row=linha_cab, values_only=True))
        header_norm = tuple(normalizar_cel_cabecalho(c) for c in header_raw)
        _validar_cabecalho(header_norm, ano, filepath)

        resultado: List[Dict[str, Any]] = []
        if layout["familia"] == "2017":
            for row in ws.iter_rows(min_row=linha_cab + 1, values_only=True):
                rec = _linha_2017(row, filepath, ufs_alvo, brs_alvo, toleradas)
                if rec is not None:
                    resultado.append(rec)
        elif layout["familia"] == "2021":
            idx = {nome: i for i, nome in enumerate(header_norm)}
            for row in ws.iter_rows(min_row=linha_cab + 1, values_only=True):
                rec = _linha_2021(row, idx, ufs_alvo, brs_alvo)
                if rec is not None:
                    resultado.append(rec)
        else:  # "padrao"
            idx = {nome: i for i, nome in enumerate(header_norm)}
            for row in ws.iter_rows(min_row=linha_cab + 1, values_only=True):
                rec = _linha_padrao(row, idx, layout, ufs_alvo, brs_alvo)
                if rec is not None:
                    resultado.append(rec)
        return resultado
    finally:
        wb.close()


# --------------------------------------------------------------------------
# Série tidy
# --------------------------------------------------------------------------

def _fmt(valor: Optional[float], casas: int) -> str:
    if valor is None:
        return ""
    return f"{round(valor, casas):.{casas}f}".rstrip("0").rstrip(".") if casas else str(round(valor))


def gerar_series(
    raw_dir: pathlib.Path = DEFAULT_RAW_DIR,
    manifest_path: pathlib.Path = DEFAULT_MANIFEST_PATH,
    series_path: pathlib.Path = DEFAULT_SERIES_PATH,
    anos: Sequence[int] = ANOS,
    ufs_alvo: Optional[Sequence[str]] = (UF_ALVO,),
    brs_alvo: Optional[Sequence[str]] = None,
    escopo: str = ESCOPO_SERIE,
    toleradas: Optional[List[Dict[str, Any]]] = None,
) -> Dict[int, int]:
    """Baixa (idempotente) todos os `anos`, extrai o recorte definido por
    `ufs_alvo`/`brs_alvo` de cada um (default: recorte MG, qualquer BR — o
    comportamento histórico), e grava a série tidy em `series_path` com a
    coluna `escopo` preenchida com `escopo`. Devolve {ano: linhas no
    recorte} para quem quiser imprimir um resumo. `toleradas`, se passado, é
    repassado a `ler_ano`/`_linha_2017` — acumula as linhas de 2017 com
    divergência tolerada entre a soma das 20 colunas PNCT e `VMDa_T` (ver
    guarda (d) no docstring do módulo)."""
    manifest = _ler_manifest(manifest_path)

    linhas_por_ano: Dict[int, int] = {}
    colunas = [
        "ano", "chave_linha", "uf", "br", "km_inicial", "km_final", "origem_km",
        "extensao_km", "origem_extensao", "extensao_oficial_km", "vmda_total",
        "superficie", "geh", "classificacao", "versao_snv", "jurisdicao_bruta",
        "jurisdicao", "contagem_trecho", "escopo", "harmonizada",
    ]
    linhas_csv = [colunas]

    seq = 0
    for ano in anos:
        filepath = baixar_ano_idempotente(ano, raw_dir, manifest)
        registros = ler_ano(ano, filepath, ufs_alvo=ufs_alvo, brs_alvo=brs_alvo, toleradas=toleradas)
        linhas_por_ano[ano] = len(registros)
        for rec in registros:
            seq += 1
            # `chave_linha` é um identificador SEQUENCIAL, só para satisfazer o
            # requisito de chave única por (ano, escopo) do schema genérico de
            # bin/build_db.py — NÃO é a chave de junção desta base (essa é
            # br+km, ver METODO-ESPACIAL.md em bases/prf-acidentes/). O prefixo
            # com `br` é só para leitura humana.
            chave_linha = f"{rec['br']}_{seq:05d}"
            linhas_csv.append([
                str(ano),
                chave_linha,
                rec["uf"],
                rec["br"],
                _fmt(rec["km_inicial"], 3),
                _fmt(rec["km_final"], 3),
                rec["origem_km"],
                _fmt(rec["extensao_km"], 3),
                rec["origem_extensao"],
                _fmt(rec["extensao_oficial_km"], 3),
                _fmt(rec["vmda_total"], 2),
                rec["superficie"],
                rec["geh"],
                rec["classificacao"],
                rec["versao_snv"],
                rec["jurisdicao_bruta"],
                normalizar_jurisdicao(rec["jurisdicao_bruta"]),
                "1",
                escopo,
                "0",
            ])

    _gravar_manifest(manifest_path, manifest)

    series_path.parent.mkdir(parents=True, exist_ok=True)
    with open(series_path, "w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(linhas_csv)

    return linhas_por_ano


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw-dir", type=pathlib.Path, default=DEFAULT_RAW_DIR)
    ap.add_argument("--manifest", type=pathlib.Path, default=DEFAULT_MANIFEST_PATH)
    ap.add_argument("--series-path", type=pathlib.Path, default=DEFAULT_SERIES_PATH)
    args = ap.parse_args()

    # Compartilhado entre as duas chamadas de `gerar_series` abaixo (MG e
    # corredores) — a única linha tolerada medida (BR-153/TO, diff 1,0) só
    # aparece no recorte corredores (o recorte MG filtra por UF antes de
    # chegar na guarda), mas o contador é do RUN inteiro, não de uma série
    # só. Ver docstring do módulo, guarda (d): tolerar sem contar é guarda
    # desligada.
    toleradas: List[Dict[str, Any]] = []

    linhas_por_ano = gerar_series(
        raw_dir=args.raw_dir, manifest_path=args.manifest, series_path=args.series_path,
        toleradas=toleradas,
    )

    print(f"OK: {args.series_path} gerado.")
    total = 0
    for ano in ANOS:
        n = linhas_por_ano.get(ano, 0)
        total += n
        print(f"  {ano}: {n:>5,d} trechos em MG")
    print(f"Total: {total:>6,d} linhas (recorte MG, 2017-2025).")

    linhas_por_ano_corredores = gerar_series(
        raw_dir=args.raw_dir,
        manifest_path=args.manifest,
        series_path=DEFAULT_SERIES_PATH_CORREDORES,
        ufs_alvo=None,
        brs_alvo=BRS_CORREDORES,
        escopo=ESCOPO_SERIE_CORREDORES,
        toleradas=toleradas,
    )

    print(f"OK: {DEFAULT_SERIES_PATH_CORREDORES} gerado.")
    total_corredores = 0
    for ano in ANOS:
        n = linhas_por_ano_corredores.get(ano, 0)
        total_corredores += n
        print(f"  {ano}: {n:>6,d} trechos nos corredores (10 BRs, todas as UFs)")
    print(f"Total: {total_corredores:>7,d} linhas (recorte corredores, 2017-2025).")

    if toleradas:
        print(
            f"aviso: {len(toleradas)} linha"
            f"{'s' if len(toleradas) != 1 else ''} com divergência tolerada "
            f"(<=1) entre a soma das 20 colunas PNCT e VMDa_T em 2017"
        )
        for t in toleradas:
            print(
                f"  - {t['filepath']}: uf={t['uf']} br={t['br']} "
                f"soma={t['vmda_total']} VMDa_T={t['referencia']} diff={t['diff']}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
