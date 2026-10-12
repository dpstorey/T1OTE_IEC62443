import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SK = ROOT / "skill" / "T1OTE-iec62443-onboarding"
sys.path.insert(0, str(SK / "scripts"))
EXAMPLES = ROOT / "examples"
