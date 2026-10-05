#!/usr/bin/env python3
"""Extrai e consolida a base de Acidentes em Rodovias Federais (Agrupados por Ocorrência) (PRF, 2007-2026).

Leitor único dos 20 ZIPs brutos em `raw/prf-acidentes/` (datatran2007.zip a datatran2026.zip).
Lê o CSV de dentro do ZIP usando `zipfile` (D2), sem extrair.

⚠️ TETO DE MEMÓRIA — restrição dura:
  - Processa uma safra por vez, agregando via streaming e liberando a safra antes da seguinte;
  - `ler_todos_anos()` devolve `{ano: agregado}` (20 dicts pequenos), não lista de registros;
  - `registros(ano)` é gerador que relê o ZIP daquele ano sob demanda;
  - Pico de RSS medido via `resource.getrusage` mantido abaixo de 1 GB.

Guardas como ERRO DURO, nunca aviso:
  (a) sha256 de cada ZIP bruto confere com `manifest.json`;
  (b) decodificação com o `encoding` DECLARADO no manifest (latin-1) — decoding estrito;
  (c) cabeçalho (strip + minúsculas + sem acento) casa com um dos 3 layouts conhecidos (26/25/30 cols)
      e é normalizado para os 25 nomes comuns;
  (d) todas as colunas do layout presentes em toda linha;
  (e) `data_inversa` parseada detectando o formato (yyyy-mm-dd, dd/mm/yyyy, dd/mm/yy), toda data no ano do arquivo
      e 12 meses presentes em todo ano completo (2026 tem 7);
  (f) `classificacao_acidente` no vocabulário fechado {"Com Vítimas Feridas", "Com Vítimas Fatais", "Sem Vítimas", "Ignorado", "NA", "(null)", ""};
  (g) `mortos`, `feridos`, `feridos_leves`, `feridos_graves`, `ilesos`, `pessoas`, `veiculos` são inteiros;
  (h) coerência: zero `Sem Vítimas` com `mortos > 0` e zero `Com Vítimas Fatais` com `mortos == 0`;
  (i) `ano` é sempre `int` e sempre o ano do arquivo (coluna do arquivo descartada pós-checagem).

Uso:
    python3 bin/extrai_prf_acidentes.py [--raw-dir CAMINHO] [--manifest CAMINHO]
"""

import argparse
import collections
import csv
import hashlib
import io
import json
import pathlib
import resource
import sys
import unicodedata
import zipfile
from typing import Any, Dict, Generator, List, Optional, Tuple

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_RAW_DIR = ROOT / "raw" / "prf-acidentes"
DEFAULT_MANIFEST_PATH = ROOT / "bases" / "prf-acidentes" / "manifest.json"
DEFAULT_SERIES_DIR = ROOT / "bases" / "prf-acidentes" / "series"

LAYOUT_2007_2015 = [
    "id", "data_inversa", "dia_semana", "horario", "uf", "br", "km",
    "municipio", "causa_acidente", "tipo_acidente", "classificacao_acidente",
    "fase_dia", "sentido_via", "condicao_metereologica", "tipo_pista",
    "tracado_via", "uso_solo", "ano", "pessoas", "mortos", "feridos_leves",
    "feridos_graves", "ilesos", "ignorados", "feridos", "veiculos",
]

LAYOUT_2016 = [
    "id", "data_inversa", "dia_semana", "horario", "uf", "br", "km",
    "municipio", "causa_acidente", "tipo_acidente", "classificacao_acidente",
    "fase_dia", "sentido_via", "condicao_metereologica", "tipo_pista",
    "tracado_via", "uso_solo", "pessoas", "mortos", "feridos_leves",
    "feridos_graves", "ilesos", "ignorados", "feridos", "veiculos",
]

LAYOUT_2017_2026 = [
    "id", "data_inversa", "dia_semana", "horario", "uf", "br", "km",
    "municipio", "causa_acidente", "tipo_acidente", "classificacao_acidente",
    "fase_dia", "sentido_via", "condicao_metereologica", "tipo_pista",
    "tracado_via", "uso_solo", "pessoas", "mortos", "feridos_leves",
    "feridos_graves", "ilesos", "ignorados", "feridos", "veiculos",
    "latitude", "longitude", "regional", "delegacia", "uop",
]

VOCAB_CLASSIFICACAO = {
    "Com Vítimas Feridas",
    "Com Vítimas Fatais",
    "Sem Vítimas",
    "Ignorado",
    "NA",
    "(null)",
    "",
}

CAMPOS_INTEIROS = [
    "mortos",
    "feridos",
    "feridos_leves",
    "feridos_graves",
    "ilesos",
    "pessoas",
    "veiculos",
]


def remover_acentos(txt: str) -> str:
    """Remove diacríticos e acentos de uma string."""
    return "".join(
        c for c in unicodedata.normalize("NFD", txt)
        if unicodedata.category(c) != "Mn"
    )


def normalizar_cabecalho(header_raw: List[str]) -> List[str]:
    """Normaliza nomes de colunas: strip + minúsculas + sem aspas + sem acentos."""
    return [
        remover_acentos(col.strip().strip('"').strip("\ufeff")).lower()
        for col in header_raw
    ]


def check_sha256(filepath: pathlib.Path, expected_sha256: str) -> None:
    """Confere o SHA256 de um arquivo contra o hash do manifest."""
    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    actual = sha.hexdigest()
    if actual.lower() != expected_sha256.lower():
        raise SystemExit(
            f"ERRO: sha256 de {filepath} divergiu do manifest!\n"
            f"  Esperado: {expected_sha256}\n"
            f"  Obtido:   {actual}"
        )


def _parse_data(data_str: str) -> Tuple[int, int, int]:
    """Parseia strings de data nos formatos YYYY-MM-DD, DD/MM/YYYY ou DD/MM/YY.

    Devolve (dia, mes, ano).
    """
    s = data_str.strip()
    if "-" in s:
        parts = s.split("-")
        if len(parts) == 3:
            return int(parts[2]), int(parts[1]), int(parts[0])
    elif "/" in s:
        parts = s.split("/")
        if len(parts) == 3:
            d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
            if y < 100:
                y += 2000
            return d, m, y
    raise ValueError(f"Formato de data inválido: '{data_str}'")


def _validar_cabecalho(
    header_norm: List[str], ano_esperado: int, filepath: pathlib.Path
) -> List[str]:
    """Valida se o cabeçalho normalizado casa com um dos 3 layouts esperados."""
    if 2007 <= ano_esperado <= 2015:
        esperado = LAYOUT_2007_2015
    elif ano_esperado == 2016:
        esperado = LAYOUT_2016
    elif 2017 <= ano_esperado <= 2026:
        esperado = LAYOUT_2017_2026
    else:
        raise SystemExit(f"ERRO: ano {ano_esperado} fora do intervalo suportado (2007-2026)")

    if header_norm != esperado:
        raise SystemExit(
            f"ERRO: cabeçalho de {filepath} (ano {ano_esperado}) divergiu do layout esperado.\n"
            f"  Esperado ({len(esperado)} cols): {esperado}\n"
            f"  Obtido ({len(header_norm)} cols):   {header_norm}"
        )
    return header_norm


def _obter_info_manifest(
    ano: int, manifest_path: pathlib.Path, raw_dir: pathlib.Path
) -> Tuple[pathlib.Path, str, str]:
    """Recupera metadados da safra (caminho local, sha256, encoding) do manifest."""
    if not manifest_path.exists():
        raise SystemExit(f"ERRO: manifest não encontrado em {manifest_path}")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    for item in manifest.get("arquivos", []):
        if item.get("ano") == ano:
            filepath = ROOT / item["arquivo_local"]
            if not filepath.exists() and raw_dir:
                alt = raw_dir / pathlib.Path(item["arquivo_local"]).name
                if alt.exists():
                    filepath = alt
            sha256_exp = item["sha256"]
            encoding = item.get("encoding", manifest.get("encoding", "latin-1"))
            return filepath, sha256_exp, encoding

    raise SystemExit(f"ERRO: safra {ano} não encontrada em {manifest_path}")


def registros(
    ano: int,
    raw_dir: Optional[pathlib.Path] = None,
    manifest_path: Optional[pathlib.Path] = None,
) -> Generator[Dict[str, Any], None, None]:
    """Gerador que relê o ZIP da safra de forma estritamente streaming e emite registros dict.

    NUNCA materializa lista com todas as linhas do ano.
    """
    if raw_dir is None:
        raw_dir = DEFAULT_RAW_DIR
    if manifest_path is None:
        manifest_path = DEFAULT_MANIFEST_PATH

    filepath, sha256_exp, encoding = _obter_info_manifest(ano, manifest_path, raw_dir)

    if not filepath.exists():
        raise SystemExit(f"ERRO: arquivo bruto não encontrado em {filepath}")

    check_sha256(filepath, sha256_exp)

    meses_vistos = set()

    try:
        with zipfile.ZipFile(filepath, "r") as z:
            membros = z.namelist()
            membro_esperado = f"datatran{ano}.csv"
            if membros != [membro_esperado]:
                raise SystemExit(
                    f"ERRO: {filepath} deve conter exatamente um membro "
                    f"'{membro_esperado}', achei: {membros}"
                )
            csv_name = membro_esperado
            with z.open(csv_name, "r") as raw_bytes:
                text_stream = io.TextIOWrapper(raw_bytes, encoding=encoding)
                reader = csv.reader(text_stream, delimiter=";")
                try:
                    header_raw = next(reader)
                except StopIteration:
                    raise SystemExit(f"ERRO: CSV em {filepath} está vazio")

                header_norm = normalizar_cabecalho(header_raw)
                _validar_cabecalho(header_norm, ano, filepath)

                for line_num, row in enumerate(reader, start=2):
                    if not row or all(not c.strip() for c in row):
                        continue
                    if len(row) != len(header_norm):
                        raise SystemExit(
                            f"ERRO: linha {line_num} de {filepath} possui {len(row)} colunas "
                            f"(esperado: {len(header_norm)})"
                        )

                    celulas = [c.strip() for c in row]
                    row_dict = dict(zip(header_norm, celulas))

                    # Pegadinha 9: se o CSV tem coluna 'ano' (2007-2015), confere e descarta
                    if "ano" in row_dict:
                        ano_str = row_dict["ano"]
                        try:
                            ano_row = int(ano_str)
                        except ValueError:
                            raise SystemExit(f"ERRO: linha {line_num} de {filepath}: ano inválido '{ano_str}'")
                        if ano_row != ano:
                            raise SystemExit(
                                f"ERRO: linha {line_num} de {filepath}: coluna ano ({ano_row}) "
                                f"diverge do arquivo ({ano})"
                            )

                    # Pegadinha 2: data_inversa em múltiplos formatos
                    data_str = row_dict["data_inversa"]
                    try:
                        dia, mes, ano_dt = _parse_data(data_str)
                    except ValueError as e:
                        raise SystemExit(f"ERRO: linha {line_num} de {filepath}: {e}")

                    if ano_dt != ano:
                        raise SystemExit(
                            f"ERRO: linha {line_num} de {filepath}: ano da data ({ano_dt}) "
                            f"diverge do ano do arquivo ({ano})"
                        )
                    meses_vistos.add(mes)

                    # Guarda (f): vocabulário fechado de classificacao_acidente
                    cla = row_dict["classificacao_acidente"]
                    if cla not in VOCAB_CLASSIFICACAO:
                        raise SystemExit(
                            f"ERRO: linha {line_num} de {filepath}: classificacao_acidente '{cla}' "
                            f"fora do vocabulário fechado. O vocabulário precisa ser revisto antes de publicar."
                        )

                    # Guarda (g): colunas numéricas como inteiros
                    for campo in CAMPOS_INTEIROS:
                        val_str = row_dict.get(campo, "0")
                        try:
                            int(val_str)
                        except ValueError:
                            raise SystemExit(
                                f"ERRO: linha {line_num} de {filepath}: campo '{campo}' "
                                f"contém valor não inteiro '{val_str}'"
                            )

                    mortos = int(row_dict["mortos"])

                    # Guarda (h): coerência Sem Vítimas / Fatais
                    if cla == "Sem Vítimas" and mortos > 0:
                        raise SystemExit(
                            f"ERRO: linha {line_num} de {filepath}: 'Sem Vítimas' com mortos > 0 ({mortos})"
                        )
                    if cla == "Com Vítimas Fatais" and mortos == 0:
                        raise SystemExit(
                            f"ERRO: linha {line_num} de {filepath}: 'Com Vítimas Fatais' com mortos == 0"
                        )

                    # Monta o registro final
                    # ano é sempre int e sempre o ano do arquivo
                    rec: Dict[str, Any] = {"ano": int(ano)}
                    for k, v in row_dict.items():
                        if k == "ano":
                            continue
                        if k in CAMPOS_INTEIROS:
                            rec[k] = int(v)
                        else:
                            rec[k] = v

                    yield rec

    except zipfile.BadZipFile:
        raise SystemExit(f"ERRO: arquivo {filepath} não é um ZIP válido")

    # Guarda (e): 12 meses presentes (1 a 7 para 2026)
    meses_esperados = set(range(1, 13)) if ano < 2026 else set(range(1, 8))
    faltando = meses_esperados - meses_vistos
    if faltando:
        raise SystemExit(
            f"ERRO: {filepath}: meses sem nenhuma ocorrência: {sorted(faltando)} — "
            f"cobertura temporal quebrada."
        )


def agregado(
    ano: int,
    raw_dir: Optional[pathlib.Path] = None,
    manifest_path: Optional[pathlib.Path] = None,
) -> Dict[str, Any]:
    """Processa a safra via streaming e devolve dict de agregados do ano."""
    total = 0
    com_vitima = 0
    feridas = 0
    fatais = 0
    sem_vitima = 0
    ignorado_ou_na = 0
    tot_mortos = 0
    tot_feridos = 0

    ids_vistos = set()
    ids_repetidos = set()

    for rec in registros(ano, raw_dir=raw_dir, manifest_path=manifest_path):
        total += 1
        cla = rec["classificacao_acidente"]
        if cla == "Com Vítimas Feridas":
            feridas += 1
            com_vitima += 1
        elif cla == "Com Vítimas Fatais":
            fatais += 1
            com_vitima += 1
        elif cla == "Sem Vítimas":
            sem_vitima += 1
        else:
            ignorado_ou_na += 1

        tot_mortos += rec["mortos"]
        tot_feridos += rec["feridos"]

        rec_id = rec["id"]
        if rec_id in ids_vistos:
            ids_repetidos.add(rec_id)
        else:
            ids_vistos.add(rec_id)

    return {
        "ano": int(ano),
        "total": total,
        "com_vitima": com_vitima,
        "feridas": feridas,
        "fatais": fatais,
        "sem_vitima": sem_vitima,
        "ignorado_ou_na": ignorado_ou_na,
        "mortos": tot_mortos,
        "feridos": tot_feridos,
        "id_duplicados": len(ids_repetidos),
    }


def por_classificacao(
    ano: int,
    raw_dir: Optional[pathlib.Path] = None,
    manifest_path: Optional[pathlib.Path] = None,
) -> Dict[str, int]:
    """Devolve a contagem de acidentes por classificacao_acidente no ano."""
    counts: Dict[str, int] = collections.defaultdict(int)
    for rec in registros(ano, raw_dir=raw_dir, manifest_path=manifest_path):
        counts[rec["classificacao_acidente"]] += 1
    return dict(counts)


def por_mes(
    ano: int,
    raw_dir: Optional[pathlib.Path] = None,
    manifest_path: Optional[pathlib.Path] = None,
) -> Dict[int, int]:
    """Devolve a contagem de acidentes por mês (1..12) no ano."""
    counts: Dict[int, int] = collections.defaultdict(int)
    for rec in registros(ano, raw_dir=raw_dir, manifest_path=manifest_path):
        d, m, y = _parse_data(rec["data_inversa"])
        counts[m] += 1
    return dict(counts)


def ler_todos_anos(
    raw_dir: Optional[pathlib.Path] = None,
    manifest_path: Optional[pathlib.Path] = None,
) -> Dict[int, Dict[str, Any]]:
    """Lê o manifest e processa cada safra uma por uma, devolvendo `{ano: agregado}`.

    ⚠️ Não acumula registros na memória. Devolve apenas os 20 dicts de agregados.
    """
    if raw_dir is None:
        raw_dir = DEFAULT_RAW_DIR
    if manifest_path is None:
        manifest_path = DEFAULT_MANIFEST_PATH

    if not manifest_path.exists():
        raise SystemExit(f"ERRO: manifest não encontrado em {manifest_path}")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    arquivos = manifest.get("arquivos", [])
    if not arquivos:
        raise SystemExit(f"ERRO: nenhuma safra anual em {manifest_path}")

    resultado: Dict[int, Dict[str, Any]] = {}
    for item in arquivos:
        ano = item["ano"]
        agr = agregado(ano, raw_dir=raw_dir, manifest_path=manifest_path)
        resultado[ano] = agr

    anos = sorted(resultado.keys())
    if anos != list(range(anos[0], anos[-1] + 1)):
        raise SystemExit(f"ERRO: safras com buraco no meio: {anos}")

    return resultado


def escopo_regime(ano: int) -> str:
    """Devolve o escopo de regime de registro para o ano (2007-2025)."""
    if 2007 <= ano <= 2014:
        return "registro_pleno_2007_2014"
    elif ano == 2015:
        return "registro_transicao_2015"
    elif 2016 <= ano <= 2017:
        return "registro_reduzido_2016_2017"
    elif ano == 2018:
        return "registro_transicao_2018"
    elif 2019 <= ano <= 2025:
        return "registro_minimo_2019_2025"
    else:
        raise ValueError(f"Ano {ano} fora do intervalo 2007-2025")


def gerar_series(
    raw_dir: Optional[pathlib.Path] = None,
    manifest_path: Optional[pathlib.Path] = None,
    series_dir: Optional[pathlib.Path] = None,
    agregados_por_ano: Optional[Dict[int, Dict[str, Any]]] = None,
) -> None:
    """Gera os CSVs de séries em bases/prf-acidentes/series/."""
    if raw_dir is None:
        raw_dir = DEFAULT_RAW_DIR
    if manifest_path is None:
        manifest_path = DEFAULT_MANIFEST_PATH
    if series_dir is None:
        series_dir = DEFAULT_SERIES_DIR

    series_dir.mkdir(parents=True, exist_ok=True)

    if agregados_por_ano is None:
        agregados_por_ano = ler_todos_anos(raw_dir=raw_dir, manifest_path=manifest_path)


    # 1) classificacao_por_ano_2007_2025.csv (Passo 3)
    path_cla = series_dir / "classificacao_por_ano_2007_2025.csv"
    linhas_cla = [["ano", "classificacao", "acidentes", "escopo", "harmonizada"]]
    for ano in range(2007, 2026):
        a = agregados_por_ano[ano]
        esc = escopo_regime(ano)
        tot = a["total"]
        fer = a["feridas"]
        fat = a["fatais"]
        sem = a["sem_vitima"]
        ign = a["ignorado_ou_na"]

        if fer + fat + sem + ign != tot:
            raise SystemExit(
                f"ERRO: ano {ano}: soma das classificações ({fer + fat + sem + ign}) diverge do total ({tot})"
            )

        linhas_cla.append([str(ano), "com_vitimas_feridas", str(fer), esc, "1"])
        linhas_cla.append([str(ano), "com_vitimas_fatais", str(fat), esc, "1"])
        linhas_cla.append([str(ano), "sem_vitimas", str(sem), esc, "1"])
        linhas_cla.append([str(ano), "ignorado_ou_na", str(ign), esc, "1"])

    with open(path_cla, "w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(linhas_cla)
    print(f"OK: gerado {path_cla} ({len(linhas_cla) - 1} linhas)")

    # 2) com_vitima_por_ano_2007_2025.csv (Passo 4)
    path_vit = series_dir / "com_vitima_por_ano_2007_2025.csv"
    linhas_vit = [["ano", "indicador", "valor", "escopo", "harmonizada"]]
    escopo_vit = "com_vitima_harmonizado_2007_2025"
    for ano in range(2007, 2026):
        a = agregados_por_ano[ano]
        com_v = a["com_vitima"]
        fat = a["fatais"]
        mort = a["mortos"]
        fer = a["feridos"]
        tx_mort = f"{(mort / com_v) * 100:.2f}"

        linhas_vit.append([str(ano), "acidentes_com_vitima", str(com_v), escopo_vit, "1"])
        linhas_vit.append([str(ano), "acidentes_fatais", str(fat), escopo_vit, "1"])
        linhas_vit.append([str(ano), "mortos", str(mort), escopo_vit, "1"])
        linhas_vit.append([str(ano), "feridos", str(fer), escopo_vit, "1"])
        linhas_vit.append([str(ano), "mortos_por_100_acidentes_com_vitima", tx_mort, escopo_vit, "1"])

    with open(path_vit, "w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(linhas_vit)
    print(f"OK: gerado {path_vit} ({len(linhas_vit) - 1} linhas)")

    # 3) indice_registro_2007_2025.csv (Passo 5)
    path_ind = series_dir / "indice_registro_2007_2025.csv"
    linhas_ind = [["ano", "serie", "indice", "escopo", "harmonizada"]]
    tot_2011 = agregados_por_ano[2011]["total"]
    vit_2011 = agregados_por_ano[2011]["com_vitima"]
    mor_2011 = agregados_por_ano[2011]["mortos"]

    for ano in range(2007, 2026):
        a = agregados_por_ano[ano]
        esc_tot = escopo_regime(ano)
        tot = a["total"]
        vit = a["com_vitima"]
        mor = a["mortos"]

        ind_tot = f"{(tot / tot_2011) * 100:.1f}"
        ind_vit = f"{(vit / vit_2011) * 100:.1f}"
        ind_mor = f"{(mor / mor_2011) * 100:.1f}"

        linhas_ind.append([str(ano), "todos_os_registros", ind_tot, esc_tot, "1"])
        linhas_ind.append([str(ano), "acidentes_com_vitima", ind_vit, escopo_vit, "1"])
        linhas_ind.append([str(ano), "mortos", ind_mor, escopo_vit, "1"])

    with open(path_ind, "w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(linhas_ind)
    print(f"OK: gerado {path_ind} ({len(linhas_ind) - 1} linhas)")



def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw-dir", type=pathlib.Path, default=DEFAULT_RAW_DIR)
    ap.add_argument("--manifest", type=pathlib.Path, default=DEFAULT_MANIFEST_PATH)
    ap.add_argument("--series-dir", type=pathlib.Path, default=DEFAULT_SERIES_DIR)
    args = ap.parse_args()

    # Processa todas as safras em streaming
    agregados_por_ano = ler_todos_anos(raw_dir=args.raw_dir, manifest_path=args.manifest)

    print("OK: leitor único de acidentes PRF (2007-2026)")
    total_ocorrencias = 0
    for ano in sorted(agregados_por_ano.keys()):
        agr = agregados_por_ano[ano]
        tot = agr["total"]
        total_ocorrencias += tot
        sem_vit = agr["sem_vitima"]
        com_vit = agr["com_vitima"]
        mortos = agr["mortos"]
        feridos = agr["feridos"]
        dup_ids = agr["id_duplicados"]
        print(
            f"  {ano}: {tot:>8,d} acidentes | Sem Vítimas: {sem_vit:>7,d} | "
            f"Com Vítima: {com_vit:>7,d} | Mortos: {mortos:>5,d} | Feridos: {feridos:>7,d} | "
            f"IDs repetidos: {dup_ids}"
        )

    print(f"Total: {total_ocorrencias:>10,d} ocorrências processadas.")

    # Medição rígida de memória (pico de RSS)
    rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    rss_mb = rss_kb / 1024.0
    print(f"Pico de RSS: {rss_mb:.2f} MB ({rss_kb} KB)")

    # Limite rígido de 1 GB (1.048.576 KB ou 1.000.000 KB)
    if rss_mb > 1000.0:
        raise SystemExit(
            f"ERRO DE MEMÓRIA: pico de RSS foi {rss_mb:.2f} MB, excedendo o teto de 1 GB!"
        )

    # Verificações de reconciliação de reconhecimento prévio
    # 2011: 192.326 linhas e 118.745 Sem Vítimas
    a2011 = agregados_por_ano[2011]
    if a2011["total"] != 192326 or a2011["sem_vitima"] != 118745:
        raise SystemExit(
            f"DIVERGÊNCIA 2011: esperado (192326 total, 118745 sem vítima), "
            f"obtido ({a2011['total']} total, {a2011['sem_vitima']} sem vítima)"
        )

    # 2025: 72.529 total, 11.138 Sem Vítimas, 61.390 com vítima, 6.043 mortos
    a2025 = agregados_por_ano[2025]
    if (
        a2025["total"] != 72529
        or a2025["sem_vitima"] != 11138
        or a2025["com_vitima"] != 61390
        or a2025["mortos"] != 6043
    ):
        raise SystemExit(
            f"DIVERGÊNCIA 2025: esperado (72529, 11138 sem vit, 61390 com vit, 6043 mortos), "
            f"obtido ({a2025['total']}, {a2025['sem_vitima']}, {a2025['com_vitima']}, {a2025['mortos']})"
        )

    # 2016: 96.363 linhas
    a2016 = agregados_por_ano[2016]
    if a2016["total"] != 96363:
        raise SystemExit(
            f"DIVERGÊNCIA 2016: esperado 96363 total, obtido {a2016['total']}"
        )

    # 2026: 42.322 linhas e 7 meses
    a2026 = agregados_por_ano[2026]
    if a2026["total"] != 42322:
        raise SystemExit(
            f"DIVERGÊNCIA 2026: esperado 42322 total, obtido {a2026['total']}"
        )

    gerar_series(
        raw_dir=args.raw_dir,
        manifest_path=args.manifest,
        series_dir=args.series_dir,
        agregados_por_ano=agregados_por_ano,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

