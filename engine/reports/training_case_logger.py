import json
from pathlib import Path


def write_training_cases(image_path, jsdn_path, suggestions, output_path="database/training_cases.jsonl"):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a", encoding="utf-8") as handle:
        for suggestion in suggestions:
            case = {
                "case_id": f"case_{suggestion['suggestion_id']}",
                "image_path": str(image_path),
                "jsdn_path": str(jsdn_path),
                "suggestion_id": suggestion["suggestion_id"],
                "problem_type": suggestion["problem_type"],
                "current_primitives": suggestion["current_primitives"],
                "suggested_primitives": suggestion["suggested_primitives"],
                "suggested_action": suggestion["suggested_action"],
                "user_decision": "pending",
                "notes": "",
            }
            handle.write(json.dumps(case, ensure_ascii=False) + "\n")

    return str(path)
