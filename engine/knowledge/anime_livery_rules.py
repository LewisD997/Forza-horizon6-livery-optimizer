import json
from pathlib import Path


DEFAULT_RULE_PATH = "database/anime_livery_rules.json"


def load_anime_livery_rules(path=DEFAULT_RULE_PATH) -> dict:
    rule_path = Path(path)
    if not rule_path.exists():
        return _empty_rules(f"Rules file not found: {rule_path}")

    try:
        data = json.loads(rule_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _empty_rules(f"Rules file could not be loaded: {exc}")

    if not isinstance(data, dict):
        return _empty_rules("Rules file root must be a JSON object.")

    rules = data.get("rules")
    if not isinstance(rules, list):
        data = dict(data)
        data["rules"] = []
        data.setdefault("notes", []).append("Rules file has no valid 'rules' list.")
        return data

    data["rules"] = [rule for rule in rules if isinstance(rule, dict)]
    data.setdefault("notes", [])
    return data


def get_rules_for_region_type(region_type: str) -> list:
    target = str(region_type or "").strip().lower()
    rules = load_anime_livery_rules().get("rules", [])
    return [
        rule
        for rule in rules
        if str(rule.get("region_type", "")).strip().lower() == target
    ]


def get_rules_by_confidence(confidence: str) -> list:
    target = str(confidence or "").strip().lower()
    rules = load_anime_livery_rules().get("rules", [])
    return [
        rule
        for rule in rules
        if str(rule.get("confidence", "")).strip().lower() == target
    ]


def summarize_rule_evidence() -> dict:
    rules = load_anime_livery_rules().get("rules", [])
    confidence_counts = {}
    evidence_levels = {}
    total_cases = 0
    confirmed = 0
    rejected = 0

    for rule in rules:
        confidence = str(rule.get("confidence", "unknown"))
        confidence_counts[confidence] = confidence_counts.get(confidence, 0) + 1

        evidence_level = int(_number(rule.get("evidence_level")))
        evidence_levels[str(evidence_level)] = evidence_levels.get(str(evidence_level), 0) + 1

        evidence_cases = rule.get("evidence_cases")
        if isinstance(evidence_cases, list):
            total_cases += len(evidence_cases)

        confirmed += int(_number(rule.get("user_confirmed_count")))
        rejected += int(_number(rule.get("rejected_count")))

    return {
        "total_rules": len(rules),
        "confidence_counts": confidence_counts,
        "evidence_level_counts": evidence_levels,
        "total_evidence_case_links": total_cases,
        "user_confirmed_count": confirmed,
        "rejected_count": rejected,
    }


def _empty_rules(note):
    return {
        "schema_version": "0.1",
        "description": "Anime livery rules unavailable.",
        "rules": [],
        "notes": [note],
    }


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0
