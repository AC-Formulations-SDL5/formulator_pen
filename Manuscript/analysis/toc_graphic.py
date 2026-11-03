"""Table-of-contents graphic (8 cm x 4 cm): SVG plus 600-dpi PNG.

Left: the Cartesian gantry in oblique view, with a tool dock of parked Formulator-Pens at the
back and one pen held by the gantry Z axis, dispensing into a vial on the balance. Right: tested
viscosity range and job times at 37,020 cP.

Usage: python toc_graphic.py <output_stem>
"""
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyBboxPatch, Polygon, Rectangle

plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Arial"]
OUT = sys.argv[1] if len(sys.argv) > 1 else "toc_graphic"
INK, NAVY, BLUE, RED, YELLOW = "#1E2533", "#1F3F8F", "#2F6FD6", "#E5484D", "#F2C230"
FLUID, LW = "#5B8DEF", 0.7

fig = plt.figure(figsize=(8 / 2.54, 4 / 2.54))
ax = fig.add_axes([0.0, 0.0, 0.64, 1.0]); ax.set_xlim(-3, 86); ax.set_ylim(-4, 50); ax.set_aspect("equal"); ax.axis("off")

def P(x, y, z):
    """Oblique projection: depth y recedes to the upper right."""
    return (x + 0.5 * y, z + 0.3 * y)

def face(pts, fc, z=2, ec=INK, lw=LW):
    ax.add_patch(Polygon([P(*p) for p in pts], closed=True, facecolor=fc, edgecolor=ec, lw=lw, zorder=z, joinstyle="round"))

def box(x0, x1, y0, y1, z0, z1, top, front, side, z=2):
    face([(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], top, z)
    face([(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)], front, z)
    face([(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)], side, z)

def pen(x, y, z, s=1.0, body="#FFFFFF", fill=FLUID, zorder=6):
    """Pen glyph whose needle tip sits at world point (x, y, z)."""
    u, v = P(x, y, z)
    ax.plot([u, u], [v, v + 4.2 * s], color=INK, lw=0.9, zorder=zorder)
    ax.add_patch(Circle((u, v + 5.0 * s), 1.05 * s, facecolor=RED, edgecolor=INK, lw=LW, zorder=zorder + 1))
    ax.add_patch(FancyBboxPatch((u - 1.7 * s, v + 6.0 * s), 3.4 * s, 9.0 * s, boxstyle=f"round,pad=0,rounding_size={0.7 * s}",
                                facecolor=body, edgecolor=INK, lw=LW, zorder=zorder))
    ax.add_patch(Rectangle((u - 1.2 * s, v + 6.6 * s), 2.4 * s, 5.0 * s, facecolor=fill, edgecolor="none", zorder=zorder + 1))
    ax.add_patch(Rectangle((u - 0.5 * s, v + 15.0 * s), 1.0 * s, 2.2 * s, facecolor=INK, edgecolor=INK, lw=0.3, zorder=zorder))

def arrow(a, b, label, lpos, color=INK):
    ax.annotate("", xy=P(*b), xytext=P(*a), zorder=9,
                arrowprops=dict(arrowstyle="<|-|>", color=color, lw=0.8, mutation_scale=5))
    ax.text(*P(*lpos), label, fontsize=5.2, fontweight="bold", color=color, ha="center", va="center", zorder=9)

# base plate with dotted deck, corner feet
box(0, 60, 0, 40, 0, 2.2, "#ECEFF3", "#D5DAE2", "#C4CAD4", z=1)
for gx in range(8, 58, 7):
    for gy in range(6, 38, 7):
        ax.plot(*P(gx, gy, 2.25), marker=".", ms=0.8, color="#B5BCC8", zorder=1)
for fx, fy in ((0, 0), (56, 0), (0, 36), (56, 36)):
    box(fx, fx + 4, fy, fy + 4, -2.0, 0.6, "#3E7BE0", "#2A5FC0", "#1F4E9C", z=1)

def post(x, y):
    box(x, x + 3, y, y + 3, 2.2, 31, NAVY, "#173276", "#122860", z=2)

# back posts, side rails and the tool dock with parked, material-specific pens (behind)
post(2, 35); post(55, 35)
box(9, 10.5, 34, 35.5, 2.2, 15, "#B7BEC9", "#9AA3B1", "#8A94A3", z=2)
box(29, 30.5, 34, 35.5, 2.2, 15, "#B7BEC9", "#9AA3B1", "#8A94A3", z=2)
box(7, 32, 34, 36, 15, 16.6, YELLOW, "#D9A91C", "#C29516", z=3)
for px, body, fill in ((12.5, "#2B2F36", "#4F6FD8"), (19.5, "#FFFFFF", "#9DB7F2"), (26.5, "#FFFFFF", "#E3A35B")):
    pen(px, 35, 4.6, s=0.62, body=body, fill=fill, zorder=4)
ax.text(*P(19.5, 35, 20.5), "tool dock", fontsize=4.6, style="italic", color=INK, ha="center", va="center", zorder=9)

# balance with vial (front right)
box(35, 53, 3, 17, 2.2, 6.0, "#E9ECF1", "#D3D8E0", "#BFC6D1", z=5)
box(47.5, 51.5, 3, 3.6, 3.0, 5.2, "#123C8C", "#123C8C", "#123C8C", z=6)
box(41.5, 46.5, 8, 13, 6.0, 12.4, "#FFFFFF", "#FFFFFF", "#E8ECF3", z=6)
face([(41.5, 8, 6.4), (46.5, 8, 6.4), (46.5, 8, 9.6), (41.5, 8, 9.6)], FLUID, z=7, ec="none")

# side rails, cross beam, Z carriage, Z rod and the active pen
box(2, 5, 2, 38, 31, 33, "#E7EAEF", "#C9CFD9", "#B4BCC9", z=5)
box(55, 58, 2, 38, 31, 33, "#E7EAEF", "#C9CFD9", "#B4BCC9", z=5)
box(2, 58, 9, 13, 33, 36.5, "#E7EAEF", "#C9CFD9", "#B4BCC9", z=6)
box(39, 49, 6.5, 15.5, 29.5, 39, BLUE, "#2A5FC0", "#1F4E9C", z=7)
box(43, 45, 10, 12, 26.0, 29.5, "#B7BEC9", "#9AA3B1", "#8A94A3", z=7)
pen(44, 11, 13.6, s=0.80, zorder=8)
ax.add_patch(Polygon([P(43.6, 10.5, 13.0), P(44.4, 10.5, 13.0), P(44.0, 10.5, 12.0)], closed=True, facecolor=FLUID,
                     edgecolor="none", zorder=9))

# front posts (in front of everything on the deck)
post(2, 2); post(55, 2)

# axis arrows
arrow((16, 11, 41.5), (34, 11, 41.5), "X", (25, 11, 44.5))
arrow((63.5, 6, 0.5), (63.5, 30, 0.5), "Y", (68.5, 16, 0.5))
arrow((60.5, 11, 15), (60.5, 11, 26), "Z", (63.6, 11, 20.5))

# ---------------------------------------------------------------- right: results column
axr = fig.add_axes([0.64, 0.0, 0.36, 1.0]); axr.set_xlim(0, 30); axr.set_ylim(40, 0); axr.axis("off")
axr.add_patch(FancyBboxPatch((0.6, 1.0), 28.6, 38.0, boxstyle="round,pad=0,rounding_size=1.4", facecolor="#F3F6FC",
                             edgecolor="#9BB5E6", lw=0.6))
axr.text(15.0, 5.0, "1 → 69,080 cP", fontsize=6.6, fontweight="bold", color="#123C8C", ha="center", va="center")
axr.text(15.0, 9.2, "0.5–5 g, one pen per material", fontsize=4.5, color=INK, ha="center", va="center")
axr.text(15.0, 14.2, "job time, 3 g at 37,020 cP", fontsize=4.4, color=INK, ha="center", va="center", fontweight="bold")
for k, (lab, t, c) in enumerate((("remote", 19.44, BLUE), ("on-board", 5.43, BLUE), ("pressurized", 2.61, RED))):
    y = 17.8 + k * 4.2
    w = 9.0 * t / 19.44
    axr.add_patch(FancyBboxPatch((12.2, y - 1.25), max(w, 0.8), 2.5, boxstyle="round,pad=0,rounding_size=0.4",
                                 facecolor=c, edgecolor=INK, lw=LW))
    axr.text(11.6, y, lab, fontsize=4.2, color=INK, ha="right", va="center")
    axr.text(12.2 + w + 0.6, y, f"{t:.1f} min", fontsize=4.2, color=INK, ha="left", va="center")
axr.text(15.0, 33.5, "< US$200", fontsize=7.0, fontweight="bold", color=RED, ha="center", va="center")
axr.text(15.0, 36.6, "per pen", fontsize=4.6, color=INK, ha="center", va="center")

fig.savefig(OUT + ".svg", format="svg")
fig.savefig(OUT + ".png", dpi=600)
print("saved", OUT)
