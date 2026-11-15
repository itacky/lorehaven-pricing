"""Build writeup.pdf from writeup.md. Every number in the text is a {{metrics.json key|format}} token.
Keys starting with crosscheck. come from outputs/robustness/crosscheck.json (the simple-vs-model comparison).

Usage:  python writeup/build.py          -> writeup/writeup.html and writeup/writeup.pdf (needs Chrome or Edge)
Formats: pct0 pct1 (share -> %), spct0 (signed %), pp1 (share -> percentage points), k1 ($ thousands),
         usd2, num2, num3, int.  An unknown key or format stops the build.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
METRICS = {**json.loads((ROOT / "outputs" / "results" / "metrics.json").read_text()),
           **json.loads((ROOT / "outputs" / "robustness" / "crosscheck.json").read_text())}
FORMATS = {
    "pct0": lambda v: f"{100 * v:.0f}%", "pct1": lambda v: f"{100 * v:.1f}%", "spct0": lambda v: f"{100 * v:+.0f}%",
    "pp1": lambda v: f"{100 * v:.1f}pp", "k1": lambda v: f"${v / 1000:.1f}k", "usd2": lambda v: f"${v:.2f}",
    "num2": lambda v: f"{v:.2f}", "num3": lambda v: f"{v:.3f}", "int": lambda v: f"{v:,.0f}",
}
TOKEN = re.compile(r"\{\{\s*([\w.\-]+)\s*\|\s*(\w+)\s*\}\}")


def fill_numbers(text: str) -> str:
    def replace(match):
        key, fmt = match.groups()
        if key not in METRICS:
            sys.exit(f"Unknown metrics key in write-up: {key}")
        if fmt not in FORMATS:
            sys.exit(f"Unknown format '{fmt}' for {key}")
        return FORMATS[fmt](METRICS[key]["value"])
    return TOKEN.sub(replace, text)


def find_browser():
    for name in ("google-chrome", "chrome", "chromium", "msedge"):
        if shutil.which(name):
            return shutil.which(name)
    for path in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                 r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"):
        if Path(path).exists():
            return path
    return None


def main():
    source = (ROOT / "writeup" / "writeup.md").read_text(encoding="utf-8")
    body = markdown.markdown(fill_numbers(source), extensions=["tables", "attr_list", "md_in_html"])
    css = (ROOT / "writeup" / "writeup.css").read_text(encoding="utf-8")
    html = f'<!doctype html><html><head><meta charset="utf-8"><style>{css}</style></head><body>{body}</body></html>'
    html_path = ROOT / "writeup" / "writeup.html"
    html_path.write_text(html, encoding="utf-8")
    browser = find_browser()
    if not browser:
        sys.exit(f"Wrote {html_path}. No Chrome/Edge found: open it and print to PDF.")
    pdf_path = ROOT / "writeup" / "writeup.pdf"
    subprocess.run([browser, "--headless", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={pdf_path}", html_path.as_uri()], check=True, capture_output=True)
    print(f"wrote {pdf_path}")


if __name__ == "__main__":
    main()
