"""Download the default models once so the first verification does not wait.

    python backend/scripts/download_models.py
    python backend/scripts/download_models.py --nli cross-encoder/nli-deberta-v3-small
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Paths, RuntimeSettings, configure_hf_cache  # noqa: E402


def main() -> int:
    d = RuntimeSettings()
    ap = argparse.ArgumentParser(description="Pre-download TruthLens AI models into data/models")
    ap.add_argument("--nli", default=d.nli_model)
    ap.add_argument("--embedding", default=d.embedding_model)
    args = ap.parse_args()
    configure_hf_cache(Paths.default())
    ok = True
    try:
        from sentence_transformers import SentenceTransformer
        print(f"Downloading embedding model {args.embedding} ...")
        SentenceTransformer(args.embedding, device="cpu")
        print("  OK")
    except Exception as e:
        ok = False
        print(f"  FAILED: {e}")
    try:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        print(f"Downloading NLI model {args.nli} ...")
        AutoTokenizer.from_pretrained(args.nli)
        AutoModelForSequenceClassification.from_pretrained(args.nli)
        print("  OK")
    except Exception as e:
        ok = False
        print(f"  FAILED: {e}")
    print("\nAll models ready." if ok else "\nSome downloads failed. Check your internet connection and run again.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
