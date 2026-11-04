"""Run the local LEGAL OS host behind native Windows SSPI."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from examples.human_case_operator_host import build_operator
from native_windows.frontend import run_frontend

if __name__ == "__main__":
    run_frontend(build_operator(), port=8786)
