# ARAC — African Representation Atlas of Cochrane

> The first cross-cutting audit of how the global evidence base — operationalised as the Cochrane Library — represents African populations, African investigators, and African patients.

## Plan 1 status: foundation shipped (v0.0.1, 2026-04-27)

This release is the engine substrate only — it does **not** yet contain Tier-S/A/P classifiers, the RGS instrument, the verification UI, or the public atlas. Those are Plans 2, 3, and 4.

What v0.0.1 ships:

- A Python package (`arac/`) that loads Pairwise70 .rda files and exposes per-trial enumeration with stable `trial_id`s for downstream Tier labelling.
- A subset re-pool engine (`arac.repool.repool_subset`) that computes inverse-variance fixed-effect pooled estimates on arbitrary trial-index subsets — bit-identical to the methodology published in [repro-floor-atlas](https://github.com/mahmood726-cyber/repro-floor-atlas) v0.1.0 (max drift across smoke set: 0.00e+00).
- A pre-flight regression test that asserts Pairwise70 .rda files contain a per-trial identifier column (the `Study` field is universally present; ~81% Author-Year, ~1% NCT, ~19% trial acronyms).
- A gating regression that confirms ARAC reproduces repro-floor-atlas's published 14.3% non-reproducibility headline within ±0.5pp (overall 14.30%, binary 12.89%, continuous 25.03%, giv 26.96% — see `baseline.json`).
- Sentinel pre-push hook integrity checks (0 BLOCK, 0 WARN as of v0.0.1).

## Documents

- **Spec:** `docs/superpowers/specs/2026-04-27-arac-design.md` — full project design, deliverables, governance.
- **Plan 1:** `docs/superpowers/plans/2026-04-27-arac-foundation-and-repool-validation.md` — 10-task TDD plan for this release.
- **Pre-flight artefact:** `docs/preflight-pairwise70-schema.txt` — schema dump of the 595 Pairwise70 .rda files.
- **Numerical baseline:** `baseline.json` — TruthCert-pattern record of the v0.0.1 headline values + commit SHA.

## External dependencies

- **Pairwise70** (R package, ~595 .rda files) at `<drive>:/Projects/Pairwise70/data/` (override via `PAIRWISE70_DIR`).
- **repro-floor-atlas** (Python package) at `<drive>:/Projects/repro-floor-atlas/src/` (override via `REPRO_FLOOR_ATLAS_SRC`).
- **MetaAudit** (transitively, via repro-floor-atlas) at `C:/MetaAudit/`.

## Run the tests

From the repo root:

```bash
pip install -e ".[dev]"
python -m pytest -v
```

Expected: 7 tests pass.

## License

MIT — see `LICENSE`.

## Project lead

Mahmood Ahmad (Makerere University, by partnership). PhD-cohort component leads + slice owners assigned per Plan 4 governance.
