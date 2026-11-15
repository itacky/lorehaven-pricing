"""Run the model-based appendix, then compare its answers with the simple pipeline's.

Usage:  python -m lorehaven.robustness   (needs the raw data and statsmodels/scipy; takes a few minutes)
"""
from lorehaven.robustness import advanced_pipeline, compare

# Inputs:  raw CSVs (via data_prep) and outputs/results/metrics.json from the simple pipeline
# Outputs: outputs/robustness/metrics.json, the comparison table and crosscheck.json

if __name__ == "__main__":
    advanced_pipeline.main()
    compare.main()
