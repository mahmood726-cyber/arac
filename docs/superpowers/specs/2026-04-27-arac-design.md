# ARAC — The African Representation Atlas of Cochrane

**Status:** Design (brainstorming output, pre-implementation-plan)
**Date:** 2026-04-27
**Senior author / project lead:** Mahmood Ahmad (Makerere University, by partnership)
**Cohort:** ~190 PhD public-health students at Makerere University (existing weekly course)

---

## 1. Project identity & headline ambition

**Working title:** **ARAC — The African Representation Atlas of Cochrane**

### One-paragraph pitch

ARAC is the first cross-cutting audit of how the global evidence base — operationalised as the Cochrane Library — represents African populations, African investigators, and African patients. Every reproducible Cochrane meta-analysis (MA) in the **Pairwise70 base** (a prior Makerere/Mahmood Ahmad project: ~6,386 reproducible Cochrane MAs with study-level rows already extracted) is re-pooled using African-data subsets at three tiers (site, authorship, participants), and the gap is quantified along five orthogonal dimensions. The atlas yields one umbrella headline number, one disease-specific deep-dive (TB + HIV + Malaria), a methods paper that defines the **Representation Gap Score (RGS)** as a citable instrument, ~150 student-led E156 micro-papers (one per slice owner), and ~20 Cochrane Review Group cluster papers (led by mid-cohort PhDs).

### Top-line headline format

> *"Of N Cochrane meta-analyses examined, X% are 'African-invisible' (no African-led trials at all). Of the remainder, Y% would yield a clinically different recommendation if restricted to African-led data. The cascade from African-site → African-led → African-participant-majority collapses by ~Z-fold."*

### Deliverable bundle

1. **Umbrella paper** — *Lancet Global Health* / *BMJ Global Health* tier
2. **Companion deep-dive** — Big Three (TB + HIV + Malaria) — *PLOS Global Public Health* or *Lancet Infectious Diseases*
3. **Methods paper** — defines the RGS instrument — *Research Synthesis Methods* or *BMJ Open*
4. **Public atlas** — `arac.makerere.ac.ug` (or GitHub Pages mirror) — interactive, searchable, downloadable
5. **~150 student E156 micro-papers + ~20 CRG cluster papers** — each slice owner produces an E156; cluster leads produce mid-tier journal papers
6. **Optional B3 sequel** — Living African Evidence Platform on whichever disease the atlas reveals as most equity-damaged

### Ownership posture

- **Makerere-led.** Mahmood Ahmad as senior author on umbrella + methods.
- **Students as first authors** on their E156 slices and cluster-level mid-papers.
- **Optional Cochrane co-authorship invited *after* preregistration is locked** (not before — preserves audit independence).

---

## 2. Architecture & component structure

```
ARAC/
├── data/
│   ├── cochrane_index/        # all Cochrane Reviews (CRG, year, condition, MA count)
│   ├── pairwise70_link/       # foreign-key bridge to existing Pairwise70 dataset
│   ├── extractions/           # per-trial Tier-S/A/P classifications
│   └── pools/                 # per-MA African-only re-pool results
├── engine/
│   ├── classifier/            # Tier-S/A/P assignment (rules + LLM-assisted)
│   ├── repool/                # re-pools using repro-floor-atlas methodology
│   ├── rgs/                   # five gap metrics
│   └── invisibility/          # counts MAs with insufficient African data per tier
├── atlas/                     # public website (single-file HTML pattern)
│   ├── index.html             # umbrella view + cascade figure
│   ├── reviews/               # per-CRG drill-downs
│   └── slice/<student-slug>/  # each student's slice gets a permanent URL
├── papers/
│   ├── umbrella/              # Lancet GH manuscript
│   ├── companion-bigthree/    # TB+HIV+Malaria
│   ├── methods-rgs/           # RGS instrument definition
│   └── e156/                  # 190 micro-papers, one per student slice
├── governance/
│   ├── PREREGISTRATION.md     # OSF + Zenodo locked before extraction begins
│   ├── SOP_classification.md  # tier rules; ambiguity adjudication
│   ├── SOP_repool.md          # exact stats pipeline (DL→REML+HKSJ+PI)
│   └── COI.md                 # explicit declaration of editorial-board overlaps
└── tests/                     # extends Sentinel + Overmind harness
```

### Five components, five owners

| Component | Owner role | What they ship |
|---|---|---|
| **Classifier engine** | 1 senior PhD | Reproducible Tier-S/A/P labeling pipeline; IRR ≥ 0.85 |
| **Re-pool engine** | 1 senior PhD (stats lead) | Reuses repro-floor-atlas methodology; emits per-MA pool |
| **RGS computation** | 1 senior PhD | Five gap metrics + invisibility counter; methods-paper first author |
| **Atlas / dashboard** | 1 senior PhD (web/dev) | Single-file HTML atlas; per-slice permalinks |
| **Editorial coordination** | 1 senior PhD | Manages 190 student slices; ensures SOP compliance; co-author of umbrella |

### Reuse from existing portfolio

- **Pairwise70** — base MA index (study-level rows already extracted); no need to re-scrape Cochrane.
- **repro-floor-atlas methodology** — re-pool engine + |Δ|>0.005 threshold.
- **ImpossibleMA primitive** — handles k=1 / missing-SE African subsets gracefully.
- **Sentinel** — pre-push integrity checks on every student commit.
- **Overmind** — nightly verification of the atlas as a portfolio repo.
- **E156 protocol** — student micro-paper format (already taught to cohort).
- **RapidMeta v11.8 auto-confirm pattern** — verification UI substrate (per `feedback_rapidmeta_screen_review.md`).

### Critical guardrail — dual confirmation, not dual extraction

Every classification (Tier-S/A/P) is **algorithmically pre-populated** and then **dual-confirmed** by two independent student reviewers. Disagreements escalate to an adjudication panel (3 senior PhDs + Mahmood). Inter-rater reliability is reported per tier in the methods paper. (See §6 for the full workforce model.)

---

## 3. Data flow

### Pipeline

```
[Pairwise70 base — ALREADY HAS STUDY-LEVEL ROWS]   [Cochrane Library (auxiliary metadata)]
         │                                                    │
         └──────────────────────────┬─────────────────────────┘
                                    ▼
        [1. MA universe — pre-satisfied by Pairwise70 (~6,386 MAs, ~60-65k trial rows)]
                                    │
                                    ▼
        [2. Algorithmic pre-classification — DONE BY ENGINE, NOT STUDENTS]
        ┌─ Tier-S: ≥1 site in African country (CT.gov + AACT + Cochrane appendix)
        ├─ Tier-A: first OR senior author at African institution (PubMed + ORCID + ROR)
        └─ Tier-P: ≥50% African participants (LLM-extracted from trial reports)
        Each label gets a confidence score.
                                    │
                                    ▼
        [3. Cohort verification UI — RapidMeta-style]
        - One MA at a time, all fields pre-filled
        - Student: confirm (1 click) or flag for adjudication
        - Dual-confirm before row locks
        - IRR computed per tier; disagreements → adjudication panel
                                    │
                                    ▼
        [4. African-subset pool computation]
        For each MA × Tier:
        ┌─ if k_african ≥ 3 → REML+HKSJ+PI (per advanced-stats.md)
        ├─ if k_african = 1-2 → ImpossibleMA primitive
        └─ if k_african = 0  → flag as INVISIBLE for that tier
                                    │
                                    ▼
        [5. RGS computation per MA × Tier]
        ┌─ Reproduction gap (|Δ|>0.005, published threshold)
        ├─ Precision gap (CI width ratio)
        ├─ Heterogeneity gap (τ² delta, k-adjusted)
        ├─ Sign-flip indicator (does African pool cross null?)
        └─ Recommendation-change indicator (crosses preregistered MCID?)
                                    │
                                    ▼
        [6. Atlas aggregation]
        ┌─ Cascade figure (Tier-S → Tier-A → Tier-P collapse)
        ├─ Per-CRG breakdown
        ├─ Per-condition breakdown (companion paper)
        └─ Invisibility map
                                    │
                                    ▼
        [7. Outputs: atlas + 4 papers + 190 E156s]
```

### Critical data-handling rules

1. **No silent imputation.** Every missing field (especially Tier-P participant geography) is reported as "not extractable" rather than imputed. Imputation rates per tier become a top-line methods-paper number.
2. **MCID per condition is preregistered.** Recommendation-change cannot be defined post-hoc. Each disease cluster gets MCIDs locked in `governance/PREREGISTRATION.md` before extraction begins. Existing published MCIDs preferred; otherwise the cluster lead documents the most-cited threshold.
3. **Repool engine verified against existing artifacts.** The engine must reproduce repro-floor-atlas's headline 14.3% non-reproducible figure on the original Pairwise70 set before it runs on African subsets. Regression test, not optional.
4. **Every African-subset pool is publicly auditable.** Per-MA result rows include trial IDs, computed effect, CI, k, τ², and input data hash. Anyone can re-run a single row.
5. **Identifier discipline** (per `lessons.md`). NCT IDs, PMIDs, DOIs, ROR IDs treated as typed fields, validated against source registries before classification commits. No identifier substitution to make a test pass.
6. **Encoding & path discipline** (per `rules.md`). UTF-8 throughout; no hardcoded `C:\Users\...` paths in shipped atlas/papers; lockfiles for any JS components.

### Data sources

- **Cochrane Library** — institutional access (Makerere has Cochrane Wiley access)
- **CT.gov** — existing MCP
- **PubMed** — existing MCP
- **ROR** (Research Organization Registry) — open API for institution affiliation
- **AACT** — D: drive snapshot for high-throughput trial-site queries

---

## 4. Authorship economics

### Atlas scope (with Pairwise70 as base)

- ~6,386 MAs in Pairwise70
- Average ~10 trials per MA → **~60,000–65,000 trial × MA classification rows**
- Each row needs Tier-S, Tier-A, Tier-P labels (3 fields)

### Workforce arithmetic (under verification model — see §6)

- **Per student per MA: ≤5 minutes** (one-screen verification, one-click confirm)
- **150 students × ~150 MAs each over one academic term = atlas complete**
- Total per-student time: ~12 hours over a term (sustainable alongside coursework)

### Authorship cascade — five tiers

| Tier | Who | What they ship | How many |
|---|---|---|---|
| **Senior author** | Mahmood Ahmad | Umbrella paper, methods paper | 1 |
| **First-author umbrella** | 1 senior PhD | Drives the umbrella manuscript | 1 |
| **Component leads** | 5 senior PhDs | Lead engine components — each becomes first author of methods/sub-paper | 5 |
| **Cluster leads** | ~15–25 mid-cohort PhDs | Lead Cochrane Review Group clusters — first author of CRG-level paper, co-author on umbrella | 15–25 |
| **Slice owners** | ~150 PhDs | Own a Pairwise70 slice (~150 MAs each), publish E156 micro-paper on slice findings | 150 |

### Total publication footprint

- 1 umbrella paper (*Lancet GH* tier)
- 1 companion paper (TB + HIV + Malaria)
- 1 methods paper (RGS instrument)
- ~20 CRG cluster papers
- ~150 student E156 micro-papers (Synthēsis or equivalent)

### Per-student deliverable contract

1. Verify ~150 MAs' trial rows (dual-confirmed via UI; ~12 hours over a term)
2. Compile their slice's RGS results (engine generates; student reviews)
3. Write one E156 micro-paper on the most striking finding in their slice
4. Co-author credit on the CRG cluster paper they belong to
5. Acknowledged contributor on the umbrella + methods papers (or co-author if ≥80% slice verified)

### Why this is impressive to PhD students specifically

- **Real first-author papers** — PhD CVs in public health are graded on first-author count.
- **Permanent atlas slice URL** — `arac.makerere.ac.ug/slice/<their-name>` — citable on grant applications forever.
- **Co-authorship on a paper that will get cited everywhere.**
- **Participation in shaping a citable instrument (RGS)** — methodological contribution PhD examiners reward.
- **Real ethical stakes** — documenting a structural inequity in their own region's evidence base.

### Authorship governance (non-negotiable)

- **ICMJE compliance.** Every co-author meets all four ICMJE criteria; otherwise → contributor acknowledgment.
- **CRediT taxonomy** declared per author per paper.
- Per `feedback_e156_authorship.md`: middle-author-only on E156 papers where applicable.
- **Authorship order locked at preregistration.** No post-hoc reshuffling.

---

## 5. Timeline, preregistration & governance

### Timeline (one Makerere academic year, with explicit gates)

```
Month 0  ── Pre-launch (Mahmood + 5 component leads only) ─────────────────
            • Lock preregistration (OSF + Zenodo + Internet Archive + OpenTimestamps)
            • Build classifier engine + repool engine + atlas scaffold
            • Algorithmic pre-classification of full Pairwise70 trial set
            • Run regression test: repool engine reproduces repro-floor-atlas's 14.3% headline ✓
            • Pre-register all MCIDs by disease cluster (LOCKED)
            • Pilot verification on 50 MAs across 5 disease clusters
            • Compute pilot IRR per tier; iterate UI/SOPs until IRR ≥ 0.85

GATE 0    ── Preregistration timestamped + pilot IRR met → only then do
              students touch live verification UI.

Month 1-2 ── Full cohort onboarded ────────────────────────────────────────
            • SOP training (1 hour, not 1 week — verification UI is intuitive)
            • Student slices assigned (~150 students × ~150 MAs)
            • Dual-confirm verification begins; rolling adjudication panel

Month 3-4 ── Atlas computation & validation ──────────────────────────────
            • Re-pool engine runs on completed verifications (rolling)
            • RGS computed per MA × tier
            • Atlas dashboard ships v0.1 (internal review only)
            • Cluster leads draft CRG cluster papers

Month 5   ── Public atlas v1.0 + manuscript drafting ─────────────────────
            • Atlas goes public (with DOI via Zenodo)
            • Umbrella, companion, methods papers drafted in parallel

Month 6   ── Internal review + Cochrane pre-engagement ───────────────────
            • Independent statistical review (external, paid)
            • Pre-submission outreach to Cochrane editorial (courtesy)
            • Student E156 micro-papers submitted to Synthēsis (rolling)

Month 7-8 ── Submissions ─────────────────────────────────────────────────
            • Umbrella → Lancet GH (or BMJ GH if rejected)
            • Methods → Research Synthesis Methods
            • Companion → Lancet Infectious Diseases or PLOS GPH
            • CRG cluster papers → BMC Med Res Methodol / discipline-specific
```

### Preregistration content (locked at Month 0)

Timestamped via Zenodo + OSF + OpenTimestamps + Internet Archive.

1. Hypotheses — directional predictions per gap dimension
2. Tier definitions — exact rules for S/A/P, including edge cases
3. MCID list — per disease cluster, with citation source
4. Statistical pipeline — REML+HKSJ+PI for re-pools
5. Threshold — |Δ|>0.005 (locked from prior published work)
6. Invisibility definition — k_african < 3 → INVISIBLE for that tier
7. Authorship list — order, CRediT contributions
8. Stopping rules
9. Conflicts of interest — including any student affiliations with trial sponsors
10. Funding sources

### Governance bodies

| Body | Composition | Role |
|---|---|---|
| **Steering committee** | Mahmood + 5 component leads | Weekly cadence; SOP changes require unanimity |
| **Adjudication panel** | 3 senior PhDs (rotating) | Resolves classification disputes; logs all rulings publicly |
| **External methods reviewer** | 1 Cochrane methodologist (paid; arms-length) | Reviews preregistration BEFORE lock; reviews methods paper draft |
| **External statistical reviewer** | 1 biostatistician (Wits / KEMRI / not Cochrane) | Audits re-pool engine + RGS computation |
| **Student ombudsperson** | 1 senior PhD elected by cohort | Authorship disputes; workload concerns |

### Ethics & political guardrails

- **No human-subjects ethics board needed** — research-on-published-research. Confirm with Makerere IRB anyway (≤2 weeks).
- **Cochrane pre-engagement is *informational*.** Sent at Month 6, after preregistration is timestamped. Not approval-seeking.
- Per `feedback_e156_authorship.md`: middle-author-only on Synthēsis-bound E156 micro-papers.
- **Pre-empt "you cherry-picked Cochrane"** — preregister explicit use of complete Pairwise70 reproducible-MA set. Exclusions reported, not silently dropped.
- **Pre-empt "you mis-classified my trial"** — public dispute portal in atlas. Trial authors challenge post-publication; rulings versioned.

---

## 6. Risks, guardrails & the verify-don't-extract workforce model

### Workforce pivot

The Makerere cohort **verifies pre-classified data**, they do not perform raw extraction. Per `feedback_makerere_student_workload.md`:

```
[MAHMOOD + 5 component leads]              [190 PhD COHORT]
────────────────────────────                ──────────────────────
1. Algorithmic pre-classification:    →    2. Verification UI (RapidMeta-style):
   • Tier-S via CT.gov + Pairwise70           • One MA at a time
   • Tier-A via PubMed + ROR + ORCID          • All fields pre-populated
   • Tier-P via LLM extraction from           • Full source context inline
     trial reports (flagged when missing)     • Buttons: [Confirm] / [Flag]
   • LLM produces confidence per claim        • Per-MA target: ≤5 minutes
                                              • Per-student total: ~12 hours / term
```

**Moral architecture:** Making African students re-key extraction data on a project *about African data labour inequality* would be a structural contradiction. The cohort's contribution is **epistemic authority** (their judgment on classifications stands), not throughput. That justifies first-author E156s and umbrella co-authorship under ICMJE.

### Verification UI (extends RapidMeta v11.8 auto-confirm pattern)

- Single-file HTML, mobile-friendly
- Shows: trial title, NCT ID, PMID link, abstract snippet, classifier-assigned Tier-S/A/P + confidence
- Default: pre-confirmed if all three classifier confidences > 0.9
- Action: scan, confirm (one click), or flag with reason
- Dual-confirm: 2 students must confirm before a row locks
- Disagreements + flags → adjudication panel queue

### Risks & mitigations

| # | Risk | Mitigation |
|---|---|---|
| 1 | Classifier bias against African affiliations | Audit on stratified random sample (20 MAs × 5 disease clusters) before cohort onboarding. Per-tier IRR vs human gold standard ≥ 0.85 required. |
| 2 | Cochrane political response | Pre-engagement at Month 6 (informational). Frame as partnership on a problem Cochrane already publicly acknowledges. |
| 3 | "You mis-classified my trial" attacks | Public dispute portal. Versioned rulings. Re-classification updates atlas and credits correction. |
| 4 | Student burnout / drop-off | 5-min/MA ceiling; no student on critical path. Drop = slice rolls back to pool. |
| 5 | MCID disputes | Preregistered Month 0, locked. Cite prereg + source paper. No post-hoc changes. |
| 6 | Re-pool engine bugs | Regression test against repro-floor-atlas's 14.3% headline before any African-subset pool runs. (Per integration-tests-first rule.) |
| 7 | Encoding / path / lockfile drift | Sentinel pre-push hook installed in repo from Day 0. P0 blockers stop pushes. |
| 8 | E156 papers fail Synthēsis 7-sentence contract | E156 validator runs in CI on every micro-paper PR. Cluster leads review. Workbook protection: never edit a student's "YOUR REWRITE". |
| 9 | "You used Pairwise70 which itself has classification gaps" | Acknowledge upfront. Sensitivity: re-classify stratified sample directly from Cochrane source; report concordance. |
| 10 | Identifier corruption (per negated-counts incident) | NCT/PMID/DOI typed fields. Identifier change requires source-evidence note. Sentinel rule enforces. |
| 11 | Timeline slip past 8 months | Hard gate Month 5 — if atlas v1.0 isn't shipping, ship companion (Big Three) standalone. Companion alone is publishable. |
| 12 | Memory drift / status promotion errors | `reconcile_counts.py` runs before any "ARAC is ready" claim. Status promotion requires fresh tests + path verification. |

### Stopping rules (preregistered)

- Pilot IRR < 0.70 on any tier after 3 SOP iterations → halt, redesign classifier
- Re-pool engine fails to reproduce repro-floor-atlas headline (within ±0.5pp) → halt, debug
- > 20% of MAs INVISIBLE at all three tiers → atlas finding becomes "Africa is invisible," reframe paper accordingly (not a failure — a stronger headline)

---

## Implementation-plan scope

**The first implementation plan covers Month 0 only** (engine + atlas scaffold + preregistration + pilot). Months 1–8 are deferred to follow-up plans because:
- Month 0 outputs are the gating prerequisites for everything else
- Pilot IRR results may force SOP/UI revisions that change downstream plans
- Trying to plan all 8 months as one document produces a useless meta-plan

Month 0 plan should produce: working classifier engine (Tier-S/A/P), working repool engine (passing repro-floor-atlas regression test), working RGS computation, atlas v0.1 scaffold, locked preregistration document, working verification UI, and a 50-MA pilot complete with measured IRR per tier.

## Open items for the implementation plan

These are decisions deferred to the writing-plans phase:

- Specific external methods reviewer (which Cochrane methodologist?)
- Specific external statistical reviewer (Wits vs KEMRI vs other?)
- LLM model choice for Tier-P extraction (Claude Opus / GPT-5 / open-weights?)
- Disease cluster boundaries (how many clusters? which CRG splits?)
- E156 micro-paper template specialisation for ARAC slices
- Atlas hosting (`arac.makerere.ac.ug` vs GitHub Pages mirror — depends on Makerere IT)
- Funding source for external reviewers (currently zero — needs identifying)

---

## Provenance

Brainstormed 2026-04-27. Five upstream questions answered:

- Q1 (shape): B — shared African evidence infrastructure
- Q2 (sub-flavor): B1 atlas primary, B3 living-platform optional sequel
- Q3 (scope anchor): E cross-cutting Cochrane atlas primary, A Big Three companion
- Q4 (African-data definition): B tiered (Tier-S / Tier-A / Tier-P)
- Q5 (gap metric): C multi-dimensional RGS, with B reproduction-floor as primary headline + invisibility metric

User course-correct mid-design (Section 6): **verify, don't extract** — saved as `feedback_makerere_student_workload.md`.
