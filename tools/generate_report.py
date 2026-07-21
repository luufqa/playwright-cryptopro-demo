from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from html import escape, unescape
from pathlib import Path


STATUS_CLASS = {
    "Passed": "pass",
    "Failed": "fail",
    "Error": "fail",
    "Skipped": "skip",
    "XFailed": "skip",
    "XPassed": "fail",
}


@dataclass
class TestResult:
    test_id: str
    name: str
    module: str
    page_title: str
    description: str
    result: str
    duration: str
    seconds: float
    log: str
    crash: str


BASE_CSS = """
:root {
    --ink: #111827;
    --muted: #647084;
    --line: #dbe3ef;
    --panel: rgba(255, 255, 255, 0.82);
    --panel-solid: #ffffff;
    --pass: #16845f;
    --fail: #c63d35;
    --skip: #b7791f;
    --skip-metric: #6b7280;
    --blue: #245fc8;
    --slow: #f59e0b;
    --teal: #0f766e;
    --shadow: 0 24px 70px rgba(17, 24, 39, 0.12);
}
* { box-sizing: border-box; }
body {
    background:
        radial-gradient(circle at 12% 0%, rgba(36, 95, 200, 0.18), transparent 30%),
        radial-gradient(circle at 90% 4%, rgba(15, 118, 110, 0.14), transparent 26%),
        linear-gradient(135deg, #eef4ff, #f7faf8);
    color: var(--ink);
    font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    margin: 0;
}
button, input, textarea, select { font: inherit; }
.page { min-height: 100vh; padding: 24px 88px; }
.shell { margin: 0 auto; max-width: 1480px; }
.hero {
    align-items: stretch;
    background: #111827;
    border-radius: 8px;
    box-shadow: var(--shadow);
    color: white;
    display: grid;
    gap: 24px;
    grid-template-columns: minmax(0, 1fr) minmax(300px, 420px);
    overflow: hidden;
    padding: 28px;
}
.hero-copy { align-content: center; display: grid; }
.eyebrow {
    color: #93c5fd;
    font-size: 15px;
    font-weight: 850;
    letter-spacing: 0.12em;
    margin: 0 0 10px;
    text-transform: uppercase;
}
h1 {
    font-size: clamp(32px, 4vw, 58px);
    letter-spacing: 0;
    line-height: 0.98;
    margin: 0;
}
h2, h3, p { margin-top: 0; }
.hero-panel {
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 8px;
    display: grid;
    gap: 12px;
    padding: 16px;
}
.run-line { align-items: center; display: flex; justify-content: space-between; }
.run-line span { color: #c8d3e2; font-size: 13px; }
.run-line strong { font-size: 14px; }
.block {
    background: var(--panel);
    backdrop-filter: blur(18px);
    border: 1px solid rgba(217, 225, 236, 0.86);
    border-radius: 8px;
    box-shadow: var(--shadow);
    margin: 18px 0;
    overflow: hidden;
}
.block-head {
    border-bottom: 1px solid var(--line);
    padding: 22px 28px;
}
.block-head-action { cursor: pointer; }
.block-head-action:hover h2 { color: var(--blue); }
.block-head h2 { font-size: 23px; margin: 0 0 4px; }
.block-head p { color: var(--muted); font-size: 13px; margin: 0; }
.block-body { padding: 22px 28px; }
.grid { display: grid; gap: 14px; }
.summary-layout { grid-template-columns: minmax(580px, 1.24fr) minmax(300px, 0.76fr); }
.summary-stack { align-content: start; display: grid; gap: 14px; }
.metrics { align-items: stretch; grid-template-columns: repeat(4, minmax(92px, 1fr)); }
.two-col { grid-template-columns: minmax(0, 1fr) minmax(360px, 0.82fr); }
.card, .metric, .failure-detail, .failure-item, .empty-state, .reveal-panel {
    background: var(--panel-solid);
    border: 1px solid var(--line);
    border-radius: 8px;
}
.metric {
    align-items: center;
    color: inherit;
    display: flex;
    gap: 14px;
    justify-content: space-between;
    min-height: 88px;
    padding: 12px 14px;
    text-align: left;
    width: 100%;
}
button.metric { cursor: pointer; }
button.metric:hover, button.metric.is-active { border-color: #9db9f4; box-shadow: 0 0 0 3px rgba(36, 95, 200, 0.11); }
.metric span {
    color: var(--muted);
    display: block;
    font-size: 12px;
    font-weight: 850;
    letter-spacing: 0.07em;
    margin-bottom: 10px;
    text-transform: uppercase;
}
.metric strong { display: block; font-size: 28px; line-height: 1; }
.metric-pass strong, .status.pass { color: var(--pass); }
.metric-fail strong, .status.fail { color: var(--fail); }
.metric-total strong { color: var(--blue); }
.metric-skip strong { color: var(--skip-metric); }
.reveal-panel { margin-top: 14px; padding: 0; overflow: hidden; }
.reveal-panel h3 {
    background: rgba(248, 251, 255, 0.45);
    border-bottom: 1px solid var(--line);
    font-size: 16px;
    margin: 0;
    padding: 14px 16px;
}
.reveal-panel .compact-list,
.reveal-panel .empty-state {
    margin: 14px;
}
.reveal-panel .compact-list {
    max-height: 560px;
    overflow-y: auto;
    padding-right: 4px;
}
.compact-list { display: grid; gap: 8px; }
.compact-row {
    align-items: center;
    background: #f8fafc;
    border: 1px solid #edf1f6;
    border-radius: 8px;
    display: grid;
    gap: 12px;
    grid-template-columns: auto minmax(0, 1fr) 72px;
    padding: 10px;
}
.compact-row strong {
    display: block;
    font-size: 13px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.compact-description {
    color: var(--ink);
    display: block;
    font-size: 12px;
    font-style: normal;
    line-height: 1.4;
    margin-top: 5px;
    overflow-wrap: anywhere;
}
.compact-row span, .compact-row small { color: var(--muted); font-size: 12px; }
.card { overflow: hidden; padding: 0; }
.card-title {
    align-items: start;
    background: rgba(248, 251, 255, 0.45);
    border-bottom: 1px solid var(--line);
    display: flex;
    gap: 16px;
    justify-content: space-between;
    margin-bottom: 0;
    padding: 16px;
}
.card-title h3 { font-size: 17px; margin: 0 0 4px; }
.card-title p { color: var(--muted); font-size: 12px; line-height: 1.45; margin: 0; }
.card > .slow-test,
.card > .empty-state {
    margin-left: 16px;
    margin-right: 16px;
}
.card > .slow-test:first-of-type,
.card > .empty-state:first-of-type {
    margin-top: 14px;
}
.card > .slow-test:last-child,
.card > .empty-state:last-child {
    margin-bottom: 22px;
}
.module-list {
    max-height: 420px;
    overflow-y: auto;
    padding: 14px 16px 22px;
}
.module-row {
    align-items: center;
    display: grid;
    gap: 12px;
    grid-template-columns: minmax(200px, 1fr) 120px 70px;
    margin-bottom: 12px;
}
.module-list > .module-row:last-child { margin-bottom: 0; }
.module-title {
    color: var(--ink);
    display: block;
    font-size: 13px;
    font-weight: 800;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.module-meta { color: var(--muted); display: block; font-size: 11px; margin-top: 3px; }
.bar, .slow-meter {
    background: #edf2f7;
    border-radius: 999px;
    display: flex;
    height: 11px;
    overflow: hidden;
}
.bar-pass { background: var(--pass); }
.bar-fail { background: var(--fail); }
.bar-skip { background: var(--skip); }
.module-score { font-size: 13px; font-weight: 900; text-align: right; }
.slow-test {
    align-items: center;
    border-top: 1px solid #edf1f6;
    display: grid;
    gap: 12px;
    grid-template-columns: minmax(0, 1fr) 120px 70px;
    padding: 12px 0;
}
.slow-test:first-of-type { border-top: 0; padding-top: 0; }
.slow-test span, .slow-test small { color: var(--muted); display: block; font-size: 12px; }
.slow-test strong {
    display: block;
    font-size: 13px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.slow-description {
    color: var(--ink);
    display: block;
    font-size: 12px;
    font-style: normal;
    line-height: 1.35;
    margin-top: 4px;
    overflow-wrap: anywhere;
    white-space: normal;
}
.slow-meter div { background: var(--slow); }
.status {
    border-radius: 999px;
    display: inline-flex;
    font-size: 11px;
    font-weight: 900;
    padding: 5px 8px;
    text-transform: uppercase;
}
.status.pass { background: #e8f6ef; }
.status.fail { background: #fdebea; }
.status.skip { background: #fff6df; color: var(--skip); }
.failure-layout { display: grid; gap: 14px; grid-template-columns: 390px minmax(0, 1fr); }
.failure-list {
    align-content: start;
    display: grid;
    gap: 10px;
    max-height: 760px;
    overflow-y: auto;
    padding-right: 4px;
}
.failure-item {
    cursor: pointer;
    display: grid;
    gap: 8px;
    padding: 14px;
    text-align: left;
    width: 100%;
}
.failure-item.is-active { border-color: var(--fail); box-shadow: 0 0 0 3px rgba(198, 61, 53, 0.12); }
.failure-item header { align-items: center; display: flex; justify-content: space-between; }
.failure-item strong {
    font-size: 14px;
    line-height: 1.35;
    overflow-wrap: anywhere;
}
.failure-item small { color: var(--muted); font-size: 12px; line-height: 1.4; }
.failure-detail { display: none; padding: 16px; }
.failure-detail.is-active { display: block; }
.failure-detail-head {
    align-items: start;
    display: flex;
    gap: 16px;
    justify-content: space-between;
    margin-bottom: 14px;
}
.failure-detail-head h3 { font-size: 17px; margin: 0 0 4px; overflow-wrap: anywhere; }
.failure-detail-head p { color: var(--muted); font-size: 12px; line-height: 1.45; margin: 0; overflow-wrap: anywhere; }
.failure-description {
    color: var(--ink) !important;
    font-size: 13px !important;
    font-weight: 400;
    margin-top: 7px !important;
}
.failure-grid {
    display: grid;
    gap: 14px;
    grid-template-columns: minmax(0, 0.82fr) minmax(0, 1.18fr);
}
.trace, .log {
    background: #101828;
    border-radius: 8px;
    color: #d6deeb;
    font-family: "SFMono-Regular", Consolas, monospace;
    font-size: 12px;
    line-height: 1.55;
    margin: 0;
    max-height: 430px;
    overflow: auto;
    padding: 14px;
    white-space: pre-wrap;
}
.log { background: #14213d; }
.empty-state { padding: 18px; }
.empty-state p { color: var(--muted); margin-bottom: 0; }
@media (max-width: 1180px) {
    .hero, .summary-layout, .metrics, .two-col, .failure-layout, .failure-grid { grid-template-columns: 1fr; }
    .module-row, .slow-test { grid-template-columns: 1fr; }
    .module-score { text-align: left; }
}
@media (max-width: 720px) {
    .page { padding: 16px; }
    .hero, .block-body, .block-head { padding: 16px; }
    .compact-row { grid-template-columns: 1fr; }
}
"""


MODERN_CSS = """
body.theme-modern {
    background:
        linear-gradient(180deg, rgba(255,255,255,0.72), rgba(255,255,255,0)),
        linear-gradient(135deg, #eef6ff 0%, #f8fbff 46%, #eefaf6 100%);
}
.theme-modern .shell { max-width: 1520px; }
.theme-modern .hero {
    background: linear-gradient(135deg, #0c1628 0%, #153c64 54%, #0f766e 100%);
    border: 1px solid rgba(255, 255, 255, 0.18);
}
.theme-modern .hero-panel {
    background: rgba(255, 255, 255, 0.11);
    backdrop-filter: blur(18px);
}
.theme-modern .block {
    background: rgba(255, 255, 255, 0.76);
    border-color: rgba(194, 210, 232, 0.72);
    box-shadow: 0 18px 55px rgba(36, 95, 200, 0.12);
}
.theme-modern .block-head {
    align-items: center;
    display: flex;
    justify-content: space-between;
}
.theme-modern .block-head h2 { font-size: 21px; }
.theme-modern .metric {
    background: rgba(255, 255, 255, 0.9);
    border-color: rgba(198, 213, 234, 0.86);
    min-height: 86px;
}
.theme-modern .metric-pass { border-left: 4px solid var(--pass); }
.theme-modern .metric-fail { border-left: 4px solid var(--fail); }
.theme-modern .metric-total { border-left: 4px solid var(--blue); }
.theme-modern .metric-rate { border-left: 4px solid var(--teal); }
.theme-modern .card,
.theme-modern .reveal-panel,
.theme-modern .failure-item,
.theme-modern .failure-detail,
.theme-modern .empty-state {
    background: rgba(255, 255, 255, 0.9);
    border-color: rgba(205, 217, 235, 0.92);
}
.theme-modern .bar,
.theme-modern .slow-meter {
    height: 9px;
}
.theme-modern .status {
    border: 1px solid currentColor;
    background: white;
}
.theme-modern .failure-item.is-active {
    background: #fff7f7;
}
"""


SCRIPT = """
<script>
const toggleButtons = document.querySelectorAll("[data-toggle-panel]");
const failureSection = document.getElementById("failure-command");
const failureBody = document.getElementById("failure-command-body");

function togglePanel(panelId, button) {
    const panel = document.getElementById(panelId);
    if (!panel) return;
    const willOpen = panel.hasAttribute("hidden");
    document.querySelectorAll(".reveal-panel").forEach((item) => item.setAttribute("hidden", ""));
    toggleButtons.forEach((item) => item.classList.remove("is-active"));
    if (willOpen) {
        panel.removeAttribute("hidden");
        button.classList.add("is-active");
    }
}

function selectFailure(index) {
    document.querySelectorAll("[data-failure-index]").forEach((item) => {
        item.classList.toggle("is-active", item.dataset.failureIndex === index);
    });
    document.querySelectorAll("[data-failure-panel]").forEach((item) => {
        item.classList.toggle("is-active", item.dataset.failurePanel === index);
    });
}

function openFailures(index) {
    if (!failureBody) return;
    const shouldClose = !failureBody.hasAttribute("hidden") && !index;
    if (shouldClose) {
        failureBody.setAttribute("hidden", "");
        failureSection.classList.remove("is-open");
        return;
    }
    failureBody.removeAttribute("hidden");
    failureSection.classList.add("is-open");
    const firstIndex = document.querySelector("[data-failure-index]")?.dataset.failureIndex;
    selectFailure(index || firstIndex || "");
    failureSection.scrollIntoView({ behavior: "smooth", block: "start" });
}

toggleButtons.forEach((button) => {
    button.addEventListener("click", () => togglePanel(button.dataset.togglePanel, button));
});

document.querySelectorAll("[data-open-failures]").forEach((button) => {
    button.addEventListener("click", () => openFailures(button.dataset.openFailures || ""));
});

document.querySelectorAll("[data-failure-index]").forEach((button) => {
    button.addEventListener("click", () => openFailures(button.dataset.failureIndex));
});

const firstFailure = document.querySelector("[data-failure-index]");
if (firstFailure) {
    selectFailure(firstFailure.dataset.failureIndex);
}
</script>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a compact QA dashboard from pytest-html data.")
    parser.add_argument("--source", default="reports/report.html", help="Path to pytest-html report.")
    parser.add_argument("--output", default="reports/report.html", help="Path to generated dashboard.")
    parser.add_argument(
        "--include-prefix",
        action="append",
        default=[],
        help="Keep only test ids that start with this prefix. Can be used multiple times.",
    )
    return parser.parse_args()


def deep_unescape(value: str) -> str:
    previous = value
    for _ in range(4):
        current = unescape(previous)
        if current == previous:
            return current
        previous = current
    return previous


def strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value)


def extract_data(source: Path) -> dict:
    content = source.read_text(encoding="utf-8")
    match = re.search(r'id="data-container"\s+data-jsonblob="(.*?)"', content, re.DOTALL)
    if not match:
        raise ValueError(f"Could not find pytest-html data-jsonblob in {source}")
    return json.loads(unescape(match.group(1)))


def parse_duration(duration: str) -> float:
    value = duration.strip()
    if not value:
        return 0.0
    if value.endswith(" ms"):
        return float(value[:-3].strip()) / 1000
    if ":" in value:
        parts = [float(part) for part in value.split(":")]
        while len(parts) < 3:
            parts.insert(0, 0.0)
        hours, minutes, seconds = parts[-3:]
        return hours * 3600 + minutes * 60 + seconds
    match = re.search(r"[\d.]+", value)
    return float(match.group(0)) if match else 0.0


def format_seconds(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds * 1000:.0f} ms"
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, remainder = divmod(seconds, 60)
    return f"{int(minutes):02d}:{remainder:04.1f}"


def extract_description(row: list[str]) -> str:
    for cell in row:
        if "col-description" in cell:
            return deep_unescape(strip_tags(cell)).strip()
    return ""


def short_test_name(test_id: str) -> str:
    return test_id.split("::")[-1]


def module_name(test_id: str) -> str:
    return test_id.split("::")[0]


def short_module(module: str) -> str:
    return Path(module).name if module else "unknown"


def extract_page_title(module: str) -> str:
    if not module:
        return "Page is not specified"
    module_path = Path(module)
    if not module_path.exists():
        return short_module(module)
    content = module_path.read_text(encoding="utf-8")
    match = re.search(r'^\s*#\s*Page\s+"([^"]+)"', content, re.MULTILINE)
    return match.group(1) if match else short_module(module)


def extract_crash(log: str) -> str:
    if not log or log == "No log output captured.":
        return ""
    error_lines = []
    for line in log.splitlines():
        stripped = line.strip()
        if stripped.startswith("E ") or stripped.startswith("E   "):
            error_lines.append(stripped[1:].strip())
    if error_lines:
        return "\n".join(error_lines[:5])
    for line in log.splitlines():
        if "AssertionError" in line or "Error:" in line:
            return line.strip()
    return log.strip().splitlines()[0] if log.strip() else ""


def collect_tests(data: dict) -> list[TestResult]:
    tests = []
    for item in [entry for entries in data.get("tests", {}).values() for entry in entries]:
        test_id = item.get("testId", "")
        log = deep_unescape(item.get("log", "")).strip()
        duration = item.get("duration", "")
        tests.append(
            TestResult(
                test_id=test_id,
                name=short_test_name(test_id),
                module=module_name(test_id),
                page_title=extract_page_title(module_name(test_id)),
                description=extract_description(item.get("resultsTableRow", [])),
                result=item.get("result", "Unknown"),
                duration=duration,
                seconds=parse_duration(duration),
                log=log,
                crash=extract_crash(log),
            )
        )
    return tests


def apply_filters(tests: list[TestResult], include_prefixes: list[str], exclude_prefixes: list[str]) -> list[TestResult]:
    filtered = tests
    if include_prefixes:
        filtered = [test for test in filtered if any(test.test_id.startswith(prefix) for prefix in include_prefixes)]
    if exclude_prefixes:
        filtered = [test for test in filtered if not any(test.test_id.startswith(prefix) for prefix in exclude_prefixes)]
    return filtered


def status_class(result: str) -> str:
    return STATUS_CLASS.get(result, "skip")


def status_counts(tests: list[TestResult]) -> tuple[int, int, int]:
    counts = Counter(test.result for test in tests)
    passed = counts.get("Passed", 0)
    failed = counts.get("Failed", 0) + counts.get("Error", 0)
    skipped = len(tests) - passed - failed
    return passed, failed, skipped


def sort_tests_alpha(tests: list[TestResult]) -> list[TestResult]:
    return sorted(tests, key=lambda test: (test.name.casefold(), test.module.casefold(), test.test_id.casefold()))


def render_metric(
    title: str,
    value: str,
    modifier: str,
    *,
    button_attrs: str = "",
    extra: str = "",
) -> str:
    tag = "button" if button_attrs else "article"
    attrs = f' type="button" {button_attrs}' if button_attrs else ""
    return f"""
                    <{tag} class="metric {modifier}"{attrs}>
                        <div>
                            <span>{escape(title)}</span>
                            <strong>{escape(value)}</strong>
                        </div>
                        {extra}
                    </{tag}>"""


def render_compact_list(tests: list[TestResult], empty_text: str, *, show_description: bool = False) -> str:
    if not tests:
        return f'<div class="empty-state"><p>{escape(empty_text)}</p></div>'
    rows = []
    for test in tests:
        description = test.description or "Description is not set"
        description_html = f'<em class="compact-description">{escape(description)}</em>' if show_description else ""
        rows.append(
            f"""
                        <div class="compact-row">
                            <span class="status {status_class(test.result)}">{escape(test.result)}</span>
                            <div>
                                <strong title="{escape(test.test_id)}">{escape(test.name)}</strong>
                                <small>{escape(test.module)}</small>
                                {description_html}
                            </div>
                            <b>{escape(format_seconds(test.seconds))}</b>
                        </div>"""
        )
    return f'<div class="compact-list">{"".join(rows)}</div>'


def render_module_rows(tests: list[TestResult]) -> str:
    modules: dict[tuple[str, str], list[TestResult]] = defaultdict(list)
    for test in tests:
        modules[(test.module, test.page_title)].append(test)

    rows = []
    module_stats = []
    for (module, page_title), module_tests in modules.items():
        passed, failed, skipped = status_counts(module_tests)
        total = len(module_tests)
        duration = sum(test.seconds for test in module_tests)
        pass_width = passed / total * 100 if total else 0
        fail_width = failed / total * 100 if total else 0
        skip_width = skipped / total * 100 if total else 0
        module_stats.append((page_title.casefold(), module, page_title, passed, failed, skipped, total, duration, pass_width, fail_width, skip_width))

    for _, module, page_title, passed, failed, skipped, total, duration, pass_width, fail_width, skip_width in sorted(module_stats):
        meta_parts = [f"{passed} passed"]
        if failed:
            meta_parts.append(f"{failed} failed")
        if skipped:
            meta_parts.append(f"{skipped} skipped")
        meta_parts.append(format_seconds(duration))
        rows.append(
            f"""
                        <div class="module-row">
                            <div>
                                <span class="module-title" title="{escape(module)}">{escape(page_title)}</span>
                                <span class="module-meta">{escape(short_module(module))} · {escape(' · '.join(meta_parts))}</span>
                            </div>
                            <div class="bar" aria-label="{escape(module)}">
                                <div class="bar-pass" style="width: {pass_width:.1f}%"></div>
                                <div class="bar-fail" style="width: {fail_width:.1f}%"></div>
                                <div class="bar-skip" style="width: {skip_width:.1f}%"></div>
                            </div>
                            <strong class="module-score">{passed}/{total}</strong>
                        </div>"""
        )
    return "".join(rows) if rows else '<div class="empty-state"><p>No module data is available.</p></div>'


def render_slow_tests(tests: list[TestResult]) -> str:
    slowest = sorted(tests, key=lambda test: test.seconds, reverse=True)[:3]
    if not slowest:
        return '<div class="empty-state"><p>No duration data is available.</p></div>'
    max_seconds = slowest[0].seconds or 1
    rows = []
    for index, test in enumerate(slowest, start=1):
        width = test.seconds / max_seconds * 100 if max_seconds else 0
        description = test.description or "Description is not set"
        rows.append(
            f"""
                        <article class="slow-test">
                            <div>
                                <span>#{index}</span>
                                <strong title="{escape(test.test_id)}">{escape(test.name)}</strong>
                                <small>{escape(test.module)}</small>
                                <span class="slow-description">{escape(description)}</span>
                            </div>
                            <div class="slow-meter"><div style="width: {width:.1f}%"></div></div>
                            <b>{escape(format_seconds(test.seconds))}</b>
                        </article>"""
        )
    return "".join(rows)


def render_failure_center(tests: list[TestResult]) -> str:
    failed_tests = sort_tests_alpha([test for test in tests if status_class(test.result) == "fail"])
    failures = list(enumerate(failed_tests, start=1))
    if not failures:
        return """
                    <section class="empty-state">
                        <h3>Failed tests</h3>
                        <p>The selected test set has no failed/error results.</p>
                    </section>"""

    items = []
    details = []
    for position, (index, test) in enumerate(failures):
        active = " is-active" if position == 0 else ""
        description = test.description or "Description is not set"
        crash = test.crash or "Crash message was not found in the log."
        log = test.log or "No log output was captured."
        items.append(
            f"""
                        <button class="failure-item{active}" type="button" data-failure-index="{index}">
                            <header>
                                <span class="status fail">{escape(test.result)}</span>
                                <b>{escape(format_seconds(test.seconds))}</b>
                            </header>
                            <strong>{escape(test.name)}</strong>
                            <small>{escape(description)}</small>
                        </button>"""
        )
        details.append(
            f"""
                        <article class="failure-detail{active}" data-failure-panel="{index}">
                            <div class="failure-detail-head">
                                <div>
                                    <h3>{escape(test.name)}</h3>
                                    <p>{escape(test.module)}</p>
                                    <p class="failure-description">{escape(description)}</p>
                                </div>
                                <span class="status fail">{escape(test.result)}</span>
                            </div>
                            <div class="failure-grid">
                                <article>
                                    <h3>Crash message</h3>
                                    <pre class="trace">{escape(crash)}</pre>
                                </article>
                                <article>
                                    <h3>Console / pytest log</h3>
                                    <pre class="log">{escape(log)}</pre>
                                </article>
                            </div>
                        </article>"""
        )

    return f"""
                    <div class="failure-layout">
                        <aside class="failure-list">
                            {"".join(items)}
                        </aside>
                        <section>
                            {"".join(details)}
                        </section>
                    </div>"""


def build_html(tests: list[TestResult]) -> str:
    passed, failed, skipped = status_counts(tests)
    total = len(tests)
    pass_rate = passed / total * 100 if total else 0
    total_seconds = sum(test.seconds for test in tests)
    passed_tests = sort_tests_alpha([test for test in tests if status_class(test.result) == "pass"])
    skipped_tests = sort_tests_alpha([test for test in tests if status_class(test.result) == "skip"])
    total_tests = sort_tests_alpha(tests)

    run_status = f"{passed} passed / {failed} failed"
    if skipped:
        run_status += f" / {skipped} skipped"

    css = BASE_CSS + MODERN_CSS
    label = "Autotests QA dashboard"

    metrics = [
        render_metric("Passed", str(passed), "metric-pass", button_attrs='data-toggle-panel="passed-panel"'),
        render_metric("Failed", str(failed), "metric-fail", button_attrs='data-open-failures=""'),
        render_metric("Skipped", str(skipped), "metric-skip", button_attrs='data-toggle-panel="skipped-panel"'),
        render_metric("Total", str(total), "metric-total", button_attrs='data-toggle-panel="total-panel"'),
    ]

    failure_hidden = " hidden"

    return f"""<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{escape(label)}</title>
    <style>{css}</style>
</head>
<body class="theme-modern">
<main class="page">
    <div class="shell">
        <section class="hero">
            <div class="hero-copy">
                <h1>{escape(label)}</h1>
            </div>
            <aside class="hero-panel">
                <div class="run-line"><span>Run status</span><strong>{escape(run_status)}</strong></div>
                <div class="run-line"><span>Pass rate</span><strong>{pass_rate:.0f}%</strong></div>
                <div class="run-line"><span>Duration</span><strong>{escape(format_seconds(total_seconds))}</strong></div>
            </aside>
        </section>

        <section class="block">
            <header class="block-head">
                <div>
                    <h2>Report</h2>
                    <p>Key test run metrics</p>
                </div>
            </header>
            <div class="block-body">
                <div class="grid summary-layout">
                    <section class="summary-stack">
                        <div class="grid metrics">
                            {"".join(metrics)}
                        </div>

                        <section class="reveal-panel" id="passed-panel" hidden>
                            <h3>Passed tests</h3>
                            {render_compact_list(passed_tests, "The selected test set has no passed tests.", show_description=True)}
                        </section>

                        <section class="reveal-panel" id="skipped-panel" hidden>
                            <h3>Skipped tests</h3>
                            {render_compact_list(skipped_tests, "The selected test set has no skipped tests.")}
                        </section>

                        <section class="reveal-panel" id="total-panel" hidden>
                            <h3>All selected tests</h3>
                            {render_compact_list(total_tests, "The selected test set has no tests.", show_description=True)}
                        </section>

                        <section class="card">
                            <div class="card-title">
                                <div>
                                    <h3>Top 3 slow tests</h3>
                                    <p>The slowest tests in the current report.</p>
                                </div>
                            </div>
                            {render_slow_tests(tests)}
                        </section>
                    </section>

                    <section class="card">
                        <div class="card-title">
                            <div>
                                <h3>Module health</h3>
                                <p>Grouped by test file: passed/failed/skipped</p>
                            </div>
                        </div>
                        <div class="module-list">
                            {render_module_rows(tests)}
                        </div>
                    </section>
                </div>

            </div>
        </section>

        <section class="block failure-block" id="failure-command">
            <header class="block-head block-head-action" data-open-failures="">
                <div>
                    <h2>Failure analysis</h2>
                    <p>Failed/error tests are listed on the left, with the active test log on the right.</p>
                </div>
            </header>
            <div class="block-body" id="failure-command-body"{failure_hidden}>
                {render_failure_center(tests)}
            </div>
        </section>
    </div>
</main>
{SCRIPT}
</body>
</html>
"""


def generate_dashboard(source: Path | str, output: Path | str, include_prefixes: tuple[str, ...] = ("tests/",)) -> None:
    source = Path(source)
    output = Path(output)
    data = extract_data(source)
    all_tests = collect_tests(data)
    tests = apply_filters(all_tests, list(include_prefixes), [])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_html(tests), encoding="utf-8")


def main() -> None:
    args = parse_args()
    generate_dashboard(args.source, args.output, tuple(args.include_prefix or ("tests/",)))
    print(f"Generated {args.output} from {args.source}")


if __name__ == "__main__":
    main()
