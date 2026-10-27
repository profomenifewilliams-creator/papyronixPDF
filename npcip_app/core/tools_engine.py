"""Offline analysis helpers. Files are read, never executed or sent to third parties."""
import hashlib
import json
from collections import Counter

MAX_AUDIT_LINE_BYTES = 1_048_576
MAX_AUDIT_RECORDS = 100_000

def detect_file_type(prefix: bytes) -> str:
    if prefix.startswith(b"\x89PNG\r\n\x1a\n"): return "PNG image"
    if prefix.startswith(b"\xff\xd8\xff"): return "JPEG image"
    if prefix.startswith(b"%PDF"): return "PDF document"
    if prefix.startswith(b"PK\x03\x04"): return "ZIP-based container"
    if prefix.startswith(b"MZ"): return "Windows executable"
    if prefix.startswith(b"\x7fELF"): return "ELF executable"
    return "Empty file" if not prefix else "Unknown / text / binary"

def fingerprint_stream(stream, chunk_size: int = 1024 * 1024) -> dict:
    digest = hashlib.sha256()
    size, prefix = 0, bytearray()
    while True:
        chunk = stream.read(chunk_size)
        if not chunk: break
        digest.update(chunk)
        size += len(chunk)
        if len(prefix) < 16: prefix.extend(chunk[:16-len(prefix)])
    return {"size_bytes": size, "sha256": digest.hexdigest(), "kind": detect_file_type(bytes(prefix))}

def summarize_audit_jsonl(lines) -> dict:
    counts = Counter()
    total = matched = malformed = 0
    for line in lines:
        if total >= MAX_AUDIT_RECORDS: raise ValueError(f"Audit file exceeds {MAX_AUDIT_RECORDS} lines")
        total += 1
        if len(line.encode("utf-8", errors="replace")) > MAX_AUDIT_LINE_BYTES:
            malformed += 1
            continue
        if not line.strip(): continue
        try: record = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            malformed += 1
            continue
        action = record.get("action") if isinstance(record, dict) else None
        if isinstance(action, str) and action.strip():
            counts[action.strip()[:120]] += 1
            matched += 1
        else: malformed += 1
    return {
        "total_lines": total,
        "records_with_action": matched,
        "invalid_or_missing_action": malformed,
        "unique_actions": len(counts),
        "action_counts": dict(sorted(counts.items())),
        "notice": "Counts only; not a finding of wrongdoing."
    }
