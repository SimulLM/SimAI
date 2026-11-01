"""Import one explicit CSV row/column with a full normalized-record metadata JSON."""
import argparse

from common import ROOT, finite_nonnegative, project_path, read_csv, read_json, run_record, sha256, write_json
from baseline import normalized_value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True)
    parser.add_argument("--row", type=int, required=True, help="zero-based data row")
    parser.add_argument("--column", required=True)
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--output", required=True, help="new normalized record under results/dag/phase1/<run_id>/")
    args = parser.parse_args()
    source, target = project_path(args.csv), project_path(args.output)
    if not target.is_relative_to(project_path("results/dag/phase1")):
        raise ValueError("import output must be within results/dag/phase1")
    if target.exists():
        raise ValueError("refusing to overwrite an imported record")
    record = read_json(project_path(args.metadata))
    rows = read_csv(source)
    if args.row < 0 or args.row >= len(rows):
        raise ValueError("row outside CSV")
    record["raw_value"] = finite_nonnegative(rows[args.row][args.column])
    normalized_value(record)  # Never infer units from the column name.
    record["evidence"] = [{"path": args.csv, "sha256": sha256(source)},
                          *record.get("evidence", [])]
    record["import_selector"] = {"row": args.row, "column": args.column}
    # Import does not promote unknown metadata into verified evidence.
    record.setdefault("verification", "unverified")
    target.parent.mkdir(parents=True, exist_ok=True)
    run_record(target.parent.relative_to(ROOT).as_posix(), "import-" + target.stem,
               [source, project_path(args.metadata), ROOT / "scripts/dag_phase1/import_results.py",
                ROOT / "scripts/dag_phase1/baseline.py", ROOT / "scripts/dag_phase1/common.py"],
               0, vars(args))
    write_json(target, record)
    print(args.output)


if __name__ == "__main__":
    main()
