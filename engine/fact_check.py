"""Check project-page references against the feature and transfer contracts."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DOCUMENT_FIELDS = {
    "__terrain__",
    "cell_id",
    "qa_flags",
    "earth_grid",
    "moon_grid",
    "mars_grid",
    "terrain_features",
    "terrain_windows",
    "err_note",
}


def check_document(document: str | Path, contract_dir: str | Path | None = None) -> list[str]:
    path = Path(document)
    text = path.read_text(encoding="utf-8")
    contracts = Path(contract_dir) if contract_dir else ROOT / "contract"
    dictionary = yaml.safe_load(
        (contracts / "feature_dictionary.yaml").read_text(encoding="utf-8")
    )
    transfers = yaml.safe_load(
        (contracts / "transfer_rules.yaml").read_text(encoding="utf-8")
    )
    feature_ids = {row["id"] for row in dictionary.get("features", [])}
    feature_ids.update(row["id"] for row in dictionary.get("logistics", []))
    errors = []

    for token in re.findall(r"`([^`]+)`", text):
        if (
            re.fullmatch(r"[a-z][a-z0-9_]*", token)
            and "_" in token
            and token not in feature_ids
            and token not in DOCUMENT_FIELDS
        ):
            errors.append(f"unknown contract identifier `{token}`")

    for feature, bodies in (transfers.get("rules", {}) or {}).items():
        if feature not in feature_ids:
            errors.append(f"transfer rule references unknown feature `{feature}`")
            continue
        for body, rule in bodies.items():
            if rule.get("status") == "conditional" and not (
                rule.get("correction") or rule.get("note")
            ):
                errors.append(f"{feature}/{body} is conditional but has no explanation")
            explanation = rule.get("correction", rule.get("note", ""))
            if explanation and len(str(explanation).split()) > 30:
                errors.append(f"{feature}/{body} transfer note exceeds 30 words")

    if re.search(r"\b(?:TODO|TBD|PLACEHOLDER)\b", text, re.IGNORECASE):
        errors.append("document contains an unresolved TODO/TBD/PLACEHOLDER")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document", help="Markdown document to check")
    parser.add_argument("--contract-dir", help="contract directory (defaults to repository contract/)")
    args = parser.parse_args()
    if not Path(args.document).is_file():
        parser.error(f"document not found: {args.document}")
    errors = check_document(args.document, args.contract_dir)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("contract references and transfer-rule wording passed")
    print("This check cannot verify scientific claims; have the cited sources reviewed before submission.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
