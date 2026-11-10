"""Run the FEVER evaluation from the command line (same code the Evaluation page uses).

    python evaluation/run_fever_eval.py --sample-size 150
    python evaluation/run_fever_eval.py --sample-size 60 --top-k 3 --distractors 150    # fast, for weak laptops

Results are written to evaluation/results/latest.json and shown on the Evaluation page.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import Paths, configure_hf_cache, configure_logging  # noqa: E402
from app.database import Database  # noqa: E402
from app.evaluation.fever import discover_fever_files, load_claims, load_or_build_pages  # noqa: E402
from app.evaluation.runner import EvalConfig, run_evaluation_core  # noqa: E402
from app.services.managers import ModelManager, SettingsStore  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fever-path")
    ap.add_argument("--wiki-dir")
    ap.add_argument("--sample-size", type=int, default=150, help="total claims, balanced over the 3 labels")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--window", type=int, default=3, help="sentences per passage")
    ap.add_argument("--distractors", type=int, default=300, help="extra random Wikipedia pages in the subset corpus")
    ap.add_argument("--calibration-fraction", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=13)
    args = ap.parse_args()

    paths = Paths.default()
    paths.ensure()
    configure_logging()
    configure_hf_cache(paths)
    found = discover_fever_files(paths.evaluation)
    fever, wiki = args.fever_path or found["claims_file"], args.wiki_dir or found["wiki_dir"]
    if not fever or not wiki:
        print("FEVER data not found. Run: python evaluation/download_fever.py", file=sys.stderr)
        return 1

    db = Database(paths.db)
    settings = SettingsStore(db)
    models = ModelManager(settings)
    print("Loading models (the first run downloads them) ...")
    models.load_all()
    snap = models.snapshot()
    if snap["nli"]["state"] != "ready":
        print("NLI model unavailable:", snap["nli"]["message"], file=sys.stderr)
        return 1

    cfg = EvalConfig(fever, wiki, args.sample_size, args.top_k, args.window, args.distractors,
                     args.calibration_fraction, args.seed)
    t0 = time.time()
    last = {"stage": None}

    def progress(stage, done, total):
        if stage != last["stage"] or done == total:
            print(f"  [{stage}] {done}/{total}")
            last["stage"] = stage

    claims = load_claims(fever, cfg.sample_size, cfg.seed)
    pages = load_or_build_pages(claims, wiki, cfg.distractors, cfg.seed, cfg.window, paths.evaluation / "cache",
                                lambda d, t: progress("reading_wikipedia", d, t))
    res = run_evaluation_core(cfg, models.require_nli(), models.require_embedder(), settings.get(), claims, pages, progress)
    out = paths.evaluation / "results"
    out.mkdir(parents=True, exist_ok=True)
    (out / "latest.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    rid = db.create_eval_run(cfg.__dict__)
    db.update_eval_run(rid, status="completed", results=res, finished_at=res["generated_at"],
                       progress={"stage": "done", "done": 1, "total": 1})
    print(f"\nDone in {time.time() - t0:.0f}s. Test claims: {res['dataset']['test']['n']}")
    print(f"{'method':62s} {'acc':>6s} {'macroF1':>8s}")
    for m in res["methods"].values():
        print(f"{m['name']:62s} {m['metrics']['accuracy']:6.3f} {m['metrics']['macro_f1']:8.3f}")
    print("Saved:", out / "latest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
