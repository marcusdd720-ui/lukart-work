"""Render the human-readable convergence note from the machine-readable SSOT."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lukart_work.convergence.contract import strict_json_loads

MANIFEST = ROOT / "contracts" / "cross_repo" / "v1" / "manifest.json"
OUTPUT = ROOT / "docs" / "CROSS_REPO_CONTRACT_CONVERGENCE.md"


def render(manifest: dict[str, object]) -> str:
    lines = [
        "# Cross-Repo Contract & Evidence Convergence",
        "",
        "> DERIVED VIEW — authoritative semantics live in "
        "`contracts/cross_repo/v1/manifest.json`, its schemas and profiles.",
        "",
        f"Contract: `{manifest['contract_id']}`",
        "",
        f"Architecture: **{manifest['architecture']}**.",
        "",
        "## Baselines",
        "",
        "| Repository | Commit | Role |",
        "|---|---|---|",
    ]
    for item in manifest["baselines"]:
        lines.append(
            f"| `{item['repository']}` | `{item['commit']}` | {item['role']} |"
        )
    lines += [
        "",
        "## Contract gap matrix",
        "",
        "| Area | Inventory | Resolution | Status |",
        "|---|---|---|---|",
    ]
    for row in manifest["gap_matrix"]:
        lines.append(
            f"| {row['area']} | {row['inventory']} | {row['resolution']} | "
            f"`{row['status']}` |"
        )
    lines += ["", "## Normative schema IDs", ""]
    lines.extend(f"- `{item}`" for item in manifest["schema_ids"])
    lines += ["", "## Invariants", ""]
    lines.extend(f"- {item}" for item in manifest["invariants"])
    lines += [
        "",
        "## Compatibility boundary",
        "",
        "Existing `lukart-work` and `lukart-ros` payloads remain authoritative in "
        "their own repositories. The convergence layer is an adapter/conformance "
        "boundary only: it does not rewrite historical payloads and has no "
        "`lukart-work -> lukart-ros` runtime dependency.",
        "",
        "Reporting is a derived view over canonical result/evidence/provenance "
        "semantics. This Markdown file is not an SSOT.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    manifest = strict_json_loads(MANIFEST.read_text(encoding="utf-8"))
    expected = render(manifest)
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != expected:
            raise SystemExit("DERIVED_DOC_DRIFT")
        print("PASS: derived convergence documentation is current.")
        return 0
    OUTPUT.write_text(expected, encoding="utf-8")
    print(OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
