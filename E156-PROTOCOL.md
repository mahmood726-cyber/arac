# E156 Protocol: ARAC: An End-to-End African Representation Atlas of Cochrane with Per-Trial Verification UI

**Project**: arac
**E156 Entry**: #486
**Type**: methods
**Primary Estimand**: Representation Gap Score (RGS) per Cochrane MA × per Tier (S/A/P)
**Data**: Pairwise70 (6,386 reproducible MAs, 108,732 trial rows, 595 review files); AACT 2026-04-12 snapshot; PubMed E-Utilities; ClinicalTrials.gov v2

**Date Created**: 2026-04-27
**Date Last Updated**: 2026-04-28
**Status**: DRAFT (12 plans shipped, 12 annotated tags through v0.9.0)

**Dashboard**: [https://mahmood726-cyber.github.io/arac/](https://mahmood726-cyber.github.io/arac/)
**Code**: [https://github.com/mahmood726-cyber/arac](https://github.com/mahmood726-cyber/arac)

## E156 Abstract (CURRENT BODY, 155 words)

What gap separates Cochrane's African-site, African-led-authorship, and African-majority-participant trials from the global pool, and how does the African-restricted answer differ? We instrument the Pairwise70 corpus (6,386 reproducible meta-analyses, 108,732 trial rows, 595 reviews) plus AACT 2026-04-12, PubMed E-Utilities, and ClinicalTrials.gov v2 metadata. Three-tier classification (site, authorship, participants) drives five Representation Gap Score metrics per meta-analysis per tier: reproduction, precision, sign-flip, heterogeneity, recommendation-change. The engine reproduces the published 14.30% (binary 12.89%, continuous 25.03%, GIV 26.96%) Pairwise70 reproduction-floor headline within ±0.5 percentage points; twelve plans ship across twelve annotated tags. Robustness: 110 unit tests pass, Sentinel pre-push fail-closed integrity checks return zero BLOCKs across master, and word-boundary regex eliminates substring false-positives on alias "car". The atlas substrate is research-paper-shape; cohort verification of pre-classified algorithmic decisions follows the spec's moral architecture, never raw extraction by Makerere students. Pre-1995 NLM lacks structured affiliations, MCID defaults are placeholders, gold-standard inter-rater cohort and full Pairwise70 production atlas extraction remain user-authorized future work.

## Module versions shipped

| Plan | Tag | Date | Description |
|---|---|---|---|
| Plan 1 (Foundation) | v0.0.1 | 2026-04-27 | Engine substrate; reproduces 14.3% repro-floor headline |
| Plan 2A (Resolver) | v0.1.0 | 2026-04-27 | Multi-source resolver (PubMed/CT.gov/acronym) |
| Plan 2B (Tier-S) | v0.2.0 | 2026-04-27 | AACT-backed site classifier |
| Plan 2A.1 (PubMed enrichment) | v0.2.1 | 2026-04-27 | NLM efetch for affiliation backfill |
| Plan 2C (Tier-A) | v0.3.0 | 2026-04-27 | First-or-senior-author classifier |
| Plan 2C.1 (Word-boundary) | v0.3.1 | 2026-04-28 | Eliminates "car"→"cardiovascular" false-positives |
| Plan 2D (Tier-P) | v0.4.0 | 2026-04-28 | LLM-based participant-geography extraction |
| Plan 3A (RGS Engine) | v0.5.0 | 2026-04-28 | First atlas CSV; 3 of 5 metrics |
| Plan 3B (Dashboard) | v0.6.0 | 2026-04-28 | Single-file HTML atlas viewer |
| Plan 3A.1 (Heterogeneity-gap) | v0.7.0 | 2026-04-28 | REML τ² + I²; 4 of 5 metrics |
| Plan 3A.2 (Recommendation-change) | v0.8.0 | 2026-04-28 | MCID equivalence-zone; 5 of 5 metrics |
| Plan 3C (Verification UI) | v0.9.0 | 2026-04-28 | RapidMeta-style auto-confirm UI |

## Reproducibility manifest

- **Test count**: 110 pytest tests (1 SKIP — live LLM API validation, no API key in CI env)
- **Sentinel pre-push checks**: 0 BLOCK across master
- **Numerical regression**: Plan 1's `test_headline_within_tolerance` confirms ARAC reproduces repro-floor-atlas v0.1.0's published 14.30% / 12.89% / 25.03% / 26.96% within ±0.5 percentage points
- **Atlas CSV format**: 24 columns (per-MA × per-Tier; 5 RGS metrics + full/subset pool stats)
- **Verification UI format**: 21-column trial-labels CSV (18 canonical + 3 context fields); single-file HTML with localStorage state + JSON export

## Spec deviations recorded

1. **Plan 1**: Spec asked for REML+HKSJ+PI; shipped fixed-effect inverse-variance pool (matches repro-floor-atlas substrate exactly). REML added in Plan 3A.1 as a side-computation for heterogeneity gap; pooled estimates remain fixed-effect for atlas.csv backwards compatibility.
2. **Plan 2A**: Spec implied `client.messages.parse()` (claude-api skill recommendation); SDK 0.72.0 doesn't expose that API. Adapted to standard forced-tool-use pattern (`messages.create()` with `tool_choice={"type": "tool", "name": ...}`).
3. **Plan 3A**: Mutable default arguments in dataclasses raise `ValueError` in Python 3.13. Used `__post_init__` guard pattern with `field: T = None` + null-check.
4. **Plan 2B**: Spec assumed AACT was either postgres or sqlite; actual local install (snapshot 2026-04-12) is pipe-delimited TSV (`.txt` files). Added a `TSV_DIR` backend with auto-discovery of `YYYY-MM-DD` snapshot subdirectories.

## Known limitations & future work

- **Production atlas extraction not yet run.** The pipeline is shipped; running `python scripts/build_atlas.py --max-mas 6386 --tier-mode sap` requires user authorization (~$30 LLM cost amortized via prompt caching).
- **Per-trial labels CSV not yet built at scale.** The verification UI reads from `outputs/trial_labels.csv`; the batch generator from Pairwise70 + classifiers is deferred to a dedicated user-driven session.
- **Pre-1995 NLM gap.** PubMed records prior to ~1995 lack structured `<AffiliationInfo>`. Plan 2A.1's enrichment helps post-1995 trials only. Cochrane JATS reference-list scrape (Plan 2F) would close the long tail.
- **MCID defaults are placeholders.** `binary=abs(log(0.80))≈0.223`, `continuous=0.2 SMD`, `giv=abs(log(0.85))≈0.163`. Plan 4 preregistration locks per-condition values via per-MA MCID CSV override.
- **Gold-standard IRR cohort not assembled.** Plan 2E requires Mahmood + cohort cohort-assembly first; the verification UI's export-JSON pattern is the dual-confirm mechanism.

---
*Generated by E156 pipeline on 2026-04-28*
