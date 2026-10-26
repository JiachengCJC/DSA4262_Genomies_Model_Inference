# H04 Model Inference

Run [notebooks/inference.py](notebooks/inference.py) to generate RNA-site scores and predictions using the saved H04 model. No training or labels are required.

The script uses the helper code in `src/` automatically. Your entry point is `notebooks/inference.py`.

## 1. Prepare your AWS instance

Use an EC2 instance running **Ubuntu 24.04 LTS (Python 3.12)**. This model runs on CPU; a GPU is unnecessary.

For the raw-read workflow below, choose **at least `t3.medium`**; use `t3.large` for more memory headroom:

| Recommendation | Instance type | vCPUs | Memory | Run settings |
| --- | --- | --- | --- | --- |
| Minimum recommended | `t3.medium` | 2 | 4 GiB | `--batch-size 50000 --threads 2` |
| More memory headroom | `t3.large` | 2 | 8 GiB | `--batch-size 200000 --threads 2` |

These are starting recommendations, not benchmarked minimum requirements. The `t3.small` option (2 GiB RAM) is not recommended for this setup. Hardware specifications: [AWS T3 instances](https://aws.amazon.com/ec2/instance-types/t3/).

## 2. Clone the project and install dependencies

After connecting to your AWS instance, run these commands **in the AWS terminal** to clone the GitHub repository and install dependencies.

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip

cd ~
git clone https://github.com/JiachengCJC/DSA4262_Genomies_Model_Inference DSA4262_Genomies_Model_Inference
cd DSA4262_Genomies_Model_Inference

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

`git clone` downloads the project directly from GitHub onto AWS. Keep the pinned versions in `requirements.txt` to match the saved model's training environment.

Before running predictions, make sure your input dataset are present on AWS. Cloning only downloads files stored in the repository. If you wish to use the model with your own data, obtain them from the project owner and place them in `data/raw/`.

## 3. Set your input and run predictions

Run this from the project folder, changing the arguments to choose your dataset and output folder. This example uses the recommended settings for `t3.medium`:

```bash
python notebooks/inference.py \
  --input data/raw/dataset2.json.gz \
  --output-dir outputs \
  --batch-size 50000 \
  --threads 2
```

Only `--input` is required. The other arguments have defaults:

| Argument | Default | Purpose |
| --- | --- | --- |
| `--input` | Required | Input dataset path |
| `--input-kind` | `reads` | `reads` or `features` |
| `--output-dir` | `outputs` | Folder for all three result files |
| `--model` | `models/h04.joblib` | Saved model bundle |
| `--batch-size` | `50000` | Reads or feature rows per batch |
| `--threads` | `2` | Model computation threads |

Keep the SSH session open until the script finishes and prints the three output paths. It reads `.gz` files directly and creates the output folder automatically. Relative paths are resolved from the project folder; absolute paths are also accepted.

On `t3.large`, you can use `--batch-size 200000`; keep `--threads 2` because both instance sizes have 2 vCPUs. To rerun the same dataset, choose a new `--output-dir`, such as `outputs/run2`. Existing results are not overwritten.

To view all options:

```bash
python notebooks/inference.py --help
```

## 4. Get your results

For `dataset2.json.gz`, the script saves three files in `outputs/` on EC2:

- `Genomies_dataset2.csv` — `transcript_id`, `transcript_position`, and `score`.
- `Genomies_dataset2_pred.csv` — the same columns plus `prediction`.
- `Genomies_dataset2.metadata.json` — input details, model checksum, threshold, and number of sites scored.

`score` ranges from 0 to 1. `prediction` is **1 (modified)** when the score is at least the saved threshold (approximately **0.208393**), and **0 (unmodified)** otherwise. Scores are not guaranteed to be calibrated probabilities.

## Input format

**Recommended:** Use `--input-kind reads` (the default) for most datasets. The script automatically calculates the features required by the saved model. Use `--input-kind features` only if you already have a complete feature table prepared using the same feature definitions as training.

For `--input-kind reads`, use the project's JSON/JSONL files (optionally `.gz`) or per-read Parquet files. JSON input has **one complete site per line**, with a transcript ID, position, seven-base A/C/G/T sequence, and an array of reads:

```json
{"ENST000001":{"100":{"ACGTACG":[[0.01,1.2,100.0,0.02,1.1,101.0,0.03,1.3,102.0]]}}}
```

Each read contains nine measurements in this order: **dwell time, signal standard deviation, signal mean** for the **previous, central, and next** positions. Dwell times must be positive. Include all reads for each site; for per-read Parquet, keep each site's rows together.

### Prepared site-feature tables (`--input-kind features`)

Use this option when you have already calculated the model's features. Supply a **`.csv` or `.parquet` file with one row per site**, containing all reads for that site aggregated into a single feature row. Feature calculation is skipped in this mode.

| Column(s) | Required format |
| --- | --- |
| `transcript_id` | Nonempty transcript ID, stored as text; for example, `ENST000001`. |
| `transcript_position` | A finite integer position within the transcript; for example, `100`. |
| Every name in the model bundle's `feature_columns` | One numeric value per feature. No missing values, `NaN`, or infinity. Column names must match exactly; column order can vary. |
| `dataset` (optional) | Nonempty dataset identifier, such as `data0`, when combining datasets. |

Each (`transcript_id`, `transcript_position`) pair must be unique. If `dataset` is present, each (`dataset`, `transcript_id`, `transcript_position`) combination must be unique instead.

The bundled `models/h04.joblib` requires **162 feature columns**, in addition to the identifiers:

| Feature group | Columns | Examples / naming pattern |
| --- | --- | --- |
| Read count | 1 | `n_reads` |
| Per-site statistics | 105 | Each of the 15 derived read measurements has `_mean`, `_sd`, `_min`, `_max`, `_p25`, `_median`, and `_p75` statistics; for example, `minus1_log_dwell_mean`. |
| Seven-base sequence encoding | 28 | `seq_pos0_A` through `seq_pos6_T`: one 0/1 column for each position (0–6) and base (`A`, `C`, `G`, `T`). |
| Central five-base motif encoding | 19 | One 0/1 column per supported motif, such as `motif_AAACA`, plus `motif_other`. |
| Raw measurement means | 9 | `raw_mean__{position}_{measurement}`, where position is `minus1`, `central`, or `plus1`, and measurement is `dwell`, `signal_sd`, or `signal_mean`. |

Values must use the same feature definitions as training. The project's [features_from_reads](src/inference.py) function creates the complete feature table from per-read data, using the calculations in [feature_engineering.py](src/feature_engineering.py). A `sequence` column or the nine raw measurements alone does not replace the required features. If you have raw reads, use `--input-kind reads` to calculate these features automatically.

To print the **exact required feature names** for your model, run this from the project folder after installing the dependencies (change the model path if using `--model`):

```bash
python - <<'PY'
from src.inference import load_model_bundle

bundle = load_model_bundle("models/h04.joblib")
print("\n".join(bundle["feature_columns"]))
PY
```

CSV files must be comma-separated, with column names in the first row. This shortened example illustrates the layout; **`...` represents omitted feature columns and values and must not appear in the actual file**:

```csv
transcript_id,transcript_position,n_reads,minus1_log_dwell_mean,...,raw_mean__plus1_signal_mean
ENST000001,100,20,-4.60,...,102.0
ENST000001,125,35,-4.42,...,101.5
```

Parquet uses the same column names and one-row-per-site layout. The two site identifiers can also be stored as named Parquet index levels. Labels are not required. Extra columns such as `label`, `gene_id`, or `sequence` are ignored for prediction.

Run predictions on a complete feature table with:

```bash
python notebooks/inference.py \
  --input data/site_features.csv \
  --input-kind features \
  --output-dir outputs/features_run
```

The command exports only the result columns listed above; input features, extra columns, and the optional `dataset` identifier are not included in the result CSVs. Use separate runs and output folders if you need to keep datasets distinguishable in those files.

## Troubleshooting

- **Missing package:** activate `.venv` and finish installing `requirements.txt` from step 2.
- **Cannot clone the repository:** check the repository URL and your GitHub access.
- **Cannot find the model or input data:** check that those files were downloaded onto AWS and that your `--model` and `--input` paths match their locations.
- **`FileExistsError`:** choose a new `--output-dir` and rerun the script.
- **`No matching distribution found`:** check that Python is 3.12 and your package index provides the pinned versions.
