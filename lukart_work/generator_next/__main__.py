"""Run a built-in synthetic example; intentionally no case-file input option."""
import argparse
import json
from pathlib import Path
import subprocess
from hashlib import sha256

from .demo import synthetic_case
from .service import CATALOGUE, CodeIdentity, propose, verify_candidate, write_candidate


def main():
    parser = argparse.ArgumentParser(description="Synthetic-only Generator Next recovery candidate")
    parser.add_argument("--type", choices=tuple(CATALOGUE), default="payment")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true", help="Read an existing demo after restart")
    args = parser.parse_args()
    # Pin code provenance to this module's checkout, never the caller's directory.
    root = Path(__file__).resolve().parents[2]
    dirty = subprocess.check_output(["git", "-C", str(root), "status", "--porcelain",
        "--untracked-files=all", "--", "lukart_work"], text=True)
    sha = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    runtime = sha256()
    for source in sorted((root / "lukart_work").rglob("*")):
        if source.is_file() and source.suffix in (".py", ".sql", ".js"):
            name = source.relative_to(root).as_posix().encode("utf-8")
            data = source.read_bytes()
            runtime.update(len(name).to_bytes(8, "big") + name + len(data).to_bytes(8, "big") + data)
    identity = CodeIdentity(sha, runtime.hexdigest(), "UNCOMMITTED" if dirty.strip() else "CLEAN")
    view, intake = synthetic_case(args.type)
    proposal = propose(view, intake)
    if not args.verify:
        write_candidate(proposal, args.output, identity=identity)
    result = verify_candidate(args.output, expected_input_hash=proposal.input_hash, identity=identity)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
