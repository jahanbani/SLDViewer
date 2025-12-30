import React, { useEffect, useRef, useState, useCallback } from "react";
import cytoscape, { Core, NodeSingular, EdgeSingular } from "cytoscape";

// API base URL - uses Vite proxy in development, env vars in production
const API_BASE_URL = import.meta.env.VITE_API_URL || "";

// Type definitions for API request/response
type ViewMode = "bus" | "substation" | "station_detail";

type ViewSpec = {
  mode: ViewMode;
  center_bus_numbers: number[] | null;
  center_substation_ids: string[] | null;
  degrees: number;
  filters: {
    include_equipment?: boolean;
    equipment_types?: string[] | null;
  };
  layout: string;
  limit: number | null;
};

type BusNodeData = {
  id: string;
  kind: "bus";
  psse_number: number;
  name: string;
  base_kv: number;
  substation_id: string | null;
  area: number;
  zone: number;
  vm: number | null;
  va: number | null;
  vmax: number | null;
  vmin: number | null;
  owner: number;
};

type EquipmentNodeData = {
  id: string;
  kind: "equipment";
  equipment_type: "generator" | "load" | "shunt" | "svc" | "statcom" | "vsc_converter" | "csc_converter" | "other";
  bus_id: string;
  name: string | null;
  status: boolean | null;
  p_mw: number | null;
  q_mvar: number | null;
  metadata: Record<string, unknown>;
};

type BranchEdgeData = {
  id: string;
  kind: "branch";
  type: "line" | "xfmr" | "xfmr3" | "switch" | "dc_line" | "hvdc";
  source: string;
  target: string;
  circuit: string;
  r: number;
  x: number;
  b: number;
  g: number;
  r0: number | null;
  x0: number | null;
  b0: number | null;
  rate_a: number | null;
  rate_b: number | null;
  rate_c: number | null;
  rating_mva: number;
  tap_module: number | null;
  tap_phase: number | null;
  length: number | null;
  p_from_mw: number | null;
  q_from_mvar: number | null;
  p_to_mw: number | null;
  q_to_mvar: number | null;
};

type EquipmentLinkData = {
  id: string;
  kind: "equipment_link";
  source: string;
  target: string;
};

type TransformerLinkData = {
  id: string;
  kind: "transformer_link";
  source: string;
  target: string;
};

type TransformerNodeData = {
  id: string;
  kind: "transformer";
  type: "xfmr" | "xfmr3";
  name: string;
  circuit: string;
  r: number;
  x: number;
  b: number;
  g: number;
  r0: number | null;
  x0: number | null;
  b0: number | null;
  rate_a: number | null;
  rate_b: number | null;
  rate_c: number | null;
  rating_mva: number;
  tap_module: number | null;
  tap_phase: number | null;
  from_bus_id: string;
  to_bus_id: string;
};

type SubstationNodeData = {
  id: string;
  kind: "substation" | "neighbor_substation_stub" | "substation_group";
  name: string;
  area?: number | null;
  zone?: number | null;
  nominal_kv?: number | null;
  voltage_levels?: number[];
  latitude?: number | null;
  longitude?: number | null;
};

type NodeData = BusNodeData | EquipmentNodeData | TransformerNodeData | SubstationNodeData;
type EdgeData = BranchEdgeData | EquipmentLinkData | TransformerLinkData;

type CytoscapeNode = {
  data: NodeData;
};

type CytoscapeEdge = {
  data: EdgeData;
};

type ViewResponse = {
  elements: {
    nodes: CytoscapeNode[];
    edges: CytoscapeEdge[];
  };
  meta: {
    mode: string;
    truncated: boolean;
    node_count: number;
    edge_count: number;
    equipment_count?: number;
    degrees: number;
    limit: number;
  };
};

type GraphViewerProps = {
  fileId: string;
};

// Voltage-based color mapping for buses
function getVoltageColor(baseKv: number): string {
  if (baseKv >= 500) return "#e74c3c"; // Red - EHV
  if (baseKv >= 345) return "#9b59b6"; // Purple
  if (baseKv >= 230) return "#3498db"; // Blue
  if (baseKv >= 115) return "#27ae60"; // Green
  if (baseKv >= 69) return "#f39c12"; // Orange
  return "#95a5a6"; // Gray - LV
}

// Equipment type styling
const EQUIPMENT_STYLES: Record<string, { color: string; shape: string; label: string }> = {
  generator: { color: "#2ecc71", shape: "triangle", label: "G" },
  load: { color: "#e74c3c", shape: "diamond", label: "L" },
  shunt: { color: "#9b59b6", shape: "rectangle", label: "SH" },
  svc: { color: "#1abc9c", shape: "pentagon", label: "SVC" },
  statcom: { color: "#16a085", shape: "hexagon", label: "ST" },
  vsc_converter: { color: "#f39c12", shape: "octagon", label: "VSC" },
  csc_converter: { color: "#d35400", shape: "octagon", label: "CSC" },
  other: { color: "#7f8c8d", shape: "ellipse", label: "?" },
};

// Equipment positioning constants
const EQUIPMENT_OFFSET = 60; // Distance from bus to first equipment (increased to avoid line overlap)
const EQUIPMENT_SPACING = 30; // Spacing between equipment nodes (increased for better separation)

/**
 * Reposition terminal nodes along their parent bus bar.
 * Terminals are positioned on the side of the bus facing their connected edge.
 * For vertical buses: left side or right side
 * For horizontal buses: top side or bottom side
 */
function repositionTerminals(cy: Core, verticalBuses: Set<string>): void {
  // Group terminals by their bus_id
  const terminalsByBus = new Map<string, NodeSingular[]>();

  cy.nodes("[kind='terminal']").forEach((termNode) => {
    const busId = termNode.data("bus_id") as string;
    if (!terminalsByBus.has(busId)) {
      terminalsByBus.set(busId, []);
    }
    terminalsByBus.get(busId)!.push(termNode);
  });

  // Position terminals along each bus
  terminalsByBus.forEach((terminals, busId) => {
    const busNode = cy.getElementById(busId);
    if (busNode.empty()) return;

    const busPos = busNode.position();
    const isVertical = verticalBuses.has(busId);

    // Separate terminals by which side they should be on
    // based on where their connected edge goes
    const leftOrTop: NodeSingular[] = [];
    const rightOrBottom: NodeSingular[] = [];

    terminals.forEach((termNode) => {
      // Find the edge connected to this terminal
      const connectedEdges = termNode.connectedEdges();
      if (connectedEdges.empty()) {
        // No edge - default to left/top
        leftOrTop.push(termNode);
        return;
      }

      // Get the other end of the edge
      const edge = connectedEdges.first();
      const sourceId = edge.data("source");
      const targetId = edge.data("target");
      const otherId = sourceId === termNode.id() ? targetId : sourceId;
      const otherNode = cy.getElementById(otherId);

      if (otherNode.empty()) {
        leftOrTop.push(termNode);
        return;
      }

      const otherPos = otherNode.position();

      if (isVertical) {
        // Vertical bus: check if other node is left or right
        if (otherPos.x < busPos.x) {
          leftOrTop.push(termNode); // Left side
        } else {
          rightOrBottom.push(termNode); // Right side
        }
      } else {
        // Horizontal bus: check if other node is above or below
        if (otherPos.y < busPos.y) {
          leftOrTop.push(termNode); // Top side
        } else {
          rightOrBottom.push(termNode); // Bottom side
        }
      }
    });

    // Sort terminals on each side by the Y position (vertical) or X position (horizontal) of their other end
    const sortByOtherPosition = (a: NodeSingular, b: NodeSingular) => {
      const getOtherPos = (term: NodeSingular) => {
        const edge = term.connectedEdges().first();
        if (!edge) return 0;
        const sourceId = edge.data("source");
        const targetId = edge.data("target");
        const otherId = sourceId === term.id() ? targetId : sourceId;
        const other = cy.getElementById(otherId);
        if (other.empty()) return 0;
        return isVertical ? other.position().y : other.position().x;
      };
      return getOtherPos(a) - getOtherPos(b);
    };

    leftOrTop.sort(sortByOtherPosition);
    rightOrBottom.sort(sortByOtherPosition);

    // Bus dimensions - scale spread based on terminal count
    // For 1-2 terminals: keep them centered with minimal spread
    // For 3+ terminals: use full bus length
    const busLength = 50;
    const getSpread = (count: number) => {
      if (count <= 1) return 0;
      if (count === 2) return 20; // Small gap for 2 terminals
      return busLength; // Full spread for 3+
    };
    const calcOffset = (idx: number, count: number) => {
      if (count <= 1) return 0;
      const spread = getSpread(count);
      return -spread / 2 + (idx / (count - 1)) * spread;
    };

    // Position terminals on left/top side
    leftOrTop.forEach((termNode, idx) => {
      const count = leftOrTop.length;
      const offset = calcOffset(idx, count);

      if (isVertical) {
        termNode.position({
          x: busPos.x - 6, // Left side of bus
          y: busPos.y + offset,
        });
      } else {
        termNode.position({
          x: busPos.x + offset,
          y: busPos.y - 6, // Top side of bus
        });
      }

      termNode.scratch("_busOffset", {
        x: termNode.position().x - busPos.x,
        y: termNode.position().y - busPos.y,
      });
    });

    // Position terminals on right/bottom side
    rightOrBottom.forEach((termNode, idx) => {
      const count = rightOrBottom.length;
      const offset = calcOffset(idx, count);

      if (isVertical) {
        termNode.position({
          x: busPos.x + 6, // Right side of bus
          y: busPos.y + offset,
        });
      } else {
        termNode.position({
          x: busPos.x + offset,
          y: busPos.y + 6, // Bottom side of bus
        });
      }

      termNode.scratch("_busOffset", {
        x: termNode.position().x - busPos.x,
        y: termNode.position().y - busPos.y,
      });
    });
  });
}

/**
 * Reposition equipment nodes to be close to their parent bus.
 * For horizontal buses: equipment arranged in a row below the bus.
 * For vertical buses: equipment arranged in a column to the right of the bus.
 */
function repositionEquipment(cy: Core, verticalBuses: Set<string>): void {
  // Get all equipment nodes grouped by their bus_id
  const equipmentByBus = new Map<string, NodeSingular[]>();
  
  cy.nodes("[kind='equipment']").forEach((eqNode) => {
    const busId = eqNode.data("bus_id") as string;
    if (!equipmentByBus.has(busId)) {
      equipmentByBus.set(busId, []);
    }
    equipmentByBus.get(busId)!.push(eqNode);
  });

  // For each bus, position its equipment
  equipmentByBus.forEach((equipmentNodes, busId) => {
    const busNode = cy.getElementById(busId);
    if (busNode.empty()) return;

    const busPos = busNode.position();
    const numEquipment = equipmentNodes.length;
    const isVertical = verticalBuses.has(busId);

    if (isVertical) {
      // Vertical bus: equipment in a column to the right
      const totalHeight = (numEquipment - 1) * EQUIPMENT_SPACING;
      const startY = busPos.y - totalHeight / 2;

      equipmentNodes.forEach((eqNode, index) => {
        const offsetX = EQUIPMENT_OFFSET;
        const offsetY = startY + index * EQUIPMENT_SPACING - busPos.y;

        eqNode.position({
          x: busPos.x + offsetX,
          y: startY + index * EQUIPMENT_SPACING,
        });

        // Store offset for drag handler
        eqNode.scratch("_offset", { x: offsetX, y: offsetY });
      });
    } else {
      // Horizontal bus: equipment in a row below
      const totalWidth = (numEquipment - 1) * EQUIPMENT_SPACING;
      const startX = busPos.x - totalWidth / 2;

      equipmentNodes.forEach((eqNode, index) => {
        const offsetX = startX + index * EQUIPMENT_SPACING - busPos.x;
        const offsetY = EQUIPMENT_OFFSET;

        eqNode.position({
          x: startX + index * EQUIPMENT_SPACING,
          y: busPos.y + offsetY,
        });

        // Store offset for drag handler
        eqNode.scratch("_offset", { x: offsetX, y: offsetY });
      });
    }
  });

  // Update bus node sizes based on orientation
  cy.nodes("[kind='bus']").forEach((busNode) => {
    const busId = busNode.id();
    const isVertical = verticalBuses.has(busId);
    if (isVertical) {
      busNode.style({
        width: 12,
        height: 60,
      });
    } else {
      busNode.style({
        width: 60,
        height: 12,
      });
    }
  });
}

/**
 * Check if a line segment intersects with a rectangle (node bounding box).
 */
function lineIntersectsRect(
  x1: number, y1: number, x2: number, y2: number,
  cx: number, cy: number, hw: number, hh: number
): boolean {
  const left = cx - hw;
  const right = cx + hw;
  const top = cy - hh;
  const bottom = cy + hh;

  const p1Inside = x1 >= left && x1 <= right && y1 >= top && y1 <= bottom;
  const p2Inside = x2 >= left && x2 <= right && y2 >= top && y2 <= bottom;
  if (p1Inside || p2Inside) return true;

  if (x1 === x2) {
    const minY = Math.min(y1, y2);
    const maxY = Math.max(y1, y2);
    return x1 >= left && x1 <= right && minY <= bottom && maxY >= top;
  }
  if (y1 === y2) {
    const minX = Math.min(x1, x2);
    const maxX = Math.max(x1, x2);
    return y1 >= top && y1 <= bottom && minX <= right && maxX >= left;
  }
  return false;
}

/**
 * Count how many nodes a taxi-routed edge would collide with.
 */
function countTaxiCollisions(
  sourcePos: { x: number; y: number },
  targetPos: { x: number; y: number },
  direction: "horizontal" | "vertical",
  nodes: NodeSingular[],
  excludeIds: Set<string>
): number {
  let collisions = 0;
  let seg1End: { x: number; y: number };

  if (direction === "horizontal") {
    seg1End = { x: targetPos.x, y: sourcePos.y };
  } else {
    seg1End = { x: sourcePos.x, y: targetPos.y };
  }

  for (const node of nodes) {
    if (excludeIds.has(node.id())) continue;
    const pos = node.position();
    const w = node.outerWidth() / 2;
    const h = node.outerHeight() / 2;

    if (
      lineIntersectsRect(sourcePos.x, sourcePos.y, seg1End.x, seg1End.y, pos.x, pos.y, w, h) ||
      lineIntersectsRect(seg1End.x, seg1End.y, targetPos.x, targetPos.y, pos.x, pos.y, w, h)
    ) {
      collisions++;
    }
  }
  return collisions;
}

/**
 * Optimize edge routing by choosing the best taxi-direction for each edge
 * to minimize collisions with nodes.
 */
function optimizeEdgeRouting(cy: Core): void {
  const collidableNodes = cy.nodes().filter((node) => {
    const kind = node.data("kind");
    return kind === "bus" || kind === "transformer" || kind === "substation" || kind === "neighbor_substation_stub" || kind === "equipment";
  }).toArray() as NodeSingular[];

  const taxiEdges = cy.edges().filter((edge) => {
    const kind = edge.data("kind");
    return kind === "branch" || kind === "transformer_link";
  });

  taxiEdges.forEach((edge) => {
    const sourceNode = edge.source();
    const targetNode = edge.target();
    const sourcePos = sourceNode.position();
    const targetPos = targetNode.position();

    const excludeIds = new Set<string>([sourceNode.id(), targetNode.id()]);
    const sourceBusId = sourceNode.data("bus_id");
    const targetBusId = targetNode.data("bus_id");
    if (sourceBusId) excludeIds.add(sourceBusId);
    if (targetBusId) excludeIds.add(targetBusId);

    const horizontalCollisions = countTaxiCollisions(sourcePos, targetPos, "horizontal", collidableNodes, excludeIds);
    const verticalCollisions = countTaxiCollisions(sourcePos, targetPos, "vertical", collidableNodes, excludeIds);

    let bestDirection: "horizontal" | "vertical" | "auto" = "auto";
    if (horizontalCollisions < verticalCollisions) {
      bestDirection = "horizontal";
    } else if (verticalCollisions < horizontalCollisions) {
      bestDirection = "vertical";
    }

    edge.style("taxi-direction", bestDirection);
  });
}

const GraphViewer: React.FC<GraphViewerProps> = ({ fileId }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [elements, setElements] = useState<ViewResponse["elements"] | null>(null);
  const [meta, setMeta] = useState<ViewResponse["meta"] | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("bus");
  const [centerBus, setCenterBus] = useState<number | null>(null);
  const [degrees, setDegrees] = useState<number>(1);
  const [showEquipment, setShowEquipment] = useState<boolean>(true);
  const [showSubstationGroups, setShowSubstationGroups] = useState<boolean>(true);
  const [selectedElement, setSelectedElement] = useState<NodeData | EdgeData | null>(null);
  const [verticalBuses, setVerticalBuses] = useState<Set<string>>(new Set());

  // Use a ref for position caching to avoid triggering re-renders
  const cachedPositionsRef = useRef<Record<string, { x: number; y: number }>>({});

  // Ref to track showSubstationGroups for initial render (avoids adding to dependency array)
  const showSubstationGroupsRef = useRef(showSubstationGroups);
  showSubstationGroupsRef.current = showSubstationGroups;

  // Fetch graph view from API
  const fetchView = useCallback(async (
    id: string,
    mode: ViewMode,
    nextCenterBus: number | null,
    nextDegrees: number,
    includeEquipment: boolean
  ) => {
    setLoading(true);
    setError(null);

    const viewSpec: ViewSpec = {
      mode: mode,
      center_bus_numbers: mode === "bus" && nextCenterBus != null ? [nextCenterBus] : null,
      center_substation_ids: null,
      degrees: nextDegrees,
      filters: {
        // In substation mode, equipment is not shown (overview mode)
        include_equipment: mode === "substation" ? false : includeEquipment,
      },
      layout: "preset",
      limit: null,
    };

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/graphs/${id}/view`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(viewSpec),
        }
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(
          errorData.error?.message || `HTTP ${response.status}: ${response.statusText}`
        );
      }

      const data: ViewResponse = await response.json();
      setElements(data.elements);
      setMeta(data.meta);

      // DON'T clear cached positions - preserve positions for nodes that still exist
      // This allows incremental layout when degrees changes (1→2 keeps existing buses in place)

      // Set all buses to VERTICAL by default
      const busIds = data.elements.nodes
        .filter((n) => n.data.kind === "bus")
        .map((n) => n.data.id);
      setVerticalBuses(new Set(busIds));
    } catch (err) {
      const errorMessage =
        err instanceof Error ? err.message : "Failed to load graph view";
      setError(errorMessage);
      console.error("Error fetching graph view:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  // Initialize Cytoscape
  useEffect(() => {
    if (!containerRef.current || !elements) {
      return;
    }

    // Save current positions before destroying instance (for layout caching)
    if (cyRef.current) {
      cyRef.current.nodes().forEach((node) => {
        const pos = node.position();
        cachedPositionsRef.current[node.id()] = { x: pos.x, y: pos.y };
      });
      cyRef.current.destroy();
    }

    // Build dynamic styles based on voltage levels in the data
    const busStyles = elements.nodes
      .filter((n) => n.data.kind === "bus")
      .map((n) => {
        const bus = n.data as BusNodeData;
        return {
          selector: `node[id="${bus.id}"]`,
          style: {
            "background-color": getVoltageColor(bus.base_kv),
          },
        };
      });

    // Build equipment styles (including out-of-service styling)
    const equipmentStyles = elements.nodes
      .filter((n) => n.data.kind === "equipment")
      .map((n) => {
        const eq = n.data as EquipmentNodeData;
        const style = EQUIPMENT_STYLES[eq.equipment_type] || EQUIPMENT_STYLES.other;
        const isOutOfService = eq.status === false;
        return {
          selector: `node[id="${eq.id}"]`,
          style: {
            "background-color": style.color,
            shape: style.shape as cytoscape.Css.NodeShape,
            // Out-of-service: dashed border and reduced opacity
            ...(isOutOfService ? {
              "border-style": "dashed" as const,
              opacity: 0.5,
            } : {}),
          },
        };
      });

    // Build equipment link styles (solid for in-service, dashed for out-of-service)
    const equipmentLinkStyles = elements.edges
      .filter((e) => e.data.kind === "equipment_link")
      .filter((e) => (e.data as { status?: boolean }).status === false)
      .map((e) => ({
        selector: `edge[id="${e.data.id}"]`,
        style: {
          "line-style": "dashed" as const,
          opacity: 0.5,
        },
      }));

    // Always include all nodes - substation visibility is controlled via style, not filtering
    // This prevents recreating the entire graph when toggling substations
    const filteredNodes = elements.nodes;

    // Initialize Cytoscape
    const cy = cytoscape({
      container: containerRef.current,
      elements: {
        nodes: filteredNodes,
        edges: elements.edges,
      },
      style: [
        // Base node style
        {
          selector: "node",
          style: {
            label: "data(name)",
            "text-valign": "bottom",
            "text-halign": "center",
            "font-size": 10,
            width: 24,
            height: 24,
            "background-color": "#666",
            "border-width": 2,
            "border-color": "#333",
          },
        },
        // Bus nodes - rectangular bar shape
        {
          selector: "node[kind='bus']",
          style: {
            shape: "round-rectangle",
            width: 60,
            height: 12,
            "text-valign": "top",
            "text-margin-y": -4,
            label: (ele: NodeSingular) => {
              const data = ele.data() as BusNodeData;
              return `${data.psse_number}\n${data.name}`;
            },
            "text-wrap": "wrap",
            "font-size": 9,
          },
        },
        // Equipment nodes - smaller
        {
          selector: "node[kind='equipment']",
          style: {
            width: 18,
            height: 18,
            "font-size": 8,
            "border-width": 1,
            label: (ele: NodeSingular) => {
              const data = ele.data() as EquipmentNodeData;
              const style = EQUIPMENT_STYLES[data.equipment_type] || EQUIPMENT_STYLES.other;
              return style.label;
            },
            "text-valign": "center",
            "text-halign": "center",
            color: "#fff",
            "text-outline-width": 0,
          },
        },
        // Transformer nodes - distinctive symbol (two circles / coils)
        {
          selector: "node[kind='transformer']",
          style: {
            shape: "ellipse",
            width: 28,
            height: 28,
            "background-color": "#8e44ad",
            "border-width": 3,
            "border-color": "#5b2c6f",
            label: "T",
            "text-valign": "center",
            "text-halign": "center",
            color: "#fff",
            "font-size": 10,
            "font-weight": "bold",
          },
        },
        // Substation group nodes (compound parents) - minimal styling, just for grouping
        {
          selector: "node[kind='substation_group']",
          style: {
            shape: "round-rectangle",
            "background-color": "rgba(52, 73, 94, 0.1)", // Very light background
            "background-opacity": 0.3,
            "border-width": 1,
            "border-color": "rgba(52, 73, 94, 0.3)",
            "border-style": "dashed",
            label: "data(name)",
            "text-valign": "top",
            "text-halign": "center",
            color: "#34495e",
            "font-size": 9,
            "text-opacity": 0.7,
            padding: "10px",
          },
        },
        // Substation nodes - larger rounded rectangle (for substation mode)
        {
          selector: "node[kind='substation']",
          style: {
            shape: "round-rectangle",
            width: 100,
            height: 50,
            "background-color": "#2c3e50",
            "border-width": 2,
            "border-color": "#1a252f",
            label: "data(name)",
            "text-valign": "center",
            "text-halign": "center",
            color: "#fff",
            "font-size": 12,
            "font-weight": "bold",
            "text-wrap": "wrap",
            "text-max-width": "90px",
          },
        },
        // Neighbor substation stubs - smaller, dashed border
        {
          selector: "node[kind='neighbor_substation_stub']",
          style: {
            shape: "round-rectangle",
            width: 80,
            height: 40,
            "background-color": "#7f8c8d",
            "border-width": 2,
            "border-color": "#5a6268",
            "border-style": "dashed",
            label: "data(name)",
            "text-valign": "center",
            "text-halign": "center",
            color: "#fff",
            "font-size": 10,
            "text-wrap": "wrap",
            "text-max-width": "70px",
          },
        },
        // Terminal nodes - invisible connection points along bus bars
        {
          selector: "node[kind='terminal']",
          style: {
            shape: "ellipse",
            width: 4,
            height: 4,
            "background-color": "#2c3e50",
            "border-width": 0,
            label: "",  // No label
            opacity: 0,  // Invisible - just connection points
          },
        },
        // Base edge style - orthogonal (taxi) routing like PSS/E
        {
          selector: "edge",
          style: {
            width: 2,
            "line-color": "#34495e",
            "curve-style": "taxi",
            "taxi-direction": "auto",
            "taxi-turn": "50%",
            "taxi-turn-min-distance": 5,
          },
        },
        // Branch edges - transmission lines (same taxi routing)
        {
          selector: "edge[kind='branch'][type='line']",
          style: {
            "line-color": "#34495e",
            width: 2,
          },
        },
        // Transformer link edges - also orthogonal
        {
          selector: "edge[kind='transformer_link']",
          style: {
            "line-color": "#8e44ad",
            width: 2,
            "line-style": "solid",
          },
        },
        // Equipment link edges - straight lines (very short connections)
        {
          selector: "edge[kind='equipment_link']",
          style: {
            width: 1,
            "line-color": "#7f8c8d",
            "line-style": "solid",
            opacity: 0.8,
            "curve-style": "straight", // Equipment links are short, keep straight
          },
        },
        // Selected/highlighted
        {
          selector: ":selected",
          style: {
            "border-color": "#e74c3c",
            "border-width": 3,
            "line-color": "#e74c3c",
          },
        },
        // Dynamic bus colors
        ...busStyles,
        // Dynamic equipment styles
        ...equipmentStyles,
        // Dynamic equipment link styles (out-of-service = dashed)
        ...equipmentLinkStyles,
      ],
      layout: Object.keys(cachedPositionsRef.current).length > 0
        ? {
            // Use cached positions (no layout calculation)
            name: "preset",
            positions: (nodeId: string) => {
              const cached = cachedPositionsRef.current[nodeId];
              return cached || { x: 0, y: 0 };
            },
            fit: false,
            animate: false,
          }
        : {
            // COSE force-directed layout
            name: "cose",
            animate: false,
            nodeDimensionsIncludeLabels: true,
            idealEdgeLength: (edge: cytoscape.EdgeSingular) => {
              const kind = edge.data("kind");
              const type = edge.data("type");
              if (kind === "equipment_link") return 30;
              if (kind === "transformer_link" || type === "xfmr" || type === "xfmr3") return 40;
              return 150;
            },
            edgeElasticity: (edge: cytoscape.EdgeSingular) => {
              const kind = edge.data("kind");
              const type = edge.data("type");
              if (kind === "transformer_link" || type === "xfmr" || type === "xfmr3") return 400;
              if (kind === "equipment_link") return 50;
              return 100;
            },
            nodeRepulsion: () => 10000,
            gravity: 0.3,
            numIter: 1000,
            nestingFactor: 0.8,
            randomize: false,
            componentSpacing: 150,
            padding: 30,
          },
      userPanningEnabled: true,
      userZoomingEnabled: true,
      boxSelectionEnabled: false,
    });

    // Store reference
    cyRef.current = cy;

    // Make terminal nodes non-grabbable (they move with their bus)
    cy.nodes("[kind='terminal']").ungrabify();

    // Set initial substation visibility (avoids flicker on first load)
    // Use ref to avoid adding showSubstationGroups to dependency array
    if (!showSubstationGroupsRef.current) {
      cy.batch(() => {
        cy.nodes("[kind='substation_group']").style("display", "none");
        cy.nodes("[kind='bus']").forEach((busNode) => {
          if (busNode.parent().length > 0) {
            busNode.move({ parent: null });
          }
        });
        cy.nodes("[kind='terminal']").forEach((termNode) => {
          if (termNode.parent().length > 0) {
            termNode.move({ parent: null });
          }
        });
      });
    }

    // Reposition terminal nodes along bus bars
    repositionTerminals(cy, verticalBuses);

    // Reposition equipment nodes to be close to their parent bus
    repositionEquipment(cy, verticalBuses);
    // Optimize edge routing to avoid crossing through nodes
    optimizeEdgeRouting(cy);

    // Add drag listener: when bus is dragged, move equipment and terminals with it
    cy.on("drag", "node[kind='bus']", (evt) => {
      const bus = evt.target;
      const busId = bus.id();
      const busPos = bus.position();

      // Move all terminals attached to this bus
      cy.nodes("[kind='terminal']").forEach((termNode) => {
        if (termNode.data("bus_id") === busId) {
          const offset = termNode.scratch("_busOffset") || { x: 0, y: 0 };
          termNode.position({
            x: busPos.x + offset.x,
            y: busPos.y + offset.y,
          });
        }
      });

      // Move all equipment attached to this bus
      cy.nodes("[kind='equipment']").forEach((eqNode) => {
        if (eqNode.data("bus_id") === busId) {
          const offset = eqNode.scratch("_offset") || { x: 0, y: 60 };
          eqNode.position({
            x: busPos.x + offset.x,
            y: busPos.y + offset.y,
          });
        }
      });
    });

    // Node click handler (single click = select)
    cy.on("tap", "node", (evt) => {
      const node = evt.target as NodeSingular;
      const data = node.data() as NodeData;
      console.log("NODE TAP EVENT - setting selectedElement:", data.kind, data.id);
      setSelectedElement(data);

      // Log based on node type
      if (data.kind === "bus") {
        console.log("Bus clicked:", data);
      } else if (data.kind === "equipment") {
        console.log("Equipment clicked:", data);
      } else if (data.kind === "transformer") {
        console.log("Transformer clicked:", data);
      }
    });

    // Right-click handler for bus rotation toggle (frees left-click for selection)
    cy.on("cxttap", "node[kind='bus']", (evt) => {
      evt.preventDefault(); // Prevent browser context menu
      const node = evt.target as NodeSingular;
      const busId = node.id();
      console.log("RIGHT-CLICK on bus - toggling orientation:", busId);
      
      setVerticalBuses((prev) => {
        const newSet = new Set(prev);
        if (newSet.has(busId)) {
          newSet.delete(busId);
        } else {
          newSet.add(busId);
        }
        return newSet;
      });
    });

    // Edge click handler - handle branch edges
    cy.on("tap", "edge", (evt) => {
      const edge = evt.target as EdgeSingular;
      const data = edge.data() as EdgeData;
      console.log("EDGE TAP EVENT:", data.kind, data.id);
      // Only show detail panel for branch edges (lines), not for connector edges
      if (data.kind === "branch") {
        setSelectedElement(data);
        console.log("Branch clicked:", data);
      }
      // transformer_link and equipment_link are just connectors - don't show detail panel
    });

    // Background click clears selection
    cy.on("tap", (evt) => {
      // Only clear selection if we clicked on the background (not a node or edge)
      if (evt.target === cy) {
        console.log("BACKGROUND TAP - clearing selection");
        setSelectedElement(null);
      }
    });

    // Cleanup on unmount
    return () => {
      if (cyRef.current) {
        cyRef.current.destroy();
        cyRef.current = null;
      }
    };
  }, [elements]); // showSubstationGroups removed - handled by separate effect

  // Toggle substation group visibility without recreating the graph
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;

    cy.batch(() => {
      const substationGroups = cy.nodes("[kind='substation_group']");

      if (showSubstationGroups) {
        // Show substation groups
        substationGroups.style("display", "element");

        // Restore parent references for buses and terminals
        cy.nodes("[kind='bus']").forEach((busNode) => {
          const substationId = busNode.data("substation_id");
          if (substationId) {
            const parentNode = cy.getElementById(substationId);
            if (!parentNode.empty() && parentNode.data("kind") === "substation_group") {
              busNode.move({ parent: substationId });
            }
          }
        });
        cy.nodes("[kind='terminal']").forEach((termNode) => {
          const busId = termNode.data("bus_id");
          const busNode = cy.getElementById(busId);
          if (!busNode.empty()) {
            const substationId = busNode.data("substation_id");
            if (substationId) {
              const parentNode = cy.getElementById(substationId);
              if (!parentNode.empty() && parentNode.data("kind") === "substation_group") {
                termNode.move({ parent: substationId });
              }
            }
          }
        });
      } else {
        // Hide substation groups
        substationGroups.style("display", "none");

        // Remove parent references (move buses and terminals out of compound nodes)
        cy.nodes("[kind='bus']").forEach((busNode) => {
          if (busNode.parent().length > 0) {
            busNode.move({ parent: null });
          }
        });
        cy.nodes("[kind='terminal']").forEach((termNode) => {
          if (termNode.parent().length > 0) {
            termNode.move({ parent: null });
          }
        });
      }
    });
  }, [showSubstationGroups]);

  // Update bus orientation and reposition terminals/equipment when verticalBuses changes
  useEffect(() => {
    if (cyRef.current) {
      repositionTerminals(cyRef.current, verticalBuses);
      repositionEquipment(cyRef.current, verticalBuses);
      optimizeEdgeRouting(cyRef.current);
    }
  }, [verticalBuses]);

  // Fetch view when fileId or parameters change
  useEffect(() => {
    if (!fileId) {
      setError("No file ID provided");
      setLoading(false);
      return;
    }
    fetchView(fileId, viewMode, centerBus, degrees, showEquipment);
  }, [fileId, viewMode, centerBus, degrees, showEquipment, fetchView]);

  // Handle clicking "Expand from here" in detail panel
  const handleExpandFromBus = (psseNumber: number) => {
    setCenterBus(psseNumber);
  };

  // Loading state
  if (loading) {
    return (
      <div
        style={{
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          height: "100%",
          minHeight: "400px",
          background: "#1a1a2e",
          color: "#eee",
        }}
      >
        <div>Loading graph view...</div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          alignItems: "center",
          height: "100%",
          minHeight: "400px",
          padding: "20px",
          background: "#1a1a2e",
        }}
      >
        <div style={{ color: "#e74c3c", marginBottom: "10px" }}>
          Error loading graph view
        </div>
        <div style={{ color: "#888", fontSize: "14px" }}>{error}</div>
      </div>
    );
  }

  // Render graph container with detail panel
  return (
    <div style={{ width: "100%", height: "100%", position: "relative", display: "flex", background: "#f8f9fa" }}>
      {/* Main graph area */}
      <div style={{ flex: 1, position: "relative" }}>
        {/* Controls overlay */}
        <div
          style={{
            position: "absolute",
            top: "10px",
            right: "10px",
            background: "rgba(255, 255, 255, 0.95)",
            padding: "10px 14px",
            borderRadius: "6px",
            fontSize: "12px",
            zIndex: 1000,
            boxShadow: "0 2px 8px rgba(0,0,0,0.15)",
            display: "flex",
            gap: "12px",
            alignItems: "center",
          }}
        >
          <div>
            <label>Mode: </label>
            <select
              value={viewMode}
              onChange={(e) => setViewMode(e.target.value as ViewMode)}
              style={{ padding: "4px" }}
            >
              <option value="bus">Bus</option>
              <option value="substation">Substation</option>
              <option value="station_detail">Station Detail</option>
            </select>
          </div>
          <div>
            <label>Center: </label>
            <input
              type="number"
              value={centerBus ?? ""}
              placeholder="(auto)"
              onChange={(e) => {
                const v = e.target.value;
                setCenterBus(v === "" ? null : Number(v));
              }}
              style={{ width: "90px", padding: "4px" }}
              disabled={viewMode === "substation"}
              title={viewMode === "substation" ? "Center bus not used in substation mode" : ""}
            />
          </div>
          <div>
            <label>Degrees: </label>
            <input
              type="number"
              min={0}
              max={10}
              value={degrees}
              onChange={(e) => setDegrees(Number(e.target.value))}
              style={{ width: "50px", padding: "4px" }}
            />
          </div>
          <label style={{ display: "flex", alignItems: "center", gap: "4px" }}>
            <input
              type="checkbox"
              checked={showEquipment}
              onChange={(e) => setShowEquipment(e.target.checked)}
            />
            Equipment
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: "4px" }}>
            <input
              type="checkbox"
              checked={showSubstationGroups}
              onChange={(e) => setShowSubstationGroups(e.target.checked)}
            />
            Substations
          </label>
          <button
            onClick={() => setCenterBus(null)}
            style={{
              padding: "4px 10px",
              fontSize: "12px",
              cursor: "pointer",
              background: "#3498db",
              color: "#fff",
              border: "none",
              borderRadius: "4px",
            }}
          >
            Reset
          </button>
          <button
            onClick={() => {
              cachedPositionsRef.current = {};
              // Force re-render to trigger layout recalculation
              setElements((prev) => prev ? { ...prev } : prev);
            }}
            style={{
              padding: "4px 10px",
              fontSize: "12px",
              cursor: "pointer",
              background: "#e74c3c",
              color: "#fff",
              border: "none",
              borderRadius: "4px",
            }}
            title="Force layout recalculation"
          >
            Re-layout
          </button>
        </div>

        {/* Stats overlay */}
        {meta && (
          <div
            style={{
              position: "absolute",
              top: "10px",
              left: "10px",
              background: "rgba(255, 255, 255, 0.95)",
              padding: "8px 12px",
              borderRadius: "6px",
              fontSize: "11px",
              zIndex: 1000,
              boxShadow: "0 2px 8px rgba(0,0,0,0.15)",
            }}
          >
            <div>Buses: {meta.node_count}</div>
            <div>Branches: {meta.edge_count}</div>
            {meta.equipment_count !== undefined && <div>Equipment: {meta.equipment_count}</div>}
            {meta.truncated && <div style={{ color: "#e74c3c" }}>Truncated</div>}
          </div>
        )}

        {/* Legend */}
        <div
          style={{
            position: "absolute",
            bottom: "10px",
            left: "10px",
            background: "rgba(255, 255, 255, 0.95)",
            padding: "8px 12px",
            borderRadius: "6px",
            fontSize: "10px",
            zIndex: 1000,
            boxShadow: "0 2px 8px rgba(0,0,0,0.15)",
          }}
        >
          <div style={{ fontWeight: "bold", marginBottom: "4px" }}>Voltage (kV)</div>
          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
            <span><span style={{ display: "inline-block", width: 10, height: 10, background: "#e74c3c", marginRight: 3 }}></span>500+</span>
            <span><span style={{ display: "inline-block", width: 10, height: 10, background: "#9b59b6", marginRight: 3 }}></span>345</span>
            <span><span style={{ display: "inline-block", width: 10, height: 10, background: "#3498db", marginRight: 3 }}></span>230</span>
            <span><span style={{ display: "inline-block", width: 10, height: 10, background: "#27ae60", marginRight: 3 }}></span>115</span>
            <span><span style={{ display: "inline-block", width: 10, height: 10, background: "#f39c12", marginRight: 3 }}></span>69</span>
            <span><span style={{ display: "inline-block", width: 10, height: 10, background: "#95a5a6", marginRight: 3 }}></span>LV</span>
          </div>
        </div>

        {/* Cytoscape container */}
        <div
          ref={containerRef}
          style={{
            width: "100%",
            height: "100%",
            minHeight: "400px",
          }}
        />
      </div>

      {/* Detail Panel */}
      {selectedElement && (
        <div
          style={{
            width: "320px",
            background: "#fff",
            borderLeft: "1px solid #ddd",
            padding: "16px",
            overflowY: "auto",
            fontSize: "13px",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
            <h3 style={{ margin: 0, fontSize: "14px" }}>
              {selectedElement.kind === "bus" && "Bus Data"}
              {selectedElement.kind === "branch" && "Branch Data"}
              {selectedElement.kind === "equipment" && "Equipment Data"}
              {selectedElement.kind === "transformer" && "Transformer Data"}
              {(selectedElement.kind === "substation" || selectedElement.kind === "neighbor_substation_stub" || selectedElement.kind === "substation_group") && "Substation Data"}
            </h3>
            <button
              onClick={() => setSelectedElement(null)}
              style={{ background: "none", border: "none", cursor: "pointer", fontSize: "18px" }}
            >
              ×
            </button>
          </div>

          {selectedElement.kind === "bus" && (
            <BusDetailPanel data={selectedElement as BusNodeData} onExpand={handleExpandFromBus} />
          )}
          {selectedElement.kind === "branch" && (
            <BranchDetailPanel data={selectedElement as BranchEdgeData} />
          )}
          {selectedElement.kind === "equipment" && (
            <EquipmentDetailPanel data={selectedElement as EquipmentNodeData} />
          )}
          {selectedElement.kind === "transformer" && (
            <TransformerDetailPanel data={selectedElement as TransformerNodeData} />
          )}
          {(selectedElement.kind === "substation" || selectedElement.kind === "neighbor_substation_stub" || selectedElement.kind === "substation_group") && (
            <SubstationDetailPanel data={selectedElement as SubstationNodeData} />
          )}
        </div>
      )}
    </div>
  );
};

// Sub-components for detail panels
const BusDetailPanel: React.FC<{ data: BusNodeData; onExpand: (psse: number) => void }> = ({ data, onExpand }) => (
  <div>
    <table style={{ width: "100%", borderCollapse: "collapse" }}>
      <tbody>
        <DetailRow label="Bus Number" value={data.psse_number} />
        <DetailRow label="Name" value={data.name} />
        <DetailRow label="Base kV" value={data.base_kv?.toFixed(1)} />
        <DetailRow label="Area" value={data.area} />
        <DetailRow label="Zone" value={data.zone} />
        <DetailRow label="Owner" value={data.owner} />
        <DetailRow label="Vm (pu)" value={data.vm?.toFixed(4)} />
        <DetailRow label="Va (deg)" value={data.va?.toFixed(2)} />
        <DetailRow label="Vmax (pu)" value={data.vmax?.toFixed(4)} />
        <DetailRow label="Vmin (pu)" value={data.vmin?.toFixed(4)} />
      </tbody>
    </table>
    <button
      onClick={() => onExpand(data.psse_number)}
      style={{
        marginTop: "12px",
        padding: "8px 16px",
        background: "#3498db",
        color: "#fff",
        border: "none",
        borderRadius: "4px",
        cursor: "pointer",
        width: "100%",
      }}
    >
      Expand from this bus
    </button>
  </div>
);

const BranchDetailPanel: React.FC<{ data: BranchEdgeData }> = ({ data }) => (
  <div>
    <div style={{ marginBottom: "8px", padding: "6px", background: "#ecf0f1", borderRadius: "4px" }}>
      <strong>Type:</strong> {data.type.toUpperCase()}
    </div>
    <table style={{ width: "100%", borderCollapse: "collapse" }}>
      <tbody>
        <DetailRow label="Circuit ID" value={data.circuit} />
        <DetailRow label="R (pu)" value={data.r?.toFixed(6)} />
        <DetailRow label="X (pu)" value={data.x?.toFixed(6)} />
        <DetailRow label="B (pu)" value={data.b?.toFixed(6)} />
        <DetailRow label="G (pu)" value={data.g?.toFixed(6)} />
        <DetailRow label="R0 (pu)" value={data.r0?.toFixed(6)} />
        <DetailRow label="X0 (pu)" value={data.x0?.toFixed(6)} />
        <DetailRow label="B0 (pu)" value={data.b0?.toFixed(6)} />
        <DetailRow label="Rating MVA" value={data.rating_mva?.toFixed(1)} />
        <DetailRow label="Rate A" value={data.rate_a?.toFixed(1)} />
        <DetailRow label="Rate B" value={data.rate_b?.toFixed(1)} />
        <DetailRow label="Rate C" value={data.rate_c?.toFixed(1)} />
        {data.type.startsWith("xfmr") && (
          <>
            <DetailRow label="Tap Module" value={data.tap_module?.toFixed(4)} />
            <DetailRow label="Tap Phase" value={data.tap_phase?.toFixed(2)} />
          </>
        )}
        {data.type === "line" && <DetailRow label="Length" value={data.length?.toFixed(2)} />}
        <DetailRow label="P From (MW)" value={data.p_from_mw?.toFixed(2)} />
        <DetailRow label="Q From (Mvar)" value={data.q_from_mvar?.toFixed(2)} />
        <DetailRow label="P To (MW)" value={data.p_to_mw?.toFixed(2)} />
        <DetailRow label="Q To (Mvar)" value={data.q_to_mvar?.toFixed(2)} />
      </tbody>
    </table>
  </div>
);

const EquipmentDetailPanel: React.FC<{ data: EquipmentNodeData }> = ({ data }) => {
  const style = EQUIPMENT_STYLES[data.equipment_type] || EQUIPMENT_STYLES.other;
  return (
    <div>
      <div
        style={{
          marginBottom: "8px",
          padding: "6px",
          background: style.color,
          color: "#fff",
          borderRadius: "4px",
          textAlign: "center",
        }}
      >
        <strong>{data.equipment_type.toUpperCase()}</strong>
      </div>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <tbody>
          <DetailRow label="Name" value={data.name || "(unnamed)"} />
          <DetailRow label="Status" value={data.status ? "In Service" : "Out of Service"} />
          <DetailRow label="P (MW)" value={data.p_mw?.toFixed(2)} />
          <DetailRow label="Q (Mvar)" value={data.q_mvar?.toFixed(2)} />
          {data.metadata && Object.entries(data.metadata).map(([key, val]) => (
            <DetailRow key={key} label={key} value={val != null ? String(val) : "-"} />
          ))}
        </tbody>
      </table>
    </div>
  );
};

const TransformerDetailPanel: React.FC<{ data: TransformerNodeData }> = ({ data }) => (
  <div>
    <div
      style={{
        marginBottom: "8px",
        padding: "6px",
        background: "#8e44ad",
        color: "#fff",
        borderRadius: "4px",
        textAlign: "center",
      }}
    >
      <strong>TRANSFORMER ({data.type.toUpperCase()})</strong>
    </div>
    <table style={{ width: "100%", borderCollapse: "collapse" }}>
      <tbody>
        <DetailRow label="Circuit ID" value={data.circuit} />
        <DetailRow label="R (pu)" value={data.r?.toFixed(6)} />
        <DetailRow label="X (pu)" value={data.x?.toFixed(6)} />
        <DetailRow label="B (pu)" value={data.b?.toFixed(6)} />
        <DetailRow label="G (pu)" value={data.g?.toFixed(6)} />
        <DetailRow label="R0 (pu)" value={data.r0?.toFixed(6)} />
        <DetailRow label="X0 (pu)" value={data.x0?.toFixed(6)} />
        <DetailRow label="B0 (pu)" value={data.b0?.toFixed(6)} />
        <DetailRow label="Rating MVA" value={data.rating_mva?.toFixed(1)} />
        <DetailRow label="Rate A" value={data.rate_a?.toFixed(1)} />
        <DetailRow label="Rate B" value={data.rate_b?.toFixed(1)} />
        <DetailRow label="Rate C" value={data.rate_c?.toFixed(1)} />
        <DetailRow label="Tap Module" value={data.tap_module?.toFixed(4)} />
        <DetailRow label="Tap Phase" value={data.tap_phase?.toFixed(2)} />
      </tbody>
    </table>
  </div>
);

const SubstationDetailPanel: React.FC<{ data: SubstationNodeData }> = ({ data }) => (
  <div>
    <div
      style={{
        marginBottom: "8px",
        padding: "6px",
        background: data.kind === "substation" ? "#2c3e50" : "#7f8c8d",
        color: "#fff",
        borderRadius: "4px",
        textAlign: "center",
      }}
    >
      <strong>{data.kind === "substation" ? "SUBSTATION" : "NEIGHBOR SUBSTATION"}</strong>
    </div>
    <table style={{ width: "100%", borderCollapse: "collapse" }}>
      <tbody>
        <DetailRow label="Name" value={data.name} />
        <DetailRow label="Area" value={data.area} />
        <DetailRow label="Zone" value={data.zone} />
        <DetailRow label="Nominal kV" value={data.nominal_kv?.toFixed(1)} />
        <DetailRow label="Voltage Levels" value={data.voltage_levels?.join(", ") || "-"} />
        <DetailRow label="Latitude" value={data.latitude?.toFixed(6)} />
        <DetailRow label="Longitude" value={data.longitude?.toFixed(6)} />
      </tbody>
    </table>
  </div>
);

const DetailRow: React.FC<{ label: string; value: string | number | null | undefined }> = ({ label, value }) => (
  <tr style={{ borderBottom: "1px solid #eee" }}>
    <td style={{ padding: "6px 4px", color: "#666" }}>{label}</td>
    <td style={{ padding: "6px 4px", fontWeight: 500 }}>{value ?? "-"}</td>
  </tr>
);

export default GraphViewer;
