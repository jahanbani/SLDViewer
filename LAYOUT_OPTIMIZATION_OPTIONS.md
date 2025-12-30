# Layout Optimization Options for Power System Diagrams

## User's Idea (Excellent!)

**Concept**: Pre-compute optimal bus positions for entire network once, then always use those positions instead of recalculating every time.

**Benefits**:
- ✅ Consistent layout (same network always looks the same)
- ✅ No more random positions or redrawing
- ✅ Can use sophisticated optimization algorithms (not limited by real-time performance)
- ✅ Positions stored with file (like CAD software)

**Constraints**:
- Minimize line crossings
- Minimize line overlap with nodes
- Keep transformer-connected buses within radius R (e.g., 50px)
- Keep substation buses grouped together
- Respect voltage levels (optional: higher voltage at top)

This is **exactly** how professional tools like PSS/E, PowerWorld, and ETAP work!

---

## Option 1: Backend Optimization with NetworkX + SciPy (RECOMMENDED)

**Best for**: Full control, sophisticated constraints, Python ecosystem

### Implementation

#### Backend: Optimization Algorithm
```python
# backend/core/graph/layout_optimizer.py

import numpy as np
from scipy.optimize import minimize
import networkx as nx

def optimize_layout(
    buses: list[BusModel],
    branches: list[BranchModel],
    transformer_max_distance: float = 50.0
) -> dict[str, tuple[float, float]]:
    """
    Compute optimal (x, y) positions for all buses.

    Objective: Minimize total energy
    - Line crossing energy
    - Line length energy (weighted by type)
    - Overlap penalty

    Constraints:
    - Transformer-connected buses within max_distance
    - Substation buses stay clustered
    - Buses don't overlap (minimum separation)
    """

    n_buses = len(buses)
    bus_id_to_idx = {bus.id: i for i, bus in enumerate(buses)}

    # Initial positions (can start with force-directed as seed)
    x0 = np.random.randn(n_buses * 2) * 100  # Random or use COSE initial

    # Build constraints
    constraints = []

    # Constraint: Transformer buses within max_distance
    for branch in branches:
        if branch.type in ["xfmr", "xfmr3"]:
            i = bus_id_to_idx[branch.from_bus_id]
            j = bus_id_to_idx[branch.to_bus_id]

            def transformer_constraint(positions, i=i, j=j):
                xi, yi = positions[2*i], positions[2*i+1]
                xj, yj = positions[2*j], positions[2*j+1]
                dist = np.sqrt((xi - xj)**2 + (yi - yj)**2)
                return transformer_max_distance - dist  # Must be >= 0

            constraints.append({
                'type': 'ineq',
                'fun': transformer_constraint
            })

    # Constraint: Minimum bus separation (avoid overlap)
    min_separation = 30.0
    for i in range(n_buses):
        for j in range(i+1, n_buses):
            def separation_constraint(positions, i=i, j=j):
                xi, yi = positions[2*i], positions[2*i+1]
                xj, yj = positions[2*j], positions[2*j+1]
                dist = np.sqrt((xi - xj)**2 + (yi - yj)**2)
                return dist - min_separation  # Must be >= 0

            constraints.append({
                'type': 'ineq',
                'fun': separation_constraint
            })

    # Objective function
    def objective(positions):
        energy = 0.0

        # Line length energy (weighted by type)
        for branch in branches:
            i = bus_id_to_idx[branch.from_bus_id]
            j = bus_id_to_idx[branch.to_bus_id]
            xi, yi = positions[2*i], positions[2*i+1]
            xj, yj = positions[2*j], positions[2*j+1]
            length = np.sqrt((xi - xj)**2 + (yi - yj)**2)

            if branch.type in ["xfmr", "xfmr3"]:
                # Transformers: want short (target 40px)
                energy += (length - 40)**2
            else:
                # Transmission: want longer (target 150px)
                energy += 0.1 * (length - 150)**2

        # Line crossing penalty (expensive to compute, simplified)
        # For each pair of lines, check if they cross
        # (Omitted for brevity - can add if needed)

        # Keep substation buses together
        for sub_id, sub_buses in buses_by_substation.items():
            # Minimize variance of positions within substation
            sub_indices = [bus_id_to_idx[bus.id] for bus in sub_buses]
            xs = [positions[2*i] for i in sub_indices]
            ys = [positions[2*i+1] for i in sub_indices]
            energy += np.var(xs) + np.var(ys)

        return energy

    # Run optimization
    result = minimize(
        objective,
        x0,
        method='SLSQP',  # Sequential Least Squares Programming
        constraints=constraints,
        options={'maxiter': 1000}
    )

    # Extract positions
    positions = {}
    for i, bus in enumerate(buses):
        x, y = result.x[2*i], result.x[2*i+1]
        positions[bus.id] = (x, y)

    return positions
```

#### API Endpoint
```python
# backend/api/routers/graphs.py

@router.post("/{file_id}/optimize-layout")
async def optimize_layout(file_id: str) -> dict[str, Any]:
    """
    Compute optimal layout for entire network.
    Returns positions for all buses.

    Expensive operation (may take 5-30 seconds for large networks).
    Results should be cached in database.
    """
    handle = graphs_cache[file_id]

    positions = layout_optimizer.optimize_layout(
        list(handle.bus_by_id.values()),
        list(handle.branch_by_id.values())
    )

    return {
        "positions": positions,  # {bus_id: [x, y]}
        "metadata": {
            "algorithm": "scipy_slsqp",
            "constraints": ["transformer_distance", "min_separation"],
        }
    }
```

#### Frontend Usage
```typescript
// 1. On first load, check if positions exist
// 2. If not, call /optimize-layout (show progress bar)
// 3. Store positions in browser localStorage
// 4. Always use stored positions (preset layout)

const fetchOptimizedLayout = async (fileId: string) => {
  const cached = localStorage.getItem(`layout_${fileId}`);
  if (cached) return JSON.parse(cached);

  const response = await fetch(`/api/v1/graphs/${fileId}/optimize-layout`, {
    method: 'POST'
  });
  const data = await response.json();

  localStorage.setItem(`layout_${fileId}`, JSON.stringify(data.positions));
  return data.positions;
};

// In Cytoscape initialization:
layout: {
  name: "preset",
  positions: optimizedPositions,
  fit: true,
  animate: false,
}
```

**Pros**:
- ✅ Full control over optimization
- ✅ Can add any constraints
- ✅ Python ecosystem (NetworkX, SciPy, NumPy)
- ✅ Positions stored permanently

**Cons**:
- ❌ Slow for large networks (>500 buses may take 30+ seconds)
- ❌ Need to implement constraint checking
- ❌ Requires optimization expertise to tune

---

## Option 2: Specialized Layout Algorithms (Cytoscape Extensions)

### Option 2A: cytoscape-cola (Constraint-Based Layout)

**Best for**: Medium complexity, good performance

```bash
npm install cytoscape-cola
```

```typescript
import cola from 'cytoscape-cola';
cytoscape.use(cola);

layout: {
  name: 'cola',
  animate: false,

  // Constraints
  alignment: [
    // Align buses by voltage level
    {axis: 'y', offsets: voltageLevelOffsets}
  ],

  // Distance constraints
  distanceMatrix: (node1, node2) => {
    // If connected by transformer, max distance 50
    if (isTransformerConnection(node1, node2)) {
      return {ideal: 40, max: 50};
    }
    return {ideal: 150, max: 300};
  },

  // Overlap avoidance (built-in!)
  avoidOverlap: true,

  // Flow direction (optional)
  flow: {axis: 'y', minSeparation: 100}, // Top-to-bottom
}
```

**Pros**:
- ✅ Built-in overlap avoidance
- ✅ Constraint-based (can specify transformer distances)
- ✅ Reasonably fast
- ✅ Well-maintained library

**Cons**:
- ❌ Less control than custom optimization
- ❌ May not converge for complex constraints

### Option 2B: cytoscape-fcose (Fast Compound Spring Embedder)

**Best for**: Large networks with substations (compound nodes)

```bash
npm install cytoscape-fcose
```

```typescript
import fcose from 'cytoscape-fcose';
cytoscape.use(fcose);

layout: {
  name: 'fcose',
  quality: 'proof', // 'default' or 'proof' (higher quality)

  // Ideal edge lengths
  idealEdgeLength: (edge) => {
    if (edge.data('type') === 'xfmr') return 40;
    return 150;
  },

  // Compound node support (substations)
  nestingFactor: 0.5, // Tight grouping

  // Overlap removal
  nodeSeparation: 75,

  // Fast!
  numIter: 2500,
}
```

**Pros**:
- ✅ Very fast (optimized for large graphs)
- ✅ Excellent compound node support
- ✅ Good overlap removal
- ✅ Consistent results

**Cons**:
- ❌ Can't specify hard constraints (like max transformer distance)
- ❌ Less control than optimization

### Option 2C: ELK (Eclipse Layout Kernel) via elkjs

**Best for**: Hierarchical/layered layouts (voltage levels as layers)

```bash
npm install elkjs
npm install cytoscape-elk
```

```typescript
import elk from 'cytoscape-elk';
cytoscape.use(elk);

layout: {
  name: 'elk',
  elk: {
    algorithm: 'layered', // or 'force', 'stress', 'mrtree'

    // Layering (voltage levels)
    'elk.direction': 'DOWN', // Top to bottom
    'elk.layered.spacing.nodeNodeBetweenLayers': 100,

    // Edge routing
    'elk.edgeRouting': 'ORTHOGONAL', // or 'SPLINES'

    // Transformer handling
    'elk.spacing.edgeEdge': 10,
    'elk.spacing.edgeNode': 20,
  }
}
```

**Pros**:
- ✅ Professional-looking hierarchical layouts
- ✅ Voltage levels as layers (automatic)
- ✅ Excellent edge routing (no overlaps)
- ✅ Used in Eclipse IDE (battle-tested)

**Cons**:
- ❌ Opinionated (less control)
- ❌ Requires understanding of ELK options
- ❌ Larger bundle size

---

## Option 3: Hybrid Approach (BEST BALANCE)

Combine backend optimization with frontend refinement.

### Phase 1: Backend Pre-Computation
```python
# On file upload, compute initial positions
positions = optimize_layout(buses, branches)

# Store in database
layout_cache[file_id] = {
    "positions": positions,
    "algorithm": "scipy_slsqp",
    "timestamp": datetime.now(),
}
```

### Phase 2: Frontend Adjustment
```typescript
// Use backend positions as starting point
layout: {
  name: 'preset',
  positions: backendPositions,
  fit: true,
}

// Optional: Allow user to run "Re-optimize" locally
const reoptimize = () => {
  cy.layout({
    name: 'cola',
    positions: cy.nodes().positions(), // Start from current
    // ... run refinement
  }).run();
};
```

**Pros**:
- ✅ Fast initial load (positions pre-computed)
- ✅ User can refine if needed
- ✅ Positions stored in database (consistent across sessions)
- ✅ No real-time optimization overhead

**Cons**:
- ❌ More complex implementation
- ❌ Need database schema for positions

---

## Option 4: Graph Drawing Algorithms (Academic)

### Force-Directed with Constraints (Kamada-Kawai + Constraints)

```python
import networkx as nx

def kamada_kawai_with_constraints(G, constraints):
    """
    Modified Kamada-Kawai algorithm with constraints.
    """
    pos = nx.kamada_kawai_layout(G)

    # Apply constraints iteratively
    for iteration in range(100):
        for constraint in constraints:
            # Adjust positions to satisfy constraint
            # (Gradient descent or projection)
            pass

    return pos
```

### Stress Minimization (Pivot MDS)

```python
def stress_minimization_layout(G, transformer_edges):
    """
    Minimize stress while keeping transformer buses close.
    """
    # Multi-dimensional scaling with distance constraints
    pos = nx.spring_layout(
        G,
        k=1/sqrt(n),  # Optimal distance
        iterations=50
    )
    return pos
```

**Pros**:
- ✅ Theoretically optimal
- ✅ Well-studied algorithms
- ✅ Can add custom constraints

**Cons**:
- ❌ Requires implementation from scratch
- ❌ May not converge
- ❌ Academic (less practical)

---

## Option 5: Machine Learning (Overkill but Cool)

Train a neural network to predict optimal positions.

```python
# Train on thousands of power system layouts
# Input: Graph structure (adjacency matrix, node features)
# Output: (x, y) positions for each node

model = TransformerLayoutNet()  # Graph neural network
positions = model.predict(graph)
```

**Pros**:
- ✅ Very fast inference (<100ms)
- ✅ Learns from real-world layouts
- ✅ Can handle complex patterns

**Cons**:
- ❌ Requires training data (thousands of layouts)
- ❌ Black box (hard to debug)
- ❌ Massive overkill for this project

---

## Recommended Approach

### For Your Project (Power Systems, <500 buses):

**Hybrid Approach: Backend Optimization + Frontend Caching**

1. **Backend**: Use **NetworkX + SciPy** for optimization
   - Run once when file is uploaded
   - Store positions in database
   - Constraints: transformer distance, min separation, substation grouping

2. **Frontend**: Use **preset layout** with stored positions
   - Always use backend-computed positions
   - No real-time force-directed
   - User can manually adjust individual buses (saved to localStorage)

3. **Fallback**: If backend optimization fails or times out
   - Use **cytoscape-cola** with constraints
   - Good results in <1 second

### Implementation Plan

**Phase 1: Basic Backend Optimization (2-3 hours)**
```python
# Implement simple optimization in backend/core/graph/layout_optimizer.py
# - Minimize line lengths (weighted by type)
# - Constraint: transformer buses within 50px
# - Store positions in file metadata or database
```

**Phase 2: API Endpoint (30 minutes)**
```python
# POST /api/v1/graphs/{file_id}/optimize-layout
# Returns: {positions: {bus_id: [x, y]}}
```

**Phase 3: Frontend Integration (1 hour)**
```typescript
// Fetch optimized positions
// Use preset layout
// Cache in localStorage
```

**Phase 4: User Controls (30 minutes)**
```typescript
// Add "Re-optimize" button
// Add "Reset to Optimized" button
// Allow manual positioning with save
```

---

## Why Backend Optimization is Best

**For power system diagrams**:
1. ✅ Topology is relatively stable (network structure doesn't change often)
2. ✅ User wants consistent layouts (same network = same diagram)
3. ✅ Can use sophisticated algorithms (not limited by browser performance)
4. ✅ Positions are data (should be stored with file, like CAD)
5. ✅ Professional tools all work this way (PSS/E, PowerWorld, ETAP)

**User workflow**:
```
1. Upload RAWX file
2. Backend: "Optimizing layout... 10 seconds"
3. Graph appears with perfect layout
4. User can manually adjust if needed
5. Adjustments saved
6. Next time: instant load with saved positions
```

---

## About Redrawing Issue

The substation toggle redraw might be happening because:

**Hypothesis 1**: `showSubstationGroups` changes filteredNodes
```typescript
const filteredNodes = showSubstationGroups
  ? elements.nodes
  : elements.nodes.filter(...)
```
This creates a NEW array, triggering useEffect dependency.

**Fix**: Use `useMemo` for filteredNodes
```typescript
const filteredNodes = useMemo(() => {
  return showSubstationGroups
    ? elements.nodes
    : elements.nodes.filter(n => n.data.kind !== "substation_group");
}, [elements, showSubstationGroups]);
```

**Want me to**:
1. Fix the redrawing issue first?
2. Or implement backend optimization now?

Let me know which you prefer!
