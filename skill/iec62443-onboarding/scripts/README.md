# scripts

Deterministic helpers used by the skill. Stdlib only, except `generate_template.py` and `parse_workbook.py` (xlsx), which need `openpyxl`.

```
python generate_template.py --site "Plant 1" --out onboarding.xlsx
python parse_workbook.py onboarding.xlsx --out parsed.json      # {"model": ..., "gaps": [...]}
python validate_model.py parsed.json                            # exit 1 on errors
python build_plan.py parsed.json --existing existing.json --out plan.json
python build_plan.py parsed.json --format md                    # human-readable table
python journal.py next --plan plan.json --journal run.jsonl
```

Tests: `pytest tests/unit` from the repo root.
