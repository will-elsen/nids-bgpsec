#!/usr/bin/env python3
"""Execute a notebook's code cells in order, the way a kernel would.

    python3 tools/run_notebook.py nids-bgpsec.ipynb   (from the repo root)

Runs every code cell sequentially in one shared namespace and stops at the
first exception, reporting which cell failed and its source. This is the
check behind the phase's exit criterion — that a student can open the
notebook and run it top to bottom without help — and it deliberately runs the
exact source in the .ipynb rather than the builder's input, so a mistake in
the build step cannot hide.

`nbconvert --execute` would be the obvious tool; it is not installed here and
this lab should not require adding packages to a student's machine to verify
itself.
"""
import json
import os
import sys
import time
import traceback

path = sys.argv[1] if len(sys.argv) > 1 else "nids-bgpsec.ipynb"
# Python puts *this script's* directory on sys.path; a Jupyter kernel puts the
# notebook's. Match the kernel, or `import labkit` fails here and only here.
sys.path.insert(0, os.path.dirname(os.path.abspath(path)))
notebook = json.load(open(path, encoding="utf-8"))
cells = [c for c in notebook["cells"] if c["cell_type"] == "code"]

namespace: dict = {"__name__": "__main__"}
start = time.time()
failures = 0

for n, cell in enumerate(cells, 1):
    source = "".join(cell["source"])
    if not source.strip() or all(l.strip().startswith("#") for l in source.strip().splitlines()):
        continue
    first = source.strip().splitlines()[0]
    print(f"\n\033[1m--- cell {n}/{len(cells)}  ({time.time() - start:.0f}s)  {first}\033[0m")
    try:
        exec(compile(source, f"<cell {n}>", "exec"), namespace)
    except Exception:
        failures += 1
        print(f"\n\033[31mCELL {n} RAISED\033[0m\n{source}")
        traceback.print_exc()
        break

print(f"\n{'=' * 60}")
print(f"{len(cells)} code cells, {failures} raised, {(time.time() - start) / 60:.1f} min")
sys.exit(1 if failures else 0)
