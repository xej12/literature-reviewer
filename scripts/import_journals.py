"""Install a pinned third-party journal dataset; never import Zotero/private data."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-dir", type=Path, help="Import already downloaded CSV files")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "references/journal-data.json").read_text(encoding="utf-8"))
    verified = []
    for entry in manifest["files"]:
        if args.from_dir:
            content = (args.from_dir / entry["name"]).read_bytes()
        else:
            path = urllib.parse.quote("中科院分区表及JCR原始数据文件/" + entry["name"])
            url = f"https://raw.githubusercontent.com/hitfyd/ShowJCR/{manifest['commit']}/{path}"
            with urllib.request.urlopen(url, timeout=60) as response:
                content = response.read()
        if hashlib.sha256(content).hexdigest() != entry["sha256"]:
            raise ValueError(f"Checksum mismatch for {entry['name']}; no data installed")
        verified.append((entry["name"], content))
    destination = ROOT / "data/journals"
    destination.mkdir(parents=True, exist_ok=True)
    for name, content in verified:
        temporary = destination / (name + ".tmp")
        temporary.write_bytes(content)
        temporary.replace(destination / name)
    print("已导入中科院 2025 与 JCR 2025 期刊数据（第三方整理，本电脑保存）。")


if __name__ == "__main__":
    main()
