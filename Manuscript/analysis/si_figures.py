"""Supplementary figures S2-S6 of the Formulator-Pen manuscript, regenerated from the dataset.

S2, S3, S5, S6: one figure per strategy (Fill-and-Dispense, Remote-Reservoir, On-Board Reservoir,
Pressurized On-Board) with the same seven panels. S4: job-time breakdown of Remote-Reservoir versus
Pressurized On-Board at the two shared viscosities. Viscosities are the measured values (Table 2).

Usage: python si_figures.py <formulatorpen.csv> <schematics_dir> <out_dir>
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from PIL import Image
from scipy import stats

CSV, SCHEM, OUT = (Path(a) for a in sys.argv[1:4])
OUT.mkdir(parents=True, exist_ok=True)

plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Arial"]
LABEL_FS, TICK_FS, LEGEND_FS, PANEL_FS = 17, 14, 12.5, 22

VISC_MEASURED = {1: 1, 1000: 1000, 5000: 5765, 12500: 14570, 30000: 31870, 38000: 37020, 60000: 69080}
DENSITY = {1: 0.998, 1000: 1.261}          # g/mL; silicone oils 0.973
FLUID_COLORS = {1: "#4285F4", 1000: "#EA4335", 5765: "#FBBC04", 14570: "#34A853", 31870: "#8E44AD",
                37020: "#FF6D01", 69080: "#6D4C41"}
MECH = {3: ("Fill-and-Dispense", "Image_002_1.tif", "figureS2_fill_and_dispense"),
        4: ("Remote-Reservoir", "Image_003_1.tif", "figureS3_remote_reservoir"),
        5: ("On-Board Reservoir", "Image_004_1.tif", "figureS5_onboard_reservoir"),
        6: ("Pressurized On-Board", "Image_005_1.tif", "figureS6_pressurized_onboard")}
RUNS = [f"Run{i}" for i in range(1, 11)]

df = pd.read_csv(CSV, na_values="NULL")
df["Viscosity (cP)"] = df["Viscosity (cP)"].map(VISC_MEASURED)
df["mean"] = df[RUNS].mean(axis=1)
df["sd"] = df[RUNS].std(axis=1)
df["cv"] = df["sd"] / df["mean"] * 100
df["err"] = (df["mean"] - df["Volume (g)"]) / df["Volume (g)"] * 100

def vlabel(v):
    return f"{v:,} cP"

def style(ax):
    for sp in ax.spines.values():
        sp.set_linewidth(1.4)
    ax.tick_params(labelsize=TICK_FS, width=1.4, length=4)
    ax.xaxis.label.set_fontsize(LABEL_FS); ax.yaxis.label.set_fontsize(LABEL_FS)

def letter(fig, ax, s, dx=-0.045):
    bb = ax.get_position()
    fig.text(bb.x0 + dx, bb.y1 + 0.02, s, fontsize=PANEL_FS, va="bottom", ha="left")

def strategy_figure(proto):
    name, img, stem = MECH[proto]
    d = df[df["Prototype"] == proto]
    cal = d[d["Data Type"] == "Calibration"]
    val = d[d["Data Type"] == "Test"]
    viscs = sorted(cal["Viscosity (cP)"].unique())

    fig = plt.figure(figsize=(21, 10.5))
    gs = gridspec.GridSpec(2, 4, figure=fig, width_ratios=[1.15, 1, 1, 1], hspace=0.42, wspace=0.38,
                           left=0.01, right=0.985, top=0.93, bottom=0.08)
    axA = fig.add_subplot(gs[:, 0]); axB = fig.add_subplot(gs[0, 1]); axC = fig.add_subplot(gs[0, 2])
    axD = fig.add_subplot(gs[0, 3]); axE = fig.add_subplot(gs[1, 1]); axF = fig.add_subplot(gs[1, 2])
    axG = fig.add_subplot(gs[1, 3])

    axA.imshow(Image.open(SCHEM / img).convert("RGBA")); axA.axis("off")
    fig.text(0.012, 0.965, name, fontsize=PANEL_FS, fontweight="bold", va="center", ha="left")

    # B: pre-calibration dispensed vs target
    top = 0
    for v in viscs:
        s = cal[cal["Viscosity (cP)"] == v].sort_values("Volume (g)")
        axB.errorbar(s["Volume (g)"], s["mean"], yerr=s["sd"], fmt="o-", color=FLUID_COLORS[v], label=vlabel(v),
                     capsize=3, lw=1.8, ms=5)
        top = max(top, s["Volume (g)"].max())
    axB.plot([0, top * 1.05], [0, top * 1.05], "k--", lw=1.2, alpha=0.6, label="ideal")
    axB.set_xlabel("Target mass (g)"); axB.set_ylabel("Dispensed mass (g)")
    axB.legend(fontsize=LEGEND_FS - 1, frameon=False, loc="upper left")

    # C: pre-calibration slope (mass and volumetric) and RMSE
    x = np.arange(len(viscs)); slopes, vslopes, rmses = [], [], []
    for v in viscs:
        s = cal[cal["Viscosity (cP)"] == v].sort_values("Volume (g)")
        fit = stats.linregress(s["Volume (g)"], s["mean"])
        rho = DENSITY.get({b: a for a, b in VISC_MEASURED.items()}[v], 0.973)
        slopes.append(fit.slope); vslopes.append(fit.slope / rho)
        rmses.append(np.sqrt(((s["mean"] - (fit.slope * s["Volume (g)"] + fit.intercept)) ** 2).mean()))
    axC.bar(x - 0.19, slopes, 0.38, color=[FLUID_COLORS[v] for v in viscs], edgecolor="black", lw=0.8, label="slope a")
    axC.bar(x + 0.19, vslopes, 0.38, color=[FLUID_COLORS[v] for v in viscs], edgecolor="black", lw=0.8, alpha=0.45,
            hatch="//", label="volumetric slope a/ρ")
    axC.axhline(1, color="black", ls="--", lw=1.1)
    axC.set_xticks(x); axC.set_xticklabels([vlabel(v) for v in viscs], rotation=35, ha="right")
    axC.set_ylabel("Pre-calibration slope"); axC.set_ylim(0.85, max(1.3, max(slopes) + 0.05))
    axC2 = axC.twinx()
    axC2.plot(x, rmses, "D--", color="#174EA6", ms=7, lw=1.4)
    axC2.set_ylabel("RMSE (g)", color="#174EA6", fontsize=LABEL_FS); axC2.tick_params(colors="#174EA6", labelsize=TICK_FS)
    axC2.set_ylim(0, max(0.045, max(rmses) * 1.3))
    axC.legend(fontsize=LEGEND_FS - 1.5, frameon=False, loc="upper right")

    # D and E: post-calibration error and CV (validation runs)
    for v in sorted(val["Viscosity (cP)"].unique()):
        s = val[val["Viscosity (cP)"] == v].sort_values("Volume (g)")
        axD.plot(s["Volume (g)"], s["err"], "o-", color=FLUID_COLORS[v], lw=1.8, ms=6, label=vlabel(v))
        axE.plot(s["Volume (g)"], s["cv"], "o-", color=FLUID_COLORS[v], lw=1.8, ms=6, label=vlabel(v))
    axD.axhline(0, color="black", ls="--", lw=1.1)
    for yy in (-2, 2):
        axD.axhline(yy, color="#EA4335", ls=":", lw=1.1)
    axD.set_xlabel("Target mass (g)"); axD.set_ylabel("Systematic error (%)")
    axE.axhline(2, color="#34A853", ls=":", lw=1.2)
    axE.set_xlabel("Target mass (g)"); axE.set_ylabel("CV (%)")
    axD.legend(fontsize=LEGEND_FS - 1, frameon=False)

    # F: job time vs target
    for v in sorted(val["Viscosity (cP)"].unique()):
        s = val[(val["Viscosity (cP)"] == v) & val["Mean Job Time Total (s)"].notna()].sort_values("Volume (g)")
        axF.plot(s["Volume (g)"], s["Mean Job Time Total (s)"] / 60, "o-", color=FLUID_COLORS[v], lw=1.8, ms=6)
    axF.set_xlabel("Target mass (g)"); axF.set_ylabel("Job time (min)")

    # G: strategy-specific panel
    if proto == 3:
        for dtype, lab, c, m in (("Test", "1× step", "#4285F4", "o"), ("Test (2x)", "2× step", "#34A853", "^"),
                                 ("Test (3x)", "3× step", "#EA4335", "s")):
            s = d[(d["Data Type"] == dtype) & (d["Viscosity (cP)"] == 14570)].sort_values("Volume (g)")
            axG.plot(s["Volume (g)"], s["Mean Job Time Total (s)"] / 60, marker=m, color=c, lw=1.8, ms=6, label=lab)
        axG.set_xlabel("Target mass (g)"); axG.set_ylabel("Job time (min)")
        axG.legend(fontsize=LEGEND_FS, frameon=False, title="14,570 cP", title_fontsize=LEGEND_FS)
    else:
        s3 = val[np.isclose(val["Volume (g)"], 3.0) & val["Mean Job Time In (s)"].notna()].sort_values("Viscosity (cP)")
        xs = np.arange(len(s3))
        tin, tout, tmisc = (s3[c].values / 60 for c in ("Mean Job Time In (s)", "Mean Job Time Out (s)", "Mean Job Time Misc (s)"))
        axG.bar(xs, tin, 0.6, color="#4285F4", label="intake")
        axG.bar(xs, tout, 0.6, bottom=tin, color="#34A853", label="dispense")
        axG.bar(xs, tmisc, 0.6, bottom=tin + tout, color="#EA4335", label="misc")
        axG.set_xticks(xs); axG.set_xticklabels([vlabel(v) for v in s3["Viscosity (cP)"]], rotation=35, ha="right")
        axG.set_ylabel("Time at 3.0 g (min)")
        axG.legend(fontsize=LEGEND_FS, frameon=False)

    for ax in (axB, axC, axD, axE, axF, axG):
        style(ax)
    for ax, s in ((axB, "B"), (axC, "C"), (axD, "D"), (axE, "E"), (axF, "F"), (axG, "G")):
        letter(fig, ax, s)
    fig.text(0.012, 0.92, "A", fontsize=PANEL_FS, va="top", ha="left")
    fig.savefig(OUT / f"{stem}.svg", format="svg")
    fig.savefig(OUT / f"{stem}.png", dpi=300)
    plt.close(fig)

def jobtime_figure():
    """S4: intake / dispense / misc time, Remote-Reservoir vs Pressurized On-Board, shared viscosities."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.6), sharey=True)
    fig.subplots_adjust(left=0.08, right=0.99, bottom=0.2, top=0.86, wspace=0.08)
    for ax, target, lab in zip(axes, (1.0, 3.0), "AB"):
        ticks, labels = [], []
        for gi, v in enumerate((14570, 37020)):
            for si, (proto, name) in enumerate(((4, "Remote"), (6, "Pressurized"))):
                r = df[(df["Prototype"] == proto) & (df["Data Type"] == "Test") & (df["Viscosity (cP)"] == v)
                       & np.isclose(df["Volume (g)"], target)].iloc[0]
                xpos = gi * 2.6 + si
                parts = [r["Mean Job Time In (s)"] / 60, r["Mean Job Time Out (s)"] / 60, r["Mean Job Time Misc (s)"] / 60]
                bottom = 0
                for val_, c in zip(parts, ("#4285F4", "#34A853", "#EA4335")):
                    ax.bar(xpos, val_, 0.8, bottom=bottom, color=c, edgecolor="black", lw=0.6)
                    bottom += val_
                ax.text(xpos, bottom + 0.25, f"{bottom:.2f}", ha="center", va="bottom", fontsize=TICK_FS - 1)
                ticks.append(xpos); labels.append(f"{name}\n{v:,} cP")
        ax.set_xticks(ticks); ax.set_xticklabels(labels, fontsize=TICK_FS - 1)
        ax.set_title(f"{target:.1f} g target", fontsize=LABEL_FS)
        style(ax)
        bb = ax.get_position(); fig.text(bb.x0 - 0.05, bb.y1 + 0.04, lab, fontsize=PANEL_FS)
    axes[0].set_ylabel("Job time (min)")
    axes[0].set_ylim(0, 22)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in ("#4285F4", "#34A853", "#EA4335")]
    fig.legend(handles, ["intake", "dispense", "misc"], ncol=3, loc="upper center", frameon=False, fontsize=LEGEND_FS + 1)
    fig.savefig(OUT / "figureS4_jobtime_remote_vs_pressurized.svg", format="svg")
    fig.savefig(OUT / "figureS4_jobtime_remote_vs_pressurized.png", dpi=300)
    plt.close(fig)

for p in MECH:
    strategy_figure(p)
jobtime_figure()
print("saved SI figures to", OUT)
