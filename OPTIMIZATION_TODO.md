# SLD Viewer Layout Optimization TODO

This file tracks layout issues that will need proper graph optimization to solve.
Current heuristics (edge routing direction selection, terminal positioning) provide partial solutions,
but a comprehensive optimization approach will be needed for complex cases.

## Issues Requiring Full Optimization

### 1. Node Positioning to Minimize Edge Crossings
- **Current state**: COSE layout provides initial positions, but doesn't optimize for orthogonal edge routing
- **Problem**: Nodes may be placed such that edges must cross through other nodes
- **Solution**: Optimize node positions considering taxi (orthogonal) edge paths

### 2. Edge-Node Overlap
- **Current state**: `optimizeEdgeRouting()` tries both horizontal-first and vertical-first taxi directions
- **Problem**: Sometimes BOTH directions cause collisions (no collision-free path exists without moving nodes)
- **Solution**: Move nodes to create collision-free paths, or use multi-segment edge routing

### 3. Edge-Edge Overlap/Crossing
- **Current state**: Not addressed
- **Problem**: Multiple edges may share the same path or cross each other unnecessarily
- **Solution**: Edge bundling, or node repositioning to reduce crossings

### 4. Equipment Placement Conflicts
- **Current state**: Equipment placed in fixed positions relative to bus (right side for vertical buses)
- **Problem**: Equipment may overlap with edges from other buses (as seen in image 13 - bus 3 load overlapping with line)
- **Solution**: Consider edge paths when positioning equipment, or move equipment to non-conflicting side

### 5. Substation Compound Node Layout
- **Current state**: Buses within substations use COSE layout
- **Problem**: Internal layout may not be optimal for external connections
- **Solution**: Consider inter-substation connections when laying out intra-substation nodes

### 6. Bus Orientation Selection
- **Current state**: All buses default to vertical
- **Problem**: Different orientations may reduce edge crossings
- **Solution**: Optimize bus orientation based on connection directions

### 7. Terminal Assignment Optimization
- **Current state**: Terminals assigned to sides based on where connected node is
- **Problem**: May not be globally optimal when multiple edges compete for same space
- **Solution**: Global optimization of terminal-to-connection assignments

## Heuristics Currently Implemented (Quick Fixes)

1. **Edge direction selection** (`optimizeEdgeRouting`): Chooses between horizontal-first and vertical-first taxi routing based on collision count
2. **Terminal positioning** (`repositionTerminals`): Places terminals on correct side of bus, with smaller spread for fewer terminals
3. **Equipment as obstacles**: Equipment nodes are now included in collision detection for edge routing

## Recommended Optimization Approach

When implementing full optimization, consider:

1. **Constraint-based optimization** (e.g., OR-Tools, Z3)
   - Define constraints: no edge-node overlaps, minimize edge crossings
   - Variables: node positions, bus orientations, terminal assignments

2. **Force-directed with constraints**
   - Modified COSE that respects orthogonal routing
   - Repulsion forces between edges and nodes

3. **Simulated annealing**
   - Iteratively improve layout by random perturbations
   - Accept improvements, occasionally accept worse solutions to escape local minima

4. **Hierarchical layout**
   - Use Sugiyama-style layered layout for cleaner orthogonal routing
   - May be more appropriate for power system diagrams
