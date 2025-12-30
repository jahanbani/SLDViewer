#!/usr/bin/env python3
"""End-to-end test script for SLD Viewer.

Tests the full flow: parse file -> build graph -> generate view -> convert to Cytoscape.
"""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from backend.core.config import get_settings
from backend.core.graph import (
    cytoscape_converter,
    graph_builder,
    rawx_parser,
    view_engine,
)
from backend.core.graph.models import ViewMode, ViewSpec


def test_e2e():
    """Test end-to-end flow with ieee118.rawx."""
    print("=" * 60)
    print("SLD Viewer End-to-End Test")
    print("=" * 60)
    
    # Step 1: Parse file
    print("\n1. Parsing ieee118.rawx...")
    try:
        buses, branches = rawx_parser.parse_file("ieee118.rawx")
        print(f"   [OK] Parsed {len(buses)} buses and {len(branches)} branches")
        print(f"   Sample bus: {buses[0].name} (PSSE #{buses[0].psse_number}, {buses[0].base_kv}kV)")
    except Exception as e:
        print(f"   [FAIL] Failed to parse file: {e}")
        return False
    
    # Step 2: Build graph
    print("\n2. Building graph...")
    try:
        handle = graph_builder.build_graphs(buses, branches)
        print(f"   [OK] Graph built: {handle.bus_graph.number_of_nodes()} nodes, {handle.bus_graph.number_of_edges()} edges")
    except Exception as e:
        print(f"   [FAIL] Failed to build graph: {e}")
        return False
    
    # Step 3: Generate view
    print("\n3. Generating view (BUS mode, degrees=1)...")
    try:
        settings = get_settings()
        spec = ViewSpec(
            mode=ViewMode.BUS,
            center_bus_numbers=[1],  # Start from bus 1
            degrees=1,
        )
        result = view_engine.view(handle, spec, settings)
        print(f"   [OK] View generated: {len(result.buses)} buses, {len(result.branches)} branches")
        print(f"   Meta: {result.meta}")
    except Exception as e:
        print(f"   [FAIL] Failed to generate view: {e}")
        return False
    
    # Step 4: Convert to Cytoscape
    print("\n4. Converting to Cytoscape JSON...")
    try:
        cytoscape_data = cytoscape_converter.view_result_to_cytoscape(result)
        print(f"   [OK] Converted: {len(cytoscape_data['elements']['nodes'])} nodes, {len(cytoscape_data['elements']['edges'])} edges")
        print(f"   Meta keys: {list(cytoscape_data['meta'].keys())}")
    except Exception as e:
        print(f"   [FAIL] Failed to convert: {e}")
        return False
    
    print("\n" + "=" * 60)
    print("[SUCCESS] All tests passed!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = test_e2e()
    sys.exit(0 if success else 1)

