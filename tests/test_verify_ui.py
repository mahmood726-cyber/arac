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
