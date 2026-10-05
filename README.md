# Next-Generation Road Safety — companion data & code

Open data and replication code for the manuscript:

> Camargo, D. — *Counting where it matters? Exposure coverage autocorrelation
> and hot-spot validity in network crash mapping* (submitted to the
> *Next-Generation Road Safety* Collection, **Discover Civil Engineering**).

**Thesis in one line:** the spatial coverage of the traffic-counting program
that produces the AADT denominator is itself strongly autocorrelated — so a
crash-rate map that does not control for coverage partly measures the
geography of the counting program, not the geography of risk.

Permanent archival of this repository via **Zenodo** (DOI will appear here
upon publication of the first release).

## What is here

| Path | Content |
|---|---|
| `build/painel_corredores.csv` | **The panel**: 5/10/20 km bins along the ten federal corridors (BR-050, BR-101, BR-116, BR-135, BR-153, BR-158, BR-163, BR-364, BR-376, BR-381; 23 UFs), key `(br, uf, km)`, 2017–2025, with crashes, vehicle-km exposure, usable-year coverage and AADT |
| `build/moran_corredores.csv` | Global Moran's I (crude rate, EB-smoothed rate, coverage) per band size × exposure cut, 9,999 permutations |
| `build/lisa_corredores.csv` | LISA per bin (quadrants, p-values, FDR control — Caldas de Castro & Singer 2006 local correction) |
| `build/mapa/faixas_lisa_10km_anos_completos.geojson` | Spatial layer of the 10 km bins with the LISA classification (the hot-spot map of the paper) |
| `build/inventario_corredores.csv` | Inventory of the panel (bins, extension, coverage) |
| `build/figuras-artigo/` | Publication figures (Moran figure, national rate map, national LISA map — PDF + PNG 300 dpi) |
| `bases/pnct-vmda/series/vmda_corredores_por_trecho_2017_2025.csv` | DNIT/PNCT annual AADT per SNV stretch, ten corridors (the exposure source) |
| `bases/prf-acidentes/series/` | PRF aggregate yearly series (national context) |
| `bases/prf-acidentes/resultados/` | Secondary analyses: coverage×rate conditional association, sampling-precision by coverage class, HH-drop LISA decomposition (CSV + `.prov.json`) |
| `bases/*/FONTE.md`, `bases/*/manifest.json` | Data-source documentation: URLs, SHA-256, access dates of every raw file |
| `bases/prf-acidentes/METODO-ESPACIAL.md` | **The methods document** (Portuguese): every methodological decision, measured pitfall and cut, with dates |
| `bin/` | The full pipeline code (see below) |
| `infra/requirements-geo.txt` | Pinned Python environment (geopandas/esda/libpysal stack) |
| `docs/fontes_dados.yaml` | Frozen provenance manifest of every input used by the manuscript (commits, SHA-256) |
| `raw/geo-referencia/manifest.json` | Provenance of the reference geodata (DNIT SNV WFS, IBGE/geobr meshes) — kept out of git, re-downloadable |

Not included (by design): raw crash ZIPs (~69 MB, PRF), raw PNCT spreadsheets
(~27 MB) and the reference meshes (~90 MB). Every one of them is documented
with URL + SHA-256 in the manifests above and is freely re-downloadable from
the official portals (PRF/DNIT open data; INDE/DNIT WFS; geobr). This mirrors
the source repository's discipline: raw files stay at the source, hashes are
the audit trail.

## Pipeline (order)

Reproduces everything from the derived panel down. Python interpreter must be
the geo stack (see *Environment*).

```bash
# analysis chain (panel is included; rebuild only if you redo the ETL)
python bin/moran_corredores.py                 # Moran + LISA -> build/moran_corredores.csv, build/lisa_corredores.csv
python bin/associacao_corredores.py            # conditional association -> bases/prf-acidentes/resultados/
python bin/precisao_corredores.py              # sampling precision by coverage class -> resultados/
python bin/lisa_decomposicao_hh.py             # HH-drop decomposition -> resultados/
python bin/gera_figura_moran.py                # Fig. 2 -> build/figuras-artigo/f2-moran.{pdf,png}
python bin/gera_mapa_corredores.py             # bins -> GeoJSON (needs SNV raw, see manifest)
python bin/gera_figura_mapa_nacional.py        # national maps (needs state mesh, see manifest)
```

Full ETL (optional — requires the raw files plus PostgreSQL/PostGIS, see
`bases/prf-acidentes/METODO-ESPACIAL.md`):

```bash
python bin/extrai_prf_acidentes.py             # PRF ZIPs -> series (checks SHA-256)
python bin/extrai_pnct_vmda.py                 # PNCT/DNIT AADT -> bases/pnct-vmda/series/
python bin/build_geo_referencia.py             # SNV + municipal mesh -> PostGIS
python bin/build_geo_prf.py                    # geocoded crashes -> PostGIS
python bin/mede_cobertura_vmda.py              # coverage measurement
python bin/painel_corredores.py                # PostGIS + VMDa -> build/painel_corredores.csv
```

## Environment

```bash
python3 -m venv .venv && .venv/bin/pip install -r infra/requirements-geo.txt
# then run the scripts with .venv/bin/python
```

Key pins: `geopandas 1.1.4`, `shapely 2.1.2`, `libpysal 4.15.0`, `esda 2.10.0`,
`matplotlib`. The panel-to-results chain is pure Python + these libs; PostGIS
is only needed to rebuild the panel from raw crashes.

## Provenance

Every file here descends from the audited internal pipeline repository
(`dados`, commit `fe3a1adc4e24e04bb5d28af65e4d3b5d56ff769e`, 2026-10-04);
`docs/fontes_dados.yaml` freezes the per-input commits and SHA-256 hashes that
the manuscript cites. Crash data: Polícia Rodoviária Federal open data (BAT,
occurrence-level). Exposure: PNCT/DNIT annual AADT. Network: DNIT SNV
(202507a) via INDE WFS. Meshes: IBGE via geobr (v1.7.0, 2024 edition).

## License

- **Code** (`bin/`, `infra/`): MIT — see `LICENSE`.
- **Data** (`build/`, `bases/`, `docs/`, `raw/` manifests): CC-BY-4.0 — see `LICENSE-DATA`.

Source data remain under their original terms (PRF/DNIT open-data portals;
Brazilian LGPD/Lei de Acesso à Informação framework).

## Citation

See `CITATION.cff` (GitHub renders it; Zenodo picks it up on release). Please
cite both the dataset DOI (Zenodo) and the paper.
