"""
Tests for the VeraGrid adapter.
"""
from pathlib import Path
import pytest

from backend.core.graph.veragrid_adapter import (
    VeraGridAdapter,
    ParsedCase,
    parse_case_file,
)
from backend.core.graph.models import (
    BranchKind,
    EquipmentKind,
)


FIXTURES_DIR = Path(__file__).parent / "fixtures"
IEEE14_PATH = FIXTURES_DIR / "ieee14.raw"


@pytest.fixture
def ieee14_case() -> ParsedCase:
    """Parse IEEE 14 bus test case."""
    adapter = VeraGridAdapter(IEEE14_PATH, "test-ieee14", "raw")
    return adapter.parse()


class TestVeraGridAdapter:
    """Tests for VeraGridAdapter parsing."""

    def test_parse_ieee14_buses(self, ieee14_case):
        """Test that buses are parsed correctly."""
        assert len(ieee14_case.buses) == 14

        # Check first bus
        bus1 = ieee14_case.bus_by_psse.get(1)
        assert bus1 is not None
        assert bus1.psse_number == 1
        assert bus1.name == "BUS 1"
        assert bus1.base_kv == 138.0
        assert bus1.in_service is True

    def test_parse_ieee14_lines(self, ieee14_case):
        """Test that lines are parsed correctly."""
        lines = [b for b in ieee14_case.ac_branches if b.kind == BranchKind.LINE]
        # IEEE 14 has 17 lines + 3 transformers
        assert len(lines) >= 15  # At least 15 lines

    def test_parse_ieee14_transformers(self, ieee14_case):
        """Test that transformers are parsed correctly."""
        xfmrs = [b for b in ieee14_case.ac_branches if b.kind == BranchKind.XFMR2]
        assert len(xfmrs) == 3  # IEEE 14 has 3 two-winding transformers

    def test_parse_ieee14_generators(self, ieee14_case):
        """Test that generators are parsed correctly."""
        gens = [e for e in ieee14_case.equipment if e.kind == EquipmentKind.GENERATOR]
        assert len(gens) == 5  # IEEE 14 has 5 generators

    def test_parse_ieee14_loads(self, ieee14_case):
        """Test that loads are parsed correctly."""
        loads = [e for e in ieee14_case.equipment if e.kind == EquipmentKind.LOAD]
        assert len(loads) == 11  # IEEE 14 has 11 loads

    def test_parse_ieee14_shunts(self, ieee14_case):
        """Test that shunts are parsed correctly."""
        shunts = [
            e
            for e in ieee14_case.equipment
            if e.kind in (EquipmentKind.SHUNT_FIXED, EquipmentKind.SHUNT_SWITCHED)
        ]
        assert len(shunts) >= 1  # IEEE 14 has at least 1 shunt

    def test_parse_ieee14_substations(self, ieee14_case):
        """Test that substations are detected."""
        assert len(ieee14_case.substations) >= 1

    def test_parse_ieee14_voltage_levels(self, ieee14_case):
        """Test that voltage levels are collected."""
        assert 138.0 in ieee14_case.voltage_levels

    def test_deterministic_ids(self, ieee14_case):
        """Test that IDs are deterministic across parses."""
        # Parse again
        adapter2 = VeraGridAdapter(IEEE14_PATH, "test-ieee14", "raw")
        case2 = adapter2.parse()

        # IDs should match
        bus1_a = ieee14_case.bus_by_psse.get(1)
        bus1_b = case2.bus_by_psse.get(1)

        assert bus1_a.id == bus1_b.id

    def test_different_file_ids_produce_different_ids(self, ieee14_case):
        """Test that different file_ids produce different IDs."""
        adapter2 = VeraGridAdapter(IEEE14_PATH, "different-file-id", "raw")
        case2 = adapter2.parse()

        bus1_a = ieee14_case.bus_by_psse.get(1)
        bus1_b = case2.bus_by_psse.get(1)

        assert bus1_a.id != bus1_b.id

    def test_no_dangling_warnings_in_ieee14(self, ieee14_case):
        """Test that IEEE 14 has no dangling references."""
        dangling_warnings = [w for w in ieee14_case.warnings if "dangling" in w.lower()]
        assert len(dangling_warnings) == 0


class TestCaseSummary:
    """Tests for CaseSummary generation."""

    def test_summary_counts(self):
        """Test that summary has correct counts."""
        adapter = VeraGridAdapter(IEEE14_PATH, "test-ieee14", "raw")
        adapter.parse()
        summary = adapter.get_summary()

        assert summary.file_id == "test-ieee14"
        assert summary.format == "raw"
        assert summary.bus_count == 14
        assert summary.ac_branch_count >= 18  # lines + transformers
        assert summary.equipment_count >= 16  # generators + loads + shunts

    def test_summary_voltage_levels(self):
        """Test that summary has voltage levels sorted descending."""
        adapter = VeraGridAdapter(IEEE14_PATH, "test-ieee14", "raw")
        adapter.parse()
        summary = adapter.get_summary()

        assert len(summary.voltage_levels) >= 1
        # Should be sorted descending
        if len(summary.voltage_levels) > 1:
            assert summary.voltage_levels[0] >= summary.voltage_levels[-1]


class TestParseFunction:
    """Tests for the convenience parse_case_file function."""

    def test_parse_case_file(self):
        """Test the convenience function."""
        case, summary = parse_case_file(IEEE14_PATH, "test-file", "raw")

        assert len(case.buses) == 14
        assert summary.bus_count == 14


class TestBranchReferences:
    """Tests for branch-to-bus references."""

    def test_branch_references_valid_buses(self, ieee14_case):
        """Test that all branches reference valid buses."""
        bus_ids = {b.id for b in ieee14_case.buses}

        for branch in ieee14_case.ac_branches:
            assert branch.from_bus_id in bus_ids, f"Branch {branch.id} has invalid from_bus_id"
            assert branch.to_bus_id in bus_ids, f"Branch {branch.id} has invalid to_bus_id"

    def test_equipment_references_valid_buses(self, ieee14_case):
        """Test that all equipment references valid buses."""
        bus_ids = {b.id for b in ieee14_case.buses}

        for eq in ieee14_case.equipment:
            assert eq.bus_id in bus_ids, f"Equipment {eq.id} has invalid bus_id"
