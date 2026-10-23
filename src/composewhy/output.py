"""Output formatters for human text and machine-readable JSON."""

import json
from typing import TextIO
import sys

from .models import ExplainResult
from . import __version__


def render_human_text(result: ExplainResult, stream: TextIO = sys.stdout) -> None:
    stream.write(f"ComposeWhy {__version__}\n")
    stream.write(f"SERVICE   {result.service}\n")
    stream.write(f"VARIABLE  {result.variable}\n")
    stream.write(f"STATUS    {result.status.upper()}\n\n")

    if result.status == "explained" and result.winner:
        stream.write("WINNER\n")
        path_str = f"{result.winner.path}:{result.winner.line}" if result.winner.line else str(result.winner.path)
        stream.write(f"  {path_str} — {result.winner.kind}.{result.winner.key}\n")
        if result.interpolation_source:
            stream.write(f"  Interpolation input: {result.interpolation_source}\n")
        stream.write("  Value: [REDACTED]\n\n")

        if result.candidates:
            stream.write("OVERRIDDEN OR UNUSED\n")
            for c in result.candidates:
                c_path = f"{c.source.path}:{c.source.line}" if c.source.line else str(c.source.path)
                note_str = f" ({c.note})" if c.note else ""
                stream.write(f"  {c_path} — {c.source.key}{note_str}\n")
            stream.write("\n")

        stream.write("WHY\n")
        stream.write(f"  {result.explanation}\n")

    else:
        # UNKNOWN or ERROR
        stream.write(f"REASON    {result.explanation}\n")
        if result.candidates:
            stream.write("\nCANDIDATES CONSIDERED\n")
            for c in result.candidates:
                c_path = f"{c.source.path}:{c.source.line}" if c.source.line else str(c.source.path)
                note_str = f" ({c.note})" if c.note else ""
                stream.write(f"  {c_path} — {c.source.key}{note_str}\n")
        stream.write("\nNEXT      Inspect the resolved model using: docker compose config (Warning: may expose secrets)\n")


def render_json(result: ExplainResult, stream: TextIO = sys.stdout) -> None:
    data = result.to_dict(product_version=__version__)
    stream.write(json.dumps(data, indent=2) + "\n")
