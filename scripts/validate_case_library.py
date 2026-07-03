import json
from pathlib import Path


REQUIRED_RULE_FIELDS = {
    "rule_id",
    "region_type",
    "confidence",
    "evidence_level",
    "evidence_cases",
}


def main():
    root = Path(__file__).resolve().parents[1]
    rule_path = root / "database" / "anime_livery_rules.json"
    manifest_path = root / "cases" / "case_template" / "case_manifest.json"
    regions_path = root / "cases" / "case_template" / "regions.json"

    errors = []
    rules_data = _load_json(rule_path, errors)
    manifest_data = _load_json(manifest_path, errors)
    regions_data = _load_json(regions_path, errors)

    rules = []
    if isinstance(rules_data, dict):
        rules = rules_data.get("rules", [])
        if not isinstance(rules, list):
            errors.append("database/anime_livery_rules.json: 'rules' must be a list.")
            rules = []
    elif rules_data is not None:
        errors.append("database/anime_livery_rules.json: root must be an object.")

    for index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            errors.append(f"Rule {index + 1}: must be an object.")
            continue
        missing = sorted(REQUIRED_RULE_FIELDS - set(rule))
        if missing:
            errors.append(f"Rule {rule.get('rule_id', index + 1)} missing fields: {', '.join(missing)}")
        if not isinstance(rule.get("evidence_cases"), list):
            errors.append(f"Rule {rule.get('rule_id', index + 1)}: evidence_cases must be a list.")

    if isinstance(manifest_data, dict) and manifest_data.get("status") != "template":
        errors.append("cases/case_template/case_manifest.json: status should be 'template'.")

    region_count = 0
    if isinstance(regions_data, dict):
        regions = regions_data.get("regions", [])
        if isinstance(regions, list):
            region_count = len(regions)
        else:
            errors.append("cases/case_template/regions.json: 'regions' must be a list.")

    if errors:
        print("Case library validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Case library validation passed.")
    print(f"Rules: {len(rules)}")
    print(f"Template regions: {region_count}")
    print(f"Template manifest: {manifest_path.relative_to(root)}")
    return 0


def _load_json(path, errors):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append(f"{path}: file not found.")
    except json.JSONDecodeError as exc:
        errors.append(f"{path}: invalid JSON: {exc}")
    except OSError as exc:
        errors.append(f"{path}: could not read file: {exc}")
    return None


if __name__ == "__main__":
    raise SystemExit(main())
