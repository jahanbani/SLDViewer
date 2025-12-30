"""RAW/RAWX file parser for SLD Viewer.

Uses VeraGrid to parse RAW/RAWX files and convert to our canonical models.
Includes substation detection/inference.
"""

import sys
import uuid
from pathlib import Path

from backend.core.graph.models import (
    BranchModel,
    BranchType,
    BusModel,
    EquipmentModel,
    EquipmentType,
    SubstationModel,
)

def _setup_veragrid_path():
    """Set up VeraGrid path and return the path if found."""
    # Try multiple possible locations
    _veragrid_paths = [
        # From this file: backend/core/graph/rawx_parser.py -> project_root/VeraGrid/src
        Path(__file__).resolve().parent.parent.parent.parent / "VeraGrid" / "src",
        # From project root (if run from different location)
        Path.cwd() / "VeraGrid" / "src",
        # Absolute fallback
        Path(__file__).resolve().parent.parent.parent.parent.parent / "VeraGrid" / "src",
    ]
    
    for path in _veragrid_paths:
        if path.exists():
            path_str = str(path.resolve())
            if path_str not in sys.path:
                sys.path.insert(0, path_str)
            return path
    
    return None

# Set up path at module import time
_veragrid_path = _setup_veragrid_path()

# Try to import VeraGrid components
VERAGRID_AVAILABLE = False
_veragrid_import_error = None

def try_import_veragrid():
    """Try to import VeraGrid components. Can be called multiple times.
    
    This is useful when the path might be set up after the module is imported
    (e.g., in uvicorn reload scenarios).
    """
    global VERAGRID_AVAILABLE, _veragrid_import_error, _veragrid_path
    
    # Ensure path is set up
    if not _veragrid_path:
        _veragrid_path = _setup_veragrid_path()
    
    # Make sure path is in sys.path
    path_str = None
    if _veragrid_path:
        path_str = str(_veragrid_path.resolve())
        if path_str not in sys.path:
            sys.path.insert(0, path_str)
    
    # Clear import cache for VeraGridEngine modules to force re-import
    # Python caches failed imports, so we need to clear them
    modules_to_remove = [
        key for key in sys.modules.keys() 
        if key.startswith('VeraGridEngine')
    ]
    for module_name in modules_to_remove:
        del sys.modules[module_name]
    
    try:
        from VeraGridEngine.IO.file_handler import FileOpen
        from VeraGridEngine.IO.raw.rawx_parser_writer import parse_rawx
        from VeraGridEngine.IO.raw.raw_to_veragrid import psse_to_veragrid
        from VeraGridEngine.basic_structures import Logger
        VERAGRID_AVAILABLE = True
        _veragrid_import_error = None
        return True
    except ImportError as e:
        VERAGRID_AVAILABLE = False
        # Include more debugging info
        import traceback
        _veragrid_import_error = (
            f"{str(e)}\n"
            f"Path in sys.path: {path_str in sys.path if path_str else 'N/A'}\n"
            f"VeraGrid path: {_veragrid_path}\n"
            f"Traceback: {traceback.format_exc()}"
        )
        return False

# Try initial import
try_import_veragrid()


def parse_file(file_path: str) -> tuple[list[BusModel], list[BranchModel], list[EquipmentModel], list[SubstationModel]]:
    """Parse a RAW/RAWX file and return buses, branches, equipment, and substations.

    Uses VeraGrid to parse the file and convert to our canonical models.
    Automatically detects/infers substations using VeraGrid's topology analysis.

    Args:
        file_path: Path to the RAW/RAWX file

    Returns:
        Tuple of (buses, branches, equipment, substations) lists.
        Buses will have substation_id set if substations were detected.

    Raises:
        NotImplementedError: If VeraGrid is not available
        FileNotFoundError: If the file doesn't exist
        ValueError: If parsing fails
    """
    # Try to import VeraGrid if not already available (in case path was set up after module import)
    if not VERAGRID_AVAILABLE:
        # Try one more time - path might have been set up after module import
        try_import_veragrid()
    
    if not VERAGRID_AVAILABLE:
        error_msg = (
            "VeraGrid is not available. Cannot parse RAW/RAWX files. "
            "Please ensure VeraGrid is present at ./VeraGrid/src and importable."
        )
        if _veragrid_import_error:
            error_msg += f" Import diagnostics: {_veragrid_import_error}"
        if _veragrid_path:
            error_msg += f" Checked path: {_veragrid_path}"
        else:
            error_msg += " Could not locate VeraGrid/src directory."
        raise NotImplementedError(error_msg)

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    file_ext = path.suffix.lower()
    if file_ext not in [".raw", ".rawx"]:
        raise ValueError(f"Unsupported file extension: {file_ext}. Expected .raw or .rawx")

    # Parse using VeraGrid
    # Import VeraGrid components (must be imported here since they're only available when VERAGRID_AVAILABLE)
    from VeraGridEngine.IO.file_handler import FileOpen
    from VeraGridEngine.IO.raw.rawx_parser_writer import parse_rawx
    from VeraGridEngine.IO.raw.raw_to_veragrid import psse_to_veragrid
    from VeraGridEngine.basic_structures import Logger
    from VeraGridEngine.Topology import detect_substations as vg_detect_substations
    
    logger = Logger()
    
    if file_ext == ".rawx":
        # Parse RAWX file
        psse_grid = parse_rawx(str(path), logger=logger)
        circuit = psse_to_veragrid(psse_circuit=psse_grid, logger=logger)
    else:
        # Parse RAW file using FileOpen
        file_handler = FileOpen(str(path))
        circuit = file_handler.open()
        if circuit is None:
            raise ValueError(f"Failed to parse RAW file: {file_path}")

    # Detect/infer substations using VeraGrid's topology analysis
    # This assigns bus.substation and creates VoltageLevel objects
    veragrid_substations_available = False
    try:
        vg_detect_substations(circuit, r_x_threshold=1e-3)
        # Check if any substations were actually detected
        if circuit.substations and len(circuit.substations) > 0:
            veragrid_substations_available = True
    except Exception as e:
        # Substation detection failed - will use fallback inference
        print(f"Warning: VeraGrid substation detection failed: {e}")

    # Build substation ID map (VeraGrid substation -> our UUID)
    substation_id_map = {}  # Map VeraGrid substation object to our substation ID
    substations = []

    # Extract substations from VeraGrid if available
    if veragrid_substations_available:
        # Extract substations from the circuit (populated by detect_substations)
        for vg_sub in circuit.substations:
            sub_id = str(uuid.uuid4())
            substation_id_map[vg_sub] = sub_id

            # Collect voltage levels from buses in this substation
            voltage_levels = set()
            for vg_bus in circuit.buses:
                if hasattr(vg_bus, 'substation') and vg_bus.substation is vg_sub:
                    voltage_levels.add(vg_bus.Vnom)

            voltage_levels_list = sorted(voltage_levels)
            nominal_kv = max(voltage_levels_list) if voltage_levels_list else None

            # Get area/zone from substation or first bus
            area_num = None
            zone_num = None
            if hasattr(vg_sub, 'area') and vg_sub.area is not None:
                try:
                    area_code = getattr(vg_sub.area, "code", None) or getattr(vg_sub.area, "name", None)
                    area_num = int(area_code) if area_code and str(area_code).isdigit() else None
                except (ValueError, AttributeError):
                    pass
            if hasattr(vg_sub, 'zone') and vg_sub.zone is not None:
                try:
                    zone_code = getattr(vg_sub.zone, "code", None) or getattr(vg_sub.zone, "name", None)
                    zone_num = int(zone_code) if zone_code and str(zone_code).isdigit() else None
                except (ValueError, AttributeError):
                    pass

            substation = SubstationModel(
                id=sub_id,
                name=vg_sub.name or f"Substation_{len(substations) + 1}",
                area=area_num,
                zone=zone_num,
                nominal_kv=nominal_kv,
                voltage_levels=voltage_levels_list,
                latitude=vg_sub.latitude if hasattr(vg_sub, 'latitude') else None,
                longitude=vg_sub.longitude if hasattr(vg_sub, 'longitude') else None,
            )
            substations.append(substation)

    # Convert buses
    buses = []
    bus_id_map = {}  # Map VeraGrid bus to our bus ID
    
    for idx, vg_bus in enumerate(circuit.buses):
        # Generate UUID for internal ID
        bus_id = str(uuid.uuid4())
        bus_id_map[vg_bus] = bus_id
        
        # Extract PSSE bus number from code (usually numeric string)
        try:
            psse_number = int(vg_bus.code) if vg_bus.code else idx + 1
        except (ValueError, AttributeError):
            psse_number = idx + 1
        
        # Get area and zone numbers
        # Try to extract from area/zone code or name, otherwise default to 1
        try:
            if vg_bus.area:
                # Try code first (might be numeric string), then name
                area_code = getattr(vg_bus.area, "code", None) or getattr(vg_bus.area, "name", None)
                area_num = int(area_code) if area_code and str(area_code).isdigit() else 1
            else:
                area_num = 1
        except (ValueError, AttributeError):
            area_num = 1
        
        try:
            if vg_bus.zone:
                zone_code = getattr(vg_bus.zone, "code", None) or getattr(vg_bus.zone, "name", None)
                zone_num = int(zone_code) if zone_code and str(zone_code).isdigit() else 1
            else:
                zone_num = 1
        except (ValueError, AttributeError):
            zone_num = 1
        
        owner_num = 1  # Default owner (not always in VeraGrid)
        
        # Get substation ID for this bus (if detected)
        substation_id = None
        if hasattr(vg_bus, 'substation') and vg_bus.substation is not None:
            substation_id = substation_id_map.get(vg_bus.substation)
        
        bus = BusModel(
            id=bus_id,
            psse_number=psse_number,
            name=vg_bus.name or f"Bus {psse_number}",
            base_kv=vg_bus.Vnom,  # Nominal voltage in kV
            area=area_num,
            zone=zone_num,
            owner=owner_num,
            vm=vg_bus.Vm0 if hasattr(vg_bus, "Vm0") else None,
            va=vg_bus.Va0 if hasattr(vg_bus, "Va0") else None,
            vmax=vg_bus.Vmax if hasattr(vg_bus, "Vmax") else None,
            vmin=vg_bus.Vmin if hasattr(vg_bus, "Vmin") else None,
            substation_id=substation_id,
            latitude=vg_bus.latitude if hasattr(vg_bus, "latitude") else None,
            longitude=vg_bus.longitude if hasattr(vg_bus, "longitude") else None,
        )
        buses.append(bus)

    # Convert branches (lines and transformers)
    branches = []
    branch_counter = 0
    
    # Process lines
    for vg_line in circuit.lines:
        if not vg_line.active or vg_line.bus_from is None or vg_line.bus_to is None:
            continue
        
        from_bus_id = bus_id_map.get(vg_line.bus_from)
        to_bus_id = bus_id_map.get(vg_line.bus_to)
        
        if from_bus_id is None or to_bus_id is None:
            continue
        
        # Get impedance values (in per unit)
        r = vg_line.R if hasattr(vg_line, "R") else 0.0
        x = vg_line.X if hasattr(vg_line, "X") else 0.0
        b = vg_line.B if hasattr(vg_line, "B") else 0.0
        g = 0.0  # Conductance (usually zero for lines)
        
        # Zero and negative sequence
        r0 = vg_line.R0 if hasattr(vg_line, "R0") else None
        x0 = vg_line.X0 if hasattr(vg_line, "X0") else None
        b0 = vg_line.B0 if hasattr(vg_line, "B0") else None
        g0 = None
        
        r2 = vg_line.R2 if hasattr(vg_line, "R2") else None
        x2 = vg_line.X2 if hasattr(vg_line, "X2") else None
        b2 = vg_line.B2 if hasattr(vg_line, "B2") else None
        g2 = None
        
        # Rating
        rating_mva = vg_line.rate if hasattr(vg_line, "rate") else 1.0
        
        branch_id = str(uuid.uuid4())
        branch = BranchModel(
            id=branch_id,
            from_bus_id=from_bus_id,
            to_bus_id=to_bus_id,
            circuit=vg_line.code or str(branch_counter),
            type="line",
            r=r,
            x=x,
            b=b,
            g=g,
            r0=r0,
            x0=x0,
            b0=b0,
            g0=g0,
            r2=r2,
            x2=x2,
            b2=b2,
            g2=g2,
            rating_mva=rating_mva,
            length=vg_line.length if hasattr(vg_line, "length") else None,
        )
        branches.append(branch)
        branch_counter += 1
    
    # Process two-winding transformers
    for vg_xfmr in circuit.transformers2w:
        if not vg_xfmr.active or vg_xfmr.bus_from is None or vg_xfmr.bus_to is None:
            continue
        
        from_bus_id = bus_id_map.get(vg_xfmr.bus_from)
        to_bus_id = bus_id_map.get(vg_xfmr.bus_to)
        
        if from_bus_id is None or to_bus_id is None:
            continue
        
        # Transformer impedance
        r = vg_xfmr.R if hasattr(vg_xfmr, "R") else 0.0
        x = vg_xfmr.X if hasattr(vg_xfmr, "X") else 0.0
        b = vg_xfmr.B if hasattr(vg_xfmr, "B") else 0.0
        g = 0.0
        
        # Zero and negative sequence
        r0 = vg_xfmr.R0 if hasattr(vg_xfmr, "R0") else None
        x0 = vg_xfmr.X0 if hasattr(vg_xfmr, "X0") else None
        b0 = vg_xfmr.B0 if hasattr(vg_xfmr, "B0") else None
        g0 = None
        
        r2 = vg_xfmr.R2 if hasattr(vg_xfmr, "R2") else None
        x2 = vg_xfmr.X2 if hasattr(vg_xfmr, "X2") else None
        b2 = vg_xfmr.B2 if hasattr(vg_xfmr, "B2") else None
        g2 = None
        
        # Rating and tap
        rating_mva = vg_xfmr.rate if hasattr(vg_xfmr, "rate") else 1.0
        tap_module = vg_xfmr.tap_module if hasattr(vg_xfmr, "tap_module") else None
        tap_phase = vg_xfmr.tap_phase if hasattr(vg_xfmr, "tap_phase") else None
        
        branch_id = str(uuid.uuid4())
        branch = BranchModel(
            id=branch_id,
            from_bus_id=from_bus_id,
            to_bus_id=to_bus_id,
            circuit=vg_xfmr.code or str(branch_counter),
            type="xfmr",
            r=r,
            x=x,
            b=b,
            g=g,
            r0=r0,
            x0=x0,
            b0=b0,
            g0=g0,
            r2=r2,
            x2=x2,
            b2=b2,
            g2=g2,
            rating_mva=rating_mva,
            tap_module=tap_module,
            tap_phase=tap_phase,
        )
        branches.append(branch)
        branch_counter += 1
    
    # Process three-winding transformers (split into two branches)
    for vg_xfmr3 in circuit.transformers3w:
        if not vg_xfmr3.active:
            continue
        
        # Three-winding transformers have bus_from, bus_to, and bus_internal
        # We'll create two branches: from->internal and internal->to
        # For now, skip internal bus and create from->to branch
        if vg_xfmr3.bus_from is None or vg_xfmr3.bus_to is None:
            continue
        
        from_bus_id = bus_id_map.get(vg_xfmr3.bus_from)
        to_bus_id = bus_id_map.get(vg_xfmr3.bus_to)
        
        if from_bus_id is None or to_bus_id is None:
            continue
        
        # Use primary winding impedance
        r = vg_xfmr3.R1 if hasattr(vg_xfmr3, "R1") else 0.0
        x = vg_xfmr3.X1 if hasattr(vg_xfmr3, "X1") else 0.0
        b = vg_xfmr3.B1 if hasattr(vg_xfmr3, "B1") else 0.0
        g = 0.0
        
        rating_mva = vg_xfmr3.rate if hasattr(vg_xfmr3, "rate") else 1.0
        
        branch_id = str(uuid.uuid4())
        branch = BranchModel(
            id=branch_id,
            from_bus_id=from_bus_id,
            to_bus_id=to_bus_id,
            circuit=vg_xfmr3.code or str(branch_counter),
            type="xfmr3",
            r=r,
            x=x,
            b=b,
            g=g,
            rating_mva=rating_mva,
        )
        branches.append(branch)
        branch_counter += 1

    # Parse equipment (generators, loads, shunts)
    equipment = []
    
    # Process generators
    for vg_gen in circuit.generators:
        if vg_gen.bus is None:
            continue
        bus_id = bus_id_map.get(vg_gen.bus)
        if bus_id is None:
            continue
        
        eq_id = str(uuid.uuid4())
        p_mw = vg_gen.P if hasattr(vg_gen, "P") else None
        q_mvar = vg_gen.Q if hasattr(vg_gen, "Q") else None
        
        eq = EquipmentModel(
            id=eq_id,
            bus_id=bus_id,
            type=EquipmentType.GENERATOR,
            name=vg_gen.name or vg_gen.code or f"Gen@{vg_gen.bus.code}",
            status=vg_gen.active if hasattr(vg_gen, "active") else True,
            p_mw=p_mw,
            q_mvar=q_mvar,
            metadata={
                "mbase": vg_gen.Snom if hasattr(vg_gen, "Snom") else None,
                "pmax": vg_gen.Pmax if hasattr(vg_gen, "Pmax") else None,
                "pmin": vg_gen.Pmin if hasattr(vg_gen, "Pmin") else None,
                "qmax": vg_gen.Qmax if hasattr(vg_gen, "Qmax") else None,
                "qmin": vg_gen.Qmin if hasattr(vg_gen, "Qmin") else None,
            },
        )
        equipment.append(eq)
    
    # Process loads
    for vg_load in circuit.loads:
        if vg_load.bus is None:
            continue
        bus_id = bus_id_map.get(vg_load.bus)
        if bus_id is None:
            continue
        
        eq_id = str(uuid.uuid4())
        p_mw = vg_load.P if hasattr(vg_load, "P") else None
        q_mvar = vg_load.Q if hasattr(vg_load, "Q") else None
        
        eq = EquipmentModel(
            id=eq_id,
            bus_id=bus_id,
            type=EquipmentType.LOAD,
            name=vg_load.name or vg_load.code or f"Load@{vg_load.bus.code}",
            status=vg_load.active if hasattr(vg_load, "active") else True,
            p_mw=p_mw,
            q_mvar=q_mvar,
            metadata={},
        )
        equipment.append(eq)
    
    # Process shunts (fixed shunts)
    for vg_shunt in circuit.shunts:
        if vg_shunt.bus is None:
            continue
        bus_id = bus_id_map.get(vg_shunt.bus)
        if bus_id is None:
            continue
        
        eq_id = str(uuid.uuid4())
        # Shunts typically have G and B in per unit or MW/Mvar
        g_mw = vg_shunt.G if hasattr(vg_shunt, "G") else None
        b_mvar = vg_shunt.B if hasattr(vg_shunt, "B") else None
        
        eq = EquipmentModel(
            id=eq_id,
            bus_id=bus_id,
            type=EquipmentType.SHUNT,
            name=vg_shunt.name or vg_shunt.code or f"Shunt@{vg_shunt.bus.code}",
            status=vg_shunt.active if hasattr(vg_shunt, "active") else True,
            p_mw=g_mw,  # G in MW (at 1 pu voltage)
            q_mvar=b_mvar,  # B in Mvar (at 1 pu voltage)
            metadata={},
        )
        equipment.append(eq)

    # Fallback: Use our own substation inference if VeraGrid didn't provide substations
    if not veragrid_substations_available or not substations:
        print("Using fallback substation inference...")
        from backend.core.graph.substations import infer_substations, assign_substations_to_buses

        # Infer substations from topology
        inferred_substations, bus_to_sub_map = infer_substations(buses, branches)

        # Update buses with substation assignments
        buses = assign_substations_to_buses(buses, bus_to_sub_map)

        # Use inferred substations
        substations = inferred_substations

        print(f"Inferred {len(substations)} substations from topology")

    return buses, branches, equipment, substations
