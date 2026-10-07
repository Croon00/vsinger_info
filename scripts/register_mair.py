"""MaiR (formerly Hoshino Mea): reuse the guarded requested-channel workflow."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import register_nakamachi_arale as workflow

workflow.SEED = ROOT / 'data/seeds/mair_2026_10_07.json'
workflow.REPORT = ROOT / 'db-migration/reports/mair-2026-10-07'
workflow.RUN = 'mair-utawaku-2026-10-07'
workflow.SLUG = 'mair'

if __name__ == '__main__':
    workflow.main()
