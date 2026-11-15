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
from matplotlib.patches import Rectangle

from lorehaven.pipeline import RESULTS_DIR   # noqa: I001
from lorehaven.data_prep import REPO_ROOT
from lorehaven.formatting import percents_summing_to_100

FIGURES_DIR = REPO_ROOT / "outputs" / "figures"
FIGURE_SIZE = (3.6, 2.6)   # inches; identical for all three so text prints at the same physical size
ORANGE, BLUE, AQUA = "#c46a00", "#2a78d6", "#1a9e8f"
INK, MUTED, GRID, NEUTRAL = "#1c2433", "#5d6779", "#e1e0d9", "#b7bfcc"
SHORT_SEGMENT_LABELS = {"win_back": "Win-backs", "warm_listener": "Warm listeners", "lapsed_low_podcast": "Former, less engaged",
                        "cold": "Cold prospects"}

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 7, "axes.edgecolor": GRID, "axes.labelcolor": MUTED,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.titlesize": 8.5, "axes.titleweight": "bold", "axes.titlecolor": INK, "figure.dpi": 300,
                     "text.parse_math": False})   # '$' is a currency sign here, not math markup


# Inputs:  outputs/results/metrics.json and CSV tables in outputs/results/
# Outputs: the three write-up figures in outputs/figures/ (PNG)


def _metrics():
    """Read outputs/results/metrics.json into a dict."""
    return json.loads((RESULTS_DIR / "metrics.json").read_text())


def figure_who_needs_the_offer():
    """Two panels per prospect segment ($12 era): join rate with $5 off, and sign-ups per 1,000 prospects.
    Both split into would join anyway (list-price rate) and join because of the offer (uplift at $5 off)."""
    signup = pd.read_csv(RESULTS_DIR / "signup_by_segment_and_discount.csv")
    uplift = signup[signup.discount_depth == 5].set_index("segment").rename(columns={"list_rate": "p0_list", "uplift": "uplift_5"})
    uplift["anyway_per_1000"] = 1000 * uplift.share_of_prospects * uplift.p0_list
    uplift["new_per_1000"] = 1000 * uplift.share_of_prospects * uplift.uplift_5
    uplift["total_per_1000"] = uplift.anyway_per_1000 + uplift.new_per_1000
    order = uplift.total_per_1000.sort_values(ascending=False).index.tolist()     # most sign-ups first
    share_pct = percents_summing_to_100(uplift.share_of_prospects.to_dict())
    fig, (rate_ax, volume_ax) = plt.subplots(1, 2, figsize=FIGURE_SIZE, layout="constrained", sharey=True,
                                             gridspec_kw={"width_ratios": [1, 1.05]})
    for y, segment in enumerate(order[::-1]):
        row = uplift.loc[segment]
        rate_ax.barh(y, 100 * row.p0_list, color=BLUE, height=0.55)
        rate_ax.barh(y, 100 * row.uplift_5, left=100 * row.p0_list, color=ORANGE, height=0.55, edgecolor="white", linewidth=1)
        rate_ax.text(100 * (row.p0_list + row.uplift_5) + 1.5, y, f"{100 * (row.p0_list + row.uplift_5):.0f}%", va="center", fontsize=6, color=INK)
        volume_ax.barh(y, row.anyway_per_1000, color=BLUE, height=0.55)
        volume_ax.barh(y, row.new_per_1000, left=row.anyway_per_1000, color=ORANGE, height=0.55, edgecolor="white", linewidth=1)
        volume_ax.text(row.total_per_1000 + 2, y, f"{row.total_per_1000:.0f}", va="center", fontsize=6, color=INK)
    rate_ax.set_yticks(range(len(order)), [f"{SHORT_SEGMENT_LABELS[s]}\n{share_pct[s]}% of prospects" for s in order[::-1]], fontsize=6)
    rate_ax.set_xlim(0, 72)
    volume_ax.set_xlim(0, 118)
    rate_ax.set_title("Join rate (%)", fontsize=6.5, color=MUTED, loc="left", fontweight="bold")
    volume_ax.set_title("Sign-ups per 1,000", fontsize=6.5, color=MUTED, loc="left", fontweight="bold")
    for ax in (rate_ax, volume_ax):
        ax.xaxis.grid(True, color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        ax.tick_params(axis="y", length=0)
    fig.suptitle("Who a $5 offer brings in: rate and volume", x=0.02, ha="left", fontsize=8.5, fontweight="bold", color=INK)
    legend = [Rectangle((0, 0), 1, 1, color=BLUE, label="Would join anyway"),
              Rectangle((0, 0), 1, 1, color=ORANGE, label="Join because of the $5 offer")]
    fig.legend(handles=legend, loc="outside lower center", ncol=2, fontsize=6.5, frameon=False,
               title="Assumes offers were as good as random and no one is put off by one. $12 era.", title_fontsize=5.6)
    fig.savefig(FIGURES_DIR / "fig1_who_the_offer_wins.png")
    plt.close(fig)


def figure_retention_by_tenure():
    """Observed share of members who stay, by price and tenure, $12 era (2019 spring-fall). No model."""
    stay = pd.read_csv(RESULTS_DIR / "stay_by_tenure_and_price.csv")
    groups = [("first_renewal", "First renewal", ORANGE), ("second_renewal", "Second renewal", BLUE),
              ("established", "Third renewal on", AQUA)]
    fig, axes = plt.subplots(1, 2, figsize=FIGURE_SIZE, sharey=True, layout="constrained")
    for ax, segment, title in ((axes[0], "high_podcast", "Engaged listeners"), (axes[1], "low_podcast", "Less engaged")):
        for status, label, color in groups:
            rows = stay[(stay.segment == segment) & (stay.tenure_group == status)].sort_values("membership_price")
            ax.plot(rows.membership_price, 100 * rows.rate, color=color, linewidth=1.6, marker="o", markersize=3.5,
                    markeredgecolor="white", markeredgewidth=0.8, label=label)
        ax.set_title(title, loc="left", fontsize=7.5)
        ax.set_xticks(range(7, 12))
        ax.set_xlabel("Member price ($)")
        ax.yaxis.grid(True, color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
    axes[0].set_ylabel("Stay next quarter (%)")
    fig.suptitle("New members are the price-sensitive ones", x=0.02, ha="left", fontsize=8.5, fontweight="bold", color=INK)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside lower center", ncol=3, fontsize=6.5, frameon=False,
               title="Member tenure (observed shares, $12 era)", title_fontsize=6.5)
    fig.savefig(FIGURES_DIR / "fig2_retention_by_tenure.png")
    plt.close(fig)


def figure_policy_value():
    """3-year revenue per 1,000 new prospects for the main policies (projection from observed rates, no win-back offers)."""
    metrics = _metrics()
    revenue = lambda name: metrics[f"policy.{name}.revenue_per_1000_prospects"]["value"] / 1000
    best = metrics["headline.best_single_member_discount"]["value"]
    rows = [("Today: random 25% offers,\nrandom $1-$5 member discounts", revenue("today"), NEUTRAL),
            ("$5 offer to all; every member $5 off", revenue("offer_5_members_5_off"), NEUTRAL),
            ("$5 offer to all; every member $1 off", revenue("offer_5_members_1_off"), NEUTRAL),
            (f"$5 offer to all; every member ${best} off\n(best single member discount)", revenue(f"offer_5_members_{best}_off"), NEUTRAL),
            ("Recommended: $5 offer to all; $5 off first\ntwo renewals, $1 off after", revenue("recommended"), ORANGE)]
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
    fig.suptitle("Value of each policy (3 years, base $12)", x=0.02, ha="left", fontsize=8.5, fontweight="bold", color=INK)
    fig.savefig(FIGURES_DIR / "fig3_policy_value.png")
    plt.close(fig)


def main():
    """Draw all three write-up figures into outputs/figures."""
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    figure_who_needs_the_offer()
    figure_retention_by_tenure()
    figure_policy_value()
    print(f"wrote 3 figures to {FIGURES_DIR}")


if __name__ == "__main__":
    main()
