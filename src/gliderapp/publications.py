from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence


DEFAULT_BIB = Path("bibtex/input/refs.bib")
DEFAULT_OUTPUT = Path("config/publications.html")
DEFAULT_SCRIPT = Path("bibtex/bib2html.sh")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Update config/publications.html from the project BibTeX file using Pandoc."
    )
    parser.add_argument(
        "bib",
        nargs="?",
        type=Path,
        default=DEFAULT_BIB,
        help=f"BibTeX input file (default: {DEFAULT_BIB})",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"HTML output file (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--script",
        type=Path,
        default=DEFAULT_SCRIPT,
        help=f"BibTeX conversion script (default: {DEFAULT_SCRIPT})",
    )
    return parser


def update_publications(argv: Sequence[str] | None = None) -> None:
    parser = _parser()
    args = parser.parse_args(argv)

    missing = [str(path) for path in (args.script, args.bib) if not path.exists()]
    if missing:
        parser.error(f"missing required file(s): {', '.join(missing)}")

    env = os.environ.copy()
    env.setdefault("PYTHON", sys.executable)
    subprocess.run([str(args.script), str(args.bib), str(args.output)], check=True, env=env)


if __name__ == "__main__":
    update_publications()
