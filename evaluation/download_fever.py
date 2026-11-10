"""Download FEVER v1.0 claims and the Wikipedia dump into evaluation/data/fever.

    python evaluation/download_fever.py                  # claims (small) + wiki-pages.zip (~1.7 GB)
    python evaluation/download_fever.py --claims-only    # just the claim files (a few MB)

Files come from https://fever.ai/download/fever/ (the same locations the Hugging Face `fever` dataset script uses).
If the site is unreachable, download manually and place the files as described in evaluation/README.md.
"""
import argparse
import sys
import urllib.request
import zipfile
from pathlib import Path

BASE = "https://fever.ai/download/fever"
OUT = Path(__file__).resolve().parent / "data" / "fever"


def fetch(url: str, dest: Path) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  already present: {dest.name}")
        return
    print(f"  downloading {url}")
    tmp = dest.with_suffix(dest.suffix + ".part")

    def hook(blocks, bs, total):
        if total > 0:
            done = min(blocks * bs, total)
            print(f"\r    {done / 1e6:8.1f} / {total / 1e6:.1f} MB", end="", flush=True)

    urllib.request.urlretrieve(url, tmp, hook)
    print()
    tmp.rename(dest)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--claims-only", action="store_true")
    ap.add_argument("--split", default="paper_dev", choices=["paper_dev", "shared_task_dev"])
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        fetch(f"{BASE}/{args.split}.jsonl", OUT / f"{args.split}.jsonl")
        if not args.claims_only:
            zpath = OUT / "wiki-pages.zip"
            fetch(f"{BASE}/wiki-pages.zip", zpath)
            if not (OUT / "wiki-pages").exists():
                print("  extracting wiki-pages.zip ...")
                with zipfile.ZipFile(zpath) as z:
                    z.extractall(OUT)
            print("  extracted to", OUT / "wiki-pages")
    except Exception as e:
        print(f"\nDownload failed: {e}\nDownload the files manually from https://fever.ai/dataset/fever.html "
              f"and place them in {OUT}", file=sys.stderr)
        return 1
    print("\nFEVER data ready. Run:  python evaluation/run_fever_eval.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
