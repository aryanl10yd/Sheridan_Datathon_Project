"""Entirely fictional data for an offline product demonstration.

DEMO identifiers are deliberately not CVE identifiers. No record, score, event,
product, organization, or mission profile in this file is a live claim.
"""

DEMO_RECORDS = [
    ("DEMO-2026-0001", "The fictional Asterion Telemetry Relay accepts an unauthenticated telemetry packet that may permit remote code execution through improper input validation.", "2026-01-14", "Awaiting Analysis", "CWE-20", None, 0.16, False, "Asterion Demo", "Telemetry Relay"),
    ("DEMO-2026-0002", "A fictional Asterion Mission Planner authorization check may allow authentication bypass and privilege escalation for a specially crafted request.", "2026-02-03", "Undergoing Analysis", "CWE-287;CWE-269", None, 0.32, False, "Asterion Demo", "Mission Planner"),
    ("DEMO-2026-0003", "The fictional Meridian Link Gateway contains a buffer overflow in a message parser that could cause a denial of service.", "2026-02-18", "Analyzed", "CWE-120", 7.5, 0.12, False, "Meridian Demo", "Link Gateway"),
    ("DEMO-2026-0004", "The fictional Northstar Build Console may deserialize untrusted data, potentially allowing arbitrary code execution.", "2026-03-02", "Awaiting Analysis", "CWE-502", None, 0.46, True, "Northstar Demo", "Build Console"),
    ("DEMO-2026-0005", "A fictional Asterion Telemetry Relay diagnostic endpoint may cause information disclosure when access control is improperly enforced.", "2026-03-21", "Analyzed", "CWE-200;CWE-284", 5.3, 0.04, False, "Asterion Demo", "Telemetry Relay"),
    ("DEMO-2026-0006", "A fictional Meridian Ground Client query handler may allow SQL injection and unauthorized data access.", "2026-04-09", "Received", "CWE-89", None, 0.07, False, "Meridian Demo", "Ground Client"),
    ("DEMO-2026-0007", "The fictional Northstar Dependency Mirror has a memory corruption issue in its archive reader.", "2026-04-24", "Awaiting Analysis", "CWE-119", None, None, False, "Northstar Demo", "Dependency Mirror"),
    ("DEMO-2026-0008", "The fictional Meridian Link Gateway may experience denial of service from malformed control messages.", "2026-05-11", "Analyzed", "CWE-20", 6.5, 0.09, False, "Meridian Demo", "Link Gateway"),
    ("DEMO-2026-0009", "The fictional Asterion Mission Planner has an access control weakness that may expose planning metadata.", "2026-06-08", "Received", "CWE-284", None, None, False, "Asterion Demo", "Mission Planner"),
    ("DEMO-2026-0010", "The fictional Meridian Ground Client may allow privilege escalation through a misconfigured local service.", "2026-07-16", "Undergoing Analysis", "CWE-269", None, 0.02, False, "Meridian Demo", "Ground Client"),
    ("DEMO-2026-0011", "The fictional Northstar Build Console may expose build metadata via an information disclosure flaw.", "2026-08-05", "Analyzed", "CWE-200", 4.3, 0.01, False, "Northstar Demo", "Build Console"),
    ("DEMO-2026-0012", "The fictional Asterion Orbit Scheduler rejects malformed messages inconsistently; the security consequence is unknown.", "2026-09-12", "Awaiting Analysis", "", None, None, False, "Asterion Demo", "Orbit Scheduler"),
]

# Event tuples: vulnerability ID, ISO date, type, optional numerical value,
# description. These are synthetic observations, not live intelligence.
DEMO_EVENTS = [
    ("DEMO-2026-0001", "2026-01-20", "epss", 0.03, "Synthetic EPSS-like value; not an actual EPSS observation."),
    ("DEMO-2026-0001", "2026-02-20", "epss", 0.16, "Synthetic EPSS-like value; not an actual EPSS observation."),
    ("DEMO-2026-0001", "2026-02-23", "exploit_reference", None, "Fictional public proof-of-concept reference; no exploit code or verification."),
    ("DEMO-2026-0002", "2026-02-20", "exploit_reference", None, "Fictional unverified exploitation-related reference."),
    ("DEMO-2026-0003", "2026-03-05", "epss", 0.12, "Synthetic EPSS-like value; not an actual EPSS observation."),
    ("DEMO-2026-0003", "2026-04-05", "epss", 0.12, "Synthetic EPSS-like value; not an actual EPSS observation."),
    ("DEMO-2026-0004", "2026-03-08", "exploit_reference", None, "Fictional unverified proof-of-concept reference."),
    ("DEMO-2026-0004", "2026-04-14", "kev", None, "Fictional known-exploitation designation; not a real KEV listing."),
    ("DEMO-2026-0006", "2026-05-06", "exploit_reference", None, "Fictional unverified exploitation-related reference."),
]

# Dependency edges are illustrative only; assets and components do not exist.
DEMO_PROFILES = [
    {"id": "ground-ops", "name": "Ground Operations Workstation", "inventory": [{"vendor": "Meridian Demo", "product": "Ground Client"}], "dependencies": [{"from": "Ground Client", "to": "Operator display", "relationship": "supports"}, {"from": "Operator display", "to": "Simulated ground operations", "relationship": "supports"}]},
    {"id": "telemetry", "name": "Telemetry Processing Environment", "inventory": [{"vendor": "Asterion Demo", "product": "Telemetry Relay"}], "dependencies": [{"from": "Telemetry Relay", "to": "Telemetry processing", "relationship": "supports"}, {"from": "Telemetry processing", "to": "Simulated mission monitoring", "relationship": "supports"}]},
    {"id": "communications", "name": "Satellite Communication Support Server", "inventory": [{"vendor": "Meridian Demo", "product": "Link Gateway"}], "dependencies": [{"from": "Link Gateway", "to": "Message service", "relationship": "supports"}, {"from": "Message service", "to": "Simulated communications support", "relationship": "supports"}]},
    {"id": "planning", "name": "Mission Planning Environment", "inventory": [{"vendor": "Asterion Demo", "product": "Mission Planner"}, {"vendor": "Asterion Demo", "product": "Orbit Scheduler"}], "dependencies": [{"from": "Mission Planner", "to": "Planning service", "relationship": "supports"}, {"from": "Orbit Scheduler", "to": "Planning service", "relationship": "supports"}, {"from": "Planning service", "to": "Simulated mission planning", "relationship": "supports"}]},
    {"id": "development", "name": "Software Development Environment", "inventory": [{"vendor": "Northstar Demo", "product": "Build Console"}, {"vendor": "Northstar Demo", "product": "Dependency Mirror"}], "dependencies": [{"from": "Dependency Mirror", "to": "Build Console", "relationship": "supplies packages"}, {"from": "Build Console", "to": "Simulated software delivery", "relationship": "supports"}]},
    {"id": "network", "name": "Ground Station Network Support", "inventory": [{"vendor": "Meridian Demo", "product": "Link Gateway"}], "dependencies": [{"from": "Link Gateway", "to": "Network support", "relationship": "supports"}, {"from": "Network support", "to": "Simulated ground station connectivity", "relationship": "supports"}]},
]
