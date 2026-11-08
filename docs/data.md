# Data and analytics integration

## Status and provenance

No named CSVs were supplied for this build. By default, the service uses **fictional synthetic demonstration records** named `DEMO-2026-0001`, etc. These are not CVEs; all demo descriptions, products, missions, probability-like values, and dated events are invented solely to exercise the interface. They are not live intelligence or a claim of real exploitation. Source-provided records are also not independently verified.

## Dependencies and initialization

DuckDB is required (`duckdb>=1.1,<2`). It is a project dependency, not installed by this data-layer implementation. After the parent project installs its declared requirements, run the server with a single process and call `initialize()` **once at startup**:

```python
from app import data

report = data.initialize()          # reads SENTINEL_DATA_DIR (default ./data)
page = data.list_vulnerabilities(q="telemetry", limit=30, offset=0)
record = data.get_vulnerability("DEMO-2026-0001")  # dict or None
momentum = data.get_momentum("DEMO-2026-0001")     # dict, even for unknown id
inventory = data.profiles()          # list of simulated profiles
summary = data.overview()            # mode, data_source, stats, recent, signals
statistics = data.statistics()       # actual cohort counts and sample record IDs
model = data.model_status()          # unavailable until a guarded evaluation succeeds
quality = data.quality_report()      # detailed file/schema/quality metadata
```

`SENTINEL_DATA_DIR` selects the directory holding the named CSVs. `SENTINEL_DB_PATH` selects the DuckDB database (default `/tmp/sentinel_orbital.duckdb`). In code, `initialize(data_dir="/path/to/csvs", db_path="/path/to/database.duckdb", demo=True)` overrides both. For tests use `db_path=":memory:"`. Initialization **replaces tables** in that database; reserve a separate database file for this app and do not point it at unrelated data. CSV changes require explicit reinitialization; the service does not poll files. Calls are synchronized through one process-local connection and lock. DuckDB's connection/locking model here is not a multi-worker distributed database; run one server worker or use a dedicated data service for concurrency across processes. Never expose database writes to an untrusted client.

If no usable primary vulnerability records load, demo data is enabled by default, and the report explains missing, failed, or unsupported source files. `demo=False` instead returns an empty dataset. Partial related files never enrich fictional rows. No external network or live feed is consulted. If a primary file loads, even partially, mode is `dataset` and the service does not silently mix in fictional records.

## Ingestion and quality report

Recognized filenames: `vulnerabilities.csv`, `affected_products.csv`, `references.csv`, `known_exploited.csv`, `exploit_signals_2024.csv`, `exploit_signals_2025.csv`, `weakness_types.csv`, and `scoreboard_2026.csv`. Files are read through DuckDB into persistent `raw_<filename>` tables as VARCHAR, with a one-based `__source_row`. This preserves the supplied values and source-row lineage. `quality_report()` reports each file's status (`absent`, `loaded`, `unsupported`, or `error`), path, original columns, sampled inferred SQL types, aliases resolved, row counts, column null/empty counts, duplicate ID groups, excess rows sharing an ID, exact duplicate full records, join key, and warnings. Inferred types come from a sample, not a guarantee about all rows. A duplicate ID is expected in a many-to-one table such as references; it is **not automatically a duplicate record**.

Case and punctuation are ignored when matching aliases. Common supported names include:

| Logical field | Examples of accepted source names |
| --- | --- |
| ID | `cve_id`, `cve`, `id`, `vulnerability_id`, `vuln_id` |
| Description | `description`, `description_text`, `summary`, `details` |
| Publication | `published`, `published_date`, `published_at`, `publication_date` |
| Review | `status`, `nvd_status`, `analysis_status`, `vuln_status` |
| Weakness | `cwes`, `cwe`, `cwe_id`, `cwe_ids`, `weakness_id` |
| Scores | `cvss`, `cvss_score`, `cvss_v3_score`, `epss`, `epss_score`, `epss_probability` |
| Product | `vendor`, `vendor_name`, `product`, `product_name` |
| Signal time/type | `event_date`, `signal_date`, `date`, `date_added`, `snapshot_date`, `snapshot_month`; `signal_type`, `event_type`, `type` |
| Signal value/description | `signal_value`, `value`, `score`; `signal_description`, `event_description`, `description`, `details`, `notes` |
| Reference | `url`, `reference`, `reference_url`, `link` |

Primary records require an ID and description column; products require ID and product; references require ID and URL; weakness types require ID and CWE; signals require ID, a date, and a recognized signal/EPSS/exploit/KEV column. Known-exploited rows need an ID; without a date they provide only an undated source-reported current designation. Unsupported files remain in raw tables and are explicitly reported, not guessed. Nested JSON structures, unlisted formats, CPE/version-range semantics, and differently encoded labels may require an adapter before import. CWE output recognizes `CWE-<number>` tokens; unrecognized weakness values remain available in raw tables.

Normalization retains the first primary row by source order for duplicate IDs and keeps every original row for audit. Source and row number accompany returned records and events; related product/reference provenance is also retained. Source counts and fields can be incomplete or incorrect. Invalid CVSS outside 0–10 or EPSS outside 0–1 becomes null, not zero. Unparseable or absent dates remain null; undated signals are not plotted as dated events. An explicit `snapshot_month` is positioned at the end of that month as an observation snapshot, with a warning that the underlying event date is unknown; a month-only publication date is not assigned an invented day. Source URL presence, a repository, or a proof-of-concept claim is not proof of a working exploit. The 2026 scoreboard may be inspected as a raw table but is **never** joined into vulnerability features, outcomes, training, or evaluation.

### Typed KEV and public-exploit signals

An event type alone is **not** evidence that the signal is positive. For typed `kev`, `known_exploited`, or `known exploited` events, and `exploit_reference`, `public_exploit`, `poc`, or `proof_of_concept` events, the following policy applies to the supplied value (after trimming, case-insensitively):

* `true`, `yes`, `y`, `t`, or an explicit numeric-one token is affirmative. Numeric text must contain `1` with optional leading zeros or `+`, optional zero-only fractional digits, and an optional zero exponent (for example, `1`, `1.0`, `+1.00e0`); a general positive number such as `2` is not a binary true value. This deliberately excludes other spellings of one, such as `0.1e1`, instead of inferring them through floating-point rounding.
* `0`, negative numbers, `false`, `no`, `n`, `f`, and all other nonempty values, including `unknown`, `N/A`, non-finite numbers, and unrecognized strings, are **not** positive evidence. A supplied value always takes precedence over the event description, even if the description says something affirmative. Negative or unknown typed events remain on the timeline as `kev_observation` or `exploit_reference_observation`; their description marks them neutral and records the lowercased source type and trimmed source value. Finite numeric values are preserved, recognized false words normalize to `0`, and unrecognized/non-finite strings have a null numeric value. The raw table retains the original source row.
* A missing or empty value can count as an affirmative event **only** when the description is an exact accepted affirmative phrase, ignoring case, surrounding whitespace, and trailing periods. For KEV these are: `source reports known exploitation`, `source reports known exploitation; not independently verified`, `source reports known exploitation; source has not been independently verified`, `known exploitation reported`, `known exploitation observed`, `known exploitation confirmed`, `known-exploitation designation`, `added to cisa kev`, `added to cisa kev catalog`, `added to the cisa kev catalog`, `added to cisa known exploited vulnerabilities catalog`, `added to the cisa known exploited vulnerabilities catalog`, and `listed in cisa kev catalog`. For exploit references these are: `source reports a public exploit or poc reference`, `source reports a public exploit or poc reference; existence and functionality are unverified`, `public exploit reference`, `proof-of-concept reference`, `public exploit available`, `public proof of concept available`, `public poc available`, `public exploit reported`, and `public proof-of-concept reported`. Other wording, including negated or uncertain prose, stays neutral. The known, explicitly positive synthetic event descriptions are separately accepted only when marked simulated; they remain fictional. The application-added snapshot disclaimer does not change an accepted event's meaning.

Separate affirmative Boolean `kev` / public-exploit columns, and entries in a known-exploited list without a Boolean column, are independent source assertions. Where the same row also has a typed value for the **same** signal, a supplied negative or unrecognized value blocks the conflicting Boolean flag; a flag for a different signal remains independent. Likewise, a separate current source-reported KEV designation can still determine the label even if another observation is negative. No negative observation proves an absence of exploitation, and events do not automatically set the current vulnerability `kev` field. These strict rules can miss genuine positives expressed in other formats, and they do not perform general-language negation or resolve contradictory narrative text accompanying an explicit positive value. Source assertions, including accepted positive descriptions, are not authenticated or proof of a working exploit; inspect raw rows and verify sources independently.

Ingestion, filters, counts, joins, and paging execute in DuckDB; records are not loaded wholesale into Python. Search is case-insensitive literal substring matching (not an indexed full-text search); ID equality and joins have indexes, but description search and quality inspection can scan tables. Deep offsets can be slow. Exact duplicate detection and multiple text-rule scans may be expensive on multi-million-row files and may spill to disk; budget disk space for raw + normalized data and temporary sort/hash work. Query pages are capped at 200. Individual momentum timelines use the most recent 200 dated events and report truncation when applicable. Detail references, products, and profile matches have documented caps. The offline model evaluator is an explicit exception: it loads its training CSV into memory.

## Record and analytical semantics

`overview()` returns `{mode, data_source, stats: {total, unenriched, known_exploited, with_signals}, recent, signals, limitations}`. `mode` describes data, and the server may override it with an agent mode. `list_vulnerabilities(q='', characteristic='', status='', limit=30, offset=0)` returns `{items, total}`. `unreviewed` filters known source-reported incomplete review statuses. `incomplete` and `unenriched` instead include records missing CVSS, missing recognized CWE, or without a source-reported reviewed status; the overview uses this broader definition. Missing enrichment does not establish danger. `get_vulnerability(id)` is case-insensitive and returns null for an unknown identifier. `get_momentum(id)` returns an `Insufficient evidence` object for an unknown ID; an HTTP layer that wants a 404 should first check `get_vulnerability(id)`.

Every record has `id`, `description`, `published`, `status`, `cwes` array, nullable `cvss` and `epss`, `kev`, `characteristics`, `vendor`, `product`, `source`, `review_status`, and `momentum_label`, plus `provenance`, `cwe_provenance`, `enrichment`, and `simulated`. Each characteristic has the exact text evidence, zero-based half-open `evidence_span`, a fixed rule confidence, and method/uncertainty. The confidence is a hand-assigned heuristic, **not calibrated probability**, an official NIST category, a Granite inference, or proof of exploitability. Simple pattern matching can miss wording, context, and negation. CWE values are source-provided, not independently verified.

Momentum consists of `(label, reason, events, limitations)`, not a universal score. Source-reported known exploitation takes precedence and is explicitly not authenticated; the label is **Reported exploitation evidence**, not a claim of independently confirmed exploitation. Otherwise an absolute rise of at least 0.05 between first and last available EPSS observations on different dates is `Increasing signal`. If two affirmative references or stable EPSS observations span at least 30 days, it is `Persistent signal`. A single EPSS or affirmative reference observation gives `Emerging signal`; all other cases are `Insufficient evidence`. Neutral KEV or reference observations do not count as positive evidence. These thresholds are illustrative, not calibrated. EPSS changes are probability changes rather than measurements of actual attacks. The latest event window, unverified provenance, and lack of coverage limit conclusions.

`statistics()` computes actual DuckDB cohort and distinct-characteristic frequencies, with denominator and up to five supporting record IDs per finding. Counts can overlap; these are descriptive, not statistical significance, anomaly proof, causal findings, or representative population estimates. `profiles()` returns an array of six clearly fictional inventories and dependency graphs. Potential matches use exact case-insensitive vendor/product names only. `confidence=0.55` is a heuristic, not a calibrated probability; versions and configuration are unknown and the match does not establish impact.

## Guarded historical evaluation

`app.analytics.evaluate_historical(csv_path, cutoff, feature_columns)` performs a real offline standardized L2 logistic regression and compares a training-prevalence baseline and, when present, a historical EPSS baseline. It calculates precision, recall, F1 at a fixed 0.5 threshold; PR-AUC (average precision); ROC-AUC when both classes exist; and precision/recall among the top `min(500,n)` records. Ranked ties use source row order; curve ties are grouped. Missing/undefined metrics are JSON null. Model details, split dates, sample sizes, and limitations are returned. Training is deterministic and held in memory; this is an evaluator, not a deployed production prediction service.

```python
from app.analytics import evaluate_historical
result = evaluate_historical(
    "/data/validated_point_in_time_training.csv",
    cutoff="2024-12-31",
    feature_columns=["epss", "is_injection"],
)
# Only after success: app.data.model_status() exposes these calculated results.
```

Every CSV row requires exact columns `id`, `snapshot_month` (`YYYY-MM`), `outcome_start`, `outcome_end`, `label_available_at`, `label` (`0`/`1`), `source_dataset`, each selected numerical feature, and one `<feature>__available_at` for each selected feature. Availability must be at/before snapshot-month end. The subsequent outcome window must start strictly after that end, end no earlier than it starts, and be fully observed by label availability. Labels must be observable at run time. Training snapshots and their matured labels must be at/before cutoff; validation snapshots must be strictly later. The same ID cannot appear across the split, duplicate ID/months are rejected, and training needs both classes. Date-only timestamps are interpreted conservatively in UTC; timestamps with a time must include a timezone.

Allowed features: `epss`, `days_since_publication`, `has_public_exploit`, `has_cwe`, `cwe_count`, and `is_remote_code_execution`, `is_authentication_bypass`, `is_privilege_escalation`, `is_memory_corruption`, `is_buffer_overflow`, `is_injection`, `is_deserialization`, `is_denial_of_service`, `is_information_disclosure`, `is_access_control`, `is_improper_input_validation`. Retrospective `nvd_status`, affected CPE counts, reference counts, CVSS/severity, news, KEV/outcome/label fields, and scoreboard features are rejected, regardless of generic timestamp. Scoreboard-named input files or source datasets are rejected. Source-supplied timestamps and dataset identity are assertions: the service cannot independently prove that a producer did not backfill a value or relabel a scoreboard. Validate source lineage and observation completeness before trusting a result. No eligible historical dataset has been supplied; no model metrics are claimed by default.

## Verification

From the project root, after installing declared project dependencies:

```bash
python -m unittest discover -s tests -p 'test_data.py' -v
# or, if pytest is installed:
python -m pytest -q tests/test_data.py
python -m py_compile app/data.py app/analytics.py app/demo_data.py
```

The test file is standard-library `unittest` and deliberately skips its DuckDB-backed tests if DuckDB is missing. Passing only the dependency-free tests does **not** establish that CSV ingestion works in that environment. The tests include synthetic temporary input, exact metric checks, file/schema/duplicate inspection, search and paging, positive, negative and unknown event rules, provenance, scoreboard exclusion, and temporal leakage rejection.
