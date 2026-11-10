#!/usr/bin/env python3
"""
PayFlex quality gate - classifies each pipeline stage as PASS / WARNING / CRITICAL.

Usage:  python3 scripts/quality_gate.py --stage <stage>
Stages: secrets-source | unit | sonar | integration | perf | confidentiality | summary

Behaviour
  * WARNING  -> exit 0, GitHub annotation + notification line, pipeline continues
  * CRITICAL -> exit 1 (fail fast), incident report written, next stages are skipped
"""
import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPORTS = Path(os.environ.get("REPORTS_DIR", "reports"))

# ---------------------------------------------------------------- thresholds
COVERAGE_WARN = 80.0      # < 80  -> warning   (70 <= cov < 80)
COVERAGE_CRIT = 70.0      # < 70  -> critical
P95_WARN_MS = 200.0       # > 200 -> warning   (200..500)
P95_CRIT_MS = 500.0       # > 500 -> critical
ERR_WARN = 0.01           # > 1 % -> warning
ERR_CRIT = 0.02           # > 2 % -> critical
LEAK_THRESHOLD = 0        # max tolerated leaks

STAGES = ["secrets-source", "unit", "sonar", "integration", "perf", "confidentiality"]
LABELS = {
    "secrets-source": "Secrets scan (source/config)",
    "unit": "Unit tests + coverage",
    "sonar": "SonarQube static analysis",
    "integration": "Integration tests (Docker + Newman)",
    "perf": "Performance tests (k6)",
    "confidentiality": "Confidentiality (source + artifact + logs)",
}
ADVICE = {
    "secrets-source": "Remove the secret from the code/config, rotate it (it must be considered compromised) and purge it from git history.",
    "unit": "Fix the failing tests / add tests until coverage reaches at least 70% (80% target).",
    "sonar": "Open the SonarQube issues of type BUG / VULNERABILITY and fix them.",
    "integration": "Check reports/newman-report.json and the container log to find the broken API contract.",
    "perf": "Profile the slow endpoints; check recent changes, DB calls, blocking code and resource limits.",
    "confidentiality": "Remove the leaked secret/PII from the artifact or logs, rotate the credential and re-run the pipeline.",
}


def load(name):
    p = REPORTS / name
    if not p.exists():
        return None
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def new_result(stage):
    return {"stage": stage, "status": "pass", "metrics": {}, "warnings": [], "criticals": [], "details": []}


# ------------------------------------------------------------------ stages
def stage_unit(r):
    res = load("jest-results.json")
    cov = load("coverage-summary.json")
    if res is None:
        r["criticals"].append("Unit test report (jest-results.json) is missing: tests did not run.")
        return
    failed = res.get("numFailedTests", 0)
    total = res.get("numTotalTests", 0)
    r["metrics"].update({"tests_total": total, "tests_failed": failed})
    if failed > 0 or res.get("numFailedTestSuites", 0) > 0:
        r["criticals"].append(f"{failed} unit test(s) failing out of {total}: regression detected.")
    if cov is None:
        r["criticals"].append("Coverage report (coverage-summary.json) is missing.")
        return
    pct = float(cov["total"]["lines"]["pct"])
    r["metrics"]["coverage_pct"] = pct
    if pct < COVERAGE_CRIT:
        r["criticals"].append(f"Code coverage is {pct:.1f}% - below the critical threshold ({COVERAGE_CRIT:.0f}%).")
    elif pct < COVERAGE_WARN:
        r["warnings"].append(f"Attention, coverage at {pct:.1f}% (target >= {COVERAGE_WARN:.0f}%).")


def stage_sonar(r):
    meas = load("sonar-measures.json")
    gate = load("sonar-gate.json")
    if meas is None:
        r["criticals"].append("SonarQube measures are missing: analysis did not complete.")
        return
    m = {x["metric"]: x.get("value") for x in meas["component"]["measures"]}
    bugs = int(m.get("bugs", 0))
    vulns = int(m.get("vulnerabilities", 0))
    smells = int(m.get("code_smells", 0))
    r["metrics"].update({"bugs": bugs, "vulnerabilities": vulns, "code_smells": smells,
                         "sonar_coverage": m.get("coverage"), "duplication_pct": m.get("duplicated_lines_density")})
    if bugs > 0:
        r["criticals"].append(f"SonarQube found {bugs} bug(s) (blocking, e.g. potential NullPointer/TypeError).")
    if vulns > 0:
        r["criticals"].append(f"SonarQube found {vulns} vulnerability(ies).")
    if smells > 0:
        r["warnings"].append(f"Technical debt: {smells} code smell(s) reported by SonarQube.")
    if gate:
        status = gate["projectStatus"]["status"]
        r["metrics"]["sonar_quality_gate"] = status
        if status == "ERROR":
            bad = [c["metricKey"] for c in gate["projectStatus"]["conditions"] if c["status"] == "ERROR"]
            r["warnings"].append(f"SonarQube Quality Gate = ERROR (failed conditions: {', '.join(bad)}).")


def stage_integration(r):
    rep = load("newman-report.json")
    if rep is None:
        r["criticals"].append("Newman report is missing: integration scenario did not run.")
        return
    run = rep["run"]
    asserts = run["stats"]["assertions"]
    reqs = run["stats"]["requests"]
    r["metrics"].update({"requests": reqs["total"], "assertions": asserts["total"], "assertions_failed": asserts["failed"]})
    if asserts["total"] == 0:
        r["criticals"].append("No assertion executed in the integration scenario.")
    if asserts["failed"] > 0 or run.get("failures"):
        r["criticals"].append(f"{asserts['failed']} API assertion(s) failed: contract/regression error.")
        for fl in run.get("failures", [])[:10]:
            src = (fl.get("source") or {}).get("name", "?")
            r["details"].append(f"{src}: {fl['error'].get('test') or fl['error'].get('message')}")


def stage_perf(r):
    data = load("k6-summary.json")
    if data is None:
        r["criticals"].append("k6 summary is missing: load test did not run.")
        return

    def vals(name):
        m = data["metrics"].get(name, {})
        return m.get("values", m)

    p95 = float(vals("http_req_duration").get("p(95)", 0))
    err = float(vals("http_req_failed").get("rate", vals("http_req_failed").get("value", 0)))
    count = int(vals("http_reqs").get("count", 0))
    r["metrics"].update({"p95_ms": round(p95, 2), "error_rate_pct": round(err * 100, 3), "requests": count})
    if count == 0:
        r["criticals"].append("k6 executed 0 requests.")
        return
    if p95 > P95_CRIT_MS:
        r["criticals"].append(f"Latency p95 = {p95:.0f} ms exceeds the critical threshold ({P95_CRIT_MS:.0f} ms).")
    elif p95 > P95_WARN_MS:
        r["warnings"].append(f"Latency p95 = {p95:.0f} ms is above the target ({P95_WARN_MS:.0f} ms) but under {P95_CRIT_MS:.0f} ms.")
    if err > ERR_CRIT:
        r["criticals"].append(f"Error rate = {err*100:.2f}% exceeds the critical threshold ({ERR_CRIT*100:.0f}%).")
    elif err > ERR_WARN:
        r["warnings"].append(f"Error rate = {err*100:.2f}% is above the target ({ERR_WARN*100:.0f}%).")


def confidentiality_rate(leaks, threshold=LEAK_THRESHOLD):
    """Taux = (1 - leaks / threshold) * 100. With threshold 0 the ratio is undefined,
    so the denominator is max(threshold, 1): 0 leak -> 100 %, any leak -> 0 %."""
    return max(0.0, 1.0 - leaks / max(threshold, 1)) * 100.0


def stage_confidentiality(r):
    files = sorted(glob.glob(str(REPORTS / "gitleaks-*.json")))
    if not files:
        r["criticals"].append("No Gitleaks report found: confidentiality scan did not run.")
        return
    total = 0
    per_scan = {}
    for fp in files:
        with open(fp, encoding="utf-8") as f:
            findings = json.load(f) or []
        scan = Path(fp).stem.replace("gitleaks-", "")
        per_scan[scan] = len(findings)
        total += len(findings)
        for x in findings:
            r["details"].append(f"[{scan}] rule={x.get('RuleID')} file={x.get('File')} line={x.get('StartLine')}")
    rate = confidentiality_rate(total)
    r["metrics"].update({"leaks_detected": total, "confidentiality_rate_pct": rate, "per_scan": per_scan})
    if rate < 100.0:
        r["criticals"].append(f"Confidentiality rate = {rate:.0f}% (< 100%): {total} leak(s) of secrets/PII detected.")


STAGE_FUNCS = {
    "secrets-source": stage_confidentiality,
    "unit": stage_unit,
    "sonar": stage_sonar,
    "integration": stage_integration,
    "perf": stage_perf,
    "confidentiality": stage_confidentiality,
}


# ---------------------------------------------------------------- reporting
def ctx():
    repo = os.environ.get("GITHUB_REPOSITORY", "local")
    run = os.environ.get("GITHUB_RUN_ID", "-")
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    return {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "repo": repo,
        "branch": os.environ.get("GITHUB_REF_NAME", "local"),
        "sha": os.environ.get("GITHUB_SHA", "local")[:8],
        "run_url": f"{server}/{repo}/actions/runs/{run}" if run != "-" else "local run",
    }


def append_summary(text):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text + "\n")


def incident_markdown(r):
    c = ctx()
    lines = [
        "# INCIDENT REPORT - Deployment blocked",
        "",
        f"- **Date**: {c['date']}",
        f"- **Repository / branch / commit**: {c['repo']} / {c['branch']} / {c['sha']}",
        f"- **Pipeline run**: {c['run_url']}",
        f"- **Blocking stage**: {LABELS[r['stage']]}",
        "- **Classification**: CRITICAL",
        "",
        "## Exact cause",
    ]
    lines += [f"- {x}" for x in r["criticals"]]
    if r["details"]:
        lines += ["", "## Details"] + [f"- {x}" for x in r["details"]]
    lines += ["", "## Metrics"] + [f"- {k}: {v}" for k, v in r["metrics"].items()]
    if r["warnings"]:
        lines += ["", "## Non-critical warnings raised on the same stage"] + [f"- {x}" for x in r["warnings"]]
    lines += [
        "", "## Action taken",
        "Fail-fast: pipeline stopped, all following stages cancelled, **no deployment**.",
        "", "## Recommended fix", ADVICE[r["stage"]], "",
    ]
    return "\n".join(lines)


def finish(r):
    r["status"] = "critical" if r["criticals"] else ("warning" if r["warnings"] else "pass")
    REPORTS.mkdir(parents=True, exist_ok=True)
    with (REPORTS / f"gate-{r['stage']}.json").open("w", encoding="utf-8") as f:
        json.dump(r, f, indent=2)

    icon = {"pass": "PASS", "warning": "WARNING", "critical": "CRITICAL"}[r["status"]]
    print("=" * 70)
    print(f"QUALITY GATE | {LABELS[r['stage']]} | {icon}")
    print("=" * 70)
    for k, v in r["metrics"].items():
        print(f"  {k}: {v}")
    for w in r["warnings"]:
        print(f"::warning title=PayFlex NON-CRITICAL::{w}")
        print(f"  [WARNING]  {w}")
    for x in r["criticals"]:
        print(f"::error title=PayFlex CRITICAL::{x}")
        print(f"  [CRITICAL] {x}")
    for d in r["details"]:
        print(f"    - {d}")

    emoji = {"pass": "✅", "warning": "⚠️", "critical": "❌"}[r["status"]]
    md = [f"### {emoji} {LABELS[r['stage']]} - {icon}", ""]
    md += [f"- `{k}` = {v}" for k, v in r["metrics"].items()]
    md += [f"- ⚠️ {w}" for w in r["warnings"]]
    md += [f"- ❌ {x}" for x in r["criticals"]]
    append_summary("\n".join(md))

    if r["criticals"]:
        inc = incident_markdown(r)
        (REPORTS / f"incident-{r['stage']}.md").write_text(inc, encoding="utf-8")
        append_summary(inc)
        print("\nFAIL FAST: critical error, pipeline stopped. Incident report written.")
        return 1
    return 0


def stage_summary():
    c = ctx()
    rows, warnings, incidents = [], [], []
    blocked = False
    all_present = True
    for s in STAGES:
        g = load(f"gate-{s}.json")
        if g is None:
            rows.append(f"| {LABELS[s]} | ⏭️ skipped / not reached | - |")
            all_present = False
            continue
        icon = {"pass": "✅ PASS", "warning": "⚠️ WARNING", "critical": "❌ CRITICAL"}[g["status"]]
        key = ", ".join(f"{k}={v}" for k, v in g["metrics"].items() if k != "per_scan")
        rows.append(f"| {LABELS[s]} | {icon} | {key} |")
        warnings += [f"- ({s}) {w}" for w in g["warnings"]]
        if g["status"] == "critical":
            blocked = True
            p = REPORTS / f"incident-{s}.md"
            if p.exists():
                incidents.append(p.read_text(encoding="utf-8"))
    decision = "🚫 DEPLOYMENT BLOCKED" if blocked or not all_present else "🚀 DEPLOYMENT ALLOWED"
    out = [
        "# PayFlex pipeline report", "",
        f"Run: {c['run_url']} - branch `{c['branch']}` - commit `{c['sha']}` - {c['date']}", "",
        f"## Decision: {decision}", "",
        "| Stage | Result | Key metrics |", "|---|---|---|", *rows, "",
    ]
    if warnings:
        out += ["## Non-critical alerts (pipeline continued)", *warnings, ""]
    if incidents:
        out += ["## Incident report(s)", *incidents]
    text = "\n".join(out)
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "pipeline-report.md").write_text(text, encoding="utf-8")
    append_summary(text)
    print(text)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True, choices=STAGES + ["summary"])
    a = ap.parse_args()
    if a.stage == "summary":
        sys.exit(stage_summary())
    r = new_result(a.stage)
    STAGE_FUNCS[a.stage](r)
    sys.exit(finish(r))


if __name__ == "__main__":
    main()
