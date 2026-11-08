"""Data service tests; run with python -m unittest discover -s tests -p test_data.py."""
import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path

from app import analytics

HAS_DUCKDB = importlib.util.find_spec("duckdb") is not None
if HAS_DUCKDB:
    from app import data


def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)


class AnalyticsTests(unittest.TestCase):
    def test_momentum_rules_do_not_verify_exploitation(self):
        events = [{"date": "2024-01-01", "kind": "epss", "value": 0.10},
                  {"date": "2024-02-01", "kind": "epss", "value": 0.20}]
        result = analytics.assess_momentum("TEST-1", events)
        self.assertEqual(result["label"], "Increasing signal")
        self.assertIn("does not verify", result["reason"])
        self.assertEqual(analytics.assess_momentum("TEST-2", [])["label"], "Insufficient evidence")
        observed = analytics.assess_momentum("TEST-3", [{"date": "2024-01-02", "kind": "exploit_reference", "description": "public exploit reference"}])
        self.assertEqual(observed["label"], "Emerging signal")
        self.assertIn("not independently verified", " ".join(observed["limitations"]))
        reported = analytics.assess_momentum("TEST-4", [], True)
        self.assertEqual(reported["label"], "Reported exploitation evidence")
        self.assertIn("timing is unknown", reported["reason"])

    def test_momentum_binary_values_require_affirmative_evidence(self):
        negatives = [0, 0.0, -1, -0.1, False, "0", "0.0", "-1", "false", "no", "n", "f", "off",
                     "not exploited", "negative", "absent", "unknown", "pending", "N/A", "null", "none",
                     "1.00000000000000001", 2, float("nan"), float("inf")]
        for kind, description in (("kev", "Known exploitation observed."),
                                  ("exploit_reference", "Public exploit available.")):
            for value in negatives:
                with self.subTest(kind=kind, value=value):
                    events = [{"date": day, "kind": kind, "value": value, "description": description}
                              for day in ("2024-01-01", "2024-02-15")]
                    result = analytics.assess_momentum("TEST-NEGATIVE", events)
                    self.assertEqual(result["label"], "Insufficient evidence")
                    self.assertEqual(len(result["events"]), 2)
            for value in (1, 1.0, True, "1", "1.0", "+1.00e0", "true", "YES", "t"):
                with self.subTest(kind=kind, positive=value):
                    result = analytics.assess_momentum("TEST-POSITIVE", [{"date": "2024-01-01", "kind": kind, "value": value}])
                    self.assertEqual(result["label"], "Reported exploitation evidence" if kind == "kev" else "Emerging signal")
            for desc in (None, "", "unknown", "not known exploitation observed", "No public exploit available", "unverified event"):
                with self.subTest(kind=kind, description=desc):
                    self.assertEqual(analytics.assess_momentum("TEST-UNKNOWN", [{"date": "2024-01-01", "kind": kind, "value": None, "description": desc}])["label"], "Insufficient evidence")
            result = analytics.assess_momentum("TEST-DATED", [{"date": "2024-01-01", "kind": kind, "value": None, "description": description}])
            self.assertEqual(result["label"], "Reported exploitation evidence" if kind == "kev" else "Emerging signal")
            blank = analytics.assess_momentum("TEST-BLANK", [{"date": "2024-01-01", "kind": kind, "value": " ", "description": description}])
            self.assertEqual(blank["label"], result["label"])
        for value in ("false", "0", 0, -1, "unknown", None):
            self.assertEqual(analytics.assess_momentum("TEST-FLAG", [], value)["label"], "Insufficient evidence")
        demo = {"date": "2026-04-14", "kind": "kev", "value": None, "simulated": True,
                "description": "Fictional known-exploitation designation; not a real KEV listing."}
        self.assertEqual(analytics.assess_momentum("DEMO", [demo])["label"], "Reported exploitation evidence")
        demo["simulated"] = False
        self.assertEqual(analytics.assess_momentum("NOT-DEMO", [demo])["label"], "Insufficient evidence")

    def test_measured_metrics_and_ties(self):
        results = analytics._scores([1, 0, 1, 0], [0.9, 0.8, 0.2, 0.1])
        self.assertAlmostEqual(results["pr_auc"], 5/6)
        self.assertAlmostEqual(results["roc_auc"], 0.75)
        self.assertEqual(results["precision_at_500"], 0.5)
        self.assertEqual(results["recall_at_500"], 1.0)
        self.assertEqual(results["top_k_actual"], 4)
        self.assertIsNone(analytics._scores([0, 0], [0.5, 0.5])["roc_auc"])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "historical.csv"
        self.header = ["id", "snapshot_month", "outcome_start", "outcome_end", "label_available_at", "label", "source_dataset", "epss", "epss__available_at"]
        self.rows = []
        for i in range(8):
            train = i < 4
            self.rows.append({"id": f"HIST-TEST-{i}", "snapshot_month": "2024-01" if train else "2024-07",
                "outcome_start": "2024-02-01" if train else "2024-08-01",
                "outcome_end": "2024-03-31" if train else "2024-09-30",
                "label_available_at": "2024-03-31" if train else "2024-09-30",
                "label": str(i % 2), "source_dataset": "independent_historical_fixture.csv",
                "epss": "0.9" if i % 2 else "0.1", "epss__available_at": "2024-01-15" if train else "2024-07-15"})
        analytics.reset_model_status()

    def tearDown(self):
        self.temp.cleanup()
        analytics.reset_model_status()

    def run_evaluation(self):
        write_csv(self.path, self.header, self.rows)
        return analytics.evaluate_historical(self.path, "2024-06-30", ["epss"])

    def test_historical_model_and_baseline_actually_evaluate(self):
        result = self.run_evaluation()
        self.assertTrue(result["available"])
        self.assertFalse(result["scoreboard_used"])
        self.assertEqual(result["training_period"]["rows"], 4)
        self.assertEqual(result["validation_period"]["rows"], 4)
        for model in ("logistic_regression", "training_prevalence_baseline", "historical_epss_baseline"):
            for metric in ("precision", "recall", "f1", "pr_auc", "roc_auc", "precision_at_500", "recall_at_500"):
                self.assertIsNotNone(result["metrics"][model][metric])
        self.assertEqual(result["metrics"]["historical_epss_baseline"]["roc_auc"], 1.0)

    def test_temporal_guard_rejects_future_features_and_ambiguous_features(self):
        self.rows[0]["epss__available_at"] = "2024-02-01"
        with self.assertRaisesRegex(ValueError, "unavailable at snapshot"):
            self.run_evaluation()
        self.rows[0]["epss__available_at"] = "2024-01-15"
        write_csv(self.path, self.header, self.rows)
        with self.assertRaisesRegex(ValueError, "forbidden"):
            analytics.evaluate_historical(self.path, "2024-06-30", ["nvd_status"])
        with self.assertRaisesRegex(ValueError, "Missing required columns"):
            analytics.evaluate_historical(self.path, "2024-06-30", ["is_injection"])
        self.assertFalse(analytics.model_status()["available"])

    def test_temporal_guard_rejects_late_training_labels_and_overlap(self):
        self.rows[0]["label_available_at"] = "2024-07-01"
        with self.assertRaisesRegex(ValueError, "training label was not available"):
            self.run_evaluation()
        self.rows[0]["label_available_at"] = "2024-03-31"
        self.rows[4]["id"] = self.rows[0]["id"]
        with self.assertRaisesRegex(ValueError, "may not overlap"):
            self.run_evaluation()

    def test_scoreboard_is_never_used(self):
        self.rows[0]["source_dataset"] = "scoreboard_2026.csv"
        with self.assertRaisesRegex(ValueError, "scoreboard rows are forbidden"):
            self.run_evaluation()


@unittest.skipUnless(HAS_DUCKDB, "DuckDB is not installed; install project dependencies to run ingestion tests")
class DuckDBDataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_demo_fallback_is_unmistakably_fictional(self):
        report = data.initialize(self.folder, ":memory:")
        self.assertEqual(report["mode"], "demo")
        self.assertTrue(all(x["status"] == "absent" for x in report["files"].values()))
        page = data.list_vulnerabilities(limit=5, offset=0)
        self.assertEqual(len(page["items"]), 5)
        self.assertGreater(page["total"], 5)
        self.assertTrue(all(r["id"].startswith("DEMO-2026-") and r["simulated"] for r in page["items"]))
        record = data.get_vulnerability("demo-2026-0001")
        self.assertEqual(record["id"], "DEMO-2026-0001")
        evidence = record["characteristics"][0]
        self.assertEqual(record["description"][evidence["evidence_span"]["start"]:evidence["evidence_span"]["end"]].lower(), evidence["evidence"].lower())
        self.assertIn("not official", evidence["method"])
        self.assertEqual(data.get_momentum("DEMO-2026-0001")["label"], "Increasing signal")
        self.assertFalse(data.model_status()["available"])
        self.assertGreater(len(data.profiles()), 0)
        self.assertTrue(any(profile["matches"] for profile in data.profiles()))
        self.assertEqual(data.overview()["stats"]["total"], page["total"])
        self.assertEqual(data.statistics()["sample_size"], page["total"])

    def test_ingestion_aliases_quality_duplicate_search_and_sources(self):
        header = ["cve_id", "summary", "published_date", "nvd_status", "cwe_id", "cvss_score", "epss_score", "vendor", "product"]
        rows = [
            {"cve_id": "TEST-2024-0001", "summary": "Remote code execution in a fictional testing component.", "published_date": "2024-01-01", "nvd_status": "Awaiting Analysis", "cwe_id": "CWE-20", "cvss_score": "", "epss_score": "0.12", "vendor": "Example", "product": "Widget"},
            {"cve_id": "TEST-2024-0001", "summary": "Duplicate source record, preserved raw.", "published_date": "2024-01-02", "nvd_status": "Analyzed", "cwe_id": "CWE-79", "cvss_score": "7.1", "epss_score": "0.2", "vendor": "Example", "product": "Widget"},
            {"cve_id": "TEST-2024-0002", "summary": "SQL injection in an imaginary test product.", "published_date": "2024-03-01", "nvd_status": "Analyzed", "cwe_id": "CWE-89", "cvss_score": "9.0", "epss_score": "0.01", "vendor": "Example", "product": "Other"},
        ]
        write_csv(self.folder / "vulnerabilities.csv", header, rows)
        write_csv(self.folder / "exploit_signals_2024.csv", ["cve_id", "signal_date", "epss"], [
            {"cve_id": "TEST-2024-0001", "signal_date": "2024-01-10", "epss": "0.02"},
            {"cve_id": "TEST-2024-0001", "signal_date": "2024-02-10", "epss": "0.12"}])
        write_csv(self.folder / "exploit_signals_2025.csv", ["cve_id", "snapshot_month", "epss"], [{"cve_id": "TEST-2024-0001", "snapshot_month": "2025-02", "epss": "0.12"}])
        write_csv(self.folder / "weakness_types.csv", ["cve_id", "cwe_id"], [{"cve_id": "TEST-2024-0001", "cwe_id": "CWE-79"}])
        write_csv(self.folder / "references.csv", ["cve_id", "unsupported_link"], [{"cve_id": "TEST-2024-0001", "unsupported_link": "example.invalid"}])
        write_csv(self.folder / "scoreboard_2026.csv", ["cve_id", "epss"], [{"cve_id": "TEST-2024-0001", "epss": "0.99"}])
        report = data.initialize(self.folder, ":memory:")
        self.assertEqual(report["mode"], "dataset")
        quality = report["files"]["vulnerabilities.csv"]
        self.assertEqual(quality["rows"], 3)
        self.assertEqual(quality["duplicate_key_groups"], 1)
        self.assertEqual(quality["duplicate_rows"], 1)
        self.assertEqual(quality["null_counts"]["cvss_score"], 1)
        self.assertEqual(report["files"]["references.csv"]["status"], "unsupported")
        self.assertTrue(quality["inferred_types"])
        page = data.list_vulnerabilities(q="test-2024", limit=1, offset=1)
        self.assertEqual(page["total"], 2)
        self.assertEqual(len(page["items"]), 1)
        self.assertEqual(data.list_vulnerabilities(characteristic="Injection")["total"], 1)
        self.assertEqual(data.list_vulnerabilities(status="unreviewed")["total"], 1)
        self.assertEqual(data.list_vulnerabilities(q="%_")["total"], 0)
        record = data.get_vulnerability("TEST-2024-0001")
        self.assertEqual(record["epss"], 0.12)  # not the scoreboard value
        self.assertEqual(record["provenance"]["raw_table"], "raw_vulnerabilities")
        self.assertEqual(record["cwes"], ["CWE-20", "CWE-79"])
        self.assertEqual(record["cwe_provenance"][1]["source"], "weakness_types.csv")
        self.assertTrue(record["enrichment"]["incomplete"])
        self.assertEqual(data.list_vulnerabilities(status="unenriched")["total"], 1)
        momentum = data.get_momentum(record["id"])
        self.assertEqual(momentum["label"], "Increasing signal")
        self.assertEqual(momentum["events"][-1]["date"], "2025-02-28")
        self.assertIn("underlying event date is unknown", momentum["events"][-1]["description"])
        self.assertIsNone(data.get_vulnerability("TEST-NO-SUCH-ID"))

    def test_unsupported_main_schema_remains_visible_and_demo_is_explicit(self):
        write_csv(self.folder / "vulnerabilities.csv", ["bad_key", "text"], [{"bad_key": "x", "text": "y"}])
        report = data.initialize(self.folder, ":memory:")
        self.assertEqual(report["files"]["vulnerabilities.csv"]["status"], "unsupported")
        self.assertEqual(report["mode"], "demo")
        self.assertEqual(report["files"]["vulnerabilities.csv"]["rows"], 1)

    def test_typed_binary_signals_preserve_neutral_values_without_promotion(self):
        values = ["0", "0.0", "-1", "-0.1", "false", "FALSE", "no", "n", "f", "off",
                  "not exploited", "negative", "absent", "unknown", "pending", "N/A", "null", "none",
                  "1.00000000000000001", "2", "NaN", "Infinity"]
        vulnerability_rows, signal_rows, cases = [], [], []
        for kind, field, description in (("kev", "kev", "Known exploitation observed."),
                                         ("public_exploit", "public_exploit", "Public exploit available.")):
            for index, value in enumerate(values):
                identifier = f"TEST-{kind}-{index}"
                cases.append((identifier, kind, value))
                vulnerability_rows.append({"cve_id": identifier, "description": "Test record"})
                for day in ("2024-01-01", "2024-02-15"):
                    signal_rows.append({"cve_id": identifier, "signal_date": day, "signal_type": kind,
                                        "signal_value": value, "signal_description": description, field: "true"})
        write_csv(self.folder / "vulnerabilities.csv", ["cve_id", "description"], vulnerability_rows)
        write_csv(self.folder / "exploit_signals_2024.csv", ["cve_id", "signal_date", "signal_type", "signal_value", "signal_description", "kev", "public_exploit"], signal_rows)
        report = data.initialize(self.folder, ":memory:")
        self.assertEqual(report["files"]["exploit_signals_2024.csv"]["status"], "loaded")
        for identifier, kind, value in cases:
            with self.subTest(kind=kind, value=value):
                result = data.get_momentum(identifier)
                self.assertEqual(result["label"], "Insufficient evidence")
                self.assertEqual(data.get_vulnerability(identifier)["momentum_label"], "Insufficient evidence")
                self.assertEqual(len(result["events"]), 2)
                for event in result["events"]:
                    expected_kind = "kev_observation" if kind == "kev" else "exploit_reference_observation"
                    self.assertEqual(event["kind"], expected_kind)
                    self.assertIn(f"source value={value}", event["description"])
                    self.assertIn("not positive evidence", event["description"])
                    self.assertEqual(event["source"], "exploit_signals_2024.csv")
                    self.assertIsNotNone(event["source_row"])
                if value.lower() in ("0", "0.0", "false", "no", "n", "f"):
                    self.assertEqual(result["events"][0]["value"], 0.0)

    def test_explicit_positive_and_missing_typed_values(self):
        rows = [
            ("POS-KEV-NUM", "kev", "1", "unverified"),
            ("POS-KEV-EXACT", "kev", "+1.00e0", "unverified"),
            ("POS-KEV-YES", "known_exploited", "yes", "unverified"),
            ("POS-EXPLOIT-TRUE", "poc", "true", "unverified"),
            ("POS-KEV-DESC", "kev", "", "Added to the CISA KEV catalog."),
            ("POS-REF-DESC", "exploit_reference", "", "Public exploit available."),
            ("NO-KEV-DESC", "kev", "", "No known exploitation observed."),
            ("NO-REF-DESC", "exploit_reference", "", ""),
            ("UNKNOWN-KEV", "kev", "unknown", "Known exploitation observed."),
            ("NEG-REF", "exploit_reference", "false", "Public exploit available."),
        ]
        write_csv(self.folder / "vulnerabilities.csv", ["cve_id", "description"], [{"cve_id": r[0], "description": "Test record"} for r in rows])
        write_csv(self.folder / "exploit_signals_2025.csv", ["cve_id", "snapshot_month", "signal_type", "signal_value", "signal_description"], [
            {"cve_id": identifier, "snapshot_month": "2025-02", "signal_type": kind, "signal_value": value, "signal_description": description}
            for identifier, kind, value, description in rows])
        report = data.initialize(self.folder, ":memory:")
        self.assertEqual(report["files"]["exploit_signals_2025.csv"]["status"], "loaded")
        for identifier, kind, value, _ in rows:
            with self.subTest(identifier=identifier):
                result = data.get_momentum(identifier)
                if identifier.startswith("POS-KEV"):
                    self.assertEqual(result["label"], "Reported exploitation evidence")
                    self.assertNotIn("timing is unknown", result["reason"])
                elif identifier.startswith("POS-"):
                    self.assertEqual(result["label"], "Emerging signal")
                else:
                    self.assertEqual(result["label"], "Insufficient evidence")
                self.assertEqual(result["events"][0]["date"], "2025-02-28")
                self.assertIn("underlying event date is unknown", result["events"][0]["description"])
                if identifier == "POS-KEV-DESC":
                    self.assertIsNone(result["events"][0]["value"])

    def test_positive_dated_event_sources_and_synthetic_event(self):
        write_csv(self.folder / "vulnerabilities.csv", ["cve_id", "description"], [
            {"cve_id": name, "description": "Test record"} for name in ("KNOWN", "KEV-FLAG", "REF-FLAG")])
        write_csv(self.folder / "known_exploited.csv", ["cve_id", "date_added"], [{"cve_id": "KNOWN", "date_added": "2024-01-10"}])
        write_csv(self.folder / "exploit_signals_2024.csv", ["cve_id", "signal_date", "kev", "public_exploit"], [
            {"cve_id": "KEV-FLAG", "signal_date": "2024-01-10", "kev": "true"},
            {"cve_id": "REF-FLAG", "signal_date": "2024-01-10", "public_exploit": "yes"}])
        data.initialize(self.folder, ":memory:")
        for name in ("KNOWN", "KEV-FLAG"):
            result = data.get_momentum(name)
            self.assertEqual(result["label"], "Reported exploitation evidence")
            self.assertNotIn("timing is unknown", result["reason"])
        self.assertEqual(data.get_momentum("REF-FLAG")["label"], "Emerging signal")
        data.initialize(self.folder / "empty", ":memory:")
        demo = data.get_momentum("DEMO-2026-0004")
        self.assertEqual(demo["label"], "Reported exploitation evidence")
        self.assertNotIn("timing is unknown", demo["reason"])
        self.assertTrue(any(e["kind"] == "kev" and e["value"] is None for e in demo["events"]))

    def test_typed_event_without_value_column_needs_description(self):
        rows = [
            {"cve_id": "NO-VALUE", "signal_date": "2024-01-01", "signal_type": "kev", "signal_description": ""},
            {"cve_id": "POS-VALUE", "signal_date": "2024-01-01", "signal_type": "kev", "signal_description": "Known exploitation observed."},
            {"cve_id": "NO-REF", "signal_date": "2024-01-01", "signal_type": "poc", "signal_description": "not a public exploit reference"},
        ]
        write_csv(self.folder / "vulnerabilities.csv", ["cve_id", "description"], [{"cve_id": r["cve_id"], "description": "Test"} for r in rows])
        write_csv(self.folder / "exploit_signals_2024.csv", ["cve_id", "signal_date", "signal_type", "signal_description"], rows)
        report = data.initialize(self.folder, ":memory:")
        self.assertEqual(report["files"]["exploit_signals_2024.csv"]["status"], "loaded")
        self.assertEqual(data.get_momentum("NO-VALUE")["label"], "Insufficient evidence")
        self.assertEqual(data.get_momentum("NO-REF")["label"], "Insufficient evidence")
        result = data.get_momentum("POS-VALUE")
        self.assertEqual(result["label"], "Reported exploitation evidence")
        self.assertNotIn("timing is unknown", result["reason"])

    def test_unrelated_positive_flag_is_independent_of_neutral_typed_signal(self):
        write_csv(self.folder / "vulnerabilities.csv", ["cve_id", "description"], [{"cve_id": "TEST-MIXED", "description": "Test"}])
        write_csv(self.folder / "exploit_signals_2024.csv", ["cve_id", "signal_date", "signal_type", "signal_value", "kev"], [
            {"cve_id": "TEST-MIXED", "signal_date": "2024-01-01", "signal_type": "poc", "signal_value": "0", "kev": "true"}])
        report = data.initialize(self.folder, ":memory:")
        self.assertEqual(report["files"]["exploit_signals_2024.csv"]["status"], "loaded")
        result = data.get_momentum("TEST-MIXED")
        self.assertEqual(result["label"], "Reported exploitation evidence")
        self.assertEqual({e["kind"] for e in result["events"]}, {"kev", "exploit_reference_observation"})


if __name__ == "__main__":
    unittest.main()
