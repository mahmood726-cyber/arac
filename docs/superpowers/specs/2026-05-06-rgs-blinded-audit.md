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
- **Stratum 1 (Enriched):** MAs with at least one trial whose study string contains an African country keyword from ARAC's `african_countries.py`: `Uganda`, `Kenya`, `South Africa`, `Nigeria`, `Tanzania`, `Ghana`, `Malawi`, `Ethiopia`, `Zimbabwe`, `Zambia`, `Mozambique`, `Rwanda`, `Cameroon`, `Senegal`, `Mali`, `Gambia`, `Burkina Faso`, `Botswana`, `Côte d'Ivoire`, `Democratic Republic`, `Sudan`.
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

---

## 4. LLM Comparator

**Entry point.** `scripts/tier_p_audit_batch.py` (to be written) accepts the JSON sample list and emits `data/audit_v0.1.1/audit_llm_outputs.json` with one record per trial: `trial_id`, `pmid`, `tier_p` (`african_majority` / `not_african_majority` / `insufficient_data`), `confidence`, `african_pct`, `countries_mentioned`, `evidence_source`. Calls the same `TierPClassifier.classify()` used in production.

**Model.** `claude-opus-4-7` (default; `ARAC_TIER_P_MODEL` env override). Same model that runs in production — calibration must transfer.

**Cache.** `outputs/cache/resolve/tier_p_llm/` populates on first run; subsequent re-runs are free.

---

## 5. Comparison Statistics

**Primary: sensitivity** = TP / (TP + FN), where TP = LLM `african_majority` AND auditor `African_majority`; FN = LLM `not_african_majority` AND auditor `African_majority`. Trials marked `Insufficient` by either party are excluded.

**Secondary:**
- Specificity = TN / (TN + FP)
- Positive predictive value = TP / (TP + FP)
- Cohen's κ = (P_observed − P_chance) / (1 − P_chance) on the 2×2

**CI method.** Wilson score 95% CI:
```
n = TP + FN  (for sensitivity)
p = TP / n
CI = (p + z²/2n ± z·sqrt(p(1-p)/n + z²/4n²)) / (1 + z²/n)
z = 1.96
```

**Headline for `tiba.yaml`.** Sensitivity (point estimate, Wilson 95% CI), e.g. `"83.3% (95% CI: 58.6–96.4%); n=30, 12/30 auditor-positive"`. If sensitivity cannot be computed (zero auditor positives despite enriched stratum), protocol fails — see §12 Risk 1.

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
  label: "Tier-P blinded-audit sensitivity: LLM african-majority classifier vs human auditor, n=30 Pairwise70 trials"
  value: "<XX.X%>"
  ci_or_qualifier: "Wilson 95% CI [<A.A%>–<B.B%>]; TP=<M>, FN=<N>, FP=<P>, TN=<Q>; <M+N> auditor-positive trials; 15 enriched + 15 random stratum; auditor: mahmood726-cyber (v0.1.1; Makerere IRR planned for v0.2); pre-reg OTS <hash prefix>"
  source: "arac v0.1.1 (2026-05-XX)"
last_verified: "2026-05-XX"
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

1. **Auditor:** mahmood726-cyber (steward). Bias risk acknowledged; mitigated by required `evidence_quote` field.
2. **IRR:** v0.2 — Makerere PhD-cohort second blinded auditor on the same 30 trials; Cohen's κ between human raters.
3. **Threshold:** 50% African-majority (matches production code). Locked.

---

## 10. Cost & Time Budget

- **LLM cost:** 30 trials × ~$0.01–$0.04 = **$0.30–$1.20** total. No prompt-caching benefit at this scale.
- **Auditor time:** 30 trials × 5–10 min = **2.5–5 hours** total. Recommended: 3 sessions × 10 trials over 1–2 weeks.
- **Infrastructure:** zero new infrastructure. OTS is a free CLI call. UI is a static HTML file.
- **Total:** under $2 in API cost, one human-day of effort, 2–3 weeks elapsed.

---

## 11. Acceptance Criteria for ARAC v0.1.1

A v0.1.1 tag is cut when ALL hold:
1. `data/audit_v0.1.1/sample_list.json` exists with exactly 30 entries (each with confirmed PMID).
2. `sample_list.json.ots` and `audit_instrument.html.ots` and this spec's `.ots` are committed (verifiable via `ots verify`).
3. `audit_auditor_results.json` has exactly 30 entries, all with non-null `auditor_verdict`.
4. `audit_llm_outputs.json` has exactly 30 entries, all with non-null `tier_p`.
5. `audit_calibration_report.json` exists with: `sensitivity`, `specificity`, `ppv`, `kappa`, `ci_lower`, `ci_upper`, `n_auditor_positive`, `n_insufficient_excluded`, `confusion_matrix`.
6. `tiba.yaml` `value` field equals the sensitivity point estimate from `audit_calibration_report.json` (verified by `tests/test_tiba_headline.py`).
7. All existing 110 pytest tests pass (no regressions).
8. `E156-PROTOCOL.md` updated: "Plan 2D (Tier-P) calibration audit complete" row added.

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
