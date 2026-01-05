"""
Tests for Pydantic models and deterministic ID helpers.
"""
import pytest
from backend.core.graph.models import (
    # ID helpers
    make_case_namespace,
    make_deterministic_id,
    make_bus_id,
    make_ac_branch_id,
    make_transformer3w_id,
    make_equipment_id,
    make_converter_id,
    make_dc_link_id,
    make_substation_id,
    # Enums
    EquipmentKind,
    BranchKind,
    DcTechnology,
    ViewMode,
    TopologyMode,
    TerminalMode,
    # Models
    BusModel,
    AcBranchModel,
    Transformer3WModel,
    EquipmentModel,
    DcLinkModel,
    SubstationModel,
    CaseSummary,
    ViewSpec,
    ViewResult,
    CytoscapePayload,
)


# =============================================================================
# Deterministic ID Tests
# =============================================================================


class TestDeterministicIds:
    """Tests for deterministic ID generation."""

    def test_case_namespace_is_deterministic(self):
        """Same file_id produces same namespace."""
        ns1 = make_case_namespace("file-123")
        ns2 = make_case_namespace("file-123")
        assert ns1 == ns2

    def test_case_namespace_differs_for_different_files(self):
        """Different file_ids produce different namespaces."""
        ns1 = make_case_namespace("file-123")
        ns2 = make_case_namespace("file-456")
        assert ns1 != ns2

    def test_deterministic_id_is_stable(self):
        """Same namespace and key produce same ID."""
        ns = make_case_namespace("test-file")
        id1 = make_deterministic_id(ns, "bus::101")
        id2 = make_deterministic_id(ns, "bus::101")
        assert id1 == id2

    def test_deterministic_id_differs_for_different_keys(self):
        """Different keys produce different IDs."""
        ns = make_case_namespace("test-file")
        id1 = make_deterministic_id(ns, "bus::101")
        id2 = make_deterministic_id(ns, "bus::102")
        assert id1 != id2

    def test_bus_id_deterministic(self):
        """Bus IDs are deterministic."""
        ns = make_case_namespace("test-file")
        id1 = make_bus_id(ns, 101)
        id2 = make_bus_id(ns, 101)
        assert id1 == id2

        # Different bus numbers produce different IDs
        id3 = make_bus_id(ns, 102)
        assert id1 != id3

    def test_ac_branch_id_deterministic(self):
        """AC branch IDs are deterministic."""
        ns = make_case_namespace("test-file")

        id1 = make_ac_branch_id(ns, "line", 101, 102, "1", 0)
        id2 = make_ac_branch_id(ns, "line", 101, 102, "1", 0)
        assert id1 == id2

        # Different circuit produces different ID
        id3 = make_ac_branch_id(ns, "line", 101, 102, "2", 0)
        assert id1 != id3

        # Different kind produces different ID
        id4 = make_ac_branch_id(ns, "xfmr2", 101, 102, "1", 0)
        assert id1 != id4

    def test_transformer3w_id_deterministic(self):
        """3W transformer IDs are deterministic."""
        ns = make_case_namespace("test-file")

        id1 = make_transformer3w_id(ns, 101, 102, 103, "T1")
        id2 = make_transformer3w_id(ns, 101, 102, 103, "T1")
        assert id1 == id2

        # Different buses produce different ID
        id3 = make_transformer3w_id(ns, 101, 102, 104, "T1")
        assert id1 != id3

    def test_equipment_id_deterministic(self):
        """Equipment IDs are deterministic."""
        ns = make_case_namespace("test-file")

        id1 = make_equipment_id(ns, "GENERATOR", 101, "GEN1", 0)
        id2 = make_equipment_id(ns, "GENERATOR", 101, "GEN1", 0)
        assert id1 == id2

        # Different kind produces different ID
        id3 = make_equipment_id(ns, "LOAD", 101, "GEN1", 0)
        assert id1 != id3

    def test_converter_id_deterministic(self):
        """Converter IDs are deterministic."""
        ns = make_case_namespace("test-file")

        id1 = make_converter_id(ns, "dc-link-1", "A")
        id2 = make_converter_id(ns, "dc-link-1", "A")
        assert id1 == id2

        # Different side produces different ID
        id3 = make_converter_id(ns, "dc-link-1", "B")
        assert id1 != id3

    def test_dc_link_id_deterministic(self):
        """DC link IDs are deterministic."""
        ns = make_case_namespace("test-file")

        id1 = make_dc_link_id(ns, "ttdc", "conv-a", "conv-b")
        id2 = make_dc_link_id(ns, "ttdc", "conv-a", "conv-b")
        assert id1 == id2

        # Different technology produces different ID
        id3 = make_dc_link_id(ns, "vscdc", "conv-a", "conv-b")
        assert id1 != id3

    def test_substation_id_deterministic(self):
        """Substation IDs are deterministic."""
        ns = make_case_namespace("test-file")

        id1 = make_substation_id(ns, "Station A", 0)
        id2 = make_substation_id(ns, "Station A", 0)
        assert id1 == id2

        # Different name produces different ID
        id3 = make_substation_id(ns, "Station B", 0)
        assert id1 != id3

    def test_ids_are_valid_hex_strings(self):
        """Generated IDs are valid 32-char hex strings (MD5 hashes)."""
        ns = make_case_namespace("test-file")
        bus_id = make_bus_id(ns, 101)

        # Should be 32-char hex string
        assert len(bus_id) == 32
        assert all(c in "0123456789abcdef" for c in bus_id)


# =============================================================================
# Model Validation Tests
# =============================================================================


class TestBusModel:
    """Tests for BusModel."""

    def test_minimal_bus(self):
        """Bus with only required fields."""
        bus = BusModel(
            id="bus-1",
            psse_number=101,
            name="BUS101",
            base_kv=138.0,
        )
        assert bus.id == "bus-1"
        assert bus.psse_number == 101
        assert bus.in_service is True
        assert bus.metadata == {}

    def test_full_bus(self):
        """Bus with all fields."""
        bus = BusModel(
            id="bus-1",
            psse_number=101,
            name="BUS101",
            base_kv=138.0,
            area=1,
            zone=2,
            owner=3,
            in_service=False,
            vm=1.02,
            va=-5.5,
            vmax=1.05,
            vmin=0.95,
            substation_id="sub-1",
            latitude=40.7128,
            longitude=-74.0060,
            metadata={"source": "psse"},
        )
        assert bus.area == 1
        assert bus.in_service is False
        assert bus.vm == 1.02
        assert bus.metadata["source"] == "psse"


class TestAcBranchModel:
    """Tests for AcBranchModel."""

    def test_minimal_branch(self):
        """Branch with only required fields."""
        branch = AcBranchModel(
            id="branch-1",
            from_bus_id="bus-1",
            to_bus_id="bus-2",
            kind=BranchKind.LINE,
        )
        assert branch.kind == BranchKind.LINE
        assert branch.in_service is True
        assert branch.is_closed is None

    def test_switch_with_is_closed(self):
        """Switch branch with is_closed status."""
        switch = AcBranchModel(
            id="switch-1",
            from_bus_id="bus-1",
            to_bus_id="bus-2",
            kind=BranchKind.SWITCH,
            is_closed=False,
        )
        assert switch.kind == BranchKind.SWITCH
        assert switch.is_closed is False

    def test_effective_rate_computed_from_rate_a(self):
        """effective_rate_mva computed from rate_a."""
        branch = AcBranchModel(
            id="branch-1",
            from_bus_id="bus-1",
            to_bus_id="bus-2",
            kind=BranchKind.LINE,
            rate_a=100.0,
            rate_b=80.0,
            rate_c=60.0,
        )
        assert branch.effective_rate_mva == 100.0

    def test_effective_rate_falls_back_to_rate_b(self):
        """effective_rate_mva falls back to rate_b if rate_a is None."""
        branch = AcBranchModel(
            id="branch-1",
            from_bus_id="bus-1",
            to_bus_id="bus-2",
            kind=BranchKind.LINE,
            rate_a=None,
            rate_b=80.0,
            rate_c=60.0,
        )
        assert branch.effective_rate_mva == 80.0

    def test_effective_rate_falls_back_to_rate_c(self):
        """effective_rate_mva falls back to rate_c if rate_a and rate_b are None."""
        branch = AcBranchModel(
            id="branch-1",
            from_bus_id="bus-1",
            to_bus_id="bus-2",
            kind=BranchKind.LINE,
            rate_a=None,
            rate_b=None,
            rate_c=60.0,
        )
        assert branch.effective_rate_mva == 60.0

    def test_transformer_with_tap(self):
        """2-winding transformer with tap settings."""
        xfmr = AcBranchModel(
            id="xfmr-1",
            from_bus_id="bus-1",
            to_bus_id="bus-2",
            kind=BranchKind.XFMR2,
            tap_module=1.05,
            tap_phase_deg=0.0,
        )
        assert xfmr.kind == BranchKind.XFMR2
        assert xfmr.tap_module == 1.05


class TestTransformer3WModel:
    """Tests for Transformer3WModel."""

    def test_minimal_transformer3w(self):
        """3W transformer with required fields."""
        xfmr = Transformer3WModel(
            id="xfmr3-1",
            bus1_id="bus-1",
            bus2_id="bus-2",
            bus3_id="bus-3",
        )
        assert xfmr.in_service is True
        assert xfmr.leg1_in_service is True
        assert xfmr.leg2_in_service is True
        assert xfmr.leg3_in_service is True

    def test_transformer3w_with_partial_leg_status(self):
        """3W transformer with some legs out of service."""
        xfmr = Transformer3WModel(
            id="xfmr3-1",
            bus1_id="bus-1",
            bus2_id="bus-2",
            bus3_id="bus-3",
            leg2_in_service=False,
        )
        assert xfmr.leg1_in_service is True
        assert xfmr.leg2_in_service is False
        assert xfmr.leg3_in_service is True


class TestEquipmentModel:
    """Tests for EquipmentModel."""

    def test_generator(self):
        """Generator equipment."""
        gen = EquipmentModel(
            id="gen-1",
            bus_id="bus-1",
            kind=EquipmentKind.GENERATOR,
            name="GEN1",
            p_mw=100.0,
            q_mvar=50.0,
        )
        assert gen.kind == EquipmentKind.GENERATOR
        assert gen.p_mw == 100.0

    def test_converter(self):
        """Converter equipment."""
        conv = EquipmentModel(
            id="conv-1",
            bus_id="bus-1",
            kind=EquipmentKind.CONVERTER_CSC,
            name="CONV1",
        )
        assert conv.kind == EquipmentKind.CONVERTER_CSC


class TestDcLinkModel:
    """Tests for DcLinkModel."""

    def test_ttdc_link(self):
        """Two-terminal DC link."""
        dc = DcLinkModel(
            id="dc-1",
            technology=DcTechnology.TTDC,
            from_converter_id="conv-a",
            to_converter_id="conv-b",
            rating_mw=500.0,
        )
        assert dc.technology == DcTechnology.TTDC
        assert dc.rating_mw == 500.0

    def test_vscdc_link(self):
        """VSC DC link."""
        dc = DcLinkModel(
            id="dc-1",
            technology=DcTechnology.VSCDC,
            from_converter_id="conv-a",
            to_converter_id="conv-b",
        )
        assert dc.technology == DcTechnology.VSCDC


class TestSubstationModel:
    """Tests for SubstationModel."""

    def test_minimal_substation(self):
        """Substation with required fields."""
        sub = SubstationModel(
            id="sub-1",
            name="Station A",
        )
        assert sub.name == "Station A"
        assert sub.voltage_levels == []

    def test_substation_with_voltage_levels(self):
        """Substation with voltage levels."""
        sub = SubstationModel(
            id="sub-1",
            name="Station A",
            voltage_levels=[345.0, 138.0, 69.0],
            metadata={"name_source": "veragrid"},
        )
        assert 345.0 in sub.voltage_levels
        assert sub.metadata["name_source"] == "veragrid"


class TestCaseSummary:
    """Tests for CaseSummary."""

    def test_case_summary(self):
        """CaseSummary with all counts."""
        summary = CaseSummary(
            file_id="file-123",
            format="raw",
            bus_count=1000,
            ac_branch_count=1500,
            transformer3w_count=50,
            equipment_count=200,
            dc_link_count=5,
            substation_count=100,
            voltage_levels=[345.0, 230.0, 138.0, 69.0],
        )
        assert summary.bus_count == 1000
        assert summary.format == "raw"
        assert len(summary.voltage_levels) == 4
        assert summary.created_at_iso  # Should have default


class TestViewSpec:
    """Tests for ViewSpec."""

    def test_default_view_spec(self):
        """ViewSpec with defaults."""
        spec = ViewSpec()
        assert spec.mode == ViewMode.BUS
        assert spec.max_depth == 1
        assert spec.node_limit == 400
        assert spec.edge_limit == 800
        assert spec.topology_mode == TopologyMode.AS_MODELED
        assert spec.terminal_mode == TerminalMode.EXPLICIT_NODES

    def test_custom_view_spec(self):
        """ViewSpec with custom values."""
        spec = ViewSpec(
            mode=ViewMode.STATION_DETAIL,
            center_bus_numbers=[101, 102],
            max_depth=3,
            topology_mode=TopologyMode.ENERGIZED_ONLY,
            voltage_kv_min=100.0,
            voltage_kv_max=400.0,
        )
        assert spec.mode == ViewMode.STATION_DETAIL
        assert spec.center_bus_numbers == [101, 102]
        assert spec.topology_mode == TopologyMode.ENERGIZED_ONLY


class TestViewResult:
    """Tests for ViewResult."""

    def test_empty_view_result(self):
        """Empty ViewResult."""
        result = ViewResult()
        assert result.buses == []
        assert result.ac_branches == []
        assert result.meta == {}

    def test_view_result_with_data(self):
        """ViewResult with buses and branches."""
        bus = BusModel(id="bus-1", psse_number=101, name="BUS101", base_kv=138.0)
        branch = AcBranchModel(
            id="branch-1",
            from_bus_id="bus-1",
            to_bus_id="bus-2",
            kind=BranchKind.LINE,
        )

        result = ViewResult(
            buses=[bus],
            ac_branches=[branch],
            meta={"truncated": False},
        )
        assert len(result.buses) == 1
        assert len(result.ac_branches) == 1
        assert result.meta["truncated"] is False


class TestCytoscapePayload:
    """Tests for CytoscapePayload."""

    def test_empty_payload(self):
        """Empty CytoscapePayload."""
        payload = CytoscapePayload()
        assert payload.elements == {"nodes": [], "edges": []}
        assert payload.meta == {}

    def test_payload_with_elements(self):
        """CytoscapePayload with elements."""
        payload = CytoscapePayload(
            elements={
                "nodes": [{"data": {"id": "n1", "kind": "bus"}}],
                "edges": [{"data": {"id": "e1", "source": "n1", "target": "n2"}}],
            },
            meta={"node_count": 1, "edge_count": 1},
        )
        assert len(payload.elements["nodes"]) == 1
        assert len(payload.elements["edges"]) == 1


# =============================================================================
# ID Stability Across Parses Test
# =============================================================================


class TestIdStabilityAcrossParses:
    """Test that IDs are stable across multiple 'parses' (simulated)."""

    def test_ids_stable_for_same_file(self):
        """IDs generated for the same file_id are identical."""
        file_id = "case-file-abc123"

        # Simulate first parse
        ns1 = make_case_namespace(file_id)
        bus_id_1 = make_bus_id(ns1, 101)
        branch_id_1 = make_ac_branch_id(ns1, "line", 101, 102, "1", 0)
        xfmr3_id_1 = make_transformer3w_id(ns1, 101, 102, 103, "T1")
        eq_id_1 = make_equipment_id(ns1, "GENERATOR", 101, "GEN1", 0)

        # Simulate second parse (same file)
        ns2 = make_case_namespace(file_id)
        bus_id_2 = make_bus_id(ns2, 101)
        branch_id_2 = make_ac_branch_id(ns2, "line", 101, 102, "1", 0)
        xfmr3_id_2 = make_transformer3w_id(ns2, 101, 102, 103, "T1")
        eq_id_2 = make_equipment_id(ns2, "GENERATOR", 101, "GEN1", 0)

        # All IDs should match
        assert ns1 == ns2
        assert bus_id_1 == bus_id_2
        assert branch_id_1 == branch_id_2
        assert xfmr3_id_1 == xfmr3_id_2
        assert eq_id_1 == eq_id_2

    def test_ids_differ_for_different_files(self):
        """IDs generated for different file_ids are different."""
        ns1 = make_case_namespace("file-A")
        ns2 = make_case_namespace("file-B")

        bus_id_1 = make_bus_id(ns1, 101)
        bus_id_2 = make_bus_id(ns2, 101)

        # Same bus number but different files -> different IDs
        assert bus_id_1 != bus_id_2
