"""Conservative, offline journal matching. Independent implementation, no plugin code copied."""
import csv
import hashlib
import json
import re
import threading
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data/journals"
MANIFEST = json.loads((ROOT / "references/journal-data.json").read_text(encoding="utf-8"))


def title_key(value):
    value = unicodedata.normalize("NFKC", str(value)).casefold().strip()
    value = re.sub(r"^the\s+", "", value)
    return "".join(c for c in value if c.isalnum())


def issns(value):
    return {m.replace("-", "").upper() for m in re.findall(r"\b\d{4}-?\d{3}[\dXx]\b", str(value))}


def division(value):
    match = re.match(r"\s*([1-4])(?:\s|$)", value or "")
    return int(match[1]) if match else None


def has_division(metrics):
    """An IF or matched journal name alone does not establish a quartile."""
    metrics = metrics or {}
    cas, jcr = metrics.get("cas") or {}, metrics.get("jcr") or {}
    return (cas.get("division") in (1, 2, 3, 4)
            or any(s.get("division") in (1, 2, 3, 4) for s in cas.get("subjects", []))
            or any(s.get("quartile") in {"Q1", "Q2", "Q3", "Q4"} for s in jcr.get("subjects", [])))


class Catalog:
    def __init__(self, directory=DATA_DIR):
        self.rows = {"cas": [], "jcr": []}
        self.index = {kind: {"issn": {}, "title": {}} for kind in self.rows}
        self.errors = []
        for entry in MANIFEST["files"]:
            path = Path(directory) / entry["name"]
            try:
                raw = path.read_bytes()
                if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
                    raise ValueError("数据校验失败")
                rows = list(csv.DictReader(raw.decode("utf-8-sig").splitlines()))
                self.add_rows(entry["kind"], rows)
            except (OSError, ValueError) as exc:
                self.errors.append(f"{entry['kind']}: {type(exc).__name__}")

    def add_rows(self, kind, rows):
        for row in rows:
            number = len(self.rows[kind])
            self.rows[kind].append(row)
            identifiers = issns(row.get("ISSN/EISSN", "") + " " + row.get("ISSN", "") + " " + row.get("EISSN", ""))
            for identifier in identifiers:
                self.index[kind]["issn"].setdefault(identifier, set()).add(number)
            key = title_key(row.get("Journal", ""))
            if key:
                self.index[kind]["title"].setdefault(key, set()).add(number)

    def match(self, kind, item):
        identifiers = issns(item.get("issn", ""))
        hits = set().union(*(self.index[kind]["issn"].get(i, set()) for i in identifiers)) if identifiers else set()
        if len(hits) > 1:
            return None, "ambiguous"
        if hits:
            return self.rows[kind][next(iter(hits))], "issn"
        # An explicitly supplied, unmatched ISSN must not silently fall back
        # to a conflicting journal title (often a metadata error).
        if identifiers:
            return None, "issn_unmatched"
        hits = self.index[kind]["title"].get(title_key(item.get("publicationTitle", "")), set())
        if len(hits) == 1:
            return self.rows[kind][next(iter(hits))], "title"
        return None, "ambiguous" if hits else "unmatched"

    def status(self):
        return {"ready": not self.errors, "casCount": len(self.rows["cas"]), "jcrCount": len(self.rows["jcr"]),
                "source": MANIFEST["source"], "url": MANIFEST["url"], "notice": MANIFEST["notice"],
                "casYear": 2025, "jcrYear": 2025}

    def lookup(self, item):
        result = {"status": "unmatched", "cas": None, "jcr": None, "source": MANIFEST["source"],
                  "sourceUrl": MANIFEST["url"], "sourceCommit": MANIFEST["commit"], "notice": MANIFEST["notice"]}
        venue = item.get("publicationTitle", "")
        if item.get("itemType") in {"conferencePaper", "book", "bookSection", "thesis", "patent"} or re.search(r"\barxiv\b|\bbiorxiv\b|\bmedrxiv\b", venue, re.I):
            return {**result, "status": "not_applicable"}
        if self.errors:
            return {**result, "status": "data_unavailable"}
        cas, cas_method = self.match("cas", item)
        jcr, jcr_method = self.match("jcr", item)
        if cas:
            result["cas"] = {"journal": cas["Journal"], "year": 2025, "category": cas.get("大类", ""),
                "division": division(cas.get("大类分区", "")), "rank": cas.get("大类分区", ""),
                "top": cas.get("Top", "").strip() == "是", "match": cas_method,
                "subjects": [{"category": cas[f"小类{i}"].strip(), "division": division(cas.get(f"小类{i}分区", "")),
                              "rank": cas.get(f"小类{i}分区", "")} for i in range(1, 7) if cas.get(f"小类{i}", "").strip()]}
        if jcr:
            value = jcr.get("IF(2025)", "").strip()
            result["jcr"] = {"journal": jcr["Journal"], "year": 2025,
                "impactFactor": float(value) if re.fullmatch(r"\d+(?:\.\d+)?", value) else None,
                "match": jcr_method, "subjects": [{"category": jcr[f"Category_{i}"].strip(),
                    "quartile": jcr.get(f"IF Quartile(2025)_{i}", "").strip(),
                    "rank": jcr.get(f"IF Rank(2025)_{i}", "").strip()} for i in range(1, 7) if jcr.get(f"Category_{i}", "").strip()]}
        if cas or jcr:
            result["status"] = "matched"
        elif "ambiguous" in (cas_method, jcr_method):
            result["status"] = "ambiguous"
        elif "issn_unmatched" in (cas_method, jcr_method):
            result["status"] = "issn_unmatched"
        return result


_catalog = None
_stamp = None
_lock = threading.Lock()


def catalog():
    global _catalog, _stamp
    stamp = tuple((p.stat().st_mtime_ns, p.stat().st_size) if p.exists() else None for p in (DATA_DIR / e["name"] for e in MANIFEST["files"]))
    with _lock:
        if _catalog is None or stamp != _stamp:
            _catalog, _stamp = Catalog(), stamp
        return _catalog
