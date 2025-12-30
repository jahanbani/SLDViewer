"""Tests for rawx_parser module."""

from pathlib import Path

import pytest

from backend.core.graph import rawx_parser


def test_parse_file_veragrid_unavailable_raises_not_implemented():
    """If VeraGrid can't import, parsing is not supported and should raise NotImplementedError."""
    if rawx_parser.VERAGRID_AVAILABLE:
        pytest.skip("VeraGrid is available in this environment; skip unavailability test.")

    with pytest.raises(NotImplementedError):
        rawx_parser.parse_file("dummy_path.rawx")


def test_parse_file_parses_sample_when_veragrid_available():
    """If VeraGrid is available, we should be able to parse an included sample RAWX file."""
    if not rawx_parser.VERAGRID_AVAILABLE:
        pytest.skip("VeraGrid is not available in this environment; skip parse test.")

    project_root = Path(__file__).resolve().parents[2]
    sample = project_root / "ieee118.rawx"
    assert sample.exists(), f"Expected sample file to exist at: {sample}"

    buses, branches, equipment, substations = rawx_parser.parse_file(str(sample))
    assert len(buses) > 0
    # Some files could be bus-only, but ieee118 should have branches
    assert len(branches) > 0
    # Substations should be detected/inferred
    assert len(substations) > 0, "Expected substations to be detected"
    # Buses should have substation_id assigned
    buses_with_substations = [b for b in buses if b.substation_id is not None]
    assert len(buses_with_substations) > 0, "Expected some buses to have substation_id"
    # ieee118 should have generators, loads, and shunts
    assert len(equipment) > 0

