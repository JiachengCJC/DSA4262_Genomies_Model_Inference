"""Run H04 predictions; use --help to see the command-line options."""

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory
import csv
import json
import sys

ROOT = Path(__file__).resolve().parents[1]


def positive_int(value):
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("must be a positive integer") from None
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def parse_arguments(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate H04 scores, predictions, and metadata for an input dataset.",
        epilog="Relative paths are resolved from the project folder. Existing outputs are preserved.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--input", required=True, type=Path, default=argparse.SUPPRESS,
        help="Input dataset path (required)",
    )
    parser.add_argument(
        "--input-kind", choices=("reads", "features"), default="reads",
        help="Use reads for project JSON/JSONL or reads Parquet; features for site-feature CSV/Parquet",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"), help="Output folder")
    parser.add_argument("--model", type=Path, default=Path("models/h04.joblib"), help="Saved model bundle")
    parser.add_argument("--batch-size", type=positive_int, default=50_000, help="Reads or feature rows per batch")
    parser.add_argument("--threads", type=positive_int, default=2, help="Model computation threads")
    return parser.parse_args(argv)


def resolve_path(path):
    return (ROOT / path.expanduser()).resolve()


def main(argv=None):
    args = parse_arguments(argv)
    model_path = resolve_path(args.model)
    input_path = resolve_path(args.input)
    output_dir = resolve_path(args.output_dir)

    # Parse arguments first so --help works before dependencies are installed.
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from src.inference import load_model_bundle, predict_to_csv

    print("Project:", ROOT)
    print("Model:", model_path)
    print("Input:", input_path)
    print("Input kind:", args.input_kind)

    bundle = load_model_bundle(model_path)
    print("Model:", bundle.get("model_name", type(bundle["model"]).__name__))
    print("Training run:", bundle.get("run_id"))
    print("Validation threshold:", bundle.get("threshold"))

    input_name = input_path
    if input_name.suffix.lower() == ".gz":
        input_name = input_name.with_suffix("")
    dataset_name = input_name.stem
    output_path = output_dir / f"Genomies_{dataset_name}.csv"
    prediction_path = output_path.with_name(f"{output_path.stem}_pred.csv")
    metadata_path = output_path.with_suffix(".metadata.json")
    score_columns = ["transcript_id", "transcript_position", "score"]
    prediction_columns = [*score_columns, "prediction"]

    for path in (output_path, prediction_path, metadata_path):
        if path.exists():
            raise FileExistsError(f"Move the existing output or choose another --output-dir: {path}")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Score once, then export the exact column layouts without rounding the scores.
    with TemporaryDirectory(prefix=".genomies-", dir=output_dir) as temporary_dir:
        temporary_dir = Path(temporary_dir)
        scored_path = temporary_dir / "scored.csv"
        run_metadata = predict_to_csv(
            model_path, input_path, scored_path,
            input_kind=args.input_kind, batch_size=args.batch_size, threads=args.threads,
        )
        score_export = temporary_dir / output_path.name
        prediction_export = temporary_dir / prediction_path.name
        with (
            scored_path.open(encoding="utf-8", newline="") as source,
            score_export.open("x", encoding="utf-8", newline="") as score_file,
            prediction_export.open("x", encoding="utf-8", newline="") as prediction_file,
        ):
            score_writer = csv.DictWriter(score_file, fieldnames=score_columns, extrasaction="ignore")
            prediction_writer = csv.DictWriter(prediction_file, fieldnames=prediction_columns, extrasaction="ignore")
            score_writer.writeheader()
            prediction_writer.writeheader()
            for row in csv.DictReader(source):
                score_writer.writerow(row)
                prediction_writer.writerow(row)

        run_metadata.update(
            output_path=str(output_path),
            output_columns=score_columns,
            identifier_columns=score_columns[:2],
            prediction_output_path=str(prediction_path),
            prediction_output_columns=prediction_columns,
        )
        metadata_export = temporary_dir / metadata_path.name
        metadata_export.write_text(json.dumps(run_metadata, indent=2), encoding="utf-8")
        score_export.rename(output_path)
        prediction_export.rename(prediction_path)
        metadata_export.rename(metadata_path)

    print(f"Scores CSV: {output_path}")
    print(f"Predictions CSV: {prediction_path}")
    print(f"Metadata: {metadata_path}")


if __name__ == "__main__":
    main()
