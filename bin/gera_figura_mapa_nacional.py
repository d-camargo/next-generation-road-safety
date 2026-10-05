#!/usr/bin/env python3
r"""Gera as figuras nacionais dos dez corredores para o artigo.

Duas variantes (PDF vetorial + PNG 300 dpi) em build/figuras-artigo/:

  1. mapa_lisa_nacional          — faixas 10 km coloridas por quadrante LISA
                                    (FDR ≤ 0,05 destacadas; demais em cinza);
  2. mapa_taxa_nacional          — faixas 10 km coloridas por taxa contínua
                                    (sinistros / 100M veíc-km), quantis.

Contexto: malha estadual simplificada 2019 (geobr), preenchimento claro e
contorno fino. Título NÃO vai na figura — vai na \caption do LaTeX.

Projeção de plotagem: Albers equal-conic ajustada ao Brasil (SIRGAS 2000) —
afigura sem a distorção "achatada" do plot em graus.

Fonte dos dados: build/mapa/faixas_lisa_10km_anos_completos.geojson
(gerado por bin/gera_mapa_corredores.py a partir do SNV 202507a).

Uso:
    ~/.venvs/geo/bin/python bin/gera_figura_mapa_nacional.py
"""
from __future__ import annotations

import pathlib

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT = pathlib.Path(__file__).resolve().parent.parent
LISA = ROOT / "build" / "mapa" / "faixas_lisa_10km_anos_completos.geojson"
STATES = ROOT / "raw" / "geo-referencia" / "states2019"
SAIDA = ROOT / "build" / "figuras-artigo"

# Albers equal-conic para o Brasil (SIRGAS 2000)
CRS_PLOT = "+proj=aea +lat_1=-5 +lat_2=-27 +lat_0=-15 +lon_0=-55 +ellps=GRS80 +units=m +no_defs"

COR_QUADRANTE = {
    "alto-alto": "#d7191c",      # vermelho: hotspot
    "baixo-baixo": "#2c7bb6",    # azul: coldspot
    "alto-baixo": "#fdae61",     # laranja: outlier alto cercado de baixo
    "baixo-alto": "#abd9e9",     # azul-claro: outlier baixo cercado de alto
}
COR_NAO_SIG = "#555555"

LARGURA_POL = 1.6      # espessura da faixa significativa (m => pt via escala)
LARGURA_CINZA = 0.6

LABEL_QUADRANTE = {
    "alto-alto": "High-High (hotspot)",
    "baixo-baixo": "Low-Low (coldspot)",
    "alto-baixo": "High-Low outlier",
    "baixo-alto": "Low-High outlier",
}


def base_ax(ax, estados):
    estados.plot(ax=ax, facecolor="#f4f4f0", edgecolor="#d0cfc9", linewidth=0.4, zorder=1)
    ax.set_axis_off()


def mapa_lisa(estados, lisa):
    fig, ax = plt.subplots(figsize=(9.5, 9.0))
    base_ax(ax, estados)
    nominal = lisa[lisa["p_valor"] < 0.05]
    nao_sig = lisa[lisa["p_valor"] >= 0.05]
    nao_sig.plot(ax=ax, color=COR_NAO_SIG, linewidth=0.8, zorder=2)
    for q in ("baixo-alto", "alto-baixo", "baixo-baixo", "alto-alto"):
        sub = nominal[nominal["quadrante"] == q]
        if len(sub):
            sub.plot(ax=ax, color=COR_QUADRANTE[q], linewidth=2.2, zorder=3)
    # FDR-significantes: marcador no centroide por cima
    fdr = lisa[lisa["significativo_fdr"]]
    for q in ("baixo-alto", "alto-baixo", "baixo-baixo", "alto-alto"):
        sub = fdr[fdr["quadrante"] == q]
        if len(sub):
            cent = sub.geometry.representative_point()
            ax.scatter(cent.x, cent.y, s=42, color=COR_QUADRANTE[q],
                       edgecolor="black", linewidth=0.5, zorder=4)
    handles = [Line2D([0], [0], color=c, lw=3, label=LABEL_QUADRANTE[q])
               for q, c in COR_QUADRANTE.items()]
    handles.append(Line2D([0], [0], color=COR_NAO_SIG, lw=2,
                          label="Not significant (p >= 0.05)"))
    handles.append(Line2D([0], [0], marker="o", color="none", markerfacecolor="white",
                          markeredgecolor="black", markersize=9,
                          label="Circled: significant after FDR (q <= 0.05)"))
    ax.legend(handles=handles, loc="lower left", fontsize=9, frameon=True,
              framealpha=0.95, edgecolor="#cccccc", title="LISA clusters (p < 0.05)")
    ax.get_legend().get_title().set_fontsize(9)
    return fig


def mapa_taxa(estados, lisa):
    fig, ax = plt.subplots(figsize=(9.5, 9.0))
    base_ax(ax, estados)
    lisa = lisa.copy()
    lisa["taxa"] = lisa["taxa_por_100M_veic_km"]
    lisa.plot(ax=ax, column="taxa", cmap="YlOrRd", scheme="quantiles", k=5,
              linewidth=2.2, zorder=3, legend=True,
              legend_kwds={"loc": "lower left", "fontsize": 8, "title": "Crashes per 100 M veh-km",
                           "interval": True})
    leg = ax.get_legend()
    if leg:
        leg.get_title().set_fontsize(9)
    return fig


def main():
    SAIDA.mkdir(parents=True, exist_ok=True)
    lisa = gpd.read_file(LISA).to_crs(CRS_PLOT)
    estados = gpd.GeoDataFrame(
        pd_concat := __import__("pandas").concat(
            [gpd.read_file(f) for f in sorted(STATES.glob("*.gpkg"))], ignore_index=True
        ),
        crs="EPSG:4674",
    ).to_crs(CRS_PLOT)

    for nome, fn in (
        ("mapa_lisa_nacional", mapa_lisa),
        ("mapa_taxa_nacional", mapa_taxa),
    ):
        fig = fn(estados, lisa)
        fig.savefig(SAIDA / f"{nome}.pdf", bbox_inches="tight")
        fig.savefig(SAIDA / f"{nome}.png", dpi=300, bbox_inches="tight")
        plt.close(fig)
        print(f"ok: {nome}.pdf / .png")


if __name__ == "__main__":
    main()
