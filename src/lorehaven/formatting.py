"""Display helpers shared by the figures and the tool (plain Python, so the tool still needs only Flask)."""


# Inputs:  numbers to display
# Outputs: the same numbers rounded for display (returned)

def percents_summing_to_100(shares: dict) -> dict:
    """Round shares (0-1) to whole percents that add up to exactly 100 (largest-remainder rounding)."""
    exact = {key: 100 * value / sum(shares.values()) for key, value in shares.items()}
    rounded = {key: int(value) for key, value in exact.items()}
    leftover = 100 - sum(rounded.values())
    for key in sorted(exact, key=lambda k: exact[k] - rounded[k], reverse=True)[:leftover]:
        rounded[key] += 1
    return rounded
