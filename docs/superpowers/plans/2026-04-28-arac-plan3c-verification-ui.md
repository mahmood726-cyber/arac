# ARAC — Plan 3C: Verification UI (RapidMeta-style auto-confirm)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the verification UI — the spec's moral architecture deliverable. Per `feedback_makerere_student_workload.md`: the Makerere PhD cohort **verifies** pre-classified data RapidMeta-style, NOT raw extraction. Plan 3C delivers the single-file HTML UI that shows one trial at a time with all three Tier classifications pre-populated, source context inline, and Confirm/Flag buttons per tier. Decisions persist in localStorage; export-to-JSON enables dual-confirm reconciliation later.

**Architecture:**
- New artifact: per-trial classifications CSV (`outputs/trial_labels.csv`) — one row per trial × tier, with all classifier outputs + source context (PubMed abstract excerpt, author affiliations, AACT countries)
- New script `scripts/build_trial_labels.py` runs the resolver + tier classifiers in batch and emits the CSV (separate from the atlas RGS pipeline; reuses the same components)
- Single-file HTML verification UI (`scripts/build_verification.py` reads the CSV, embeds rows inline, renders a one-trial-at-a-time card with prev/next navigation)
- Vanilla JS + localStorage for state — no server, no build step
- Decisions are stored as `{trial_id: {tier_s: "confirm|flag", tier_a: "confirm|flag", tier_p: "confirm|flag", flag_reason: "..."}}`
- Export button dumps localStorage state as a JSON file the user can email or commit

**Out of scope:**
- Adjudication compare view (Plan 3C.1 if needed — diff two reviewers' JSON exports)
- Server-side dual-confirm tracking (the export-to-JSON pattern handles dual-confirm offline)
- Per-cohort-member auth or assignment (the user manages this manually via separate JSON exports)
- Live LLM re-extraction in the UI (Plan 3C ships static labels; Plan 4's pilot can add re-run if needed)

**Tech Stack:** Python 3.13. No new dependencies.

**Companion files (read-only inputs):**
- All Plan 2 modules (resolver, classifiers)
- `outputs/atlas.csv` is NOT a dependency — verification works on per-trial labels, not per-MA aggregates
- `baseline.json` — append v0.9.0 record at end

---

### Task 1: Per-trial labels CSV emitter

**Files:**
- Create: `C:/Projects/arac/src/arac/verify/__init__.py`
- Create: `C:/Projects/arac/src/arac/verify/labels.py`
- Create: `C:/Projects/arac/tests/test_verify_labels.py`

- [ ] **Step 1: Write the failing test**

```python
"""Per-trial labels CSV: emit one row per (trial, tier) for verification UI."""

from __future__ import annotations

import csv
from pathlib import Path

from arac.verify.labels import (
    LABEL_COLUMNS,
    TrialLabel,
    write_trial_labels,
)


def test_label_columns_count() -> None:
    # 18 columns total (identifier + per-tier fields + source context)
    assert len(LABEL_COLUMNS) == 18
    assert LABEL_COLUMNS[0] == "trial_id"
    assert "tier_s_label" in LABEL_COLUMNS
    assert "tier_a_label" in LABEL_COLUMNS
    assert "tier_p_label" in LABEL_COLUMNS
    assert "abstract_excerpt" in LABEL_COLUMNS


def test_write_labels_round_trip(tmp_path: Path) -> None:
    rows = [
        TrialLabel(
            trial_id="MA1::t0", ma_id="MA1", trial_index=0,
            study_string="Smith 2010",
            pmid="12345", nct_id=None, title="Test Trial",
            tier_s_label="african_site", tier_s_source="aact",
            tier_s_confidence=0.97, tier_s_country="Uganda",
            tier_a_label="african_led", tier_a_position="first",
            tier_a_confidence=0.85, tier_a_country="Uganda",
            tier_p_label="african_majority", tier_p_confidence=0.95,
            tier_p_african_pct=80.0, tier_p_evidence="800 of 1000 in Uganda.",
            abstract_excerpt="Test abstract excerpt...",
            authors_list="Smith, Jones, Mukasa",
        ),
    ]
    out = tmp_path / "trial_labels.csv"
    n = write_trial_labels(rows, out)
    assert n == 1

    with out.open() as f:
        loaded = list(csv.DictReader(f))
    assert len(loaded) == 1
    assert loaded[0]["trial_id"] == "MA1::t0"
    assert loaded[0]["tier_s_label"] == "african_site"
    assert loaded[0]["tier_p_african_pct"] == "80.0"
```

- [ ] **Step 2: Run, verify FAIL**

Expected: FAIL on import.

- [ ] **Step 3: Implement `src/arac/verify/__init__.py`**

```python
"""Verification UI infrastructure for ARAC.

Per feedback_makerere_student_workload.md: the Makerere PhD cohort verifies
pre-classified algorithmic decisions via a RapidMeta-style UI, NOT raw
extraction. This package provides the per-trial labels CSV emitter and the
verification UI HTML generator.
"""
```

- [ ] **Step 4: Implement `src/arac/verify/labels.py`**

```python
"""Per-trial labels CSV: one row per trial with all 3 Tier classifications
+ source context for the verification UI.

The CSV is the durable interface between the batch classifier run and the
interactive verification UI. Students see one trial at a time, with all
algorithmic decisions pre-populated, and either confirm or flag each tier.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


LABEL_COLUMNS = (
    "trial_id",
    "ma_id",
    "trial_index",
    "study_string",
    "pmid",
    "nct_id",
    "title",
    "tier_s_label",
    "tier_s_source",
    "tier_s_confidence",
    "tier_s_country",
    "tier_a_label",
    "tier_a_position",
    "tier_a_confidence",
    "tier_a_country",
    "tier_p_label",
    "tier_p_confidence",
    "tier_p_african_pct",
)
# Note: 18 columns. abstract_excerpt + authors_list + tier_p_evidence are
# additional context fields appended below for richness; they ride alongside
# the canonical LABEL_COLUMNS but the CSV header includes them too.
_EXTRA_COLUMNS = ("tier_p_evidence", "abstract_excerpt", "authors_list")
ALL_COLUMNS = LABEL_COLUMNS + _EXTRA_COLUMNS


@dataclass(frozen=True)
class TrialLabel:
    trial_id: str
    ma_id: str
    trial_index: int
    study_string: str
    pmid: Optional[str]
    nct_id: Optional[str]
    title: Optional[str]
    tier_s_label: Optional[str]
    tier_s_source: Optional[str]
    tier_s_confidence: Optional[float]
    tier_s_country: Optional[str]
    tier_a_label: Optional[str]
    tier_a_position: Optional[str]
    tier_a_confidence: Optional[float]
    tier_a_country: Optional[str]
    tier_p_label: Optional[str]
    tier_p_confidence: Optional[float]
    tier_p_african_pct: Optional[float]
    tier_p_evidence: Optional[str]
    abstract_excerpt: Optional[str]
    authors_list: Optional[str]


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    return str(value)


def _row_to_dict(r: TrialLabel) -> dict[str, str]:
    return {
        "trial_id": r.trial_id, "ma_id": r.ma_id,
        "trial_index": _cell(r.trial_index),
        "study_string": _cell(r.study_string),
        "pmid": _cell(r.pmid), "nct_id": _cell(r.nct_id),
        "title": _cell(r.title),
        "tier_s_label": _cell(r.tier_s_label),
        "tier_s_source": _cell(r.tier_s_source),
        "tier_s_confidence": _cell(r.tier_s_confidence),
        "tier_s_country": _cell(r.tier_s_country),
        "tier_a_label": _cell(r.tier_a_label),
        "tier_a_position": _cell(r.tier_a_position),
        "tier_a_confidence": _cell(r.tier_a_confidence),
        "tier_a_country": _cell(r.tier_a_country),
        "tier_p_label": _cell(r.tier_p_label),
        "tier_p_confidence": _cell(r.tier_p_confidence),
        "tier_p_african_pct": _cell(r.tier_p_african_pct),
        "tier_p_evidence": _cell(r.tier_p_evidence),
        "abstract_excerpt": _cell(r.abstract_excerpt),
        "authors_list": _cell(r.authors_list),
    }


def write_trial_labels(rows: Iterable[TrialLabel], out: Path) -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(ALL_COLUMNS))
        writer.writeheader()
        for r in rows:
            writer.writerow(_row_to_dict(r))
            n += 1
    return n
```

- [ ] **Step 5: Run, verify PASS**

Run: `cd C:/Projects/arac && python -m pytest tests/test_verify_labels.py -v`
Expected: 2 PASSED.

- [ ] **Step 6: Sentinel + commit**

```bash
cd "C:/Projects/arac"
python -m sentinel scan --repo .
git add src/arac/verify tests/test_verify_labels.py
git commit -m "feat(verify): per-trial labels CSV (18 canonical + 3 context columns)"
```

---

### Task 2: Verification UI HTML template + generator

**Files:**
- Create: `C:/Projects/arac/src/arac/verify/html_template.py`
- Modify: `C:/Projects/arac/src/arac/verify/labels.py` — add `render_verification_ui(rows) -> str`
- Create: `C:/Projects/arac/tests/test_verify_ui.py`

The UI is single-file HTML with vanilla JS + localStorage. Pattern matches Plan 3B's dashboard (no external CDN, ES5-compatible JS to avoid `string.Template` `$` conflicts).

- [ ] **Step 1: Write the failing test**

```python
"""Verification UI: HTML template renders one-trial-at-a-time card."""

from __future__ import annotations

from pathlib import Path

from arac.verify.labels import (
    TrialLabel, render_verification_ui, write_trial_labels,
)


def _sample_label() -> TrialLabel:
    return TrialLabel(
        trial_id="MA1::t0", ma_id="MA1", trial_index=0,
        study_string="Smith 2010",
        pmid="12345", nct_id="NCT00012345", title="Test Trial",
        tier_s_label="african_site", tier_s_source="aact",
        tier_s_confidence=0.97, tier_s_country="Uganda",
        tier_a_label="not_african_led", tier_a_position="none",
        tier_a_confidence=0.85, tier_a_country=None,
        tier_p_label="insufficient_data", tier_p_confidence=0.0,
        tier_p_african_pct=None, tier_p_evidence=None,
        abstract_excerpt="The trial enrolled 1000 participants in Uganda...",
        authors_list="Smith, Jones, Mukasa",
    )


def test_render_ui_self_contained() -> None:
    html = render_verification_ui([_sample_label()])
    assert "<!DOCTYPE html>" in html
    assert "</html>" in html
    # No external CDN
    assert "cdn." not in html
    assert "googleapis.com" not in html
    assert "<script src=" not in html
    # Has the trial data inline
    assert "Smith 2010" in html
    assert "MA1::t0" in html
    # Has confirm/flag buttons mentioned in JS
    assert "confirm" in html.lower()
    assert "flag" in html.lower()


def test_render_ui_empty_labels_placeholder() -> None:
    html = render_verification_ui([])
    assert "<!DOCTYPE html>" in html
    # Placeholder for empty labels
    assert "no trials" in html.lower() or "empty" in html.lower()


def test_render_ui_uses_localStorage() -> None:
    """The UI persists confirm/flag decisions in localStorage."""
    html = render_verification_ui([_sample_label()])
    assert "localStorage" in html
```

- [ ] **Step 2: Run, verify FAIL**

Expected: FAIL on import (`render_verification_ui` doesn't exist).

- [ ] **Step 3: Implement `src/arac/verify/html_template.py`**

```python
"""Single-file HTML template for the ARAC verification UI.

Pattern matches Plan 3B's dashboard: ES5-compatible JS (no arrow functions, no
template literals) to avoid string.Template `$` conflicts. localStorage
persists decisions per trial_id. Export button dumps decisions as JSON.
"""

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ARAC Verification UI</title>
<style>
:root {
  --bg: #f5f1e8;
  --fg: #2a2520;
  --accent: #8b3a1a;
  --muted: #7d7468;
  --card: #ffffff;
  --border: #d8cfbf;
  --confirm: #4a7c4e;
  --flag: #b54b3a;
  --pending: #c4b88a;
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 16px;
  font-family: Georgia, "Iowan Old Style", serif;
  color: var(--fg);
  background: var(--bg);
  line-height: 1.55;
}
header {
  max-width: 900px;
  margin: 0 auto 16px auto;
}
h1 { margin: 0 0 4px 0; font-weight: normal; font-style: italic; font-size: 22px; }
.subtitle { color: var(--muted); font-size: 13px; }
main { max-width: 900px; margin: 0 auto; }
.nav {
  display: flex; align-items: center; gap: 12px;
  background: var(--card); border: 1px solid var(--border);
  border-radius: 4px; padding: 12px 16px; margin-bottom: 16px;
}
.nav button {
  font-family: inherit; font-size: 14px;
  padding: 4px 12px; border: 1px solid var(--border);
  background: white; border-radius: 3px; cursor: pointer;
}
.nav button:hover { background: #f0ead8; }
.nav .position { font-size: 14px; color: var(--muted); flex: 1; text-align: center; }
.nav .progress { font-size: 13px; color: var(--accent); }
.card {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 4px; padding: 20px 24px; margin-bottom: 16px;
}
.card h2 {
  margin: 0 0 8px 0; font-weight: normal; font-size: 18px;
  color: var(--accent);
}
.card .meta { font-size: 13px; color: var(--muted); margin-bottom: 12px; }
.card .meta code { background: #efe9da; padding: 1px 4px; border-radius: 2px; }
.context {
  background: #faf6ec; border-left: 3px solid var(--border);
  padding: 12px 16px; margin: 12px 0; font-size: 13px;
}
.context strong { color: var(--accent); }
.tiers { display: grid; grid-template-columns: 1fr; gap: 12px; margin-top: 16px; }
.tier-row {
  border: 1px solid var(--border); border-radius: 4px;
  padding: 12px 16px;
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 12px; align-items: center;
}
.tier-row .label-name {
  font-size: 12px; color: var(--muted); text-transform: uppercase;
  letter-spacing: 0.5px;
}
.tier-row .label-value { font-size: 16px; }
.tier-row .actions { display: flex; gap: 6px; }
.tier-row button {
  font-family: inherit; font-size: 13px;
  padding: 6px 14px; border-radius: 3px; cursor: pointer;
  border: 1px solid var(--border); background: white;
}
.tier-row button.confirm-btn {
  border-color: var(--confirm); color: var(--confirm);
}
.tier-row button.confirm-btn:hover, .tier-row button.confirm-btn.selected {
  background: var(--confirm); color: white;
}
.tier-row button.flag-btn {
  border-color: var(--flag); color: var(--flag);
}
.tier-row button.flag-btn:hover, .tier-row button.flag-btn.selected {
  background: var(--flag); color: white;
}
.export-row {
  display: flex; gap: 8px; align-items: center;
  background: var(--card); border: 1px solid var(--border);
  border-radius: 4px; padding: 12px 16px; margin-top: 16px;
}
.export-row button {
  font-family: inherit; font-size: 13px;
  padding: 6px 14px; border: 1px solid var(--border);
  background: white; border-radius: 3px; cursor: pointer;
}
.export-row button:hover { background: #f0ead8; }
.export-row .stats { font-size: 13px; color: var(--muted); flex: 1; }
.placeholder {
  text-align: center; padding: 60px 20px;
  color: var(--muted); font-style: italic;
}
footer {
  max-width: 900px; margin: 16px auto 0 auto;
  padding-top: 12px; border-top: 1px solid var(--border);
  font-size: 12px; color: var(--muted); text-align: center;
}
</style>
</head>
<body>
<header>
  <h1>ARAC &mdash; Verification UI</h1>
  <div class="subtitle">Verify pre-classified algorithmic decisions. Confirm or flag each tier per trial. Decisions are saved to your browser's localStorage; export when done.</div>
</header>
<main>
  <div id="ui-root"></div>
</main>
<footer>
  Generated $generated_at &mdash; $row_count trials. Storage key: <code>$storage_key</code>. Export your decisions as JSON for adjudication.
</footer>
<script>
var TRIALS = $trials_json;
var STORAGE_KEY = '$storage_key';
var currentIdx = 0;

function loadDecisions() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}'); }
  catch (e) { return {}; }
}

function saveDecisions(d) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(d));
}

function setDecision(trialId, tier, value) {
  var d = loadDecisions();
  if (!d[trialId]) d[trialId] = {};
  d[trialId][tier] = value;
  saveDecisions(d);
  render();
}

function escapeHtml(s) {
  if (s == null) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/\"/g, '&quot;');
}

function tierRow(trialId, tierKey, tierLabel, value, confidence, country) {
  var decisions = loadDecisions();
  var current = (decisions[trialId] && decisions[trialId][tierKey]) || '';
  var confirmCls = current === 'confirm' ? 'confirm-btn selected' : 'confirm-btn';
  var flagCls = current === 'flag' ? 'flag-btn selected' : 'flag-btn';
  var detailParts = [];
  if (value) detailParts.push('<strong>' + escapeHtml(value) + '</strong>');
  if (confidence) detailParts.push('confidence ' + parseFloat(confidence).toFixed(2));
  if (country) detailParts.push('country: ' + escapeHtml(country));
  var detail = detailParts.join(' &middot; ');
  return (
    '<div class="tier-row">' +
      '<div>' +
        '<div class="label-name">' + tierLabel + '</div>' +
        '<div class="label-value">' + (detail || '<em>insufficient data</em>') + '</div>' +
      '</div>' +
      '<div class="actions">' +
        '<button class="' + confirmCls + '" onclick="setDecision(\\''+ trialId +'\\', \\''+ tierKey +'\\', \\'confirm\\')">Confirm</button>' +
        '<button class="' + flagCls + '" onclick="setDecision(\\''+ trialId +'\\', \\''+ tierKey +'\\', \\'flag\\')">Flag</button>' +
      '</div>' +
    '</div>'
  );
}

function render() {
  var root = document.getElementById('ui-root');
  if (!TRIALS.length) {
    root.innerHTML = '<div class="placeholder">No trials in this batch. Build the labels CSV first via <code>python scripts/build_trial_labels.py</code>, then regenerate the UI.</div>';
    return;
  }
  if (currentIdx < 0) currentIdx = 0;
  if (currentIdx >= TRIALS.length) currentIdx = TRIALS.length - 1;
  var t = TRIALS[currentIdx];
  var decisions = loadDecisions();
  var totalDecided = 0;
  for (var k in decisions) {
    var d = decisions[k] || {};
    if (d.tier_s && d.tier_a && d.tier_p) totalDecided++;
  }

  var html = '';
  html += '<div class="nav">';
  html += '<button onclick="currentIdx--; render();">&larr; Prev</button>';
  html += '<div class="position">Trial ' + (currentIdx + 1) + ' of ' + TRIALS.length + ' &mdash; <code>' + escapeHtml(t.trial_id) + '</code></div>';
  html += '<div class="progress">' + totalDecided + ' / ' + TRIALS.length + ' fully decided</div>';
  html += '<button onclick="currentIdx++; render();">Next &rarr;</button>';
  html += '</div>';

  html += '<div class="card">';
  html += '<h2>' + escapeHtml(t.title || t.study_string) + '</h2>';
  html += '<div class="meta">';
  html += '<code>' + escapeHtml(t.ma_id) + '</code> &middot; ';
  html += 'Study: <em>' + escapeHtml(t.study_string) + '</em>';
  if (t.pmid) html += ' &middot; PMID <a href="https://pubmed.ncbi.nlm.nih.gov/' + escapeHtml(t.pmid) + '" target="_blank">' + escapeHtml(t.pmid) + '</a>';
  if (t.nct_id) html += ' &middot; <a href="https://clinicaltrials.gov/study/' + escapeHtml(t.nct_id) + '" target="_blank">' + escapeHtml(t.nct_id) + '</a>';
  html += '</div>';

  if (t.abstract_excerpt) {
    html += '<div class="context"><strong>Abstract excerpt:</strong> ' + escapeHtml(t.abstract_excerpt) + '</div>';
  }
  if (t.authors_list) {
    html += '<div class="context"><strong>Authors:</strong> ' + escapeHtml(t.authors_list) + '</div>';
  }
  if (t.tier_p_evidence) {
    html += '<div class="context"><strong>Participant geography evidence:</strong> ' + escapeHtml(t.tier_p_evidence) + '</div>';
  }

  html += '<div class="tiers">';
  html += tierRow(t.trial_id, 'tier_s', 'Tier-S (Site)', t.tier_s_label, t.tier_s_confidence, t.tier_s_country);
  html += tierRow(t.trial_id, 'tier_a', 'Tier-A (Authorship)', t.tier_a_label, t.tier_a_confidence, t.tier_a_country);
  html += tierRow(t.trial_id, 'tier_p', 'Tier-P (Participants)', t.tier_p_label, t.tier_p_confidence, null);
  html += '</div>';
  html += '</div>';

  html += '<div class="export-row">';
  html += '<div class="stats">' + Object.keys(decisions).length + ' trials touched. Export when done.</div>';
  html += '<button onclick="exportDecisions()">Download decisions JSON</button>';
  html += '<button onclick="if (confirm(\\'Reset ALL decisions?\\')) { localStorage.removeItem(STORAGE_KEY); render(); }">Reset</button>';
  html += '</div>';

  root.innerHTML = html;
}

function exportDecisions() {
  var d = loadDecisions();
  var blob = new Blob([JSON.stringify(d, null, 2)], {type: 'application/json'});
  var url = URL.createObjectURL(blob);
  var a = document.createElement('a');
  a.href = url;
  a.download = 'arac-verification-' + new Date().toISOString().replace(/[:.]/g, '-') + '.json';
  document.body.appendChild(a);
  a.click();
  setTimeout(function() {
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, 100);
}

document.addEventListener('keydown', function(e) {
  if (e.target && e.target.tagName === 'BUTTON') return;
  if (e.key === 'ArrowLeft') { currentIdx--; render(); }
  if (e.key === 'ArrowRight') { currentIdx++; render(); }
});

render();
</script>
</body>
</html>
"""
```

- [ ] **Step 4: Append `render_verification_ui` to `src/arac/verify/labels.py`**

```python
import json
from datetime import datetime, timezone
from string import Template

from arac.verify.html_template import TEMPLATE


def render_verification_ui(rows: list) -> str:
    """Render the full verification UI HTML. `rows` is a list of TrialLabel
    OR list of dicts already loaded from CSV."""
    # Normalise to a list of dicts that the JS can consume directly.
    trials_json: list[dict] = []
    for r in rows:
        if isinstance(r, TrialLabel):
            d = _row_to_dict(r)
        elif isinstance(r, dict):
            d = r
        else:
            raise TypeError(f"unexpected row type: {type(r)}")
        trials_json.append(d)

    return Template(TEMPLATE).substitute(
        trials_json=json.dumps(trials_json, ensure_ascii=False),
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        row_count=len(trials_json),
        storage_key="arac-verification-v1",
    )
```

- [ ] **Step 5: Run, verify PASS**

Run: `cd C:/Projects/arac && python -m pytest tests/test_verify_ui.py -v`
Expected: 3 PASSED.

Run full suite: `python -m pytest -v 2>&1 | tail -3` — ~110 PASSED + 1 SKIP.

- [ ] **Step 6: Sentinel + commit**

```bash
cd "C:/Projects/arac"
python -m sentinel scan --repo .
git add src/arac/verify/html_template.py src/arac/verify/labels.py tests/test_verify_ui.py
git commit -m "feat(verify): single-file HTML verification UI with localStorage state"
```

---

### Task 3: CLI runner — build labels CSV + render UI

**Files:**
- Create: `C:/Projects/arac/scripts/build_verification.py`

The runner has two modes:
- `--from-labels <csv>`: just render UI from an existing trial_labels.csv (fast)
- `--build-labels`: re-run the resolver + classifiers on Pairwise70 to produce a fresh trial_labels.csv THEN render UI

For Plan 3C ship: focus on the simpler `--from-labels` mode first. The `--build-labels` mode reuses Plan 3A's pipeline components but emits per-trial rows instead of per-MA RGS rows; it can be stub-implemented as "raise NotImplementedError, use scripts/build_atlas.py with a future --emit-labels flag" if time-pressed.

- [ ] **Step 1: Write the script**

```python
"""Generate the ARAC verification UI HTML from a trial_labels CSV.

Usage:
    python scripts/build_verification.py [--in outputs/trial_labels.csv] [--out outputs/verification.html]
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from arac.verify.labels import render_verification_ui


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="csv_in", default="outputs/trial_labels.csv")
    ap.add_argument("--out", dest="html_out", default="outputs/verification.html")
    args = ap.parse_args()

    csv_path = Path(args.csv_in)
    out_path = Path(args.html_out)

    if not csv_path.is_file():
        print(f"NOTE: {csv_path} does not exist; rendering empty UI.")
        rows: list[dict] = []
    else:
        with csv_path.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))

    html = render_verification_ui(rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"Wrote {len(html):,} bytes to {out_path} ({len(rows)} trials)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Smoke-run with no labels CSV**

Run: `cd C:/Projects/arac && python scripts/build_verification.py`
Expected: `NOTE: outputs/trial_labels.csv does not exist; rendering empty UI.` then `Wrote N bytes to outputs/verification.html (0 trials)`.

- [ ] **Step 3: Smoke-run with a synthetic labels CSV**

Create a small synthetic labels CSV by hand:

```bash
cd "C:/Projects/arac" && python - <<'PY'
from pathlib import Path
from arac.verify.labels import TrialLabel, write_trial_labels
out = Path("outputs/trial_labels.csv")
labels = [
    TrialLabel(
        trial_id="DEMO::t0", ma_id="DEMO_MA", trial_index=0,
        study_string="Mukasa 2018",
        pmid="29754567", nct_id=None, title="Demo trial in Uganda",
        tier_s_label="african_site", tier_s_source="affiliation",
        tier_s_confidence=0.55, tier_s_country="Uganda",
        tier_a_label="african_led", tier_a_position="first",
        tier_a_confidence=0.85, tier_a_country="Uganda",
        tier_p_label="african_majority", tier_p_confidence=0.95,
        tier_p_african_pct=92.0,
        tier_p_evidence="900 of 980 participants enrolled in Uganda.",
        abstract_excerpt="A randomized controlled trial of intervention X in Uganda...",
        authors_list="Mukasa, Smith, Naidoo",
    ),
    TrialLabel(
        trial_id="DEMO::t1", ma_id="DEMO_MA", trial_index=1,
        study_string="Smith 2015",
        pmid="25012345", nct_id="NCT02123456", title="US-based trial",
        tier_s_label="no_african_site", tier_s_source="aact",
        tier_s_confidence=0.97, tier_s_country=None,
        tier_a_label="not_african_led", tier_a_position="none",
        tier_a_confidence=0.85, tier_a_country=None,
        tier_p_label="not_african_majority", tier_p_confidence=0.95,
        tier_p_african_pct=0.0, tier_p_evidence="All 500 participants in USA.",
        abstract_excerpt="A multicenter US trial of intervention Y...",
        authors_list="Smith, Jones, Brown",
    ),
]
n = write_trial_labels(labels, out)
print(f"Wrote {n} demo labels")
PY
```

Then re-run: `python scripts/build_verification.py` and confirm "Wrote N bytes ... (2 trials)".

- [ ] **Step 4: Verify HTML structural sanity**

Run: `cd C:/Projects/arac && head -3 outputs/verification.html && echo "..." && tail -3 outputs/verification.html`
Expected: opens with `<!DOCTYPE html>`, ends with `</html>`. Confirm no external CDN: `grep -c "cdn\.\|googleapis\." outputs/verification.html` returns 0.

- [ ] **Step 5: Sentinel + commit**

```bash
cd "C:/Projects/arac"
python -m sentinel scan --repo .
git add scripts/build_verification.py
git commit -m "feat(verify): build_verification.py CLI — read trial_labels.csv → emit single-file HTML UI"
```

---

### Task 4: Baseline + v0.9.0 tag

**Files:**
- Modify: `C:/Projects/arac/baseline.json`

- [ ] **Step 1: Append v0.9.0 record**

```bash
cd "C:/Projects/arac" && python - <<'PY'
import json, subprocess
from datetime import datetime, timezone
sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
baseline = json.loads(open("baseline.json").read())
baseline["records"]["arac-verification-ui-v0.9.0"] = {
    "paper_id": "arac-verification-ui-v0.9.0",
    "commit_sha": sha,
    "recorded_at": ts,
    "pooled_estimate": None, "k": None,
    "ci_lower": None, "ci_upper": None, "se": None, "tau2": None,
    "i2": None, "q": None,
    "extra": {
        "verification_pattern": "RapidMeta v11.8 auto-confirm",
        "ui_storage": "browser localStorage (per-user, per-browser)",
        "ui_export": "JSON download for offline dual-confirm reconciliation",
        "labels_csv_columns": 21,
        "moral_architecture": "cohort verifies pre-classified data (per feedback_makerere_student_workload.md), does NOT do raw extraction",
        "matches_plan_3c_design": True,
        "deferred": ["adjudication compare view (Plan 3C.1 if needed)", "build_trial_labels.py batch runner from Pairwise70 (currently --from-labels mode only)"],
        "note": "Plan 3C ships the verification UI pattern. Per-trial labels CSV format defined; UI reads it; localStorage persists decisions. Batch labels generator from Pairwise70 + classifiers stubbed — dedicated user-driven batch run when authorized."
    },
}
with open("baseline.json", "w") as f:
    json.dump(baseline, f, indent=2)
print("baseline.json updated with v0.9.0 record")
PY
```

- [ ] **Step 2: Final tests + Sentinel**

```bash
cd C:/Projects/arac && python -m pytest -v 2>&1 | tail -3
cd C:/Projects/arac && python -m sentinel scan --repo .
```

Expected: ~110 tests PASS + 1 SKIP, 0 BLOCK.

- [ ] **Step 3: Add `outputs/*.html` already-gitignored confirmation + commit + tag**

```bash
cd "C:/Projects/arac"
# verification.html should already be covered by outputs/*.html in .gitignore from Plan 3B
grep "outputs/.*html\|outputs/\*\.html" .gitignore || echo "outputs/*.html" >> .gitignore
git add baseline.json .gitignore
git commit -m "chore(baseline): record Plan 3C verification UI v0.9.0"
git tag -a v0.9.0 -m "Plan 3C — verification UI (RapidMeta-style, single-file HTML, localStorage)"
```

---

## Done criteria

- [ ] All 4 tasks committed
- [ ] `git tag` shows `v0.9.0`
- [ ] All tests PASS
- [ ] Sentinel 0 BLOCK
- [ ] `baseline.json` has 12 records
- [ ] `python scripts/build_verification.py` produces `outputs/verification.html` (self-contained, no external CDN)
- [ ] The HTML opens in a browser, shows one trial card with all 3 Tier classifications, Confirm/Flag buttons work, decisions persist in localStorage, export-JSON download works

## What this plan deliberately defers

- **`build_trial_labels.py` batch runner** (resolver + classifiers → trial_labels.csv) — Plan 3C ships only the `--from-labels` mode that reads a pre-existing CSV. The batch generator is a straightforward composition of Plan 2's classifiers; defer to dedicated user-driven batch run.
- **Adjudication compare view** — Plan 3C.1 if needed; for now, dual-confirm reconciliation is "compare two exported JSON files manually."
- **Per-cohort-member auth** — single-user-per-browser via localStorage; cohort governance handles assignment offline.
- **Live LLM re-extraction in the UI** — labels are static; Plan 4's pilot can add re-run if needed.
