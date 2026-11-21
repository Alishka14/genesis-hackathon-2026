"""Run the trusted synthetic dataset peer audit from this checkout.

Loads evaluator-private truth only within ledgergym.independent_dataset_audit.
The report contains aggregate counts, never source documents or issue IDs.
"""
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ledgergym.independent_dataset_audit import main


if __name__ == "__main__":
    main()
