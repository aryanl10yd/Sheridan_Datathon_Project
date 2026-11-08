"""Deterministic analytics and leakage-guarded historical model evaluation.

No prediction or evaluation is fabricated from the demonstration data. The
historical evaluator runs only on explicitly supplied, point-in-time labelled CSVs.
"""
from __future__ import annotations

import copy
import csv
import math
import os
import re
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any


# Exact, affirmative event descriptions accepted only when a signal value is
# absent. A bare event kind, arbitrary prose, or an unrecognized value is not
# evidence. Keep this small and auditable rather than guessing at negation.
_POSITIVE_EVENT_DESCRIPTIONS = {
    "kev": frozenset({
        "source reports known exploitation",
        "source reports known exploitation; not independently verified.",
        "source reports known exploitation; source has not been independently verified.",
        "known exploitation reported",
        "known exploitation observed",
        "known exploitation confirmed",
        "known-exploitation designation",
        "added to cisa kev",
        "added to cisa kev catalog",
        "added to the cisa kev catalog",
        "added to cisa known exploited vulnerabilities catalog",
        "added to the cisa known exploited vulnerabilities catalog",
        "listed in cisa kev catalog",
    }),
    "exploit_reference": frozenset({
        "source reports a public exploit or poc reference",
        "source reports a public exploit or poc reference; existence and functionality are unverified.",
        "public exploit reference",
        "proof-of-concept reference",
        "public exploit available",
        "public proof of concept available",
        "public poc available",
        "public exploit reported",
        "public proof-of-concept reported",
    }),
}
_POSITIVE_DEMO_DESCRIPTIONS = {
    "kev": frozenset({"fictional known-exploitation designation; not a real kev listing."}),
    "exploit_reference": frozenset({
        "fictional public proof-of-concept reference; no exploit code or verification.",
        "fictional unverified exploitation-related reference.",
        "fictional unverified proof-of-concept reference.",
    }),
}
_SNAPSHOT_SUFFIX = " monthly observation snapshot placed at month-end; the underlying event date is unknown."
_TRUE_NUMERIC_TOKEN = r"[+]?0*1(?:[.]0*)?(?:[eE][+-]?0+)?"


def _positive_signal_event(event: dict) -> bool:
    """Interpret affirmative binary values or a small set of explicit event texts.

    Any supplied value takes precedence over text: invalid, false, negative, and
    unrecognized values cannot be rescued by an affirmative description.
    """
    kind = event.get("kind")
    if kind not in _POSITIVE_EVENT_DESCRIPTIONS:
        return False
    value = event.get("value")
    if isinstance(value, str) and not value.strip():
        value = None
    if value is not None:
        if isinstance(value, str):
            value = value.strip().lower()
            if value in ("true", "yes", "y", "t"):
                return True
            return bool(re.fullmatch(_TRUE_NUMERIC_TOKEN, value))
        return isinstance(value, (int, float)) and value == 1 and math.isfinite(value)
    description = str(event.get("description") or "").strip().lower()
    if description.endswith(_SNAPSHOT_SUFFIX):
        description = description[:-len(_SNAPSHOT_SUFFIX)]
    return (description.rstrip(".") in {item.rstrip(".") for item in _POSITIVE_EVENT_DESCRIPTIONS[kind]} or
            bool(event.get("simulated") or event.get("is_demo")) and description in _POSITIVE_DEMO_DESCRIPTIONS[kind])


def assess_momentum(id: str, events: list[dict], kev: bool = False) -> dict[str, Any]:
    """Classify source-reported observations without calling them verified activity.

    Increasing = an observed EPSS increase >= 0.05 between distinct dates.
    Persistent = at least two dated exploit-reference observations >=30 days
    apart, or two EPSS observations >=30 days apart differing by <0.05.
    Emerging = at least one affirmative dated exploit-reference or EPSS observation.
    Source-reported KEV has priority but is not independently authenticated.
    """
    ordered = sorted((dict(e) for e in events if e.get("date")), key=lambda x: str(x["date"]))
    epss = [e for e in ordered if e.get("kind") == "epss" and isinstance(e.get("value"), (int, float)) and 0 <= e["value"] <= 1]
    refs = [e for e in ordered if e.get("kind") == "exploit_reference" and _positive_signal_event(e)]
    kev_events = [e for e in ordered if e.get("kind") == "kev" and _positive_signal_event(e)]
    reported_kev = _positive_signal_event({"kind": "kev", "value": kev})
    restrictions = ["Source reports and references are not independently verified; a reference is not proof of a working exploit.",
                    "Only supplied dated observations are evaluated; sparse data cannot establish absence of exploitation.",
                    "EPSS change is a change in source-reported probability, not a measurement of actual exploitation.",
                    "Thresholds are demonstration heuristics, not a universal risk score.",
                    "KEV and exploit-reference observations count only when explicitly affirmative; unrecognized wording may be missed."]
    total_events = max((int(e.get("total_events", len(ordered))) for e in ordered), default=0)
    if total_events > len(ordered):
        restrictions.append(f"Assessment uses the latest {len(ordered)} of {total_events} dated observations; earlier history is omitted.")
    if any(e.get("simulated") for e in ordered):
        restrictions.insert(0, "All demonstration signals are fictional; they are not live threat intelligence.")
    if kev_events or reported_kev:
        label = "Reported exploitation evidence"
        reason = "A supplied source reports a known-exploitation designation; this file has not been independently authenticated."
        if reported_kev and not kev_events:
            reason += " No valid dated designation was supplied, so timing is unknown."
    elif len(epss) >= 2 and epss[-1]["date"] != epss[0]["date"] and epss[-1]["value"] - epss[0]["value"] >= 0.05 - 1e-12:
        label = "Increasing signal"
        reason = f"Source-reported EPSS-like values rose by {epss[-1]['value'] - epss[0]['value']:.3f} from {epss[0]['date']} to {epss[-1]['date']}; this does not verify exploitation."
    else:
        def span_days(values):
            try:
                return (date.fromisoformat(str(values[-1]["date"])[:10]) - date.fromisoformat(str(values[0]["date"])[:10])).days
            except (ValueError, TypeError, IndexError):
                return 0
        persistent_ref = len(refs) >= 2 and span_days(refs) >= 30
        persistent_epss = len(epss) >= 2 and span_days(epss) >= 30 and abs(epss[-1]["value"] - epss[0]["value"]) < 0.05
        if persistent_ref or persistent_epss:
            label = "Persistent signal"
            reason = "Supplied observations of the same signal span at least 30 days; persistence of reports is not proof of persistent exploitation."
        elif refs or epss:
            label = "Emerging signal"
            reason = "A dated exploitation-related reference or probability observation exists, but a trend or actual exploitation is not established."
        else:
            label = "Insufficient evidence"
            reason = "No eligible dated exploitation-related observations are available."
    return {"id": id, "label": label, "reason": reason, "events": ordered, "total_events": total_events, "limitations": restrictions,
            "method": "Deterministic source-reported event rules; not an official assessment."}


def statistics() -> dict[str, Any]:
    """Compute descriptive characteristic frequencies and bounded supporting records."""
    from . import data
    with data._LOCK:
        conn = data._connection()
        total = conn.execute("SELECT count(*) FROM vulnerabilities").fetchone()[0]
        counts = data._rows(conn, "SELECT name, count(DISTINCT id) AS count FROM characteristics GROUP BY name ORDER BY count DESC, name LIMIT 12")
        findings = []
        for item in counts:
            records = [r[0] for r in conn.execute("SELECT DISTINCT id FROM characteristics WHERE name=? ORDER BY id LIMIT 5", [item["name"]]).fetchall()]
            findings.append({"characteristic": item["name"], "count": item["count"],
                             "proportion": item["count"] / total if total else None,
                             "sample_size": total, "records": records,
                             "method": "Count distinct normalized records with an exact deterministic description-rule match; examples are the first five sorted identifiers.",
                             "interpretation": "Descriptive frequency only; not evidence of causation, verified exploitability, or a statistical anomaly."})
        combinations = data._rows(conn, """SELECT a.name first_characteristic, b.name second_characteristic, count(DISTINCT a.id) count
          FROM characteristics a JOIN characteristics b ON a.id=b.id AND a.name<b.name
          GROUP BY 1,2 ORDER BY count DESC, first_characteristic, second_characteristic LIMIT 5""")
        for item in combinations:
            item["records"] = [r[0] for r in conn.execute("""SELECT DISTINCT a.id FROM characteristics a
              JOIN characteristics b ON a.id=b.id WHERE a.name=? AND b.name=? ORDER BY a.id LIMIT 5""",
              [item["first_characteristic"], item["second_characteristic"]]).fetchall()]
            item["sample_size"] = total
            item["method"] = "Count distinct records matching both description rules; no independence or significance test."
        status_counts = data._rows(conn, "SELECT coalesce(status,'Unknown') status, count(*) count FROM vulnerabilities GROUP BY 1 ORDER BY count DESC, status")
        return {"method": "DuckDB full-cohort descriptive counts; deterministic keyword rules can overlap.",
                "sample_size": total, "records": sorted({r for finding in findings for r in finding["records"]}),
                "findings": findings, "combinations": combinations, "status_counts": status_counts, "data_source": data._META["data_source"],
                "limitations": ["The dataset is a convenience sample, not a representative population.",
                                "One record may match multiple rules; counts do not sum to the cohort size.",
                                "Examples are capped at five per characteristic; matches may miss context or negation.",
                                "Frequencies do not measure causation, exploitation rates, or statistical significance."]}


_FEATURES = {
    "epss", "days_since_publication", "has_public_exploit", "has_cwe", "cwe_count",
    "is_remote_code_execution", "is_authentication_bypass", "is_privilege_escalation",
    "is_memory_corruption", "is_buffer_overflow", "is_injection", "is_deserialization",
    "is_denial_of_service", "is_information_disclosure", "is_access_control", "is_improper_input_validation",
}
# These fields are unsuitable even if present in a current export: their own
# retrospective update history is not established by a generic timestamp.
_BANNED = ("scoreboard", "nvd_status", "n_affected_cpes", "n_references", "cvss", "severity", "news", "future", "outcome", "label", "kev")
_MODEL: dict[str, Any] = {}


def reset_model_status() -> None:
    global _MODEL
    _MODEL = {}


def model_status() -> dict[str, Any]:
    if _MODEL:
        return copy.deepcopy(_MODEL)
    return {"available": False, "status": "unavailable", "reason": "No eligible historical model has been evaluated. Imported data is not assumed to contain point-in-time features and subsequent, fully observed labels.",
            "training_cutoff": None, "training_period": None, "validation_period": None, "feature_fields": [],
            "feature_availability": "Unknown until independently documented point-in-time inputs are supplied.",
            "target": "Subsequent exploitation within the supplied, explicitly dated outcome window.", "scoreboard_used": False,
            "metrics": None, "limitations": ["No historical evaluation has been run; there are no model results to report.",
                "The 2026 scoreboard is excluded from training and validation.", "Missing observation dates and label windows cannot establish temporal eligibility."]}


def _timestamp(value: str, field: str, end_of_day: bool = False) -> datetime:
    value = str(value or "").strip()
    if not value:
        raise ValueError(f"Missing {field}; time availability must be explicit.")
    try:
        if len(value) == 10:
            d = date.fromisoformat(value)
            return datetime.combine(d, time.max if end_of_day else time.min, tzinfo=timezone.utc)
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            raise ValueError("timezone required for timestamps")
        return dt.astimezone(timezone.utc)
    except ValueError as exc:
        raise ValueError(f"Invalid {field} timestamp {value!r}; use an ISO date or timezone-aware ISO timestamp.") from exc


def _month_end(value: str) -> datetime:
    try:
        if len(value) != 7 or value[4] != "-": raise ValueError
        year, month = (int(x) for x in value.split("-"))
        first = date(year, month, 1)
        next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
        return datetime.combine(next_month - timedelta(days=1), time.max, tzinfo=timezone.utc)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid snapshot_month {value!r}; expected YYYY-MM.")


def _scores(y: list[int], scores: list[float], k: int = 500) -> dict[str, Any]:
    """Metrics using fixed threshold .5, grouped ties and actual top-k size."""
    n, positives = len(y), sum(y)
    tp = sum(1 for a, s in zip(y, scores) if a == 1 and s >= 0.5)
    fp = sum(1 for a, s in zip(y, scores) if a == 0 and s >= 0.5)
    fn = positives - tp
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / positives if positives else None
    f1 = (2 * precision * recall / (precision + recall) if precision + recall else 0.0) if recall is not None else None
    # A stable row-order tie break is disclosed; grouped ties are used for curves.
    ranked = sorted(range(n), key=lambda i: (-scores[i], i))
    selected = ranked[:min(k, n)]
    top_true = sum(y[i] for i in selected)
    ap = 0.0 if positives else None
    roc = 0.0 if positives and positives < n else None
    cumulative_pos = cumulative_neg = 0
    previous_tpr = previous_fpr = 0.0
    index = 0
    while index < n:
        end = index + 1
        while end < n and scores[ranked[end]] == scores[ranked[index]]: end += 1
        new_positive = sum(y[i] for i in ranked[index:end])
        cumulative_pos += new_positive
        cumulative_neg += end - index - new_positive
        if positives:
            ap += (new_positive / positives) * (cumulative_pos / end)
        if roc is not None:
            tpr, fpr = cumulative_pos / positives, cumulative_neg / (n - positives)
            roc += (fpr - previous_fpr) * (tpr + previous_tpr) / 2
            previous_tpr, previous_fpr = tpr, fpr
        index = end
    return {"precision": precision, "recall": recall, "f1": f1, "pr_auc": ap, "roc_auc": roc,
            "precision_at_500": top_true / len(selected) if selected else None,
            "recall_at_500": top_true / positives if positives else None,
            "top_k_actual": len(selected), "positives": positives, "sample_size": n,
            "decision_threshold": 0.5,
            "definitions": {"pr_auc": "Average precision: sum of precision at each distinct score times recall increment; not trapezoidal PR area.",
                            "roc_auc": "Trapezoidal ROC area with tied scores grouped; null when only one class.",
                            "top_500": "First min(500,n) rows ranked by descending score; ties use input row order."}}


def _logistic(train_x, train_y, test_x, iterations=350, learning_rate=0.25, l2=0.05):
    """Small deterministic standardized logistic regression; no validation tuning."""
    n, d = len(train_x), len(train_x[0])
    means = [sum(row[j] for row in train_x) / n for j in range(d)]
    scales = [math.sqrt(sum((row[j] - means[j]) ** 2 for row in train_x) / n) or 1.0 for j in range(d)]
    def standardize(rows): return [[(row[j] - means[j]) / scales[j] for j in range(d)] for row in rows]
    tx, vx = standardize(train_x), standardize(test_x)
    weights, bias = [0.0] * d, 0.0
    for _ in range(iterations):
        gradient, intercept = [0.0] * d, 0.0
        for row, target in zip(tx, train_y):
            z = max(-40.0, min(40.0, bias + sum(w*x for w, x in zip(weights, row))))
            error = 1.0 / (1.0 + math.exp(-z)) - target
            intercept += error
            for j in range(d): gradient[j] += error * row[j]
        bias -= learning_rate * intercept / n
        weights = [weights[j] - learning_rate * (gradient[j] / n + l2 * weights[j]) for j in range(d)]
    scores = [1.0 / (1.0 + math.exp(-max(-40.0, min(40.0, bias + sum(w*x for w, x in zip(weights, row)))))) for row in vx]
    return scores, {"standardized_coefficients": weights, "intercept": bias, "means": means, "scales": scales,
                    "iterations": iterations, "learning_rate": learning_rate, "l2": l2}


def evaluate_historical(csv_path: str | os.PathLike, cutoff: str, feature_columns: list[str]) -> dict[str, Any]:
    """Train/evaluate a historical model on explicitly timestamped labeled rows.

    Every feature must be on the allowlist and have a matching <feature>__available_at
    column. Every row needs id, snapshot_month, outcome_start, outcome_end,
    label_available_at, label (0/1), and source_dataset. Features must predate the
    snapshot month end; the label window must start afterward. Train labels must
    have matured by cutoff; validation snapshots must be later than cutoff. IDs may
    not cross partitions. Source rows and path must not be scoreboard data.

    This function is intentionally an offline batch evaluator: it loads the supplied
    training table in memory and records results only after all guards pass.
    """
    global _MODEL
    if "scoreboard" in str(Path(csv_path).name).lower():
        raise ValueError("2026 scoreboard cannot be used for training or validation.")
    if not feature_columns or len(set(feature_columns)) != len(feature_columns):
        raise ValueError("Provide a nonempty, unique explicit feature list.")
    for feature in feature_columns:
        if any(banned in feature.lower() for banned in _BANNED) or feature not in _FEATURES:
            raise ValueError(f"Feature {feature!r} is forbidden or not on the point-in-time feature allowlist.")
    split = _timestamp(cutoff, "training cutoff", end_of_day=True)
    needed = {"id", "snapshot_month", "outcome_start", "outcome_end", "label_available_at", "label", "source_dataset"}
    needed.update(feature_columns)
    needed.update(f + "__available_at" for f in feature_columns)
    training, validation, seen = [], [], set()
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        missing = needed - set(reader.fieldnames or [])
        if missing: raise ValueError("Missing required columns: " + ", ".join(sorted(missing)))
        for line, row in enumerate(reader, 2):
            identifier = str(row["id"] or "").strip().upper()
            source = str(row["source_dataset"] or "").strip()
            if not identifier or not source: raise ValueError(f"Line {line}: id and source_dataset are required.")
            if "scoreboard" in source.lower(): raise ValueError(f"Line {line}: scoreboard rows are forbidden.")
            snap = _month_end(row["snapshot_month"].strip())
            key = (identifier, row["snapshot_month"].strip())
            if key in seen: raise ValueError(f"Line {line}: duplicate id/snapshot_month.")
            seen.add(key)
            start = _timestamp(row["outcome_start"], "outcome_start")
            end = _timestamp(row["outcome_end"], "outcome_end", end_of_day=True)
            known = _timestamp(row["label_available_at"], "label_available_at", end_of_day=True)
            if known > datetime.now(timezone.utc):
                raise ValueError(f"Line {line}: label is not yet observable; future evaluation results cannot be reported.")
            if start <= snap or end < start or known < end:
                raise ValueError(f"Line {line}: outcomes must start after snapshot, end after start, and be fully observed before label availability.")
            if str(row["label"]).strip() not in ("0", "1"):
                raise ValueError(f"Line {line}: label must be 0 or 1.")
            values = []
            for feature in feature_columns:
                available = _timestamp(row[feature + "__available_at"], feature + "__available_at", end_of_day=True)
                if available > snap:
                    raise ValueError(f"Line {line}: {feature} was unavailable at snapshot month end.")
                try: value = float(row[feature])
                except (TypeError, ValueError): raise ValueError(f"Line {line}: {feature} must be numeric and non-null.")
                if not math.isfinite(value): raise ValueError(f"Line {line}: {feature} must be finite.")
                if feature == "epss" and not 0 <= value <= 1: raise ValueError(f"Line {line}: EPSS must be between 0 and 1.")
                values.append(value)
            item = {"id": identifier, "snapshot": snap, "label_available": known, "y": int(row["label"]), "x": values}
            if snap <= split:
                if known > split:
                    raise ValueError(f"Line {line}: training label was not available by cutoff; move the cutoff or remove the row.")
                training.append(item)
            else:
                validation.append(item)
    if not training or not validation: raise ValueError("Need both training rows and strictly later validation snapshots.")
    overlap = {r["id"] for r in training} & {r["id"] for r in validation}
    if overlap: raise ValueError("Vulnerability IDs may not overlap training and validation partitions.")
    if len({r["y"] for r in training}) < 2: raise ValueError("Training must contain both positive and negative labels.")
    ys = [r["y"] for r in validation]
    model_scores, coefficients = _logistic([r["x"] for r in training], [r["y"] for r in training], [r["x"] for r in validation])
    prevalence = sum(r["y"] for r in training) / len(training)
    metrics = {"logistic_regression": _scores(ys, model_scores), "training_prevalence_baseline": _scores(ys, [prevalence] * len(validation))}
    if "epss" in feature_columns:
        ix = feature_columns.index("epss")
        metrics["historical_epss_baseline"] = _scores(ys, [r["x"][ix] for r in validation])
    _MODEL = {"available": True, "status": "evaluated", "training_cutoff": split.isoformat(),
              "training_period": {"earliest_snapshot_end": min(r["snapshot"] for r in training).isoformat(), "latest_snapshot_end": max(r["snapshot"] for r in training).isoformat(), "rows": len(training)},
              "validation_period": {"earliest_snapshot_end": min(r["snapshot"] for r in validation).isoformat(), "latest_snapshot_end": max(r["snapshot"] for r in validation).isoformat(), "rows": len(validation)},
              "feature_fields": feature_columns[:], "feature_availability": "Per-feature source-supplied timestamps were checked against each snapshot month end; authenticity and historical completeness are not independently verified.",
              "target": "Input label within the explicitly supplied future outcome window; all labels must be observed by label_available_at.",
              "scoreboard_used": False, "metrics": metrics, "model": {"type": "L2-regularized logistic regression", "parameters": coefficients},
              "limitations": ["Feature availability timestamps and labels are source assertions, not independently authenticated.",
                              "Results depend on the supplied historical cohort and observation horizon; no causal claim.",
                              "Rows and model training are held in memory; this evaluator is intended for explicit offline batches.",
                              "Threshold and model hyperparameters are fixed, not tuned; top-500 ties use input row order.",
                              "No model is deployed for live prediction by this offline evaluation."]}
    return copy.deepcopy(_MODEL)
