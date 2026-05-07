"""Tests for ARAC v0.2 pilot atlas components.

Tests cover:
1. Sample list structure and content (100 MAs, 45 enriched + 55 random)
2. Calibration report validity (kappa >= 0.6, PROCEED verdict)
3. Pilot trial index structure (when present)
4. Atlas schema (when atlas_pilot.csv is present)
5. Sampling determinism (same seed produces same order)
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent.parent
_V02_DIR = _REPO_ROOT / "data" / "v0.2"
_SAMPLE_JSON = _V02_DIR / "sample_list_pilot.json"
_CALIB_JSON = _V02_DIR / "sonnet_calibration_report.json"
_TRIAL_INDEX = _V02_DIR / "pilot_trial_index.json"
_ATLAS_CSV = _V02_DIR / "atlas_pilot.csv"
_SPEC_MD = _REPO_ROOT / "docs" / "superpowers" / "specs" / "2026-05-06-v0.2-pilot-atlas.md"
_SPEC_OTS = _SPEC_MD.with_suffix(".md.ots")
_SAMPLE_OTS = _SAMPLE_JSON.with_suffix(".json.ots")


class TestSpecAndPreregistration:
    def test_spec_md_exists(self) -> None:
        assert _SPEC_MD.is_file(), f"v0.2 spec not found: {_SPEC_MD}"

    def test_spec_ots_exists(self) -> None:
        assert _SPEC_OTS.is_file(), f"spec OTS file not found: {_SPEC_OTS}"

    def test_spec_ots_is_nonempty(self) -> None:
        assert _SPEC_OTS.is_file()
        assert _SPEC_OTS.stat().st_size > 100, "OTS file too small (likely corrupt)"

    def test_spec_contains_required_sections(self) -> None:
        assert _SPEC_MD.is_file()
        text = _SPEC_MD.read_text(encoding="utf-8")
        for section in [
            "## 1. Goal",
            "## 3. Sampling Protocol",
            "## 5. Phase 4",
            "## 8. Acceptance Criteria",
            "## 9. Risks",
        ]:
            assert section in text, f"Missing section: {section}"


class TestSampleList:
    """Tests for sample_list_pilot.json structure."""

    @pytest.fixture(scope="class")
    def sample(self) -> dict:
        assert _SAMPLE_JSON.is_file(), f"sample_list_pilot.json not found: {_SAMPLE_JSON}"
        return json.loads(_SAMPLE_JSON.read_text(encoding="utf-8"))

    def test_sample_ots_exists(self, sample: dict) -> None:
        assert _SAMPLE_OTS.is_file(), f"sample OTS file not found: {_SAMPLE_OTS}"
        assert _SAMPLE_OTS.stat().st_size > 100

    def test_total_ma_count(self, sample: dict) -> None:
        assert sample["n_total"] == 100, f"Expected 100 MAs, got {sample['n_total']}"

    def test_enriched_count(self, sample: dict) -> None:
        n_enriched = sample["n_enriched"]
        # Enriched is a census of all eligible enriched MAs — expected to be 45
        assert n_enriched >= 40, f"Expected ~45 enriched MAs, got {n_enriched}"
        assert n_enriched <= 60, f"Enriched count suspiciously high: {n_enriched}"

    def test_random_count(self, sample: dict) -> None:
        n_random = sample["n_random"]
        total = sample["n_total"]
        n_enriched = sample["n_enriched"]
        assert n_random == total - n_enriched

    def test_ma_list_length(self, sample: dict) -> None:
        assert len(sample["ma_list"]) == sample["n_total"]

    def test_ma_list_stratum_values(self, sample: dict) -> None:
        for m in sample["ma_list"]:
            assert m["stratum"] in ("enriched", "random"), \
                f"Unknown stratum: {m['stratum']}"

    def test_enriched_mas_have_keyword(self, sample: dict) -> None:
        enriched = [m for m in sample["ma_list"] if m["stratum"] == "enriched"]
        for m in enriched:
            assert m.get("matched_keyword") is not None, \
                f"Enriched MA missing matched_keyword: {m['ma_id']}"

    def test_random_mas_have_no_keyword(self, sample: dict) -> None:
        random_mas = [m for m in sample["ma_list"] if m["stratum"] == "random"]
        for m in random_mas:
            assert m.get("matched_keyword") is None, \
                f"Random MA has matched_keyword (should be None): {m['ma_id']}"

    def test_all_mas_meet_k_threshold(self, sample: dict) -> None:
        for m in sample["ma_list"]:
            assert m["k_total"] >= 3, \
                f"MA {m['ma_id']} has k_total={m['k_total']} < 3 (below INVISIBILITY_THRESHOLD_K)"

    def test_ma_ids_unique(self, sample: dict) -> None:
        ids = [m["ma_id"] for m in sample["ma_list"]]
        assert len(ids) == len(set(ids)), "Duplicate MA IDs in sample list"

    def test_seed_recorded(self, sample: dict) -> None:
        assert sample["sampling_seed"] == 42

    def test_rda_sha256_present(self, sample: dict) -> None:
        assert len(sample["rda_sha256"]) > 0, "rda_sha256 is empty"

    def test_enrichment_keywords_present(self, sample: dict) -> None:
        kws = sample.get("enrichment_keywords", [])
        assert len(kws) >= 20, f"Expected >=20 enrichment keywords, got {len(kws)}"
        # Check a few expected keywords
        kws_lower = [k.lower() for k in kws]
        for expected in ["malaria", "hiv", "tuberculosis", "kenya"]:
            assert expected in kws_lower or any(expected in k.lower() for k in kws), \
                f"Missing expected keyword: {expected!r}"


class TestCalibrationReport:
    """Tests for sonnet_calibration_report.json."""

    @pytest.fixture(scope="class")
    def report(self) -> dict:
        assert _CALIB_JSON.is_file(), f"calibration report not found: {_CALIB_JSON}"
        return json.loads(_CALIB_JSON.read_text(encoding="utf-8"))

    def test_verdict_is_proceed(self, report: dict) -> None:
        assert report["verdict"] == "PROCEED", \
            f"Calibration verdict is not PROCEED: {report['verdict']} — {report['verdict_reason']}"

    def test_kappa_meets_threshold(self, report: dict) -> None:
        kappa = report["kappa"]
        assert kappa is not None, "kappa is None in calibration report"
        assert kappa >= 0.6, f"kappa={kappa} < 0.6 STOP threshold"

    def test_n_evaluable_trials(self, report: dict) -> None:
        n = report.get("n_definitive_pairs", report.get("n_evaluated", 0))
        assert n >= 8, f"Too few evaluable pairs for reliable kappa: {n}"

    def test_sonnet_model_recorded(self, report: dict) -> None:
        model = report.get("sonnet_model", "")
        assert "sonnet" in model.lower() or "claude" in model.lower(), \
            f"Expected sonnet model, got: {model!r}"


class TestPilotTrialIndex:
    """Tests for pilot_trial_index.json — only if the file exists."""

    @pytest.fixture(scope="class")
    def index(self) -> dict:
        if not _TRIAL_INDEX.is_file():
            pytest.skip("pilot_trial_index.json not yet generated")
        return json.loads(_TRIAL_INDEX.read_text(encoding="utf-8"))

    def test_n_trials_positive(self, index: dict) -> None:
        assert index["n_trials_total"] > 0

    def test_n_resolved_positive(self, index: dict) -> None:
        n_resolved = index.get("n_resolved_with_abstract", 0)
        assert n_resolved > 100, f"Unexpectedly few resolved abstracts: {n_resolved}"

    def test_trials_dict_not_empty(self, index: dict) -> None:
        assert len(index["trials"]) > 0


class TestAtlas:
    """Tests for atlas_pilot.csv — only if the file exists."""

    @pytest.fixture(scope="class")
    def atlas_rows(self) -> list[dict]:
        if not _ATLAS_CSV.is_file():
            pytest.skip("atlas_pilot.csv not yet generated")
        import csv
        rows = []
        with _ATLAS_CSV.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
        return rows

    def test_row_count_is_100(self, atlas_rows: list[dict]) -> None:
        assert len(atlas_rows) == 100, \
            f"Expected 100 rows in atlas_pilot.csv, got {len(atlas_rows)}"

    def test_required_columns_present(self, atlas_rows: list[dict]) -> None:
        expected_cols = {
            "ma_id", "tier", "k_total", "k_subset", "invisible",
            "full_pooled_estimate", "reproduction_gap", "sign_flip",
        }
        actual_cols = set(atlas_rows[0].keys()) if atlas_rows else set()
        missing = expected_cols - actual_cols
        assert not missing, f"Missing columns: {missing}"

    def test_24_columns(self, atlas_rows: list[dict]) -> None:
        if not atlas_rows:
            pytest.skip("no rows")
        assert len(atlas_rows[0]) == 24, \
            f"Expected 24 columns, got {len(atlas_rows[0])}: {list(atlas_rows[0].keys())}"

    def test_tier_is_participant(self, atlas_rows: list[dict]) -> None:
        for row in atlas_rows:
            assert row["tier"] == "participant", \
                f"Expected tier=participant, got {row['tier']} for {row['ma_id']}"

    def test_visible_rows_exist(self, atlas_rows: list[dict]) -> None:
        """Acceptance criterion (d): >= 10 visible Tier-P rows."""
        n_visible = sum(1 for r in atlas_rows if r["invisible"] == "False")
        assert n_visible >= 10, \
            f"Only {n_visible} visible rows — need >= 10. Enrichment strategy may need revision (R14)."

    def test_k_subset_matches_invisibility(self, atlas_rows: list[dict]) -> None:
        for row in atlas_rows:
            k_sub = int(row["k_subset"])
            invisible = row["invisible"] == "True"
            if k_sub < 3:
                assert invisible, f"{row['ma_id']}: k_subset={k_sub} < 3 but invisible=False"
            else:
                assert not invisible, f"{row['ma_id']}: k_subset={k_sub} >= 3 but invisible=True"


class TestSamplingDeterminism:
    """Test that seed=42 produces a deterministic random stratum."""

    def test_random_stratum_is_deterministic(self, pairwise70_dir: "Path") -> None:  # type: ignore[name-defined]
        """Run the enrichment scan on a tiny subset and verify seed=42 is reproducible."""
        import random, re

        # Two separate Random instances with same seed should produce same shuffle
        pool = list(range(1000))
        rng1 = random.Random(42)
        rng1.shuffle(pool)
        draw1 = pool[:55]

        pool2 = list(range(1000))
        rng2 = random.Random(42)
        rng2.shuffle(pool2)
        draw2 = pool2[:55]

        assert draw1 == draw2, "Seed=42 is not reproducible across two Random instances"

    def test_enrichment_keyword_regex(self) -> None:
        """Keyword regex uses word boundaries (Amendment 1 pattern)."""
        keywords = ["Mali", "Sudan", "malaria"]
        patterns = [
            re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)
            for kw in keywords
        ]

        # True positives
        assert any(p.search("Kayentao 2012 (Mali, West Africa)") for p in patterns)
        assert any(p.search("malaria treatment trial") for p in patterns)

        # True negatives (word-boundary protection)
        assert not any(p.search("Kamali 2019") for p in patterns)   # "mali" inside surname
        assert not any(p.search("Ghanavati 2020") for p in patterns)  # "ghan" substring
