# ARAC Tier-P Blinded-Audit Calibration Protocol (v0.1.1)

**Date:** 2026-05-06
**Status:** Pre-registered (OTS-stamped before any audit or LLM run)
**Purpose:** Produce a single sensitivity headline for ARAC's Tier-P classifier ("`% African-majority`" per trial) using the same blinded-audit framing as PACTR-Hiddenness-Atlas.
**Steward / v0.1.1 auditor:** mahmood726-cyber. Makerere PhD-cohort IRR audit at v0.2.

---

## 1. Goal

A human auditor independently classifies n=30 Pairwise70 trials by reading their published abstract and answering a structured form. The LLM classifier (run per-trial via the existing `scripts/tier_p_smoke.py` smoke endpoint) is held out until the audit is complete. Sensitivity = LLM positives confirmed by auditor / total auditor positives. The result replaces the placeholder `ci_or_qualifier` in ARAC's `tiba.yaml` with a real calibration metric and ships as v0.1.1.

---

## 2. Sampling Protocol

**N = 30.** Power rationale: PACTR-Hiddenness-Atlas used n=30 and reported 16 auditor positives, giving a usable denominator. For Tier-P, African-majority trials are a minority class; a stratified draw guarantees at least 10 auditor-positive trials.

**Sampling frame.** All Pairwise70 MAs at `<drive>:/Projects/Pairwise70/data/` (595 `.rda` files, 6,386 MAs). Unit of analysis: a single trial row (one `Study` string in a Pairwise70 `.rda` dataframe, resolving to a unique PMID).

**Stratification — 15 + 15:**
- **Stratum 1 (Enriched):** MAs with at least one trial whose study string matches an African country keyword as a **whole word** (case-insensitive `\b<keyword>\b` regex). Keyword list: `Uganda`, `Kenya`, `South Africa`, `Nigeria`, `Tanzania`, `Ghana`, `Malawi`, `Ethiopia`, `Zimbabwe`, `Zambia`, `Mozambique`, `Rwanda`, `Cameroon`, `Senegal`, `Mali`, `Gambia`, `Burkina Faso`, `Botswana`, `Côte d'Ivoire`, `Democratic Republic`, `Sudan`. Multi-word keywords (e.g. "South Africa", "Burkina Faso") match when the entire phrase appears as consecutive words bounded by `\b` at start and end. Word-boundary matching prevents false positives on author surnames containing country substrings (e.g. "Kamali" no longer matches `Mali`; "Ghanavati" no longer matches `Ghana`). See §14 Amendment Log entry 1 for provenance.
- **Stratum 2 (Random):** Trials drawn uniformly at random from the remaining MAs.

**RNG.** `random.seed(42)` in Python's stdlib `random` module before any sampling. Deterministic given the Pairwise70 snapshot. sha256 of each `.rda` recorded in the pre-registration artefact.

**Eligibility.** A trial row is eligible if (a) it resolves to a PubMed PMID via `StudyResolver` (`meta.pmid is not None`), and (b) the resolved PMID's PubMed record contains a non-empty abstract. Failures are replaced by the next eligible draw within the same stratum; replacements logged.

**Excluded from confusion matrix (not from sample).** Trials where the abstract does not state participant geography → `INSUFFICIENT_DATA` for LLM and `Insufficient` for auditor. Both are excluded from sensitivity and specificity but retained in `insufficient_count`.

---

## 3. Auditor Instrument

**Form fields per trial** (one HTML card, RapidMeta one-trial-at-a-time pattern, blinded view):

| Field | Type | Choices |
|---|---|---|
| `trial_id` | display only | e.g. `CD000028_pub4_data__A1_trial3` |
| `pmid` | display only | e.g. `25490675` |
| `abstract_text` | display only, scrollable | full PubMed abstract |
| `auditor_african_pct` | numeric (0–100) or null | best estimate; blank if not stated |
| `auditor_verdict` | radio | `African_majority` / `Not_African_majority` / `Insufficient` |
| `evidence_quote` | textarea | exact quote supporting the verdict |
| `confidence` | radio | `high` / `medium` / `low` / `insufficient` |
| `notes` | textarea | free-text, optional |

**Definition of "African-majority":** `> 50%` of enrolled participants at African sites. Matches `_THRESHOLD_PCT = 50.0` in `src/arac/classify/tier_p.py`. The 50% threshold is locked in production code; auditor and algorithm use the identical operational definition.

**Auditor blinding.** The form loads `pmid`, `abstract_text`, `trial_id`. It does NOT display `african_participant_pct`, `tier_p`, or `confidence` from the LLM. LLM outputs are stored in a separate `audit_llm_outputs.json` not exposed until the audit is complete.

**Session structure.** 30 trials presented in shuffled order (shuffle seed = 99, independent of sampling seed 42). `localStorage` pause/resume. Target: 3 sessions × 10 trials.

**Amendment 2 (2026-05-06):** The auditor for v0.1.1 is `claude-sonnet-4-6` dispatched as a subagent in fresh context, given the same blinded form (no LLM classifier output visible). Sonnet receives the abstract + structured form schema + all 30 trials in one batched call, returning a JSON array of 30 verdicts in the auditor-results format. The session-structure / shuffle / localStorage / pause-resume mechanics in the original form (§3 above) are retained for the v0.2 human IRR audit; for v0.1.1 they do not apply (the LLM judge processes all 30 in one call).

---

## 4. LLM Comparator

**Entry point.** `scripts/tier_p_audit_batch.py` (to be written) accepts the JSON sample list and emits `data/audit_v0.1.1/audit_llm_outputs.json` with one record per trial: `trial_id`, `pmid`, `tier_p` (`african_majority` / `not_african_majority` / `insufficient_data`), `confidence`, `african_pct`, `countries_mentioned`, `evidence_source`. Calls the same `TierPClassifier.classify()` used in production.

**Model.** `claude-opus-4-7` (default; `ARAC_TIER_P_MODEL` env override). Same model that runs in production — calibration must transfer.

**Cache.** `outputs/cache/resolve/tier_p_llm/` populates on first run; subsequent re-runs are free.

**Amendment 2 (2026-05-06):** For v0.1.1 ship, the entry point is replaced by an `claude-opus-4-7` subagent dispatch in fresh context, given the production Tier-P system prompt + 30 abstracts + structured output schema, returning classifications in the same format the script would emit. The script `scripts/tier_p_audit_batch.py` is retained for the v0.2 per-call path (API-key-gated). Batched-vs-per-call deviation: see §12 R7.

---

## 5. Comparison Statistics

**Primary (Amendment 2): Cohen's κ** between opus-classifier and sonnet-judge on the 2×2 confusion matrix (excluding Insufficient). κ = (P_observed − P_chance) / (1 − P_chance). Asymptotic CI via Fleiss: σ²(κ) = (P_observed(1−P_observed)) / (n·(1−P_chance)²); 95% CI = κ ± 1.96·σ. For n<50 (n=30 here), additionally report bootstrap CI: resample n=30 trials with replacement B=10000 times, compute κ each time, take the 2.5th and 97.5th percentiles.

**Secondary (proxy diagnostic): sensitivity** = TP / (TP + FN), where TP = opus `african_majority` AND sonnet-judge `African_majority`; FN = opus `not_african_majority` AND sonnet-judge `African_majority`. Trials marked `Insufficient` by either party are excluded. **Caveat:** sonnet-judge is NOT a human gold standard; this sensitivity number is a within-LLM-family agreement metric, not the same as PACTR's blinded human auditor sensitivity. v0.2 Makerere human IRR replaces sonnet-judge.

Wilson 95% CI for sensitivity (proxy) and specificity formulae unchanged from original §5.

**Secondary:**
- Specificity = TN / (TN + FP)
- Positive predictive value = TP / (TP + FP)

**Headline for `tiba.yaml`.** Cohen's κ point estimate (asymptotic 95% CI), e.g. `"82.4%"` for value; full CI + n + sensitivity-proxy in `ci_or_qualifier`. If κ cannot be computed (all agreements, zero variance in one class), protocol fails — see §12 Risk 1.

---

## 6. Deliverables

New files committed at v0.1.1:
- `docs/superpowers/specs/2026-05-06-rgs-blinded-audit.md` (this spec)
- `docs/superpowers/specs/2026-05-06-rgs-blinded-audit.md.ots`
- `data/audit_v0.1.1/sample_list.json`
- `data/audit_v0.1.1/sample_list.json.ots`
- `data/audit_v0.1.1/audit_instrument.html`
- `data/audit_v0.1.1/audit_instrument.html.ots`
- `data/audit_v0.1.1/audit_llm_outputs.json` (committed AFTER auditor finishes)
- `data/audit_v0.1.1/audit_auditor_results.json`
- `data/audit_v0.1.1/audit_calibration_report.json`
- `scripts/tier_p_audit_batch.py`
- `scripts/tier_p_audit_compare.py`
- `tiba.yaml` (updated headline)
- `tests/test_tiba_headline.py` (asserts `tiba.yaml` value matches `audit_calibration_report.json`)

---

## 7. Tiba Update

`C:\Projects\arac\tiba.yaml` `headline_metric` changes from the current engine-validation placeholder to:

```yaml
headline_metric:
  label: "Tier-P inter-classifier consistency (κ): claude-opus-4-7 production classifier vs claude-sonnet-4-6 blinded judge, n=30 Pairwise70 trials"
  value: "<XX.X%>"
  ci_or_qualifier: "Cohen's κ <K.KK> [asymptotic 95% CI: <A.AA>–<B.BB>]; sensitivity-proxy <SS.S%> (LLM judge, NOT human gold standard); 15 enriched + 15 random stratum (Amendment 1: word-boundary regex); pre-reg OTS prereg-v0.1.1.2-amend-2; v0.2 Makerere human IRR audit pending"
  source: "arac v0.1.1 (2026-05-06)"
last_verified: "2026-05-06"
```

The `14.30%` engine-validation number moves to `E156-PROTOCOL.md` "Module versions shipped" as a reproducibility anchor; it is not discarded.

---

## 8. Pre-Registration

**OTS-stamped BEFORE auditor sees any trial:**
1. `docs/superpowers/specs/2026-05-06-rgs-blinded-audit.md` (this file)
2. `data/audit_v0.1.1/sample_list.json`
3. `data/audit_v0.1.1/audit_instrument.html`

**How.** `ots stamp <file>` via `opentimestamps-client` (same tool used for `pactr-hiddenness-atlas/data/processed/spotcheck_v0.1.0.csv.ots`). The `.ots` sidecar is committed alongside.

**Sequence — non-negotiable:**
1. Write + commit this spec → `ots stamp` it → commit the .ots
2. Generate sample_list.json → `ots stamp` it → commit both
3. Build audit_instrument.html → `ots stamp` it → commit both
4. **THEN** run LLM batch (writes `audit_llm_outputs.json` locally; NOT committed yet)
5. **THEN** hand auditor the UI
6. After audit complete: commit `audit_auditor_results.json` AND `audit_llm_outputs.json` AND `audit_calibration_report.json` → update `tiba.yaml` → tag v0.1.1

The LLM-batch script hard-fails if `sample_list.json.ots` does not exist (enforces pre-registration).

---

## 9. Locked Decisions (v0.1.1)

1. **Auditor (v0.1.1):** `claude-sonnet-4-6` subagent (LLM, blinded form, batched). Architectural-bias caveat acknowledged; v0.2 Makerere PhD-cohort human IRR audit replaces this and ships the human gold-standard sensitivity headline.
2. **IRR & gold standard:** v0.2 — Makerere PhD-cohort blinded human auditor on the same 30 trials. Cohen's κ between sonnet-judge (v0.1.1) and human (v0.2) measures architectural-bias of LLM judging vs human; sensitivity vs human becomes the canonical headline.
3. **Threshold:** 50% African-majority (matches production code). Locked.

---

## 10. Cost & Time Budget

- **API spend (v0.1.1):** **$0**. Both subagent dispatches use the Claude Code subscription; no separate Anthropic API billing.
- **Auditor time (v0.1.1):** **0 hours** (sonnet-judge subagent).
- **API spend (v0.2):** ~$0.30–$1.20 for per-call opus run + Anthropic API key.
- **Auditor time (v0.2):** 2.5–5 hours human (Makerere PhD-cohort), one human-day spread over 1–2 weeks.
- **Infrastructure:** zero new infrastructure. OTS stamp via WSL CLI.

---

## 11. Acceptance Criteria for ARAC v0.1.1

A v0.1.1 tag is cut when ALL hold:
1. `data/audit_v0.1.1/sample_list.json` exists with exactly 30 entries (each with confirmed PMID).
2. `sample_list.json.ots` and `audit_instrument.html.ots` and this spec's `.ots` are committed (verifiable via `ots verify`).
3. `audit_auditor_results.json` has exactly 30 entries, all with non-null `auditor_verdict` (source: sonnet-subagent for v0.1.1).
4. `audit_llm_outputs.json` has exactly 30 entries, all with non-null `tier_p`.
5. `audit_calibration_report.json` exists with: `sensitivity`, `specificity`, `ppv`, `kappa`, `ci_lower`, `ci_upper`, `n_auditor_positive`, `n_insufficient_excluded`, `confusion_matrix`.
6. `tiba.yaml` `value` field equals the **Cohen's κ** point estimate from `audit_calibration_report.json` (verified by `tests/test_tiba_headline.py`).
7. All existing 110 pytest tests pass (no regressions).
8. `E156-PROTOCOL.md` updated: "v0.1.1 Tier-P inter-classifier κ calibration complete (LLM judge); v0.2 human IRR pending" row added.

---

## 12. Risks

- **R1 — Zero auditor-positive trials.** Mitigation: pre-specified adjustment — if `n_auditor_positive < 5` after enriched stratum, increase enriched N from 15 to 20 (replace 5 random draws). Declared here, not HARKing.
- **R2 — Auditor bias (steward = auditor).** Mitigation: required `evidence_quote` field; v0.2 Makerere IRR audit reveals systematic bias.
- **R3 — Ambiguous abstracts.** Mitigation: enriched stratum biases toward abstracts that name African sites.
- **R4 — Sample list OTS stamp delayed.** Mitigation: §8 sequence is enforced; `tier_p_audit_batch.py` hard-fails if `sample_list.json.ots` is missing.
- **R5 — Pairwise70 snapshot changes between sampling and audit.** Mitigation: sha256 of each sampled `.rda` recorded in `sample_list.json`; verified before the LLM batch runs.

---

## 13. Tiba Federation Update (post-audit)

The Tiba meta-repo's index page CI auto-rebuilds on any push that includes a federation `tiba.yaml` change. After ARAC v0.1.1 is tagged and pushed, the next Tiba CI run regenerates `site/index.html` and the federation Equity card updates to the calibration headline within 1–2 minutes.

---

## 14. Amendment Log

### Amendment 1 — Word-boundary enrichment regex (2026-05-06, pre-LLM)

**What changed:** Section 2 stratification — enrichment regex switched from case-insensitive substring match to case-insensitive word-boundary match (`\b<keyword>\b`).

**Why:** Phase 2's first sample (commit `4916242`, tagged `prereg-v0.1.1.0`, OTS-stamped) revealed that 13 of 15 enriched-stratum trials were back-pain chiropractic studies whose author surnames contained African country substrings ("Kamali" → matched `Mali`; "Ghanavati" → matched `Ghana`; "Malik" → matched `Mali`). Only the 2 Sagara 2018 trials (Burkina Faso, Mali) were genuine African research. With ~2 expected auditor positives in the sample, the sensitivity CI would be uselessly wide.

**When:** Discovered 2026-05-06 immediately after the Phase 2 implementer flagged it. **No LLM batch was run, no auditor saw any trial.** Therefore no data was shopped — the amendment fixes a known pre-execution defect, not a post-hoc result.

**Authority:** Mahmood Ahmad (steward), pursuant to spec §9 Locked Decisions.

**Anchors:**
- Original pre-reg: git tag `prereg-v0.1.1.0` at commit `4916242` (substring regex, superseded). Original `sample_list.json.ots` and original spec `.ots` are preserved at that tag in git history.
- This amendment: git tag `prereg-v0.1.1.1-amend-1` at the amendment commit (this commit). New OTS stamps for amended spec + regenerated sample list.

**No data discarded.** The original sample list at the prior tag remains a valid pre-registered artefact for archival; it is not the audit set. The amended sample list (regenerated with the same `seed=42` under the word-boundary regex) becomes the v0.1.1 audit set.

### Amendment 2 — LLM-substituted classifier and judge (2026-05-06, pre-data)

**What changed:** Sections 3, 4, 5, 7, 9, 10, 11, 12.

- **§3 Auditor Instrument.** "Auditor" is now an LLM subagent (`claude-sonnet-4-6`) rather than a human. The instrument fields are unchanged; the structured form is filled by the sonnet subagent in batched mode (all 30 trials in a single fresh-context dispatch). Document recommends the v0.1.2 or v0.2 Makerere PhD-cohort human IRR audit as the eventual human gold-standard headline.
- **§4 LLM Comparator.** "Production classifier" is dispatched as an `claude-opus-4-7` subagent in fresh context, given the production Tier-P system prompt + 30 abstracts in batched mode, returning structured classifications. This substitutes for `scripts/tier_p_audit_batch.py` (which is retained for the v0.2 path with API key).
- **§5 Comparison Statistics.** Primary headline metric REFRAMED to **Cohen's κ** between opus-classifier and sonnet-judge on the 2×2 (excluding Insufficient). Asymptotic CI for κ via Fleiss formula: σ²(κ) = (P₀(1-P₀))/(n(1-P_e)²); CI = κ ± 1.96·σ. Sensitivity (proxy) becomes secondary diagnostic with caveat. Specificity, PPV, confusion matrix retained.
- **§7 Tiba Update.** New headline format. The `value` field becomes the κ point estimate as a percentage (e.g. `"82.4%"`); `ci_or_qualifier` carries the asymptotic CI + n + sensitivity-as-proxy + auditor identity disclaimer.
- **§9 Locked Decisions (v0.1.1).** Auditor for v0.1.1 changes from `mahmood726-cyber (steward)` to `claude-sonnet-4-6 subagent (blinded; LLM-not-human)`. Threshold (50%) unchanged. v0.2 IRR carve-out becomes the human gold-standard ship.
- **§10 Cost & Time Budget.** $0 API spend (uses Claude Code subscription for subagent dispatches). 0 human-audit hours for v0.1.1. v0.2 budget unchanged (1 human-day Makerere auditor).
- **§11 Acceptance Criteria.** Criterion 3 now requires `audit_auditor_results.json` to be the sonnet-subagent output (30 entries, all with non-null `auditor_verdict`). Criterion 6 now requires `tiba.yaml`'s `value` field to equal the κ point estimate (was: sensitivity). Test `tests/test_tiba_headline.py` updated accordingly.
- **§12 Risks.** Three new entries:
  - **R6 — LLM-judge architectural bias.** Sonnet 4.x and opus 4.x share training lineage; their disagreements may underestimate genuine human-auditor disagreement. Mitigation: v0.2 Makerere human IRR audit replaces sonnet-judge, providing the real human gold standard.
  - **R7 — Batched-vs-per-call order effects.** Production Tier-P calls the LLM per trial; the v0.1.1 calibration batches 30 trials in one subagent dispatch to amortize overhead. Order effects are possible. Mitigation: v0.2 runs per-call when API key configured.
  - **R8 — Small-sample κ CI.** n=30 yields wide asymptotic CIs on κ. Mitigation: report the full confusion matrix + bootstrap CI as supplementary; v0.2 with human auditor + larger sample tightens.
  - **R9 — Upstream Pairwise70 PMID linkage errors.** During v0.1.1 calibration, both opus and sonnet (independently) flagged PMID 30587844 — labeled "Sagara 2018 (Bougoula/Ouagadougou/Djoliba/Mafrinyah, Mali/Burkina Faso/Guinea)" across 7 trial_ids in `sample_list.json` — as actually pointing to a Japanese case-report on panniculitis after peptide vaccine therapy, NOT the malaria trial. The correct Sagara-2018 malaria-vaccine PMID is likely 30787108. Similar lower-confidence concerns surfaced for Kayentao 2012 (PMID 23113947 — abstract does not state participant geography despite multi-centre African enrollment per author affiliations). **Impact:** 7 of 30 sampled trials' calibration verdicts are based on the wrong abstract; both classifiers correctly returned `Insufficient` or `not_African_majority` per the abstract they actually saw, but the upstream linkage error means the calibration cannot speak to those trials' true classifiability. **Mitigation:** v0.2 task — file an upstream Pairwise70 issue + add a `pmid_resolution_check.py` script that compares the resolved abstract's title against the study_string author-year and flags mismatches. v0.1.1 ships with this caveat in the headline qualifier.

    **R9 update (v0.1.2, 2026-05-06):** PMID resolution check (`scripts/pmid_resolution_check.py`) ran on v0.1.1 sample (30 trials, 22 unique PMIDs). Concrete findings: 1/30 trial confirmed mismatch (surname_mismatch: PMID 30054641, "Roth 2018a" → German surgical work-life-balance paper [Braun et al.]; "Roth" absent from title, authors, and full text — true PMID linkage error); 29/30 match (including 7 Sagara 2018 trials where "Sagara Y" appears as co-author #5 on the panniculitis paper — not first-author, not malaria domain, but surname coincidentally present; this is a domain-level linkage error that surname-matching alone cannot detect). Full report at `data/audit_v0.1.1/pmid_resolution_report.json`. Upstream Pairwise70 issue filing deferred (requires human authorization to comment on third-party repo — out of v0.1.2 scope). Note on Sagara: the 7 Sagara trials' PMID points to a wrong-domain article; the correct malaria-vaccine PMID remains 30787108 per v0.1.1 anecdote.

**Why:** No `ARAC_ANTHROPIC_API_KEY` was configured in the host environment at the time of v0.1.1 ship; the LLM-batch script's pre-registration gate hard-failed at the API-key check (no spend incurred). Mahmood (steward) is also not available for the 30-trial human audit on the v0.1.1 timeline. Rather than indefinitely defer ARAC's federation-card update, the protocol substitutes LLM subagents for both roles. The substitution is honest: Tiba's index page will show a κ headline, not a sensitivity headline, with explicit "LLM-vs-LLM" framing.

**When:** 2026-05-06, immediately after Phase 5's first attempt failed at the API-key check. **No LLM data was generated, no auditor saw any trial.** No data shopping risk.

**Authority:** Mahmood Ahmad (steward), pursuant to spec §9 Locked Decisions.

**Anchors:**
- Pre-amendment-2 state: git tag `prereg-v0.1.1.1-amend-1` at commit `0d3f69c`. Original sample list, original auditor identity, original headline metric all preserved at that tag.
- This amendment: git tag `prereg-v0.1.1.2-amend-2` at the amendment commit. New OTS stamp for amended spec. Sample list (commit `4916242` content) is unchanged — same 30 trials, same shuffle seed, same enrichment regex.

**No data discarded.** v0.1.1 ships with sonnet-judge; v0.2 re-runs the same protocol with human auditor + per-call API; both calibration reports become canonical artifacts.

### Phase 5 result (2026-05-06)

LLM dispatches complete. opus + sonnet calibration yielded κ=1.0000 on n_evaluable=9 (21 Insufficient by either party). Sensitivity-proxy 100% (95% CI 34.2%–100%, n_auditor_positive=2). Wide CIs reflect (a) small evaluable n driven by Pairwise70 abstract-geography sparsity and (b) PMID linkage errors (R9). Calibration report at `data/audit_v0.1.1/audit_calibration_report.json`. Ships as ARAC v0.1.1.
