"""DuckDB ingestion and read-only intelligence APIs for Sentinel Orbital.

Raw CSVs are retained in DuckDB alongside normalized, queryable tables. Input is
untrusted and is never executed. All source data and derived fields are explicitly
attributed; imported data is not asserted to be official or independently verified.
"""
from __future__ import annotations

import copy
import os
import re
import threading
from collections import defaultdict
from pathlib import Path
from typing import Any

import duckdb

from .demo_data import DEMO_EVENTS, DEMO_PROFILES, DEMO_RECORDS

_FILES = ("vulnerabilities.csv", "affected_products.csv", "references.csv", "known_exploited.csv", "exploit_signals_2024.csv", "exploit_signals_2025.csv", "weakness_types.csv", "scoreboard_2026.csv")
_ALIASES = {
    "id": ("cve_id", "cve", "id", "vulnerability_id", "vuln_id", "cveid"),
    "description": ("description", "description_text", "cve_description", "summary", "details"),
    "published": ("published", "published_date", "published_at", "publication_date", "date_published", "publishedDate"),
    "status": ("status", "nvd_status", "vuln_status", "analysis_status", "vulnerability_status"),
    "cwes": ("cwes", "cwe", "cwe_id", "cwe_ids", "weakness", "weaknesses", "weakness_id"),
    "cvss": ("cvss", "cvss_score", "base_score", "cvss_v3_score", "cvss_v31_score", "cvss_v3"),
    "epss": ("epss", "epss_score", "epss_probability"),
    "kev": ("kev", "is_kev", "known_exploited", "is_known_exploited"),
    "vendor": ("vendor", "vendor_name", "manufacturer"),
    "product": ("product", "product_name", "software", "software_name"),
    "date": ("event_date", "signal_date", "observed_at", "observation_date", "date", "date_added", "dateAdded", "added_date", "published", "published_date", "timestamp", "snapshot_date", "snapshot_month"),
    "kind": ("signal_type", "event_type", "type", "kind"),
    "value": ("signal_value", "value", "score"),
    "text": ("signal_description", "event_description", "description", "details", "notes"),
    "url": ("url", "reference", "reference_url", "link", "href"),
    "exploit": ("exploit_available", "public_exploit", "has_exploit", "poc_available", "has_poc"),
}
# Rules use text matches, not an AI model or official classifications. RE2-compatible.
_RULES = [
    ("Remote code execution", r"(?i)remote code execution|arbitrary code execution|execute arbitrary code|execution of arbitrary code", 0.82),
    ("Authentication bypass", r"(?i)authentication bypass|bypass authentication|bypass(?:es)? authentication", 0.82),
    ("Privilege escalation", r"(?i)privilege escalation|escalat(?:e|ion) (?:of )?privileges", 0.80),
    ("Memory corruption", r"(?i)memory corruption|memory corrupt(?:ion|ed)", 0.80),
    ("Buffer overflow", r"(?i)buffer overflow|buffer overrun", 0.84),
    ("Injection", r"(?i)sql injection|command injection|code injection|injection vulnerability", 0.80),
    ("Deserialization", r"(?i)deserializ(?:e|ation|ing)|deserialis(?:e|ation|ing)", 0.75),
    ("Denial of service", r"(?i)denial.of.service|\bDoS\b", 0.78),
    ("Information disclosure", r"(?i)information disclosure|disclos(?:e|ure) (?:of )?(?:sensitive )?(?:information|data)|expose (?:sensitive |planning |build )?(?:information|data|metadata)", 0.77),
    ("Access control", r"(?i)access.control|authorization check|improper authorization", 0.72),
    ("Improper input validation", r"(?i)improper input validation|insufficient input validation|lack of input validation", 0.80),
]
_LOCK = threading.RLock()
_CONN = None
_META: dict[str, Any] = {}


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _mapping(columns: list[str]) -> dict[str, str]:
    lookup = {_name(c): c for c in columns}
    return {key: next((lookup[_name(a)] for a in aliases if _name(a) in lookup), None)
            for key, aliases in _ALIASES.items()}


def _col(mapping: dict[str, str], key: str, default: str = "NULL") -> str:
    return _quote(mapping[key]) if mapping.get(key) else default


def _text(mapping: dict[str, str], key: str, default: str = "NULL") -> str:
    return f"nullif(trim({_col(mapping, key, default)}), '')"


def _bool_expr(mapping: dict[str, str], key: str) -> str:
    return f"lower(coalesce(trim({_col(mapping, key)}), '')) IN ('true','1','yes','y','t')"


def _day(mapping: dict[str, str], key: str) -> str:
    # An explicitly monthly snapshot is positioned at month-end, not an event date.
    # Other incomplete dates stay unknown rather than inventing the first day.
    v = _text(mapping, key)
    if key == "date" and _name(mapping.get(key) or "") == "snapshotmonth":
        return f"CASE WHEN regexp_full_match({v}, '[0-9]{{4}}-[0-9]{{2}}') THEN last_day(try_cast({v} || '-01' AS DATE)) ELSE NULL END"
    return f"coalesce(try_cast({v} AS DATE), try_cast(substr({v},1,10) AS DATE))"


def _typed_signal_sql(m: dict[str, str]) -> dict[str, str]:
    """SQL fragments shared by typed event and conflicting-column ingestion."""
    from .analytics import _POSITIVE_EVENT_DESCRIPTIONS, _TRUE_NUMERIC_TOKEN

    kind = f"lower(coalesce({_text(m, 'kind')}, 'other'))"
    normalized = (f"CASE WHEN {kind} IN ('epss','epss_score') THEN 'epss' "
                  f"WHEN {kind} IN ('kev','known_exploited','known exploited') THEN 'kev' "
                  f"WHEN {kind} IN ('exploit_reference','public_exploit','poc','proof_of_concept') THEN 'exploit_reference' ELSE 'other' END")
    value = _text(m, "value")
    number = f"try_cast({value} AS DOUBLE)"
    text = _text(m, "text")
    explicit_positive = f"coalesce((lower({value}) IN ('true','yes','y','t') OR regexp_full_match({value}, '{_TRUE_NUMERIC_TOKEN}')), false)"
    # These are code-owned strings; source text is always read from a column.
    descriptions = []
    for event_kind, accepted in _POSITIVE_EVENT_DESCRIPTIONS.items():
        literals = ",".join("'" + s.rstrip('.').replace("'", "''") + "'" for s in sorted(accepted))
        descriptions.append(f"({normalized} = '{event_kind}' AND rtrim(lower({text}), '.') IN ({literals}))")
    positive = f"({explicit_positive} OR ({value} IS NULL AND coalesce(({' OR '.join(descriptions)}), false)))"
    return {"kind": kind, "normalized": normalized, "value": value, "number": number,
            "text": text, "explicit_positive": explicit_positive, "positive": positive}


def _create_tables(conn):
    conn.execute("CREATE OR REPLACE TABLE vulnerabilities (id VARCHAR PRIMARY KEY, description VARCHAR, published DATE, status VARCHAR, cwes VARCHAR, cvss DOUBLE, epss DOUBLE, kev BOOLEAN, vendor VARCHAR, product VARCHAR, source VARCHAR, source_row BIGINT, is_demo BOOLEAN)")
    conn.execute("CREATE OR REPLACE TABLE products (id VARCHAR, vendor VARCHAR, product VARCHAR, source VARCHAR, source_row BIGINT)")
    conn.execute("CREATE OR REPLACE TABLE weaknesses (id VARCHAR, cwes VARCHAR, source VARCHAR, source_row BIGINT)")
    conn.execute("CREATE OR REPLACE TABLE source_references (id VARCHAR, date DATE, url VARCHAR, source VARCHAR, source_row BIGINT)")
    conn.execute("CREATE OR REPLACE TABLE events (id VARCHAR, date DATE, kind VARCHAR, value DOUBLE, description VARCHAR, source VARCHAR, source_row BIGINT, is_demo BOOLEAN)")
    conn.execute("CREATE OR REPLACE TABLE characteristics (id VARCHAR, name VARCHAR, evidence VARCHAR, confidence DOUBLE)")


def _read_raw(conn, folder: Path, filename: str) -> tuple[dict[str, Any], dict[str, str]]:
    path = folder / filename
    raw = "raw_" + filename.removesuffix(".csv")
    report: dict[str, Any] = {"file": filename, "path": str(path), "raw_table": raw, "status": "absent", "rows": 0,
                              "columns": [], "inferred_types": {}, "null_counts": {}, "duplicate_key_groups": None,
                              "duplicate_rows": None, "exact_duplicate_records": None, "join_key": None, "warnings": []}
    conn.execute(f"DROP TABLE IF EXISTS {_quote(raw)}")
    if not path.is_file():
        return report, {}
    try:
        # Storing strings makes mixed types and retrospectively changed values lossless.
        conn.execute(f"CREATE TABLE {_quote(raw)} AS SELECT row_number() OVER () AS __source_row, * FROM read_csv(?, header=true, all_varchar=true, sample_size=20480)", [str(path)])
        cols = [r[0] for r in conn.execute(f"DESCRIBE SELECT * FROM {_quote(raw)}").fetchall() if r[0] != "__source_row"]
        if any(_name(c).startswith("sourcerow") for c in cols):
            report["warnings"].append("A source column resembles the reserved provenance column; inspect the raw table before use.")
        mapping = _mapping(cols)
        report["columns"] = cols
        report["column_mapping"] = {k: v for k, v in mapping.items() if v}
        report["rows"] = conn.execute(f"SELECT count(*) FROM {_quote(raw)}").fetchone()[0]
        if cols:
            null_sql = ",".join(f"count(*) FILTER (WHERE {_quote(c)} IS NULL OR trim({_quote(c)}) = '')" for c in cols)
            report["null_counts"] = dict(zip(cols, conn.execute(f"SELECT {null_sql} FROM {_quote(raw)}").fetchone()))
            group_sql = ", ".join(_quote(c) for c in cols)
            report["exact_duplicate_records"] = conn.execute(f"SELECT coalesce(sum(n-1),0) FROM (SELECT count(*) n FROM {_quote(raw)} GROUP BY {group_sql} HAVING count(*)>1)").fetchone()[0]
        try:
            inferred = conn.execute("DESCRIBE SELECT * FROM read_csv(?, header=true, sample_size=20480)", [str(path)]).fetchall()
            report["inferred_types"] = {r[0]: r[1] for r in inferred}
            report["warnings"].append("Inferred types use a sample; raw values are stored as VARCHAR and later values may differ.")
        except Exception as exc:
            report["warnings"].append(f"Could not infer source types: {type(exc).__name__}: {exc}")
        if mapping.get("id"):
            key = _quote(mapping["id"])
            report["join_key"] = mapping["id"]
            report["duplicate_key_groups"], report["duplicate_rows"] = conn.execute(
                f"SELECT count(*), coalesce(sum(n-1),0) FROM (SELECT count(*) n FROM {_quote(raw)} WHERE nullif(trim({key}),'') IS NOT NULL GROUP BY upper(trim({key})) HAVING count(*) > 1)").fetchone()
        report["status"] = "loaded"
    except Exception as exc:
        report["status"] = "error"
        report["warnings"].append(f"CSV read failed: {type(exc).__name__}: {exc}")
        return report, {}
    return report, mapping


def _needs(report, mapping, *keys):
    missing = [key for key in keys if not mapping.get(key)]
    if missing:
        report["status"] = "unsupported"
        report["warnings"].append("Unsupported schema: required logical fields " + ", ".join(missing) + "; raw table is retained.")
        return True
    return False


def _ingest_vulnerabilities(conn, report, m):
    if _needs(report, m, "id", "description"):
        return
    raw = _quote(report["raw_table"])
    identifier = f"upper({_text(m, 'id')})"
    cvss, epss = _text(m, "cvss"), _text(m, "epss")
    conn.execute(f"""INSERT INTO vulnerabilities
      SELECT id, coalesce(description,''), published, coalesce(status,'Unknown'), cwes,
             CASE WHEN cvss BETWEEN 0 AND 10 THEN cvss END,
             CASE WHEN epss BETWEEN 0 AND 1 THEN epss END, kev, vendor, product, ?, __source_row, false
      FROM (SELECT {identifier} id, {_text(m,'description')} description, {_day(m,'published')} published,
                   {_text(m,'status')} status, {_text(m,'cwes')} cwes, try_cast({cvss} AS DOUBLE) cvss,
                   try_cast({epss} AS DOUBLE) epss, {_bool_expr(m,'kev')} kev, {_text(m,'vendor')} vendor,
                   {_text(m,'product')} product, __source_row,
                   row_number() OVER (PARTITION BY {identifier} ORDER BY __source_row) rn FROM {raw})
      WHERE id IS NOT NULL AND rn=1""", [report["file"]])
    report["normalized_rows"] = conn.execute("SELECT count(*) FROM vulnerabilities").fetchone()[0]
    report["warnings"].append("Duplicate IDs use the first source row; all original rows remain in the raw table. Scores outside CVSS 0–10 and EPSS 0–1 become unknown.")


def _ingest_related(conn, report, m):
    name, raw = report["file"], _quote(report["raw_table"])
    if _needs(report, m, "id"):
        return
    identifier = f"upper({_text(m, 'id')})"
    source = name
    if name == "affected_products.csv":
        if not m.get("product"):
            _needs(report, m, "product"); return
        conn.execute(f"INSERT INTO products SELECT {identifier}, {_text(m,'vendor')}, {_text(m,'product')}, ?, __source_row FROM {raw} WHERE {identifier} IS NOT NULL AND {_text(m,'product')} IS NOT NULL", [source])
    elif name == "references.csv":
        if _needs(report, m, "url"): return
        conn.execute(f"INSERT INTO source_references SELECT {identifier}, {_day(m,'date')}, {_text(m,'url')}, ?, __source_row FROM {raw} WHERE {identifier} IS NOT NULL AND {_text(m,'url')} IS NOT NULL", [source])
        # An ordinary URL, even a repository URL, is not proof of a working exploit.
    elif name == "known_exploited.csv":
        condition = _bool_expr(m, "kev") if m.get("kev") else "true"
        conn.execute(f"UPDATE vulnerabilities SET kev=true WHERE id IN (SELECT {identifier} FROM {raw} WHERE {condition})")
        if m.get("date"):
            conn.execute(f"INSERT INTO events SELECT {identifier}, {_day(m,'date')}, 'kev', NULL, 'Source reports known exploitation; source has not been independently verified.', ?, __source_row, false FROM {raw} WHERE {identifier} IS NOT NULL AND {_day(m,'date')} IS NOT NULL AND {condition}", [source])
        else:
            report["warnings"].append("No date field: current source-reported designation retained, but no dated event or temporal claim created.")
    elif name == "weakness_types.csv":
        if _needs(report, m, "cwes"): return
        conn.execute(f"INSERT INTO weaknesses SELECT {identifier}, {_text(m,'cwes')}, ?, __source_row FROM {raw} WHERE {identifier} IS NOT NULL AND {_text(m,'cwes')} IS NOT NULL", [source])
    elif name.startswith("exploit_signals_"):
        if _needs(report, m, "date"): return
        if not any(m.get(k) for k in ("kind", "epss", "exploit", "kev")):
            report["status"] = "unsupported"
            report["warnings"].append("Unsupported signal schema: supply a signal type or an EPSS, exploit-availability, or KEV field. Raw rows retained.")
            return
        date = _day(m, "date")
        signal = _typed_signal_sql(m)
        if m.get("epss"):
            number = f"try_cast({_text(m,'epss')} AS DOUBLE)"
            conn.execute(f"INSERT INTO events SELECT {identifier}, {date}, 'epss', {number}, 'Source-reported historical EPSS; not independently verified.', ?, __source_row, false FROM {raw} WHERE {identifier} IS NOT NULL AND {date} IS NOT NULL AND {number} BETWEEN 0 AND 1", [source])
        if m.get("exploit"):
            # A conflicting nonpositive/unknown typed value for the same signal
            # prevents this row's dedicated flag from silently overriding it.
            conflict = f"({signal['normalized']} = 'exploit_reference' AND {signal['value']} IS NOT NULL AND NOT {signal['explicit_positive']})"
            conn.execute(f"INSERT INTO events SELECT {identifier}, {date}, 'exploit_reference', 1, 'Source reports a public exploit or PoC reference; existence and functionality are unverified.', ?, __source_row, false FROM {raw} WHERE {identifier} IS NOT NULL AND {date} IS NOT NULL AND {_bool_expr(m,'exploit')} AND NOT {conflict}", [source])
        if m.get("kev"):
            conflict = f"({signal['normalized']} = 'kev' AND {signal['value']} IS NOT NULL AND NOT {signal['explicit_positive']})"
            conn.execute(f"INSERT INTO events SELECT {identifier}, {date}, 'kev', 1, 'Source reports known exploitation; not independently verified.', ?, __source_row, false FROM {raw} WHERE {identifier} IS NOT NULL AND {date} IS NOT NULL AND {_bool_expr(m,'kev')} AND NOT {conflict}", [source])
        if m.get("kind"):
            normalized, number, value, positive = signal["normalized"], signal["number"], signal["value"], signal["positive"]
            is_binary = f"({normalized} IN ('kev','exploit_reference'))"
            neutral = f"({is_binary} AND NOT {positive})"
            event_kind = f"CASE WHEN {neutral} THEN {normalized} || '_observation' ELSE {normalized} END"
            event_value = (f"CASE WHEN {is_binary} AND lower({value}) IN ('true','yes','y','t') THEN 1.0 "
                           f"WHEN {is_binary} AND lower({value}) IN ('false','no','n','f') THEN 0.0 "
                           f"WHEN isfinite({number}) THEN {number} ELSE NULL END")
            desc = (f"coalesce({signal['text']}, 'Source-reported signal; not independently verified.') || "
                    f"CASE WHEN {neutral} THEN ' [Neutral observation: source type=' || {signal['kind']} || "
                    f"'; source value=' || coalesce({value}, '(missing)') || '; not positive evidence.]' ELSE '' END")
            conn.execute(f"INSERT INTO events SELECT {identifier}, {date}, {event_kind}, {event_value}, {desc}, ?, __source_row, false FROM {raw} WHERE {identifier} IS NOT NULL AND {date} IS NOT NULL", [source])
        report["warnings"].append("Undated or malformed observations are retained raw but excluded from the event timeline. Source claims are unverified.")
        if m.get("kind"):
            report["warnings"].append("Typed KEV and exploit-reference events with negative or unknown values are neutral observations, not positive evidence; conflicting same-row flags do not override a supplied nonpositive or unknown value.")
    if name in ("known_exploited.csv", "exploit_signals_2024.csv", "exploit_signals_2025.csv") and _name(m.get("date") or "") == "snapshotmonth":
        report["warnings"].append("snapshot_month is plotted at month-end as an observation snapshot, not a claim that the underlying event occurred that day.")
        conn.execute("UPDATE events SET description=coalesce(description,'') || ' Monthly observation snapshot placed at month-end; the underlying event date is unknown.' WHERE source=?", [source])


def _derive(conn):
    # Prefer vulnerability-row product fields, otherwise choose a deterministic source-row match.
    conn.execute("""UPDATE vulnerabilities v SET vendor=coalesce(v.vendor,p.vendor), product=coalesce(v.product,p.product)
      FROM (SELECT id, first(vendor ORDER BY source_row) vendor, first(product ORDER BY source_row) product FROM products GROUP BY id) p WHERE v.id=p.id""")
    for name, pattern, confidence in _RULES:
        conn.execute("""INSERT INTO characteristics SELECT id, ?, regexp_extract(description, ?), ? FROM vulnerabilities
                       WHERE regexp_matches(description, ?)""", [name, pattern, confidence, pattern])
    # Indexes accelerate joins and equality predicates; free-text substring search still scans.
    for name, table, column in [("idx_events_id", "events", "id"), ("idx_products_id", "products", "id"), ("idx_weakness_id", "weaknesses", "id"), ("idx_chars_id", "characteristics", "id"), ("idx_refs_id", "source_references", "id")]:
        conn.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table}({column})")


def initialize(data_dir: str | os.PathLike | None = None, db_path: str | os.PathLike | None = None, demo: bool = True) -> dict[str, Any]:
    """Replace the normalized database from named CSVs, then return quality metadata.

    Defaults: SENTINEL_DATA_DIR or ./data; SENTINEL_DB_PATH or a persistent local
    database in the system temp directory. Pass ':memory:' for isolated tests.
    Explicit reinitialization replaces all tables (including raw tables).
    """
    global _CONN, _META
    with _LOCK:
        if _CONN is not None:
            _CONN.close()
        folder = Path(data_dir or os.environ.get("SENTINEL_DATA_DIR", Path(__file__).resolve().parent.parent / "data")).expanduser().resolve()
        database = str(db_path or os.environ.get("SENTINEL_DB_PATH", "/tmp/sentinel_orbital.duckdb"))
        _CONN = duckdb.connect(database=database)
        conn = _CONN
        _create_tables(conn)
        reports, mappings = {}, {}
        for filename in _FILES:
            reports[filename], mappings[filename] = _read_raw(conn, folder, filename)
        main = reports["vulnerabilities.csv"]
        if main["status"] == "loaded":
            try:
                conn.execute("BEGIN TRANSACTION")
                _ingest_vulnerabilities(conn, main, mappings["vulnerabilities.csv"])
                conn.execute("COMMIT")
            except Exception as exc:
                conn.execute("ROLLBACK")
                main["status"] = "error"; main["warnings"].append(f"Normalization failed: {type(exc).__name__}: {exc}")
        has_real = conn.execute("SELECT count(*) FROM vulnerabilities").fetchone()[0] > 0
        # Import related data only when the vulnerability file produced records.
        for filename in _FILES[1:-1]:
            report = reports[filename]
            if report["status"] != "loaded": continue
            try:
                conn.execute("BEGIN TRANSACTION")
                _ingest_related(conn, report, mappings[filename])
                conn.execute("COMMIT")
            except Exception as exc:
                conn.execute("ROLLBACK")
                report["status"] = "error"; report["warnings"].append(f"Normalization failed: {type(exc).__name__}: {exc}")
        if reports["scoreboard_2026.csv"]["status"] == "loaded":
            reports["scoreboard_2026.csv"]["warnings"].append("Inspection only: scoreboard rows are never joined into features, model training, or outcome labels.")
        if not has_real and demo:
            # No real primary records exist: never attach orphan source rows to fictional IDs.
            conn.execute("DELETE FROM products; DELETE FROM weaknesses; DELETE FROM source_references; DELETE FROM events")
            conn.executemany("INSERT INTO vulnerabilities VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'fictional demo data (not live)', NULL, true)", DEMO_RECORDS)
            conn.executemany("INSERT INTO events VALUES (?, ?, ?, ?, ?, 'fictional demo data (not live)', NULL, true)", DEMO_EVENTS)
        _derive(conn)
        from .analytics import reset_model_status
        reset_model_status()
        mode = "dataset" if has_real else ("demo" if demo else "empty")
        _META = {"mode": mode, "data_source": "Imported CSVs; not independently verified" if has_real else ("Fictional, synthetic demonstration data; not live" if demo else "No vulnerability records loaded"),
                 "data_dir": str(folder), "database": database, "files": reports,
                 "limitations": ["CSV schemas are inferred and aliases are limited; inspect each file's quality report.", "Missing files mean incomplete coverage, not absence of threats.", "Input sources and events are not independently verified.", "Text-rule characteristics are non-official hypotheses, not proof of exploitability.", "Current snapshots, severity and source labels are not point-in-time training features.", "Demo records, scores, events, products and profiles are completely fictional."]}
        return copy.deepcopy(_META)


def _connection():
    if _CONN is None:
        initialize()
    return _CONN


def quality_report() -> dict[str, Any]:
    """Dataset schemas, row/null/duplicate counts, aliases and source limitations."""
    with _LOCK:
        _connection()
        return copy.deepcopy(_META)


def _rows(conn, sql, params=()):
    cursor = conn.execute(sql, params)
    columns = [d[0] for d in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _date(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def _event_rows(conn, ids):
    if not ids: return {}
    placeholders = ",".join("?" for _ in ids)
    data = _rows(conn, f"""SELECT id, date, kind, value, description, source, source_row, is_demo, total_events
        FROM (SELECT *, count(*) OVER (PARTITION BY id) total_events,
          row_number() OVER (PARTITION BY id ORDER BY date DESC, source, source_row) rn
          FROM events WHERE id IN ({placeholders})) WHERE rn<=200 ORDER BY date, source, source_row""", ids)
    out = defaultdict(list)
    for event in data:
        event["date"] = _date(event["date"])
        event["type"] = event["kind"]
        event["simulated"] = event.pop("is_demo")
        out[event["id"]].append(event)
    return out


def _serialize(conn, rows):
    from .analytics import assess_momentum
    if not rows: return []
    ids = [r["id"] for r in rows]
    placeholders = ",".join("?" for _ in ids)
    chars = defaultdict(list)
    for c in _rows(conn, f"SELECT c.id, c.name, c.evidence, c.confidence, strpos(lower(v.description), lower(c.evidence))-1 AS start_offset FROM characteristics c JOIN vulnerabilities v ON c.id=v.id WHERE c.id IN ({placeholders}) ORDER BY c.name", ids):
        start = c.pop("start_offset")
        chars[c.pop("id")].append({**c, "evidence_span": {"start": start, "end": start + len(c["evidence"])}, "method": "deterministic text rule; not official", "uncertainty": "A phrase match is not proof of exploitability and may omit context or negation."})
    weakness_sources = defaultdict(list)
    for weakness in _rows(conn, f"SELECT id, cwes, source, source_row FROM weaknesses WHERE id IN ({placeholders}) ORDER BY source, source_row", ids):
        weakness_sources[weakness.pop("id")].append(weakness)
    events = _event_rows(conn, ids)
    result = []
    for r in rows:
        r["published"] = _date(r["published"])
        original_cwes = r.pop("cwes") or ""
        source_cwes = [{"cwes": original_cwes, "source": r["source"], "source_row": r["source_row"]}] if original_cwes else []
        source_cwes.extend(weakness_sources[r["id"]])
        r["cwes"] = list(dict.fromkeys(x.upper() for source in source_cwes for x in re.findall(r"CWE-\d+", source["cwes"], flags=re.I)))
        r["cwe_provenance"] = source_cwes
        status = (r["status"] or "").lower()
        if status in ("awaiting analysis", "undergoing analysis", "received", "not reviewed", "unreviewed", "incomplete", "new"):
            r["review_status"] = "Unreviewed / incomplete"
        elif status in ("analyzed", "reviewed", "modified"):
            r["review_status"] = "Reviewed (source-reported)"
        else:
            r["review_status"] = "Unknown"
        missing_cwe = not bool(r["cwes"])
        r["enrichment"] = {"missing_cvss": r["cvss"] is None, "missing_cwe": missing_cwe, "status_unknown": r["review_status"] == "Unknown",
                           "incomplete": r["cvss"] is None or missing_cwe or r["review_status"] != "Reviewed (source-reported)"}
        r["characteristics"] = chars[r["id"]]
        r["momentum_label"] = assess_momentum(r["id"], events[r["id"]], bool(r["kev"]))["label"]
        r["provenance"] = {"source": r["source"], "row": r.pop("source_row"), "raw_table": None if r["is_demo"] else "raw_vulnerabilities", "verified": False}
        r["simulated"] = r.pop("is_demo")
        result.append(r)
    return result


def list_vulnerabilities(q: str = "", characteristic: str = "", status: str = "", limit: int = 30, offset: int = 0) -> dict[str, Any]:
    """Filter in SQL and return one bounded page, plus the exact filtered total."""
    with _LOCK:
        conn = _connection()
        limit, offset = max(1, min(int(limit), 200)), max(0, int(offset))
        conditions, params = [], []
        if q.strip():
            conditions.append("(strpos(lower(v.id), lower(?)) > 0 OR strpos(lower(coalesce(v.description,'')), lower(?)) > 0 OR strpos(lower(coalesce(v.vendor,'')), lower(?)) > 0 OR strpos(lower(coalesce(v.product,'')), lower(?)) > 0)")
            params.extend([q.strip()] * 4)
        if characteristic.strip():
            conditions.append("EXISTS (SELECT 1 FROM characteristics c WHERE c.id=v.id AND lower(c.name)=lower(?))")
            params.append(characteristic.strip())
        if status.strip():
            if status.strip().lower() in ("unenriched", "incomplete"):
                conditions.append("""(v.cvss IS NULL OR NOT (regexp_matches(coalesce(v.cwes,''), '(?i)CWE-[0-9]+') OR EXISTS
                  (SELECT 1 FROM weaknesses w WHERE w.id=v.id AND regexp_matches(coalesce(w.cwes,''), '(?i)CWE-[0-9]+')))
                  OR lower(coalesce(v.status,'')) NOT IN ('analyzed','reviewed','modified'))""")
            elif status.strip().lower() == "unreviewed":
                conditions.append("lower(coalesce(v.status,'')) IN ('awaiting analysis','undergoing analysis','received','not reviewed','unreviewed','incomplete','new')")
            elif status.strip().lower() == "reviewed":
                conditions.append("lower(coalesce(v.status,'')) IN ('analyzed','reviewed','modified')")
            else:
                conditions.append("lower(coalesce(v.status,''))=lower(?)"); params.append(status.strip())
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        total = conn.execute("SELECT count(*) FROM vulnerabilities v" + where, params).fetchone()[0]
        rows = _rows(conn, "SELECT v.* FROM vulnerabilities v" + where + " ORDER BY v.published DESC NULLS LAST, v.id ASC LIMIT ? OFFSET ?", params + [limit, offset])
        return {"items": _serialize(conn, rows), "total": total}


def get_vulnerability(id: str) -> dict[str, Any] | None:
    with _LOCK:
        conn = _connection()
        rows = _rows(conn, "SELECT * FROM vulnerabilities WHERE id=?", [str(id).strip().upper()])
        items = _serialize(conn, rows)
        if not items: return None
        record = items[0]
        refs = _rows(conn, "SELECT date, url, source, source_row FROM source_references WHERE id=? ORDER BY date DESC NULLS LAST LIMIT 100", [record["id"]])
        for ref in refs: ref["date"] = _date(ref["date"])
        record["references"] = refs
        record["references_limit"] = 100
        record["affected_products"] = _rows(conn, "SELECT vendor, product, source, source_row FROM products WHERE id=? ORDER BY source_row LIMIT 100", [record["id"]])
        return record


def get_momentum(id: str) -> dict[str, Any]:
    from .analytics import assess_momentum
    with _LOCK:
        conn = _connection()
        vid = str(id).strip().upper()
        row = conn.execute("SELECT kev, is_demo FROM vulnerabilities WHERE id=?", [vid]).fetchone()
        if row is None:
            return {"id": vid, "label": "Insufficient evidence", "reason": "No matching vulnerability record.", "events": [], "limitations": ["Unknown identifier; no conclusion can be drawn."]}
        result = assess_momentum(vid, _event_rows(conn, [vid])[vid], bool(row[0]))
        result["simulated"] = bool(row[1])
        return result


def overview() -> dict[str, Any]:
    with _LOCK:
        conn = _connection()
        counts = conn.execute("""SELECT count(*), count(*) FILTER (WHERE v.cvss IS NULL OR NOT (regexp_matches(coalesce(v.cwes,''), '(?i)CWE-[0-9]+') OR EXISTS
          (SELECT 1 FROM weaknesses w WHERE w.id=v.id AND regexp_matches(coalesce(w.cwes,''), '(?i)CWE-[0-9]+'))) OR lower(coalesce(v.status,'')) NOT IN ('analyzed','reviewed','modified')),
          count(*) FILTER (WHERE kev), count(*) FILTER (WHERE EXISTS (SELECT 1 FROM events e WHERE e.id=v.id)) FROM vulnerabilities v""").fetchone()
        recent = list_vulnerabilities(limit=6)["items"]
        signal_rows = _rows(conn, "SELECT v.* FROM vulnerabilities v WHERE EXISTS (SELECT 1 FROM events e WHERE e.id=v.id) ORDER BY (SELECT max(date) FROM events e WHERE e.id=v.id) DESC NULLS LAST, v.id LIMIT 6")
        return {"mode": _META["mode"], "data_source": _META["data_source"], "stats": dict(zip(("total", "unenriched", "known_exploited", "with_signals"), counts)),
                "recent": recent, "signals": _serialize(conn, signal_rows), "limitations": copy.deepcopy(_META["limitations"])}


def profiles() -> list[dict[str, Any]]:
    """Name-only product matches against explicitly fictional inventories; no version claims."""
    with _LOCK:
        conn = _connection()
        result = copy.deepcopy(DEMO_PROFILES)
        for profile in result:
            profile["simulated"] = True
            profile["description"] = "Fictional mission profile, inventory, and dependencies; not an actual organization."
            profile["matches"] = []
            for asset in profile["inventory"]:
                asset["simulated"] = True
                # Query normalized rows and every affected-product row, not just first product.
                rows = _rows(conn, """SELECT DISTINCT v.id, v.description, v.kev, v.is_demo FROM vulnerabilities v
                  WHERE (lower(coalesce(v.vendor,''))=lower(?) AND lower(coalesce(v.product,''))=lower(?))
                     OR EXISTS (SELECT 1 FROM products p WHERE p.id=v.id AND lower(coalesce(p.vendor,''))=lower(?) AND lower(coalesce(p.product,''))=lower(?))
                  ORDER BY v.id LIMIT 200""", [asset["vendor"], asset["product"], asset["vendor"], asset["product"]])
                for row in rows:
                    profile["matches"].append({"id": row["id"], "vulnerability_id": row["id"], "vendor": asset["vendor"], "product": asset["product"], "description": row["description"],
                      "confidence": 0.55, "matching_confidence": 0.55, "explanation": "Vendor and product names match; version, configuration, and actual exposure are unknown.", "match_type": "Exact vendor/product name only; version and configuration unknown", "source_reported_kev": bool(row["kev"]),
                      "momentum_label": get_momentum(row["id"])["label"], "simulated_inventory": True,
                      "verification_needed": "Verify product identity, installed version, vulnerable version range, configuration, and original source before asserting exposure."})
            profile["limitations"] = ["Name matching is not proof of affected version or real exposure.", "Inventory, dependency edges, and mission impact are entirely simulated.", "Matches are capped at 200 per inventory item."]
        return result


def statistics() -> dict[str, Any]:
    from .analytics import statistics as compute_statistics
    return compute_statistics()


def model_status() -> dict[str, Any]:
    from .analytics import model_status as current_status
    return current_status()
