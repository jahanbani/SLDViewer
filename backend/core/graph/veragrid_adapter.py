"""
VeraGrid adapter for parsing RAW/RAWX files and mapping to SLD Viewer models.

This adapter:
- Parses RAW/RAWX files using VeraGrid
- Maps VeraGrid objects to our canonical models with deterministic IDs
- Handles HVDC as converter+DC link (not fake AC)
- Records dangling references as warnings
"""
import sys
from pathlib import Path
from typing import Any

from backend.core.timing import OperationTimer, logger

# Add VeraGrid to path
_veragrid_path = Path(__file__).parent.parent.parent.parent / "VeraGrid" / "src"
if str(_veragrid_path) not in sys.path:
    sys.path.insert(0, str(_veragrid_path))

from backend.core.graph.models import (
    BusModel,
    AcBranchModel,
    Transformer3WModel,
    EquipmentModel,
    DcLinkModel,
    SubstationModel,
    CaseSummary,
    BranchKind,
    EquipmentKind,
    DcTechnology,
    make_case_namespace,
    make_bus_id,
    make_ac_branch_id,
    make_transformer3w_id,
    make_equipment_id,
    make_converter_id,
    make_dc_link_id,
    make_substation_id,
    get_namespace_uuid,
    make_deterministic_id_fast,
)
from backend.core.errors import ParseError


def _safe_int(value: Any) -> int | None:
    """Safely convert a value to int, returning None if not possible."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        if value.strip() == "":
            return None
        try:
            return int(value)
        except ValueError:
            return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


class ParsedCase:
    """Container for all parsed data from a VeraGrid case."""

    def __init__(self, file_id: str, file_format: str):
        self.file_id = file_id
        self.file_format = file_format
        self.namespace = make_case_namespace(file_id)

        # Parsed models
        self.buses: list[BusModel] = []
        self.ac_branches: list[AcBranchModel] = []
        self.transformers3w: list[Transformer3WModel] = []
        self.equipment: list[EquipmentModel] = []
        self.dc_links: list[DcLinkModel] = []
        self.substations: list[SubstationModel] = []

        # Mappings for lookups
        self.bus_by_psse: dict[int, BusModel] = {}
        self.bus_id_by_psse: dict[int, str] = {}
        self.substation_by_name: dict[str, SubstationModel] = {}

        # Warnings during parse
        self.warnings: list[str] = []

        # Voltage levels found
        self.voltage_levels: set[float] = set()


class VeraGridAdapter:
    """Adapter to parse RAW/RAWX files using VeraGrid and map to our models."""

    def __init__(self, file_path: Path, file_id: str, file_format: str):
        """
        Initialize the adapter.

        Args:
            file_path: Path to the RAW/RAWX file
            file_id: Unique identifier for this file
            file_format: File format ("raw" or "rawx")
        """
        self.file_path = file_path
        self.file_id = file_id
        self.file_format = file_format
        self.case = ParsedCase(file_id, file_format)

        # VeraGrid MultiCircuit object
        self._grid: Any = None

    def parse(self) -> ParsedCase:
        """
        Parse the file and return all models.

        Returns:
            ParsedCase containing all parsed models and warnings
        """
        # Start timing the entire parse operation
        timer = OperationTimer(f"Parse {self.file_path.name}")

        try:
            from VeraGridEngine.api import open_file
        except ImportError as e:
            raise ParseError(f"VeraGrid not available: {e}")

        # Phase 1: VeraGrid file read (this is often the slowest part)
        timer.start_phase("veragrid_open_file")
        try:
            self._grid = open_file(str(self.file_path))
        except Exception as e:
            raise ParseError(f"Failed to parse file: {e}")
        timer.end_phase("veragrid_open_file")

        # Log raw counts from VeraGrid
        logger.info(f"  [COUNTS] VeraGrid loaded: "
                   f"buses={len(self._grid.buses):,}, "
                   f"lines={len(self._grid.lines):,}, "
                   f"xfmr2={len(self._grid.transformers2w):,}, "
                   f"xfmr3={len(self._grid.transformers3w):,}, "
                   f"gens={len(self._grid.generators):,}, "
                   f"loads={len(self._grid.loads):,}")

        # Phase 2: Parse and map to our models
        timer.start_phase("parse_substations")
        self._parse_substations()
        timer.end_phase("parse_substations", len(self.case.substations))

        timer.start_phase("parse_buses")
        self._parse_buses()
        timer.end_phase("parse_buses", len(self.case.buses))

        timer.start_phase("parse_lines")
        self._parse_lines()
        lines_count = len(self.case.ac_branches)
        timer.end_phase("parse_lines", lines_count)

        timer.start_phase("parse_transformers2w")
        self._parse_transformers2w()
        xfmr2_count = len(self.case.ac_branches) - lines_count
        timer.end_phase("parse_transformers2w", xfmr2_count)

        timer.start_phase("parse_transformers3w")
        self._parse_transformers3w()
        timer.end_phase("parse_transformers3w", len(self.case.transformers3w))

        timer.start_phase("parse_switches")
        prev_branch_count = len(self.case.ac_branches)
        self._parse_switches()
        timer.end_phase("parse_switches", len(self.case.ac_branches) - prev_branch_count)

        timer.start_phase("parse_series_reactances")
        prev_branch_count = len(self.case.ac_branches)
        self._parse_series_reactances()
        timer.end_phase("parse_series_reactances", len(self.case.ac_branches) - prev_branch_count)

        timer.start_phase("parse_generators")
        self._parse_generators()
        gen_count = len([e for e in self.case.equipment if e.kind == EquipmentKind.GENERATOR])
        timer.end_phase("parse_generators", gen_count)

        timer.start_phase("parse_loads")
        self._parse_loads()
        load_count = len([e for e in self.case.equipment if e.kind == EquipmentKind.LOAD])
        timer.end_phase("parse_loads", load_count)

        timer.start_phase("parse_shunts")
        self._parse_shunts()
        timer.end_phase("parse_shunts")

        timer.start_phase("parse_hvdc")
        self._parse_hvdc()
        timer.end_phase("parse_hvdc", len(self.case.dc_links))

        timer.start_phase("parse_vsc")
        self._parse_vsc()
        timer.end_phase("parse_vsc")

        # Set final counts
        timer.set_count("total_buses", len(self.case.buses))
        timer.set_count("total_branches", len(self.case.ac_branches))
        timer.set_count("total_equipment", len(self.case.equipment))
        timer.set_count("warnings", len(self.case.warnings))

        # Finish and log summary
        report = timer.finish()
        logger.info(report.summary())

        return self.case

    def get_summary(self) -> CaseSummary:
        """Generate a CaseSummary from the parsed case."""
        return CaseSummary(
            file_id=self.case.file_id,
            format=self.case.file_format,
            bus_count=len(self.case.buses),
            ac_branch_count=len(self.case.ac_branches),
            transformer3w_count=len(self.case.transformers3w),
            equipment_count=len(self.case.equipment),
            dc_link_count=len(self.case.dc_links),
            substation_count=len(self.case.substations),
            voltage_levels=sorted(self.case.voltage_levels, reverse=True),
            parse_warnings=self.case.warnings,
        )

    def _get_psse_number(self, bus) -> int:
        """Extract PSSE bus number from VeraGrid bus.code field."""
        try:
            return int(bus.code)
        except (ValueError, TypeError):
            # Fallback: use index
            return self._grid.buses.index(bus) + 1

    def _get_bus_id(self, psse_number: int) -> str | None:
        """Get our bus ID from PSSE number, or None if not found."""
        return self.case.bus_id_by_psse.get(psse_number)

    def _parse_substations(self) -> None:
        """Parse substations from VeraGrid."""
        for idx, sub in enumerate(self._grid.substations):
            sub_id = make_substation_id(self.case.namespace, sub.name, idx)

            # Safely extract area/zone codes
            area_code = None
            zone_code = None
            if sub.area:
                area_code = _safe_int(getattr(sub.area, "code", None))
            if sub.zone:
                zone_code = _safe_int(getattr(sub.zone, "code", None))

            substation = SubstationModel(
                id=sub_id,
                name=sub.name,
                area=area_code,
                zone=zone_code,
                latitude=getattr(sub, "latitude", None),
                longitude=getattr(sub, "longitude", None),
                metadata={"name_source": "veragrid"},
            )

            self.case.substations.append(substation)
            self.case.substation_by_name[sub.name] = substation

    def _parse_buses(self) -> None:
        """Parse buses from VeraGrid."""
        # Pre-cache lookups for performance
        substation_by_name = self.case.substation_by_name
        buses_list = self.case.buses
        bus_by_psse = self.case.bus_by_psse
        bus_id_by_psse = self.case.bus_id_by_psse
        voltage_levels = self.case.voltage_levels
        namespace = self.case.namespace

        # Pre-parse namespace UUID once (avoid 93k string->UUID conversions)
        ns_uuid = get_namespace_uuid(namespace)

        # Track voltage levels per substation using sets for O(1) lookup
        substation_voltages: dict[str, set[float]] = {}

        for bus in self._grid.buses:
            psse_number = self._get_psse_number(bus)
            # Use fast version with pre-parsed namespace UUID
            bus_id = make_deterministic_id_fast(ns_uuid, f"bus::{psse_number}")

            # Get substation ID if available - compute sub_name only once
            substation_id = None
            sub = None
            bus_substation = bus.substation
            if bus_substation:
                sub_name = getattr(bus_substation, "name", None) or str(bus_substation)
                sub = substation_by_name.get(sub_name)
                if sub:
                    substation_id = sub.id

            # Get area/zone as integers - use try/except instead of hasattr+getattr
            area = None
            zone = None
            bus_area = bus.area
            bus_zone = bus.zone
            if bus_area:
                try:
                    area = int(bus_area.code)
                except (AttributeError, ValueError, TypeError):
                    pass
            if bus_zone:
                try:
                    zone = int(bus_zone.code)
                except (AttributeError, ValueError, TypeError):
                    pass

            # Get optional attributes with fallback
            try:
                latitude = bus.latitude
            except AttributeError:
                latitude = None
            try:
                longitude = bus.longitude
            except AttributeError:
                longitude = None

            bus_model = BusModel(
                id=bus_id,
                psse_number=psse_number,
                name=bus.name,
                base_kv=bus.Vnom,
                area=area,
                zone=zone,
                owner=None,
                in_service=bus.active,
                vm=bus.Vm0,
                va=bus.Va0,
                vmax=bus.Vmax,
                vmin=bus.Vmin,
                substation_id=substation_id,
                latitude=latitude,
                longitude=longitude,
            )

            buses_list.append(bus_model)
            bus_by_psse[psse_number] = bus_model
            bus_id_by_psse[psse_number] = bus_id
            voltage_levels.add(bus.Vnom)

            # Track voltage levels per substation using set for O(1) membership
            if sub:
                if substation_id not in substation_voltages:
                    substation_voltages[substation_id] = set(sub.voltage_levels)
                substation_voltages[substation_id].add(bus.Vnom)

        # Batch update substation voltage levels at the end - use index for O(1) lookup
        substation_by_id = {sub.id: sub for sub in self.case.substations}
        for sub_id, voltages in substation_voltages.items():
            sub = substation_by_id.get(sub_id)
            if sub:
                sub.voltage_levels = list(voltages)

    def _parse_lines(self) -> None:
        """Parse AC lines from VeraGrid."""
        # Track branch counts for index_hint
        branch_counts: dict[tuple, int] = {}

        for line in self._grid.lines:
            from_psse = self._get_psse_number(line.bus_from)
            to_psse = self._get_psse_number(line.bus_to)

            from_bus_id = self._get_bus_id(from_psse)
            to_bus_id = self._get_bus_id(to_psse)

            if not from_bus_id or not to_bus_id:
                self.case.warnings.append(
                    f"Line {line.name}: dangling reference (from={from_psse}, to={to_psse})"
                )
                continue

            # Get circuit identifier
            circuit = getattr(line, "code", None) or "1"

            # Index hint for parallel branches
            key = ("line", from_psse, to_psse, circuit)
            index_hint = branch_counts.get(key, 0)
            branch_counts[key] = index_hint + 1

            branch_id = make_ac_branch_id(
                self.case.namespace, "line", from_psse, to_psse, circuit, index_hint
            )

            branch = AcBranchModel(
                id=branch_id,
                from_bus_id=from_bus_id,
                to_bus_id=to_bus_id,
                circuit=circuit,
                kind=BranchKind.LINE,
                in_service=line.active,
                r=line.R,
                x=line.X,
                b=line.B,
                g=getattr(line, "G", None),
                rate_a=line.rate,
                length_km=getattr(line, "length", None),
            )

            self.case.ac_branches.append(branch)

    def _parse_transformers2w(self) -> None:
        """Parse 2-winding transformers from VeraGrid."""
        branch_counts: dict[tuple, int] = {}

        for xfmr in self._grid.transformers2w:
            from_psse = self._get_psse_number(xfmr.bus_from)
            to_psse = self._get_psse_number(xfmr.bus_to)

            from_bus_id = self._get_bus_id(from_psse)
            to_bus_id = self._get_bus_id(to_psse)

            if not from_bus_id or not to_bus_id:
                self.case.warnings.append(
                    f"Transformer2W {xfmr.name}: dangling reference"
                )
                continue

            circuit = getattr(xfmr, "code", None) or "1"

            key = ("xfmr2", from_psse, to_psse, circuit)
            index_hint = branch_counts.get(key, 0)
            branch_counts[key] = index_hint + 1

            branch_id = make_ac_branch_id(
                self.case.namespace, "xfmr2", from_psse, to_psse, circuit, index_hint
            )

            branch = AcBranchModel(
                id=branch_id,
                from_bus_id=from_bus_id,
                to_bus_id=to_bus_id,
                circuit=circuit,
                kind=BranchKind.XFMR2,
                in_service=xfmr.active,
                r=xfmr.R,
                x=xfmr.X,
                rate_a=xfmr.rate,
                tap_module=getattr(xfmr, "tap_module", None),
                tap_phase_deg=getattr(xfmr, "tap_phase", None),
            )

            self.case.ac_branches.append(branch)

    def _parse_transformers3w(self) -> None:
        """Parse 3-winding transformers from VeraGrid."""
        for xfmr in self._grid.transformers3w:
            # 3W transformers have bus1, bus2, bus3
            bus1_psse = self._get_psse_number(xfmr.bus1)
            bus2_psse = self._get_psse_number(xfmr.bus2)
            bus3_psse = self._get_psse_number(xfmr.bus3)

            bus1_id = self._get_bus_id(bus1_psse)
            bus2_id = self._get_bus_id(bus2_psse)
            bus3_id = self._get_bus_id(bus3_psse)

            if not all([bus1_id, bus2_id, bus3_id]):
                self.case.warnings.append(
                    f"Transformer3W {xfmr.name}: dangling reference"
                )
                continue

            xfmr3_id = make_transformer3w_id(
                self.case.namespace, bus1_psse, bus2_psse, bus3_psse, xfmr.name
            )

            xfmr3 = Transformer3WModel(
                id=xfmr3_id,
                name=xfmr.name,
                bus1_id=bus1_id,
                bus2_id=bus2_id,
                bus3_id=bus3_id,
                in_service=xfmr.active,
                # Per-leg status if available
                leg1_in_service=getattr(xfmr, "winding1_active", True),
                leg2_in_service=getattr(xfmr, "winding2_active", True),
                leg3_in_service=getattr(xfmr, "winding3_active", True),
            )

            self.case.transformers3w.append(xfmr3)

    def _parse_switches(self) -> None:
        """Parse switches from VeraGrid."""
        branch_counts: dict[tuple, int] = {}

        for switch in self._grid.switch_devices:
            from_psse = self._get_psse_number(switch.bus_from)
            to_psse = self._get_psse_number(switch.bus_to)

            from_bus_id = self._get_bus_id(from_psse)
            to_bus_id = self._get_bus_id(to_psse)

            if not from_bus_id or not to_bus_id:
                self.case.warnings.append(f"Switch {switch.name}: dangling reference")
                continue

            circuit = getattr(switch, "code", None) or "1"

            key = ("switch", from_psse, to_psse, circuit)
            index_hint = branch_counts.get(key, 0)
            branch_counts[key] = index_hint + 1

            branch_id = make_ac_branch_id(
                self.case.namespace, "switch", from_psse, to_psse, circuit, index_hint
            )

            branch = AcBranchModel(
                id=branch_id,
                from_bus_id=from_bus_id,
                to_bus_id=to_bus_id,
                circuit=circuit,
                kind=BranchKind.SWITCH,
                in_service=switch.active,
                is_closed=switch.active,  # In VeraGrid, active often means closed
                r=getattr(switch, "R", 0.0),
                x=getattr(switch, "X", 0.0001),
            )

            self.case.ac_branches.append(branch)

    def _parse_series_reactances(self) -> None:
        """Parse series reactances from VeraGrid."""
        branch_counts: dict[tuple, int] = {}

        for sr in self._grid.series_reactances:
            from_psse = self._get_psse_number(sr.bus_from)
            to_psse = self._get_psse_number(sr.bus_to)

            from_bus_id = self._get_bus_id(from_psse)
            to_bus_id = self._get_bus_id(to_psse)

            if not from_bus_id or not to_bus_id:
                self.case.warnings.append(
                    f"Series reactance {sr.name}: dangling reference"
                )
                continue

            circuit = getattr(sr, "code", None) or "1"

            key = ("series", from_psse, to_psse, circuit)
            index_hint = branch_counts.get(key, 0)
            branch_counts[key] = index_hint + 1

            branch_id = make_ac_branch_id(
                self.case.namespace, "series", from_psse, to_psse, circuit, index_hint
            )

            branch = AcBranchModel(
                id=branch_id,
                from_bus_id=from_bus_id,
                to_bus_id=to_bus_id,
                circuit=circuit,
                kind=BranchKind.SERIES,
                in_service=sr.active,
                r=sr.R,
                x=sr.X,
            )

            self.case.ac_branches.append(branch)

    def _parse_generators(self) -> None:
        """Parse generators from VeraGrid."""
        eq_counts: dict[tuple, int] = {}

        for gen in self._grid.generators:
            bus_psse = self._get_psse_number(gen.bus)
            bus_id = self._get_bus_id(bus_psse)

            if not bus_id:
                self.case.warnings.append(f"Generator {gen.name}: dangling reference")
                continue

            key = ("GENERATOR", bus_psse, gen.name)
            index_hint = eq_counts.get(key, 0)
            eq_counts[key] = index_hint + 1

            eq_id = make_equipment_id(
                self.case.namespace, "GENERATOR", bus_psse, gen.name, index_hint
            )

            equipment = EquipmentModel(
                id=eq_id,
                bus_id=bus_id,
                kind=EquipmentKind.GENERATOR,
                name=gen.name,
                in_service=gen.active,
                p_mw=gen.P,
                q_mvar=getattr(gen, "Q", None),
            )

            self.case.equipment.append(equipment)

    def _parse_loads(self) -> None:
        """Parse loads from VeraGrid."""
        eq_counts: dict[tuple, int] = {}

        for load in self._grid.loads:
            bus_psse = self._get_psse_number(load.bus)
            bus_id = self._get_bus_id(bus_psse)

            if not bus_id:
                self.case.warnings.append(f"Load {load.name}: dangling reference")
                continue

            key = ("LOAD", bus_psse, load.name)
            index_hint = eq_counts.get(key, 0)
            eq_counts[key] = index_hint + 1

            eq_id = make_equipment_id(
                self.case.namespace, "LOAD", bus_psse, load.name, index_hint
            )

            equipment = EquipmentModel(
                id=eq_id,
                bus_id=bus_id,
                kind=EquipmentKind.LOAD,
                name=load.name,
                in_service=load.active,
                p_mw=load.P,
                q_mvar=load.Q,
            )

            self.case.equipment.append(equipment)

    def _parse_shunts(self) -> None:
        """Parse shunts from VeraGrid."""
        eq_counts: dict[tuple, int] = {}

        for shunt in self._grid.shunts:
            bus_psse = self._get_psse_number(shunt.bus)
            bus_id = self._get_bus_id(bus_psse)

            if not bus_id:
                self.case.warnings.append(f"Shunt {shunt.name}: dangling reference")
                continue

            # Determine if fixed or switched
            is_switched = getattr(shunt, "is_controlled", False)
            kind = EquipmentKind.SHUNT_SWITCHED if is_switched else EquipmentKind.SHUNT_FIXED

            key = (kind.value, bus_psse, shunt.name)
            index_hint = eq_counts.get(key, 0)
            eq_counts[key] = index_hint + 1

            eq_id = make_equipment_id(
                self.case.namespace, kind.value, bus_psse, shunt.name, index_hint
            )

            equipment = EquipmentModel(
                id=eq_id,
                bus_id=bus_id,
                kind=kind,
                name=shunt.name,
                in_service=shunt.active,
                q_mvar=getattr(shunt, "B", None),  # Susceptance as reactive
            )

            self.case.equipment.append(equipment)

    def _parse_hvdc(self) -> None:
        """Parse HVDC lines (two-terminal DC) from VeraGrid."""
        for hvdc in self._grid.hvdc_lines:
            # Get rectifier and inverter buses
            rect_bus = hvdc.bus_from
            inv_bus = hvdc.bus_to

            rect_psse = self._get_psse_number(rect_bus)
            inv_psse = self._get_psse_number(inv_bus)

            rect_bus_id = self._get_bus_id(rect_psse)
            inv_bus_id = self._get_bus_id(inv_psse)

            if not rect_bus_id or not inv_bus_id:
                self.case.warnings.append(f"HVDC {hvdc.name}: dangling reference")
                continue

            dc_id = hvdc.idtag or hvdc.name

            # Create converter A (rectifier)
            conv_a_id = make_converter_id(self.case.namespace, dc_id, "A")
            conv_a = EquipmentModel(
                id=conv_a_id,
                bus_id=rect_bus_id,
                kind=EquipmentKind.CONVERTER_CSC,
                name=f"{hvdc.name}_Rect",
                in_service=hvdc.active,
                p_mw=getattr(hvdc, "Pset", None),
            )
            self.case.equipment.append(conv_a)

            # Create converter B (inverter)
            conv_b_id = make_converter_id(self.case.namespace, dc_id, "B")
            conv_b = EquipmentModel(
                id=conv_b_id,
                bus_id=inv_bus_id,
                kind=EquipmentKind.CONVERTER_CSC,
                name=f"{hvdc.name}_Inv",
                in_service=hvdc.active,
                p_mw=-getattr(hvdc, "Pset", 0) if getattr(hvdc, "Pset", None) else None,
            )
            self.case.equipment.append(conv_b)

            # Create DC link
            link_id = make_dc_link_id(
                self.case.namespace, "ttdc", conv_a_id, conv_b_id
            )
            link = DcLinkModel(
                id=link_id,
                technology=DcTechnology.TTDC,
                from_converter_id=conv_a_id,
                to_converter_id=conv_b_id,
                in_service=hvdc.active,
                rating_mw=getattr(hvdc, "rate", None),
            )
            self.case.dc_links.append(link)

    def _parse_vsc(self) -> None:
        """Parse VSC devices from VeraGrid."""
        # VSC devices are typically point-to-point; parse as converter pairs
        # Note: In VeraGrid, VSC might be individual converters
        for idx, vsc in enumerate(self._grid.vsc_devices):
            bus_psse = self._get_psse_number(vsc.bus_from)
            bus_id = self._get_bus_id(bus_psse)

            if not bus_id:
                self.case.warnings.append(f"VSC {vsc.name}: dangling reference")
                continue

            # Create converter equipment
            eq_id = make_equipment_id(
                self.case.namespace, "CONVERTER_VSC", bus_psse, vsc.name, idx
            )

            equipment = EquipmentModel(
                id=eq_id,
                bus_id=bus_id,
                kind=EquipmentKind.CONVERTER_VSC,
                name=vsc.name,
                in_service=vsc.active,
                p_mw=getattr(vsc, "P", None),
                q_mvar=getattr(vsc, "Q", None),
            )

            self.case.equipment.append(equipment)


def parse_case_file(file_path: Path, file_id: str, file_format: str) -> tuple[ParsedCase, CaseSummary]:
    """
    Parse a case file and return the parsed case and summary.

    Args:
        file_path: Path to the file
        file_id: Unique file identifier
        file_format: File format ("raw" or "rawx")

    Returns:
        Tuple of (ParsedCase, CaseSummary)
    """
    adapter = VeraGridAdapter(file_path, file_id, file_format)
    case = adapter.parse()
    summary = adapter.get_summary()
    return case, summary
