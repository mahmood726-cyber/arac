#!/usr/bin/env python3
"""Build the blinded auditor instrument HTML for ARAC v0.1.1."""
import json
import hashlib
import sys

BASE = "C:/Projects/arac/data/audit_v0.1.1"

with open(f"{BASE}/sample_list.json", "rb") as f:
    sl_bytes = f.read()
SAMPLE_LIST_SHA256 = hashlib.sha256(sl_bytes).hexdigest()
sl = json.loads(sl_bytes.decode("utf-8"))

with open(f"{BASE}/abstracts_cache.json", "r", encoding="utf-8") as f:
    abstracts = json.load(f)

trials_data = []
for t in sl["trials"]:
    trials_data.append({
        "trial_id": t["trial_id"],
        "pmid": t["pmid"],
        "stratum": t["stratum"],
        "study_string": t["study_string"],
        "abstract_text": abstracts.get(t["pmid"], "").strip(),
    })

# Embed JSON — must escape </script> to avoid breaking HTML parser
embedded_json = json.dumps(trials_data, ensure_ascii=False)
embedded_json_safe = embedded_json.replace("</", "<\\/")

# Validate no Cochrane in visible body text
# (allowed in abstract text if the abstract itself references it, but let's flag)
cochrane_count_in_ui = 0  # will count after build

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ARAC Blinded Audit Instrument &mdash; v0.1.1</title>
<style>
:root {{
  --bg: #f5f1e8;
  --fg: #2a2520;
  --accent: #8b3a1a;
  --muted: #7d7468;
  --card: #ffffff;
  --border: #d8cfbf;
  --confirm: #4a7c4e;
  --warn: #b54b3a;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; padding: 16px;
  font-family: Georgia, "Iowan Old Style", serif;
  color: var(--fg);
  background: var(--bg);
  line-height: 1.55;
}}
header {{
  max-width: 900px;
  margin: 0 auto 16px auto;
}}
h1 {{ margin: 0 0 4px 0; font-weight: normal; font-style: italic; font-size: 22px; }}
.subtitle {{ color: var(--muted); font-size: 13px; }}
main {{ max-width: 900px; margin: 0 auto; }}
.nav {{
  display: flex; align-items: center; gap: 12px;
  background: var(--card); border: 1px solid var(--border);
  border-radius: 4px; padding: 12px 16px; margin-bottom: 12px;
}}
.nav button {{
  font-family: inherit; font-size: 14px;
  padding: 5px 14px; border: 1px solid var(--border);
  background: white; border-radius: 3px; cursor: pointer;
}}
.nav button:hover:not(:disabled) {{ background: #f0ead8; }}
.nav button:disabled {{ opacity: 0.4; cursor: not-allowed; }}
.nav .position {{ font-size: 14px; color: var(--muted); flex: 1; text-align: center; }}
.nav .answered-label {{ font-size: 13px; color: var(--accent); white-space: nowrap; }}
.progress-bar-wrap {{
  background: #e8e0d0; border-radius: 3px;
  height: 6px; margin-bottom: 12px; overflow: hidden;
}}
.progress-bar-fill {{
  background: var(--accent); height: 100%;
  transition: width 0.3s ease;
}}
.card {{
  background: var(--card); border: 1px solid var(--border);
  border-radius: 4px; padding: 20px 24px; margin-bottom: 14px;
}}
.card h2 {{
  margin: 0 0 6px 0; font-weight: normal; font-size: 17px;
  color: var(--accent);
}}
.meta-row {{ font-size: 13px; color: var(--muted); margin-bottom: 4px; }}
.meta-row code {{ background: #efe9da; padding: 1px 5px; border-radius: 2px; font-size: 12px; }}
.meta-row a {{ color: var(--accent); text-decoration: none; }}
.meta-row a:hover {{ text-decoration: underline; }}
.study-string {{ font-size: 14px; color: var(--fg); margin-bottom: 12px; font-style: italic; }}
.abstract-label {{ font-size: 12px; text-transform: uppercase; letter-spacing: 0.6px; color: var(--muted); margin-bottom: 6px; display: block; }}
.abstract-box {{
  background: #faf6ec; border-left: 3px solid var(--border);
  padding: 12px 16px; margin-bottom: 16px;
  font-size: 13px; line-height: 1.6;
  max-height: 340px; overflow-y: auto;
  white-space: pre-wrap; word-wrap: break-word;
  border-radius: 0 3px 3px 0;
  font-family: Georgia, serif;
}}
.divider {{ border: none; border-top: 1px solid var(--border); margin: 18px 0; }}
.form-section {{ margin-bottom: 18px; }}
.section-label {{
  display: block; font-size: 12px; text-transform: uppercase;
  letter-spacing: 0.6px; color: var(--muted); margin-bottom: 6px;
}}
.required-mark {{ color: var(--warn); }}
.radio-group {{ display: flex; flex-wrap: wrap; gap: 8px; }}
.radio-group label {{
  display: flex; align-items: center; gap: 6px;
  padding: 6px 12px; border: 1px solid var(--border);
  border-radius: 3px; cursor: pointer; font-size: 14px;
  background: white; user-select: none;
}}
.radio-group input[type=radio] {{ margin: 0; cursor: pointer; }}
.radio-group label:hover {{ background: #f0ead8; }}
.radio-group label.selected {{
  border-color: var(--accent); background: #faf0ea;
  color: var(--accent);
}}
input[type=number].pct-input {{
  font-family: inherit; font-size: 14px;
  padding: 6px 10px; border: 1px solid var(--border);
  border-radius: 3px; width: 110px; background: white;
}}
input[type=number].pct-input:focus {{ outline: 1px solid var(--accent); }}
textarea.evidence-area {{
  font-family: inherit; font-size: 13px;
  width: 100%; padding: 8px 10px;
  border: 1px solid var(--border); border-radius: 3px;
  resize: vertical; min-height: 80px;
  background: white; line-height: 1.5;
}}
textarea.evidence-area:focus {{ outline: 1px solid var(--accent); }}
.error-msg {{
  display: none; color: var(--warn);
  font-size: 13px; margin-top: 5px;
}}
.error-msg.visible {{ display: block; }}
.btn-row {{ display: flex; gap: 10px; align-items: center; margin-top: 8px; }}
.btn-primary {{
  font-family: inherit; font-size: 14px;
  padding: 8px 20px; border: 1px solid var(--accent);
  background: var(--accent); color: white;
  border-radius: 3px; cursor: pointer;
}}
.btn-primary:hover:not(:disabled) {{ background: #7a3316; }}
.btn-primary:disabled {{ opacity: 0.4; cursor: not-allowed; }}
.btn-secondary {{
  font-family: inherit; font-size: 14px;
  padding: 8px 16px; border: 1px solid var(--border);
  background: white; color: var(--fg);
  border-radius: 3px; cursor: pointer;
}}
.btn-secondary:hover:not(:disabled) {{ background: #f0ead8; }}
.btn-secondary:disabled {{ opacity: 0.4; cursor: not-allowed; }}
.btn-export {{
  font-family: inherit; font-size: 14px;
  padding: 8px 20px; border: 1px solid var(--confirm);
  background: var(--confirm); color: white;
  border-radius: 3px; cursor: pointer;
}}
.btn-export:hover:not(:disabled) {{ background: #3d6841; }}
.btn-export:disabled {{ opacity: 0.4; cursor: not-allowed; }}
.overlay {{
  display: none; position: fixed; inset: 0;
  background: rgba(0,0,0,0.45); z-index: 100;
  align-items: center; justify-content: center;
}}
.overlay.visible {{ display: flex; }}
.dialog {{
  background: var(--card); border: 1px solid var(--border);
  border-radius: 6px; padding: 28px 32px; max-width: 420px; width: 90%;
  box-shadow: 0 4px 24px rgba(0,0,0,0.18);
}}
.dialog h2 {{ margin: 0 0 12px 0; font-size: 18px; font-weight: normal; color: var(--accent); }}
.dialog p {{ margin: 0 0 20px 0; font-size: 14px; }}
.dialog-btns {{ display: flex; gap: 10px; }}
.completion-banner {{
  display: none;
  background: #eef6ee; border: 1px solid var(--confirm);
  border-radius: 4px; padding: 16px 20px; margin-bottom: 14px;
  font-size: 14px; color: #2d5630;
}}
.completion-banner.visible {{ display: block; }}
.export-row {{
  background: var(--card); border: 1px solid var(--border);
  border-radius: 4px; padding: 14px 16px;
  display: flex; gap: 12px; align-items: center; margin-top: 8px;
}}
.export-row .export-stats {{ font-size: 13px; color: var(--muted); flex: 1; }}
footer {{
  max-width: 900px; margin: 16px auto 0 auto;
  padding-top: 10px; border-top: 1px solid var(--border);
  font-size: 12px; color: var(--muted); text-align: center;
}}
</style>
</head>
<body>

<div class="overlay" id="resumeOverlay">
  <div class="dialog">
    <h2>Resume previous session?</h2>
    <p id="resumeMsg">A previous session was found. Resume where you left off, or start over?</p>
    <div class="dialog-btns">
      <button class="btn-primary" id="btnResume">Resume</button>
      <button class="btn-secondary" id="btnRestart">Start over</button>
    </div>
  </div>
</div>

<header>
  <h1>ARAC &mdash; Blinded Audit Instrument</h1>
  <div class="subtitle">Version 0.1.1 &middot; Pre-registered &middot; 30 Pairwise70 trials &middot; Blinded view (classifier outputs withheld until audit complete)</div>
</header>

<main>
  <div class="progress-bar-wrap">
    <div class="progress-bar-fill" id="progressFill" style="width:0%"></div>
  </div>

  <div class="nav">
    <button id="btnPrev" onclick="navigate(-1)">&#8592; Previous</button>
    <span class="position" id="posLabel">Trial 1 of 30</span>
    <button id="btnNext" onclick="navigate(1)">Next &#8594;</button>
    <span class="answered-label" id="answeredLabel">0 / 30 answered</span>
  </div>

  <div class="card" id="trialCard">
    <h2 id="cardTitle"></h2>
    <div class="meta-row">PMID: <code id="cardPmid"></code> &nbsp;&middot;&nbsp;
      <a id="cardPubmedLink" href="#" target="_blank" rel="noopener noreferrer">View on PubMed</a>
    </div>
    <div class="meta-row">Trial ID: <code id="cardTrialId"></code></div>
    <div class="meta-row">Stratum: <code id="cardStratum"></code></div>
    <div class="study-string" id="cardStudyString"></div>

    <span class="abstract-label">Abstract (PubMed full text, pre-fetched &mdash; available offline)</span>
    <div class="abstract-box" id="cardAbstract"></div>

    <hr class="divider">

    <div class="form-section">
      <label class="section-label">
        Estimated African participant %
        <span style="color:var(--muted);font-size:11px;font-weight:normal;">(0&ndash;100; leave blank if not stated in abstract)</span>
      </label>
      <input type="number" class="pct-input" id="inputPct" min="0" max="100" placeholder="blank" step="0.1">
    </div>

    <div class="form-section">
      <label class="section-label">
        Verdict <span class="required-mark">*</span>
      </label>
      <div class="radio-group" id="verdictGroup">
        <label><input type="radio" name="verdict" value="African_majority"> African_majority</label>
        <label><input type="radio" name="verdict" value="Not_African_majority"> Not_African_majority</label>
        <label><input type="radio" name="verdict" value="Insufficient"> Insufficient</label>
      </div>
      <div class="error-msg" id="errVerdict">Please select a verdict before proceeding.</div>
    </div>

    <div class="form-section" id="quoteSection">
      <label class="section-label">
        Evidence quote <span class="required-mark" id="quoteRequired">*</span>
        <span style="color:var(--muted);font-size:11px;font-weight:normal;" id="quoteOptionalNote">
          (required when verdict is African_majority or Not_African_majority)
        </span>
      </label>
      <textarea class="evidence-area" id="inputQuote"
        placeholder="Paste the exact phrase from the abstract that supports your verdict."></textarea>
      <div class="error-msg" id="errQuote">Evidence quote is required for this verdict.</div>
    </div>

    <div class="form-section">
      <label class="section-label">
        Confidence <span class="required-mark">*</span>
      </label>
      <div class="radio-group" id="confidenceGroup">
        <label><input type="radio" name="confidence" value="high"> high</label>
        <label><input type="radio" name="confidence" value="medium"> medium</label>
        <label><input type="radio" name="confidence" value="low"> low</label>
        <label><input type="radio" name="confidence" value="insufficient"> insufficient</label>
      </div>
      <div class="error-msg" id="errConfidence">Please select a confidence level before proceeding.</div>
    </div>

    <div class="form-section">
      <label class="section-label">
        Notes <span style="color:var(--muted);font-size:11px;font-weight:normal;">(optional)</span>
      </label>
      <textarea class="evidence-area" id="inputNotes" style="min-height:60px;"
        placeholder="Free-text notes (optional)."></textarea>
    </div>

    <div class="btn-row">
      <button class="btn-secondary" id="btnSave" onclick="saveCurrent(false)">Save</button>
      <button class="btn-primary" id="btnNextBottom" onclick="saveCurrent(true)">Save &amp; Next</button>
    </div>
  </div>

  <div class="completion-banner" id="completionBanner">
    All 30 trials answered. Export your results below.
  </div>

  <div class="export-row">
    <span class="export-stats" id="exportStats">0 of 30 trials answered.</span>
    <button class="btn-export" id="btnExport" onclick="exportResults()" disabled>Export results as JSON</button>
  </div>
</main>

<footer>
  ARAC v0.1.1 &middot; Blinded Audit Instrument &middot;
  spec_commit ebc8c13 &middot; amendment prereg-v0.1.1.1-amend-1 (0d3f69c) &middot;
  sample_list SHA-256: {SAMPLE_LIST_SHA256}
</footer>

<script>
// ============================================================================
// EMBEDDED TRIAL DATA — 30 Pairwise70 trials, abstracts pre-fetched from
// PubMed (offline-capable). LLM outputs are NOT present; this is the blinded view.
// ============================================================================
var TRIALS_DATA = {embedded_json_safe};

var SPEC_META = {{
  spec_version: "v0.1.1",
  spec_commit: "ebc8c13",
  amendment: "prereg-v0.1.1.1-amend-1 (commit 0d3f69c)",
  sample_list_sha256: "{SAMPLE_LIST_SHA256}",
  auditor: "mahmood726-cyber"
}};

var STORAGE_KEY = "arac_audit_v0_1_1_state";

// ============================================================================
// SEEDED PRNG — sfc32 (Small Fast Counting RNG, 128-bit state)
// Seeded from integer seed via MurmurHash3 fmix32 mixing.
// Shuffle seed = 99 (independent of sampling seed 42).
// ============================================================================
function fmix32(h) {{
  h = h >>> 0;
  h ^= h >>> 16; h = Math.imul(h, 0x85ebca6b) >>> 0;
  h ^= h >>> 13; h = Math.imul(h, 0xc2b2ae35) >>> 0;
  h ^= h >>> 16;
  return h >>> 0;
}}

function makeSfc32(a, b, c, d) {{
  return function() {{
    a >>>= 0; b >>>= 0; c >>>= 0; d >>>= 0;
    var t = (a + b + d) >>> 0;
    d = (d + 1) >>> 0;
    a = b ^ (b >>> 9);
    b = (c + (c << 3)) >>> 0;
    c = (c << 21 | c >>> 11) >>> 0;
    c = (c + t) >>> 0;
    return t / 4294967296;
  }};
}}

function seededShuffle(arr, seed) {{
  var s = seed >>> 0;
  var rng = makeSfc32(fmix32(s), fmix32(s+1), fmix32(s+2), fmix32(s+3));
  for (var w = 0; w < 15; w++) rng(); // warm up
  for (var i = arr.length - 1; i > 0; i--) {{
    var j = Math.floor(rng() * (i + 1));
    var tmp = arr[i]; arr[i] = arr[j]; arr[j] = tmp;
  }}
  return arr;
}}

// Build shuffled index array (indices into TRIALS_DATA)
var idxArr = [];
for (var z = 0; z < 30; z++) idxArr.push(z);
seededShuffle(idxArr, 99);
// shuffleOrder[position] = index into TRIALS_DATA

// ============================================================================
// STATE
// ============================================================================
var answers    = {{}};   // trial_id -> answer object
var currentPos = 0;      // 0-based position in shuffleOrder
var startedAt  = null;   // ISO8601 of first save

function trialAt(pos) {{ return TRIALS_DATA[idxArr[pos]]; }}

function countAnswered() {{
  var n = 0;
  for (var k in answers) if (Object.prototype.hasOwnProperty.call(answers, k)) n++;
  return n;
}}

function isComplete() {{ return countAnswered() >= 30; }}

// ============================================================================
// PERSISTENCE
// ============================================================================
function saveState() {{
  try {{
    localStorage.setItem(STORAGE_KEY, JSON.stringify({{
      answers: answers,
      currentPos: currentPos,
      startedAt: startedAt
    }}));
  }} catch(e) {{}}
}}

function loadState() {{
  try {{
    var raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  }} catch(e) {{ return null; }}
}}

function clearState() {{
  try {{ localStorage.removeItem(STORAGE_KEY); }} catch(e) {{}}
}}

// ============================================================================
// RENDER
// ============================================================================
function renderCard() {{
  var t = trialAt(currentPos);

  document.getElementById("cardTitle").textContent      = t.study_string || t.trial_id;
  document.getElementById("cardPmid").textContent       = t.pmid;
  document.getElementById("cardPubmedLink").href        = "https://pubmed.ncbi.nlm.nih.gov/" + t.pmid + "/";
  document.getElementById("cardTrialId").textContent    = t.trial_id;
  document.getElementById("cardStratum").textContent    = t.stratum;
  document.getElementById("cardStudyString").textContent= t.study_string;
  document.getElementById("cardAbstract").textContent   = t.abstract_text || "(abstract not available)";
  document.getElementById("posLabel").textContent       = "Trial " + (currentPos + 1) + " of 30";

  var ans = answers[t.trial_id] || {{}};

  // Restore numeric pct
  var pctVal = document.getElementById("inputPct");
  pctVal.value = (ans.auditor_african_pct !== null && ans.auditor_african_pct !== undefined)
    ? ans.auditor_african_pct : "";

  // Restore textareas
  document.getElementById("inputQuote").value = ans.evidence_quote || "";
  document.getElementById("inputNotes").value = ans.notes || "";

  // Restore radios
  ["African_majority","Not_African_majority","Insufficient"].forEach(function(v) {{
    var inp = document.querySelector('input[name="verdict"][value="' + v + '"]');
    if (inp) inp.checked = (ans.auditor_verdict === v);
  }});
  ["high","medium","low","insufficient"].forEach(function(v) {{
    var inp = document.querySelector('input[name="confidence"][value="' + v + '"]');
    if (inp) inp.checked = (ans.confidence === v);
  }});

  updateRadioStyles();
  updateQuoteHint();
  clearErrors();
  updateNav();
  updateProgress();
}}

function updateNav() {{
  document.getElementById("btnPrev").disabled = (currentPos === 0);
  var nextBtn = document.getElementById("btnNextBottom");
  nextBtn.textContent = (currentPos === 29) ? "Save" : "Save & Next";
  document.getElementById("answeredLabel").textContent = countAnswered() + " / 30 answered";
}}

function updateProgress() {{
  var pct = (countAnswered() / 30) * 100;
  document.getElementById("progressFill").style.width = pct + "%";
  document.getElementById("exportStats").textContent  = countAnswered() + " of 30 trials answered.";
  document.getElementById("btnExport").disabled       = !isComplete();
  var banner = document.getElementById("completionBanner");
  if (isComplete()) banner.classList.add("visible");
  else banner.classList.remove("visible");
}}

function updateRadioStyles() {{
  ["African_majority","Not_African_majority","Insufficient"].forEach(function(v) {{
    var inp = document.querySelector('input[name="verdict"][value="' + v + '"]');
    if (inp && inp.parentElement) {{
      if (inp.checked) inp.parentElement.classList.add("selected");
      else inp.parentElement.classList.remove("selected");
    }}
  }});
  ["high","medium","low","insufficient"].forEach(function(v) {{
    var inp = document.querySelector('input[name="confidence"][value="' + v + '"]');
    if (inp && inp.parentElement) {{
      if (inp.checked) inp.parentElement.classList.add("selected");
      else inp.parentElement.classList.remove("selected");
    }}
  }});
}}

function updateQuoteHint() {{
  var v = getVerdict();
  var required = (v === "African_majority" || v === "Not_African_majority");
  document.getElementById("quoteRequired").style.display = required ? "" : "none";
  document.getElementById("quoteOptionalNote").textContent = required
    ? "(required when verdict is African_majority or Not_African_majority)"
    : "(optional when verdict is Insufficient)";
}}

function getVerdict() {{
  var inp = document.querySelector('input[name="verdict"]:checked');
  return inp ? inp.value : null;
}}
function getConf() {{
  var inp = document.querySelector('input[name="confidence"]:checked');
  return inp ? inp.value : null;
}}
function clearErrors() {{
  ["errVerdict","errQuote","errConfidence"].forEach(function(id) {{
    document.getElementById(id).classList.remove("visible");
  }});
}}

// ============================================================================
// VALIDATION
// ============================================================================
function validate() {{
  clearErrors();
  var ok = true;
  var verdict = getVerdict();
  var conf    = getConf();
  var quote   = document.getElementById("inputQuote").value.trim();
  if (!verdict) {{
    document.getElementById("errVerdict").classList.add("visible");
    ok = false;
  }}
  if (verdict && verdict !== "Insufficient" && !quote) {{
    document.getElementById("errQuote").classList.add("visible");
    ok = false;
  }}
  if (!conf) {{
    document.getElementById("errConfidence").classList.add("visible");
    ok = false;
  }}
  return ok;
}}

// ============================================================================
// SAVE
// ============================================================================
function collectAnswer() {{
  var t    = trialAt(currentPos);
  var pRaw = document.getElementById("inputPct").value.trim();
  var pct  = (pRaw === "") ? null : parseFloat(pRaw);
  if (pct !== null && !isFinite(pct)) pct = null;
  return {{
    trial_id:            t.trial_id,
    pmid:                t.pmid,
    stratum:             t.stratum,
    auditor_african_pct: pct,
    auditor_verdict:     getVerdict(),
    evidence_quote:      document.getElementById("inputQuote").value.trim(),
    confidence:          getConf(),
    notes:               document.getElementById("inputNotes").value.trim(),
    answered_at:         new Date().toISOString(),
    shuffle_position:    currentPos + 1
  }};
}}

// saveCurrent(advance): validate, save, optionally move to next
function saveCurrent(advance) {{
  if (!validate()) return;
  if (!startedAt) startedAt = new Date().toISOString();
  var ans = collectAnswer();
  answers[ans.trial_id] = ans;
  saveState();
  updateProgress();
  updateNav();
  if (advance && currentPos < 29) {{
    currentPos++;
    saveState();
    renderCard();
    window.scrollTo(0, 0);
  }}
}}

// ============================================================================
// NAVIGATION (Previous / top-bar Next)
// ============================================================================
function navigate(dir) {{
  // Auto-save partial answer if verdict + confidence are set
  var verdict = getVerdict();
  var conf    = getConf();
  if (verdict && conf) {{
    if (!startedAt) startedAt = new Date().toISOString();
    var ans = collectAnswer();
    answers[ans.trial_id] = ans;
  }}
  var newPos = currentPos + dir;
  if (newPos < 0 || newPos > 29) return;
  currentPos = newPos;
  saveState();
  renderCard();
  window.scrollTo(0, 0);
}}

// ============================================================================
// EXPORT
// ============================================================================
function exportResults() {{
  if (!isComplete()) return;
  // Emit results in shuffle order
  var results = [];
  for (var i = 0; i < 30; i++) {{
    var t   = TRIALS_DATA[idxArr[i]];
    var ans = answers[t.trial_id];
    if (ans) results.push(ans);
  }}
  var completedAt = results.reduce(function(latest, a) {{
    return a.answered_at > latest ? a.answered_at : latest;
  }}, "");
  var out = {{
    spec_version:      SPEC_META.spec_version,
    spec_commit:       SPEC_META.spec_commit,
    amendment:         SPEC_META.amendment,
    sample_list_sha256:SPEC_META.sample_list_sha256,
    auditor:           SPEC_META.auditor,
    started_at:        startedAt || "",
    completed_at:      completedAt,
    user_agent:        navigator.userAgent,
    results:           results
  }};
  var blob = new Blob([JSON.stringify(out, null, 2)], {{type: "application/json"}});
  var url  = URL.createObjectURL(blob);
  var a    = document.createElement("a");
  a.href   = url;
  a.download = "audit_auditor_results.json";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}}

// ============================================================================
// RADIO CHANGE LISTENERS
// ============================================================================
document.querySelectorAll('input[name="verdict"]').forEach(function(inp) {{
  inp.addEventListener("change", function() {{
    updateRadioStyles(); updateQuoteHint(); clearErrors();
  }});
}});
document.querySelectorAll('input[name="confidence"]').forEach(function(inp) {{
  inp.addEventListener("change", function() {{
    updateRadioStyles(); clearErrors();
  }});
}});

// ============================================================================
// STARTUP
// ============================================================================
window.addEventListener("DOMContentLoaded", function() {{
  var saved = loadState();
  var nSaved = saved ? Object.keys(saved.answers || {{}}).length : 0;
  if (nSaved > 0) {{
    document.getElementById("resumeMsg").textContent =
      "A previous session was found with " + nSaved + " of 30 trials answered. " +
      "Resume where you left off, or start over (clears all saved answers)?";
    document.getElementById("resumeOverlay").classList.add("visible");

    document.getElementById("btnResume").onclick = function() {{
      answers    = saved.answers || {{}};
      currentPos = saved.currentPos || 0;
      startedAt  = saved.startedAt || null;
      // Jump to first incomplete trial
      for (var i = 0; i < 30; i++) {{
        var t = trialAt(i);
        if (!answers[t.trial_id]) {{ currentPos = i; break; }}
      }}
      document.getElementById("resumeOverlay").classList.remove("visible");
      renderCard();
    }};

    document.getElementById("btnRestart").onclick = function() {{
      clearState();
      answers = {{}}; currentPos = 0; startedAt = null;
      document.getElementById("resumeOverlay").classList.remove("visible");
      renderCard();
    }};
  }} else {{
    renderCard();
  }}
}});
</script>
</body>
</html>"""

out_path = f"{BASE}/audit_instrument.html"
with open(out_path, "w", encoding="utf-8") as f:
    f.write(html)

file_bytes = len(html.encode("utf-8"))
print(f"Written: {file_bytes} bytes -> {out_path}")
print(f"SAMPLE_LIST_SHA256: {SAMPLE_LIST_SHA256}")

# Quick sanity checks
import re
body_match = re.search(r'<body>(.*)</body>', html, re.DOTALL)
body_text = body_match.group(1) if body_match else html
cochrane_in_body = len(re.findall(r'cochrane', body_text, re.IGNORECASE))
print(f"'cochrane' occurrences in body: {cochrane_in_body}")

trial_id_occurrences = len(re.findall(r'trial_id', html))
print(f"'trial_id' occurrences in file: {trial_id_occurrences}")

# Check for CDN links (only pubmed should be in href)
ext_links = re.findall(r'https?://[^"\'>\s]+', html)
non_pubmed = [l for l in ext_links if 'pubmed.ncbi.nlm.nih.gov' not in l]
print(f"Non-PubMed external URLs: {non_pubmed}")

print("BUILD OK")
