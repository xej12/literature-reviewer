"""Local research profiles and reusable, evidence-based reading assessments."""
import hashlib
import json
import re
import threading
import unicodedata
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "data/research.json"
CACHE_DIR = ROOT / "data/reading-priority"
TIERS = ["夯", "顶级", "人上人", "NPC", "拉"]
DEFAULT_PROFILE = {
    "goal": "理解高对比度成像中的自适应光学、波前感知与控制及日冕仪方法，服务于系外行星直接成像研究。",
    "topics": "高对比度成像 | high contrast imaging | high-contrast imaging\n自适应光学 | adaptive optics\n波前感知 | wavefront sensing\n波前控制 | wavefront control\n日冕仪 | coronagraph | coronagraphy | coronagraphic\n系外行星直接成像 | direct imaging | exoplanet imaging",
}
_lock = threading.RLock()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:20]


def profile():
    try:
        value = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or not all(isinstance(value.get(k), str) and value[k].strip() for k in ("goal", "topics")):
            raise ValueError("Invalid profile")
        result = {k: value[k] for k in ("goal", "topics")}
    except (OSError, ValueError):
        result = dict(DEFAULT_PROFILE)
    return {**result, "version": digest(result)}


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def save_profile(value):
    if not isinstance(value, dict):
        raise ValueError("研究方向格式无效")
    result = {k: str(value.get(k, "")).strip() for k in ("goal", "topics")}
    if not all(result.values()) or len(result["goal"]) > 3000 or len(result["topics"]) > 6000:
        raise ValueError("请填写研究目标和关键词；目标不超过 3000 字，关键词不超过 6000 字")
    with _lock:
        atomic_json(PROFILE_PATH, result)
    return profile()


def input_version(item, analysis):
    return digest({"rule": 1, "paper": {k: item.get(k) for k in ("title", "abstract", "doi", "publicationTitle", "issn", "date")},
                   "attachments": [(a.get("key"), a.get("storageHash"), a.get("size")) for a in item.get("attachments", [])],
                   "summary": analysis.get("summary")})


def cache_path(item, analysis, research):
    if not re.fullmatch(r"[A-Z0-9]+", item["key"]):
        raise ValueError("无效的文献键")
    return CACHE_DIR / f"{item['key']}-{research['version']}-{input_version(item, analysis)}.json"


def normalize(value):
    return re.sub(r"\s+", " ", re.sub(r"[-‐‑–—]", " ", unicodedata.normalize("NFKC", value).casefold())).strip()


def topic_signals(item, analysis, research):
    text = normalize("\n".join([item.get("title", ""), item.get("abstract", ""), json.dumps(analysis.get("summary") or {}, ensure_ascii=False)]))
    matches = []
    for line in research["topics"].splitlines()[:40]:
        words = [normalize(part.strip()) for part in line.split("|") if part.strip()]
        for word in words:
            pattern = re.escape(word) if re.search(r"[\u4e00-\u9fff]", word) else r"(?<!\w)" + re.escape(word) + r"(?!\w)"
            if re.search(pattern, text):
                matches.append(line.split("|")[0].strip())
                break
    return list(dict.fromkeys(matches))


def priority_for(item, analysis, research=None):
    research = research or profile()
    signals = topic_signals(item, analysis, research)
    path = cache_path(item, analysis, research)
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(saved, dict) or saved.get("tier") not in TIERS + ["待评估"]:
            raise ValueError("Invalid assessment")
        return {**saved, "signals": signals, "cached": True}
    except (OSError, ValueError):
        return {"tier": "待评估", "score": None, "method": "pending", "signals": signals, "cached": False,
                "stale": any(CACHE_DIR.glob(item["key"] + "-*.json")),
                "reason": "关键词仅提供相关性线索，尚未评价论文内容。", "profileVersion": research["version"]}


def journal_points(metrics):
    cas = (metrics or {}).get("cas") or {}
    if cas.get("division") in (1, 2, 3, 4):
        return {1: 10, 2: 7, 3: 4, 4: 2}[cas["division"]]
    quartiles = [s.get("quartile") for s in ((metrics or {}).get("jcr") or {}).get("subjects", [])]
    points = [{"Q1": 7, "Q2": 5, "Q3": 3, "Q4": 1}[q] for q in quartiles if q in {"Q1", "Q2", "Q3", "Q4"}]
    return max(points) if points else None


def source_fragments(source_text, max_chars=650):
    """Number source excerpts so the model can cite IDs without retyping PDFs."""
    fragments = []
    page = None
    for section in source_text.split("\n\n"):
        marker = re.match(r"\[第\s*(\d+)\s*页\]\s*", section)
        if marker:
            page = int(marker[1])
            section = section[marker.end():]
        while section.strip():
            section = section.strip()
            end = len(section)
            if end > max_chars:
                boundary = section.rfind(" ", 0, max_chars)
                end = boundary if boundary >= max_chars // 2 else max_chars
            fragments.append({"id": f"S{len(fragments) + 1:03}", "text": section[:end], "page": page})
            section = section[end:]
    return fragments


def quote_key(value, preserve_wraps=False):
    value = unicodedata.normalize("NFKC", value).casefold()
    value = re.sub(r"[\u00ad\u200b\ufeff]", "", value)
    value = re.sub(r"(?<=\w)[-‐‑]\s*\n\s*(?=\w)", "\ue000" if preserve_wraps else "", value)
    value = value.translate(str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "‐": "-", "‑": "-", "–": "-", "—": "-"}))
    return re.sub(r"\s+", "", value)


def verified_evidence(evaluation, source_text, fragments=None):
    source_keys = {quote_key(source_text), quote_key(re.sub(r"(?<=\w)([-‐‑])\s*\n\s*(?=\w)", r"\1", source_text))}
    wrapped_source = quote_key(source_text, preserve_wraps=True)
    def matches(quote):
        key = quote_key(quote)
        if len(key) < 12:
            return False
        if any(key in source for source in source_keys):
            return True
        # Only hyphens at actual PDF line breaks may be retained or omitted.
        # Never fuzzy-match changed words, numbers, or scientific negation.
        if "\ue000" in wrapped_source:
            pattern = "\ue000*".join("[-\ue000]" if c == "-" else re.escape(c) for c in key)
            return re.search(pattern, wrapped_source) is not None
        return False
    known = {f["id"]: f for f in (fragments or [])}
    verified, rejected = [], 0
    identifiers = evaluation.get("evidenceIds", evaluation.get("evidence_ids", []))
    identifiers = [identifiers] if isinstance(identifiers, str) else identifiers
    for identifier in identifiers if isinstance(identifiers, list) else []:
        identifier = identifier.strip().strip("[]").upper() if isinstance(identifier, str) else ""
        if re.fullmatch(r"S\d+", identifier):
            identifier = f"S{int(identifier[1:]):03}"
        fragment = known.get(identifier)
        if fragment and matches(fragment["text"]):
            verified.append(fragment["text"])
        else:
            rejected += 1
    quotes = evaluation.get("evidence", [])
    quotes = [quotes] if isinstance(quotes, (str, dict)) else quotes
    for quote in quotes if isinstance(quotes, list) else []:
        if isinstance(quote, dict):
            quote = quote.get("quote", quote.get("text", ""))
        if not isinstance(quote, str):
            rejected += 1
            continue
        quote = re.sub(r"^\s*(?:\[第\s*\d+\s*页\]|\(第\s*\d+\s*页\)|（第\s*\d+\s*页）)\s*[:：]?\s*", "", quote).strip().strip('"“”')
        if matches(quote):
            verified.append(quote)
        else:
            rejected += 1
    return list(dict.fromkeys(verified))[:5], rejected


def scored_result(evaluation, metrics, source_text, fragments=None):
    if not isinstance(evaluation, dict):
        raise ValueError("模型评估格式无效")
    relevance, content = evaluation.get("relevance"), evaluation.get("contentValue")
    reason = evaluation.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("模型未提供评估理由")
    if relevance is None or content is None:
        return {"tier": "待评估", "score": None, "reason": reason, "method": "model", "evidence": [], "limitations": "提供的材料不足以判断。"}
    for value, maximum in ((relevance, 60), (content, 30)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= maximum:
            raise ValueError("模型评分不在约定范围内")
    evidence, rejected = verified_evidence(evaluation, source_text, fragments)
    verification = {"evidence": evidence, "evidenceVerification": "partial" if rejected and evidence else "verified" if evidence else "unverified"}
    if not evidence:
        return {"tier": "待评估", "score": None, "method": "model", "reason": reason[:3000],
                **verification, "limitations": str(evaluation.get("limitations", ""))[:3000],
                "proposedScores": {"relevance": relevance, "contentValue": content},
                "unverifiedEvidence": evaluation.get("evidence", []),
                "verificationNotice": "本次模型答复已保存，但引文未能在原文中核实，暂不采用评分。可查看答复或免费手动设级，无需立即再次调用模型。"}
    points = journal_points(metrics)
    score = round(relevance + content + points) if points is not None else round((relevance + content) / 90 * 100)
    if relevance < 18:
        score = min(score, 29)
    tier = TIERS[0 if score >= 85 else 1 if score >= 70 else 2 if score >= 50 else 3 if score >= 30 else 4]
    if tier == "夯" and (relevance < 48 or content < 21):
        tier = "顶级"
    return {"tier": tier, "score": score, "method": "model", "relevance": relevance, "contentValue": content,
            "journalPoints": points, "reason": reason[:3000], **verification,
            "verificationNotice": "已保留能够核实的原文引文，未匹配的引文未被采用。" if rejected else "",
            "limitations": str(evaluation.get("limitations", "请结合全文核对。"))[:3000]}


def save_result(item, analysis, result, research=None):
    research = research or profile()
    saved = {**result, "profileVersion": research["version"], "updatedAt": datetime.now().astimezone().isoformat(timespec="seconds")}
    with _lock:
        atomic_json(cache_path(item, analysis, research), saved)
    return priority_for(item, analysis, research)


def sort_key(item):
    assessment = item["readingPriority"]
    tier = assessment.get("tier", "待评估")
    return (TIERS.index(tier) if tier in TIERS else len(TIERS), -(assessment.get("score") or 0), -len(assessment.get("signals", [])), item["key"])
