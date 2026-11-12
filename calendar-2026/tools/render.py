#!/usr/bin/env python3
"""Write calendar-2026/.build/template.yaml: infra/calendar-2026/template.yaml with edge/function.js inlined."""
import pathlib
import sys

root = pathlib.Path(__file__).resolve().parent.parent          # calendar-2026/ (code)
template = (root.parent / "infra" / "calendar-2026" / "template.yaml").read_text()
js = (root / "edge" / "function.js").read_text()
marker = "      FunctionCode: __EDGE_FUNCTION_JS__"
line = next((l for l in template.splitlines() if l.startswith(marker)), None)
if line is None:
    sys.exit("placeholder not found in infra/calendar-2026/template.yaml")
if len(js.encode()) >= 10 * 1024:
    sys.exit("edge/function.js is over the 10 KB CloudFront Functions limit")
block = "      FunctionCode: |\n" + "".join("        " + l + "\n" for l in js.splitlines())
out = root / ".build" / "template.yaml"
out.parent.mkdir(exist_ok=True)
# the rendered file sits in .build/, so the code path must point one level up
out.write_text(template.replace(line + "\n", block).replace("    CodeUri: ../../calendar-2026/src/\n", "    CodeUri: ../src/\n"))
print(out)
