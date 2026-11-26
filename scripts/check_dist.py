"""Check the built wheel and sdist before publishing (T054).

Usage: python scripts/check_dist.py dist/

Asserts:
* py.typed, LICENSE and NOTICE are present;
* metadata: Requires-Python >=3.11, License-Expression Apache-2.0,
  Requires-Dist exactly httpx<1,>=0.27 and anyio>=4.0;
* the wheel is pure Python (py3-none-any) and contains no tests/ or specs/ files.

Exits non-zero (listing every problem) on failure. Standard library only.
"""

from __future__ import annotations

import sys
import tarfile
import zipfile
from email.parser import Parser
from pathlib import Path

EXPECTED_REQUIRES = {"httpx<1,>=0.27", "anyio>=4.0"}


def _normalise_requirement(req: str) -> str:
    return req.split(";", maxsplit=1)[0].replace(" ", "")


def check_wheel(path: Path) -> list[str]:
    problems: list[str] = []
    if not path.name.endswith("-py3-none-any.whl"):
        problems.append(f"{path.name}: not a pure-Python py3-none-any wheel")
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        meta_name = next((n for n in names if n.endswith(".dist-info/METADATA")), None)
        if meta_name is None:
            return [*problems, f"{path.name}: no METADATA"]
        meta = Parser().parsestr(zf.read(meta_name).decode())
    if "fvs_client/py.typed" not in names:
        problems.append("wheel: fvs_client/py.typed missing")
    for lic in ("LICENSE", "NOTICE"):
        if not any(n.endswith(f".dist-info/licenses/{lic}") for n in names):
            problems.append(f"wheel: {lic} missing from .dist-info/licenses/")
    bad = [n for n in names if n.startswith(("tests/", "specs/"))]
    if bad:
        problems.append(f"wheel: unexpected files {bad[:5]}")
    if meta.get("Requires-Python", "").replace(" ", "") != ">=3.11":
        problems.append(f"metadata: Requires-Python is {meta.get('Requires-Python')!r}")
    if meta.get("License-Expression") != "Apache-2.0":
        problems.append(f"metadata: License-Expression is {meta.get('License-Expression')!r}")
    requires = {_normalise_requirement(r) for r in meta.get_all("Requires-Dist") or []}
    if requires != EXPECTED_REQUIRES:
        problems.append(
            f"metadata: Requires-Dist is {sorted(requires)}, expected {sorted(EXPECTED_REQUIRES)}"
        )
    return problems


def check_sdist(path: Path) -> list[str]:
    problems: list[str] = []
    with tarfile.open(path) as tf:
        names = tf.getnames()
    for required in ("LICENSE", "NOTICE", "pyproject.toml", "src/fvs_client/py.typed"):
        if not any(n.endswith(f"/{required}") for n in names):
            problems.append(f"sdist: {required} missing")
    return problems


def main(argv: list[str]) -> int:
    dist = Path(argv[1] if len(argv) > 1 else "dist")
    wheels = sorted(dist.glob("fvs_client-*.whl"))
    sdists = sorted(dist.glob("fvs_client-*.tar.gz"))
    problems: list[str] = []
    if len(wheels) != 1:
        problems.append(f"expected exactly one wheel in {dist}, found {[w.name for w in wheels]}")
    if len(sdists) != 1:
        problems.append(f"expected exactly one sdist in {dist}, found {[s.name for s in sdists]}")
    for w in wheels:
        problems += check_wheel(w)
    for s in sdists:
        problems += check_sdist(s)
    for p in problems:
        print(f"FAIL: {p}", file=sys.stderr)
    if not problems:
        print(f"OK: {', '.join(p.name for p in [*wheels, *sdists])}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
