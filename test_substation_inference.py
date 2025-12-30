"""Test script to verify substation inference with real data."""

import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_path))

# Add VeraGrid to path
veragrid_path = Path(__file__).parent / "VeraGrid" / "src"
if veragrid_path.exists():
    sys.path.insert(0, str(veragrid_path))

from backend.core.graph.rawx_parser import parse_file

# Parse the IEEE 118 bus file
file_path = "ieee118.rawx"

print(f"Parsing {file_path}...")
try:
    buses, branches, equipment, substations = parse_file(file_path)

    print(f"\n[SUCCESS] Parsing successful!")
    print(f"  - Buses: {len(buses)}")
    print(f"  - Branches: {len(branches)}")
    print(f"  - Equipment: {len(equipment)}")
    print(f"  - Substations: {len(substations)}")

    # Show some substation details
    if substations:
        print(f"\nSubstation Summary:")
        for i, sub in enumerate(substations[:5]):  # Show first 5
            bus_count = sum(1 for bus in buses if bus.substation_id == sub.id)
            print(f"  {i+1}. {sub.name}")
            print(f"     - Buses: {bus_count}")
            print(f"     - Voltage levels: {sub.voltage_levels} kV")
            print(f"     - Nominal: {sub.nominal_kv} kV")
            print(f"     - Area: {sub.area}, Zone: {sub.zone}")

        if len(substations) > 5:
            print(f"  ... and {len(substations) - 5} more substations")

    # Count buses with vs without substations
    buses_with_sub = sum(1 for bus in buses if bus.substation_id is not None)
    print(f"\nBuses assigned to substations: {buses_with_sub}/{len(buses)}")

    # Show equipment breakdown
    if equipment:
        from collections import Counter
        eq_types = Counter(eq.type for eq in equipment)
        print(f"\nEquipment breakdown:")
        for eq_type, count in eq_types.items():
            print(f"  - {eq_type}: {count}")

except Exception as e:
    print(f"\n[ERROR] {e}")
    import traceback
    traceback.print_exc()
