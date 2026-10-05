#!/usr/bin/env python3
r"""Figura de barras do Moran's I: coverage vs crash rate, por bin length.

Painel balanceado (anos_completos). Texto em ingles, grayscale-safe:
azul hachurado /// para coverage, vermelho hachurado ... para taxa.
"""
import csv
import pathlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = pathlib.Path(__file__).resolve().parent.parent
DADOS = ROOT / "build" / "moran_corredores.csv"
SAIDA = ROOT / "build" / "figuras-artigo" / "f2-moran.pdf"

PAINEL_RATE = "anos_completos"   # taxa: painel balanceado
PAINEL_COV = "sem_piso"          # coverage: painel completo (no balanceado é nan/constante)
FATOR = {"5": 3479, "10": 1851, "20": 1021}


def ler():
    with open(DADOS, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    rate = {r["tamanho_km"].strip(): r for r in rows if r["piso"] == PAINEL_RATE}
    cov = {r["tamanho_km"].strip(): r for r in rows if r["piso"] == PAINEL_COV}
    out = {}
    for km in ("5", "10", "20"):
        ic = float(cov[km]["moran_anos_I"])
        ir = float(rate[km]["moran_rate_I"])
        assert ic == ic and 0 < ic < 1, (km, ic)   # nan vira False aqui
        assert ir == ir and 0 < ir < 1, (km, ir)
        out[km] = {"n": int(rate[km]["n"]), "I_cov": ic, "I_rate": ir}
        assert out[km]["n"] == FATOR[km], (km, out[km]["n"])
    return out


def main():
    dados = ler()
    escalas = ["5", "10", "20"]
    esc_rot = ["5 km", "10 km", "20 km"]
    cov = [dados[k]["I_cov"] for k in escalas]
    rat = [dados[k]["I_rate"] for k in escalas]
    n = [dados[k]["n"] for k in escalas]

    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    x = list(range(len(escalas)))
    w = 0.38

    ax.bar([i - w / 2 for i in x], cov, width=w, color="#2c7bb6",
           edgecolor="black", linewidth=0.8, hatch="///",
           label="Coverage (usable exposure years per bin, full panel)")
    ax.bar([i + w / 2 for i in x], rat, width=w, color="#d7191c",
           edgecolor="black", linewidth=0.8, hatch="...",
           label="Crash rate per vehicle-km (balanced panel)")

    for i, (c, r) in enumerate(zip(cov, rat)):
        ax.text(i - w / 2, c + 0.015, f"{c:.3f}", ha="center", fontsize=9,
                color="#1a4e71")
        ax.text(i + w / 2, r + 0.015, f"{r:.3f}", ha="center", fontsize=9,
                color="#7a1010")
        ax.text(i, max(c, r) + 0.06, f"n (rate) = {n[i]:,}", ha="center",
                fontsize=8.5, color="#333333")

    ax.set_xticks(x)
    ax.set_xticklabels(esc_rot, fontsize=10)
    ax.set_xlabel("Bin length", fontsize=10)
    ax.set_ylabel("Global Moran's I", fontsize=10)
    ax.set_ylim(0, 0.95)
    ax.grid(axis="y", alpha=0.25, linewidth=0.5)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.legend(loc="upper right", fontsize=9, frameon=True, framealpha=0.95,
              edgecolor="#666666")
    fig.tight_layout()
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(SAIDA)
    fig.savefig(SAIDA.with_suffix(".png"), dpi=300)
    print("ok: f2-moran.pdf / .png")


if __name__ == "__main__":
    main()
