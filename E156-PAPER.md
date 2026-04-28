# ARAC: An End-to-End African Representation Atlas of Cochrane with Per-Trial Verification UI

**E156 Methods Note** · 156-word, 7-sentence single-paragraph body

What gap separates Cochrane's African-site, African-led-authorship, and African-majority-participant trials from the global pool, and how does the African-restricted answer differ? We instrument the Pairwise70 corpus (6,386 reproducible meta-analyses, 108,732 trial rows, 595 reviews) plus AACT 2026-04-12, PubMed E-Utilities, and ClinicalTrials.gov v2 metadata. Three-tier classification (site, authorship, participants) drives five Representation Gap Score metrics per meta-analysis per tier: reproduction, precision, sign-flip, heterogeneity, recommendation-change. The engine reproduces the published 14.30% (binary 12.89%, continuous 25.03%, GIV 26.96%) Pairwise70 reproduction-floor headline within ±0.5 percentage points; twelve plans ship across twelve annotated tags. Robustness: 110 unit tests pass, Sentinel pre-push fail-closed integrity checks return zero BLOCKs across master, and word-boundary regex eliminates substring false-positives on alias "car". The atlas substrate is research-paper-shape; cohort verification of pre-classified algorithmic decisions follows the spec's moral architecture, never raw extraction by Makerere students. Pre-1995 NLM lacks structured affiliations, MCID defaults are placeholders, gold-standard inter-rater cohort and full Pairwise70 production atlas extraction remain user-authorized future work.

---

**Word count:** 155 (within ≤156 contract)
**Sentences:** 7 (S1=Question, S2=Dataset, S3=Method, S4=Result+number, S5=Robustness, S6=Interpretation, S7=Boundary)
**Primary estimand:** Representation Gap Score (RGS) per Cochrane MA × per Tier (S/A/P)
**Code:** https://github.com/mahmood726-cyber/arac
**Dashboard:** https://mahmood726-cyber.github.io/arac/
**Spec:** [docs/superpowers/specs/2026-04-27-arac-design.md](docs/superpowers/specs/2026-04-27-arac-design.md)
**License:** Manuscript CC-BY-4.0; Code MIT
