"""The write-up's three figures, drawn only from outputs/results (no numbers typed here).

Usage:  python -m lorehaven.figures      -> outputs/figures/fig1_*.png, fig2_*.png, fig3_*.png
Palette (validated with the dataviz validator, light mode, all pairs): orange #c46a00 (focus), blue #2a78d6,
aqua #1a9e8f. Single-series bars use one neutral plus the orange highlight.
"""
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from lorehaven.pipeline import RESULTS_DIR
from lorehaven.data_prep import REPO_ROOT

FIGURES_DIR = REPO_ROOT / "outputs" / "figures"
FIGURE_SIZE = (3.6, 2.6)   # inches; identical for all three so text prints at the same physical size
ORANGE, BLUE, AQUA = "#c46a00", "#2a78d6", "#1a9e8f"
INK, MUTED, GRID, NEUTRAL = "#1c2433", "#5d6779", "#e1e0d9", "#b7bfcc"
SEGMENT_LABELS = {"win_back": "Win-backs\n(former members, engaged)", "warm_listener": "Warm listeners\n(never members, engaged)",
                  "lapsed_low_podcast": "Former members,\nless engaged", "cold": "Cold\n(never members, less engaged)"}

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 7, "axes.edgecolor": GRID, "axes.labelcolor": MUTED,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.titlesize": 8.5, "axes.titleweight": "bold", "axes.titlecolor": INK, "figure.dpi": 300,
                     "text.parse_math": False})   # '$' is a currency sign here, not math markup


def _metrics():
    return json.loads((RESULTS_DIR / "metrics.json").read_text())


def figure_who_needs_the_offer():
    """Stacked bar per prospect segment, $12 era: joiners at list price vs extra joiners at $5 off."""
    uplift = pd.read_csv(RESULTS_DIR / "uplift_by_segment_base12.csv").set_index("segment")
    order = ["win_back", "warm_listener", "lapsed_low_podcast", "cold"]
    uplift = uplift.loc[order]
    fig, ax = plt.subplots(figsize=FIGURE_SIZE, layout="constrained")
    y = range(len(order))[::-1]
    ax.barh(y, 100 * uplift.p0_list, color=BLUE, height=0.55, label="Would join at list price (already sold)")
    ax.barh(y, 100 * uplift.uplift_5, left=100 * uplift.p0_list, color=ORANGE, height=0.55,
            edgecolor="white", linewidth=1.5, label="Join only with $5 off (persuadable)")
    for yi, (segment, row) in zip(y, uplift.iterrows()):
        total = 100 * (row.p0_list + row.uplift_5)
        ax.text(total + 1.5, yi, f"{total:.0f}% join\n{100 * row.share_of_prospects:.0f}% of prospects",
                va="center", fontsize=6.5, color=INK, linespacing=1.1)
    ax.set_yticks(list(y), [SEGMENT_LABELS[s] for s in order], fontsize=6.5)
    ax.set_xlim(0, 75)
    ax.set_xlabel("Sign-up rate per quarter (%)")
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    fig.suptitle("1. Who a $5 offer wins ($12 era)", x=0.02, ha="left", fontsize=8.5, fontweight="bold", color=INK)
    fig.legend(loc="outside lower center", fontsize=6.5, frameon=False, ncol=1,
               title="Assumes offers were as good as random and no one is put off by one", title_fontsize=6)
    fig.savefig(FIGURES_DIR / "fig1_who_the_offer_wins.png")
    plt.close(fig)


def figure_retention_by_tenure():
    """Observed retention by member price and tenure (dots) with the simulator curve (line), q9-q11."""
    fit = pd.read_csv(RESULTS_DIR / "model_fit_check_in_sample.csv")
    groups = [("member_first_renewal", "First renewal", ORANGE), ("member_second_renewal", "Second renewal", BLUE),
              ("member_established", "Third renewal on", AQUA)]
    fig, axes = plt.subplots(1, 2, figsize=FIGURE_SIZE, sharey=True, layout="constrained")
    for ax, segment, title in ((axes[0], "high_podcast", "Engaged listeners"), (axes[1], "low_podcast", "Less engaged")):
        for status, label, color in groups:
            rows = fit[(fit.segment == segment) & (fit.status == status)].sort_values("price")
            ax.plot(rows.price, 100 * rows.predicted, color=color, linewidth=1.6)
            ax.scatter(rows.price, 100 * rows.observed, color=color, s=14, edgecolor="white", linewidth=0.8, zorder=3, label=label)
        ax.set_title(title, loc="left", fontsize=7.5)
        ax.set_xticks(range(7, 12))
        ax.set_xlabel("Member price ($)")
        ax.yaxis.grid(True, color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
    axes[0].set_ylabel("Stay next quarter (%)")
    fig.suptitle("2. New members are the price-sensitive ones", x=0.02, ha="left", fontsize=8.5, fontweight="bold", color=INK)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside lower center", ncol=3, fontsize=6.5, frameon=False,
               title="Member tenure (dots = observed; lines = model fit to the same data)", title_fontsize=6.5)
    fig.savefig(FIGURES_DIR / "fig2_retention_by_tenure.png")
    plt.close(fig)


def figure_policy_value():
    """12-quarter revenue per 1,000 new prospects for the main policies (no win-back offers)."""
    metrics = _metrics()
    ltv = lambda name: metrics[f"scenario.{name}.ltv_per_1000_prospects"]["value"] / 1000
    rows = [("Today: random 25% offers,\nrandom $1-$5 member discounts", ltv("status_quo_2019"), NEUTRAL),
            ("$5 offer to all; every member $5 off", ltv("prospects_5_off_no_winback_members_5_off"), NEUTRAL),
            ("$5 offer to all; every member $1 off", ltv("prospects_5_off_no_winback_members_1_off"), NEUTRAL),
            ("$5 offer to all; every member $3 off\n(best single member discount)", ltv("prospects_5_off_no_winback_members_3_off"), NEUTRAL),
            ("Recommended: $5 offer to all; $5 off first\ntwo renewals, $1 off after", ltv("prospects_5_off_no_winback_new_5_off_established_1_off"), ORANGE)]
    fig, ax = plt.subplots(figsize=FIGURE_SIZE, layout="constrained")
    y = range(len(rows))[::-1]
    ax.barh(list(y), [r[1] for r in rows], color=[r[2] for r in rows], height=0.6)
    for yi, (_, value, _) in zip(y, rows):
        ax.text(value + 0.8, yi, f"${value:.1f}k", va="center", fontsize=6.5, color=INK)
    ax.set_yticks(list(y), [r[0] for r in rows], fontsize=6.5)
    ax.set_xlabel("Revenue per 1,000 prospects ($k)")
    ax.set_xlim(0, max(r[1] for r in rows) * 1.18)
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    fig.suptitle("3. Value of each policy (12 quarters, base $12)", x=0.02, ha="left", fontsize=8.5, fontweight="bold", color=INK)
    fig.savefig(FIGURES_DIR / "fig3_policy_value.png")
    plt.close(fig)


def main():
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    figure_who_needs_the_offer()
    figure_retention_by_tenure()
    figure_policy_value()
    print(f"wrote 3 figures to {FIGURES_DIR}")


if __name__ == "__main__":
    main()
