"""Fail if any Python code uses randomness outside the RngFactory module (reproducibility rule)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEARCH_DIRS = [ROOT / "packages", ROOT / "services"]
# The only place allowed to create random generators (added in Phase 2).
ALLOWED = re.compile(r"[\\/]rng[\\/]")
PATTERNS = [
    re.compile(r"^\s*import\s+random\b"),
    re.compile(r"^\s*from\s+random\s+import\b"),
    re.compile(r"\bnumpy\.random\b"),
    re.compile(r"\bnp\.random\b"),
    re.compile(r"^\s*from\s+numpy\s+import\s+.*\brandom\b"),
    re.compile(r"\bsecrets\.|\buuid\.uuid4\("),
]


def main() -> int:
    violations: list[str] = []
    for base in SEARCH_DIRS:
        for path in base.rglob("*.py"):
            rel = path.relative_to(ROOT)
            if ALLOWED.search(str(rel)) or "tests" in rel.parts or ".venv" in rel.parts:
                continue
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if any(p.search(line) for p in PATTERNS):
                    violations.append(f"{rel}:{lineno}: {line.strip()}")
    if violations:
        print("Randomness outside RngFactory is not allowed:")
        print("\n".join(f"  {v}" for v in violations))
        return 1
    print("RNG check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
