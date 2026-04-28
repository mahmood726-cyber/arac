"""Single-file HTML template for the ARAC verification UI.

Pattern matches Plan 3B's dashboard: ES5-compatible JS (no arrow functions, no
template literals) to avoid string.Template `$` conflicts. localStorage
persists decisions per trial_id. Export button dumps decisions as JSON.

Dollar signs in JS that are NOT substitution placeholders must be doubled ($$)
so string.Template leaves them literal. The only bare $ signs in this template
are the four substitution placeholders: $trials_json, $generated_at,
$row_count, $storage_key.
"""

TEMPLATE = r"""<!DOCTYPE html>
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
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
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
        '<button class="' + confirmCls + '" onclick="setDecision(\'' + trialId + '\', \'' + tierKey + '\', \'confirm\')">Confirm</button>' +
        '<button class="' + flagCls + '" onclick="setDecision(\'' + trialId + '\', \'' + tierKey + '\', \'flag\')">Flag</button>' +
      '</div>' +
    '</div>'
  );
}

function render() {
  var root = document.getElementById('ui-root');
  if (!TRIALS.length) {
    root.innerHTML = '<div class="placeholder">No trials in this batch. Build the labels CSV first via <code>python scripts/build_trial_labels.py</code>, then regenerate the UI. Empty batch detected.</div>';
    return;
  }
  if (currentIdx < 0) currentIdx = 0;
  if (currentIdx >= TRIALS.length) currentIdx = TRIALS.length - 1;
  var t = TRIALS[currentIdx];
  var decisions = loadDecisions();
  var totalDecided = 0;
  var dkeys = Object.keys(decisions);
  for (var ki = 0; ki < dkeys.length; ki++) {
    var d = decisions[dkeys[ki]] || {};
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
  html += '<button onclick="if (confirm(\'Reset ALL decisions?\')) { localStorage.removeItem(STORAGE_KEY); render(); }">Reset</button>';
  html += '</div>';

  root.innerHTML = html;
}

function exportDecisions() {
  var d = loadDecisions();
  var blob = new Blob([JSON.stringify(d, null, 2)], {type: 'application/json'});
  var url = URL.createObjectURL(blob);
  var a = document.createElement('a');
  a.href = url;
  a.download = 'arac-verification-decisions.json';
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
