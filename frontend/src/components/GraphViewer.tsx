/**
 * GraphViewer component for rendering Cytoscape.js diagrams.
 */
import { useEffect, useRef, useState, useCallback } from 'react';
import cytoscape, { Core, ElementDefinition, NodeSingular, EdgeSingular } from 'cytoscape';
import elk from 'cytoscape-elk';
import {
  generateView,
  defaultViewSpec,
  CytoscapePayload,
  ViewSpec,
  ApiError,
} from '../utils/api';
import { getSldStyles } from '../utils/sldStyles';
import { runSldLayout, LayoutDirection, LayoutResult } from '../utils/sldLayout';
import { recalculateEdgeRoutingForBus, recalculateEdgeRoutingOnly } from '../utils/edgeRouting';
import {
  applyDiagnostics,
  getDiagnosticsInfo,
  DEFAULT_DIAGNOSTICS,
  DiagnosticsState,
} from '../utils/diagnostics';
import { useKeyboardShortcuts, getShortcutsList } from '../utils/useKeyboardShortcuts';

// Register ELK layout (only once)
try {
  cytoscape.use(elk);
} catch {
  // Already registered
}

interface GraphViewerProps {
  fileId: string | null;
  centerBusNumber: number | null;
  onNodeSelect?: (nodeId: string, data: Record<string, unknown>) => void;
  onEdgeSelect?: (edgeId: string, data: Record<string, unknown>) => void;
}

// Selected bus state for resize control
interface SelectedBusState {
  id: string;
  name: string;
  psseNumber: number;
  currentLength: number;
  orientation: 'vertical' | 'horizontal';
}

export function GraphViewer({ fileId, centerBusNumber, onNodeSelect, onEdgeSelect }: GraphViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [meta, setMeta] = useState<Record<string, unknown> | null>(null);
  const [displayDepth, setDisplayDepth] = useState(2);
  const [layoutDirection, setLayoutDirection] = useState<LayoutDirection>('AUTO');
  const [layoutResult, setLayoutResult] = useState<LayoutResult | null>(null);
  const [dataVersion, setDataVersion] = useState(0); // Incremented on each data load
  const [diagnostics, setDiagnostics] = useState<DiagnosticsState>(DEFAULT_DIAGNOSTICS);
  const [showShortcuts, setShowShortcuts] = useState(false);
  const [lockEquipmentToBus, setLockEquipmentToBus] = useState(true);
  const lockEquipmentRef = useRef(true);

  // 17.18: Edit Mode - controls element grabbability
  const [editMode, setEditMode] = useState(false);
  const editModeRef = useRef(false);

  // Box selection state (Shift+Drag for zoom, Ctrl+Drag for multi-select)
  const [boxSelectActive, setBoxSelectActive] = useState(false);
  const [boxSelectMode, setBoxSelectMode] = useState<'zoom' | 'select'>('zoom');
  const [boxStart, setBoxStart] = useState<{ x: number; y: number } | null>(null);
  const [boxEnd, setBoxEnd] = useState<{ x: number; y: number } | null>(null);
  const boxOverlayRef = useRef<HTMLDivElement>(null);

  // Multi-select state
  const [multiSelectActive, setMultiSelectActive] = useState(false);

  // Grid overlay state
  const [showGrid, setShowGrid] = useState(false);
  const [snapToGrid, setSnapToGrid] = useState(false);
  const snapToGridRef = useRef(false);
  const gridSize = 20; // Grid spacing in pixels

  // Keep snap ref in sync with state
  useEffect(() => {
    snapToGridRef.current = snapToGrid;
  }, [snapToGrid]);

  // Selected bus state for resize control
  const [selectedBus, setSelectedBus] = useState<SelectedBusState | null>(null);

  // Context menu state
  interface ContextMenuState {
    visible: boolean;
    x: number;
    y: number;
    busId: string;
    busNumber: number;
    busName: string;
  }
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);
  const [expandDepthInput, setExpandDepthInput] = useState<number>(2);
  const [showExpandDialog, setShowExpandDialog] = useState(false);
  // Store expansion target bus info separately so it persists when context menu closes
  const [expandTargetBus, setExpandTargetBus] = useState<{ id: string; number: number; name: string } | null>(null);

  // Keep refs in sync with state
  useEffect(() => {
    lockEquipmentRef.current = lockEquipmentToBus;
  }, [lockEquipmentToBus]);

  // 17.18: Edit Mode sync and grabbability control
  useEffect(() => {
    editModeRef.current = editMode;
    const cy = cyRef.current;
    if (!cy) return;

    if (editMode) {
      // Edit Mode ON: Enable grabbing for buses, terminals, equipment, transformers
      cy.nodes('[kind="bus"], [kind="transformer"], [kind="transformer2"], [kind="transformer3"], [kind="terminal"], [kind="equipment"]').grabify();
    } else {
      // Edit Mode OFF: Disable grabbing for all editable elements
      cy.nodes('[kind="bus"], [kind="transformer"], [kind="transformer2"], [kind="transformer3"], [kind="terminal"], [kind="equipment"]').ungrabify();
    }
  }, [editMode]);

  // Initialize Cytoscape
  useEffect(() => {
    if (!containerRef.current) return;

    const cy = cytoscape({
      container: containerRef.current,
      style: getSldStyles(),
      layout: { name: 'preset' },
      minZoom: 0.05,
      maxZoom: 10,
      wheelSensitivity: 1.5, // Higher = faster zoom with scroll wheel
    });

    // Node selection handler with multi-select support (Ctrl+Click)
    cy.on('tap', 'node', (evt) => {
      const node = evt.target;
      const originalEvent = evt.originalEvent as MouseEvent;
      const isCtrlClick = originalEvent.ctrlKey || originalEvent.metaKey;

      if (isCtrlClick) {
        // Multi-select: toggle selection state
        if (node.selected()) {
          node.unselect();
        } else {
          node.select();
        }
        setMultiSelectActive(cy.$(':selected').length > 1);
        setSelectedBus(null); // Disable bus resize panel in multi-select mode
      } else {
        // Single select: deselect all others first
        cy.$(':selected').unselect();
        node.select();
        setMultiSelectActive(false);

        if (onNodeSelect) {
          onNodeSelect(node.id(), node.data());
        }
        // Track selected bus for resize control
        if (node.data('kind') === 'bus') {
          const orientation = node.data('orientation') || 'vertical';
          const currentLength = orientation === 'horizontal'
            ? (node.style('width') ? parseFloat(node.style('width')) : node.data('busbarLength') || 60)
            : (node.style('height') ? parseFloat(node.style('height')) : node.data('busbarLength') || 60);
          setSelectedBus({
            id: node.id(),
            name: node.data('label') || node.data('name') || node.id(),
            psseNumber: node.data('psse_number') || 0,
            currentLength,
            orientation,
          });
        } else {
          setSelectedBus(null);
        }
      }
    });

    // Edge selection handler
    cy.on('tap', 'edge', (evt) => {
      const edge = evt.target;
      if (onEdgeSelect) {
        onEdgeSelect(edge.id(), edge.data());
      }
      setSelectedBus(null);
    });

    // Right-click context menu for buses
    cy.on('cxttap', 'node[kind="bus"]', (evt) => {
      const node = evt.target;
      const originalEvent = evt.originalEvent as MouseEvent;

      // Get position relative to the graph wrapper
      const container = containerRef.current;
      if (!container) return;
      const rect = container.getBoundingClientRect();

      setContextMenu({
        visible: true,
        x: originalEvent.clientX - rect.left,
        y: originalEvent.clientY - rect.top,
        busId: node.id(),
        busNumber: node.data('psse_number') || 0,
        busName: node.data('label') || node.data('name') || node.id(),
      });

      originalEvent.preventDefault();
    });

    // Background click deselects bus and clears multi-select
    cy.on('tap', (evt) => {
      if (evt.target === cy) {
        setSelectedBus(null);
        setMultiSelectActive(false);
        setContextMenu(null);
        cy.$(':selected').unselect();
      }
    });

    // Track position before drag starts - includes multi-select support
    cy.on('grab', 'node[kind="bus"]', (evt) => {
      const bus = evt.target;
      bus.data('_dragStartX', bus.position('x'));
      bus.data('_dragStartY', bus.position('y'));

      // Store child node positions for this bus
      const busId = bus.id();
      cy.nodes(`[parentBusId="${busId}"], [busId="${busId}"]`).forEach((node) => {
        node.data('_dragStartX', node.position('x'));
        node.data('_dragStartY', node.position('y'));
      });

      // If part of multi-select, store start positions for ALL selected buses and their children
      const selectedBuses = cy.nodes('[kind="bus"]:selected');
      if (selectedBuses.length > 1 && bus.selected()) {
        selectedBuses.forEach((otherBus) => {
          if (otherBus.id() !== bus.id()) {
            otherBus.data('_dragStartX', otherBus.position('x'));
            otherBus.data('_dragStartY', otherBus.position('y'));
            // Store children positions
            const otherBusId = otherBus.id();
            cy.nodes(`[parentBusId="${otherBusId}"], [busId="${otherBusId}"]`).forEach((node) => {
              node.data('_dragStartX', node.position('x'));
              node.data('_dragStartY', node.position('y'));
            });
          }
        });

        // Also store transformer positions for group move
        cy.nodes('[kind="transformer"], [kind="transformer2"], [kind="transformer3"]:selected').forEach((xfmr) => {
          xfmr.data('_dragStartX', xfmr.position('x'));
          xfmr.data('_dragStartY', xfmr.position('y'));
        });
      }
    });

    // Move connected terminals and equipment when bus is dragged (with multi-select support)
    cy.on('drag', 'node[kind="bus"]', (evt) => {
      const bus = evt.target;
      const startX = bus.data('_dragStartX') ?? bus.position('x');
      const startY = bus.data('_dragStartY') ?? bus.position('y');
      const deltaX = bus.position('x') - startX;
      const deltaY = bus.position('y') - startY;

      // Helper function to move a bus and its children
      const moveBusAndChildren = (targetBus: NodeSingular, dx: number, dy: number) => {
        const targetBusId = targetBus.id();

        // Move child nodes if equipment is locked
        if (lockEquipmentRef.current) {
          cy.nodes(`[parentBusId="${targetBusId}"], [busId="${targetBusId}"]`).forEach((node) => {
            const nodeStartX = node.data('_dragStartX');
            const nodeStartY = node.data('_dragStartY');
            if (nodeStartX !== undefined && nodeStartY !== undefined) {
              node.position({ x: nodeStartX + dx, y: nodeStartY + dy });
            }
          });
        }
      };

      // Move this bus's children
      moveBusAndChildren(bus, deltaX, deltaY);

      // If part of multi-select, move all other selected buses too
      const selectedBuses = cy.nodes('[kind="bus"]:selected');
      if (selectedBuses.length > 1 && bus.selected()) {
        selectedBuses.forEach((otherBus) => {
          if (otherBus.id() !== bus.id()) {
            const otherStartX = otherBus.data('_dragStartX');
            const otherStartY = otherBus.data('_dragStartY');
            if (otherStartX !== undefined && otherStartY !== undefined) {
              otherBus.position({ x: otherStartX + deltaX, y: otherStartY + deltaY });
              moveBusAndChildren(otherBus, deltaX, deltaY);
            }
          }
        });

        // Also move selected transformers
        cy.nodes('[kind="transformer"]:selected, [kind="transformer2"]:selected, [kind="transformer3"]:selected').forEach((xfmr) => {
          const xfmrStartX = xfmr.data('_dragStartX');
          const xfmrStartY = xfmr.data('_dragStartY');
          if (xfmrStartX !== undefined && xfmrStartY !== undefined) {
            xfmr.position({ x: xfmrStartX + deltaX, y: xfmrStartY + deltaY });
          }
        });
      }

      // 17.47: Recalculate edge routing dynamically during drag
      // This updates taxi_turn and taxi_direction for connected edges
      // enabling V-H-V routing when buses become vertically stacked
      recalculateEdgeRoutingForBus(cy, bus.id());

      // If multi-select, also recalculate for other moved buses
      if (selectedBuses.length > 1 && bus.selected()) {
        selectedBuses.forEach((otherBus) => {
          if (otherBus.id() !== bus.id()) {
            recalculateEdgeRoutingForBus(cy, otherBus.id());
          }
        });
      }
    });

    // Terminal drag along bus - constrain movement to bus axis with side-switching support
    cy.on('grab', 'node[kind="terminal"]', (evt) => {
      const terminal = evt.target;
      terminal.data('_dragStartX', terminal.position('x'));
      terminal.data('_dragStartY', terminal.position('y'));
      terminal.data('_isDraggingTerminal', true);

      // Store the parent bus info for constraint
      const parentBusId = terminal.data('parentBusId');
      if (parentBusId) {
        const parentBus = cy.getElementById(parentBusId);
        if (parentBus.length > 0) {
          const busPos = parentBus.position();
          const busLength = parentBus.data('busbarLength') || 60;
          terminal.data('_busX', busPos.x);
          terminal.data('_busY', busPos.y);
          terminal.data('_busLength', busLength);
          terminal.data('_busMinY', busPos.y - busLength / 2);
          terminal.data('_busMaxY', busPos.y + busLength / 2);
        }
      }
    });

    cy.on('drag', 'node[kind="terminal"]', (evt) => {
      const terminal = evt.target;
      if (!terminal.data('_isDraggingTerminal')) return;

      const busMinY = terminal.data('_busMinY');
      const busMaxY = terminal.data('_busMaxY');
      const busX = terminal.data('_busX');
      const busThickness = 8;

      if (busMinY !== undefined && busMaxY !== undefined && busX !== undefined) {
        const currentPos = terminal.position();
        const constrainedY = Math.max(busMinY, Math.min(busMaxY, currentPos.y));

        // ENHANCED: Allow side-switching based on drag X position
        // If terminal is dragged past bus center, switch to other side
        const isLeftSide = currentPos.x < busX;
        const terminalX = isLeftSide
          ? busX - busThickness / 2 - 2   // LEFT side
          : busX + busThickness / 2 + 2;  // RIGHT side

        terminal.position({ x: terminalX, y: constrainedY });
        terminal.data('attachSide', isLeftSide ? 'LEFT' : 'RIGHT');

        // Move connected equipment with terminal (maintaining relative offset)
        const connectedEdges = terminal.connectedEdges('[kind="equipment_link"]');
        connectedEdges.forEach((edge: EdgeSingular) => {
          const equipmentId = edge.data('target');
          const equipment = cy.getElementById(equipmentId);
          if (equipment.length > 0 && equipment.data('kind') === 'equipment') {
            const equipmentOffset = 25; // Should match EQUIPMENT_OFFSET in sldLayout.ts
            const equipmentX = isLeftSide
              ? terminalX - equipmentOffset  // Further left
              : terminalX + equipmentOffset; // Further right
            equipment.position({ x: equipmentX, y: constrainedY });
            equipment.data('attachSide', isLeftSide ? 'LEFT' : 'RIGHT');
          }
        });
      }
    });

    cy.on('free', 'node[kind="terminal"]', (evt) => {
      const terminal = evt.target;
      if (!terminal.data('_isDraggingTerminal')) return;

      // Redistribute terminals on both sides to handle side-switching
      const parentBusId = terminal.data('parentBusId');

      if (parentBusId) {
        const parentBus = cy.getElementById(parentBusId);
        if (parentBus.length > 0) {
          const busPos = parentBus.position();
          const busLength = parentBus.data('busbarLength') || 60;
          const busThickness = 8;
          const equipmentOffset = 25;

          // Redistribute BOTH sides to handle side-switching
          const redistributeSide = (isLeft: boolean) => {
            const allTerminals = cy.nodes(`[kind="terminal"][parentBusId="${parentBusId}"]`);
            const sideTerminals: NodeSingular[] = [];
            allTerminals.forEach((t: NodeSingular) => {
              const tX = t.position('x');
              if (isLeft ? tX < busPos.x : tX >= busPos.x) {
                sideTerminals.push(t);
              }
            });
            sideTerminals.sort((a, b) => a.position('y') - b.position('y'));

            if (sideTerminals.length > 0) {
              // Use margin from bus edges (8px default)
              const terminalEdgeMargin = 8;
              const usableLength = busLength - 2 * terminalEdgeMargin;
              const spacing = usableLength / (sideTerminals.length + 1);
              const xOffset = isLeft ? -busThickness / 2 - 2 : busThickness / 2 + 2;

              sideTerminals.forEach((t, idx) => {
                const newY = busPos.y - busLength / 2 + terminalEdgeMargin + spacing * (idx + 1);
                t.position({ x: busPos.x + xOffset, y: newY });

                // Also move connected equipment with correct X position for this side
                const eqEdges = t.connectedEdges('[kind="equipment_link"]');
                eqEdges.forEach((eqEdge: EdgeSingular) => {
                  const eqId = eqEdge.data('target');
                  const eq = cy.getElementById(eqId);
                  if (eq.length > 0 && eq.data('kind') === 'equipment') {
                    const eqX = isLeft
                      ? busPos.x + xOffset - equipmentOffset
                      : busPos.x + xOffset + equipmentOffset;
                    eq.position({ x: eqX, y: newY });
                    eq.data('attachSide', isLeft ? 'LEFT' : 'RIGHT');
                  }
                });
              });
            }
          };

          // Redistribute both sides
          redistributeSide(true);  // LEFT
          redistributeSide(false); // RIGHT
        }
      }

      // Clean up drag data
      terminal.removeData('_dragStartY');
      terminal.removeData('_dragStartX');
      terminal.removeData('_isDraggingTerminal');
      terminal.removeData('_busX');
      terminal.removeData('_busY');
      terminal.removeData('_busLength');
      terminal.removeData('_busMinY');
      terminal.removeData('_busMaxY');

      // 17.47: Recalculate edge routing after terminal position changes
      // IMPORTANT: Use recalculateEdgeRoutingOnly to NOT reposition other terminals
      if (parentBusId) {
        recalculateEdgeRoutingOnly(cy, parentBusId);
      }
    });

    // Double-click on terminal to flip it to the other side of the bus
    cy.on('dbltap', 'node[kind="terminal"]', (evt) => {
      const terminal = evt.target;
      const parentBusId = terminal.data('parentBusId');

      if (!parentBusId) return;

      const parentBus = cy.getElementById(parentBusId);
      if (parentBus.length === 0) return;

      const busPos = parentBus.position();
      const termPos = terminal.position();
      const busThickness = 8; // From config
      const equipmentOffset = 40; // From config

      // Determine current side and flip to the opposite
      const isCurrentlyLeft = termPos.x < busPos.x;
      const newXOffset = isCurrentlyLeft ? busThickness / 2 + 2 : -busThickness / 2 - 2;
      const newX = busPos.x + newXOffset;

      // Move terminal to the other side
      terminal.position({ x: newX, y: termPos.y });

      // Also move connected equipment to the new side
      const connectedEdges = terminal.connectedEdges('[kind="equipment_link"]');
      connectedEdges.forEach((edge: EdgeSingular) => {
        const equipmentId = edge.data('target');
        const equipment = cy.getElementById(equipmentId);
        if (equipment.length > 0 && equipment.data('kind') === 'equipment') {
          // Equipment goes on same side as terminal, further out
          const side = isCurrentlyLeft ? 1 : -1; // Flipping side
          const equipmentX = newX + side * (equipmentOffset - busThickness / 2);
          equipment.position({ x: equipmentX, y: termPos.y });
        }
      });

      // Redistribute terminals on both sides to even spacing
      const redistributeTerminals = (side: 'left' | 'right') => {
        const isLeft = side === 'left';
        const allTerminals = cy.nodes(`[kind="terminal"][parentBusId="${parentBusId}"]`);
        const sideTerminals: NodeSingular[] = [];

        allTerminals.forEach((t: NodeSingular) => {
          const tX = t.position('x');
          if (isLeft ? tX < busPos.x : tX >= busPos.x) {
            sideTerminals.push(t);
          }
        });

        if (sideTerminals.length === 0) return;

        sideTerminals.sort((a, b) => a.position('y') - b.position('y'));

        const busLength = parentBus.data('busbarLength') || 60;
        // Use margin from bus edges (8px default)
        const terminalEdgeMargin = 8;
        const usableLength = busLength - 2 * terminalEdgeMargin;
        const spacing = usableLength / (sideTerminals.length + 1);
        const xOffset = isLeft ? -busThickness / 2 - 2 : busThickness / 2 + 2;

        sideTerminals.forEach((t, idx) => {
          const newY = busPos.y - busLength / 2 + terminalEdgeMargin + spacing * (idx + 1);
          t.position({ x: busPos.x + xOffset, y: newY });

          // Also reposition connected equipment
          const edges = t.connectedEdges('[kind="equipment_link"]');
          edges.forEach((edge: EdgeSingular) => {
            const eqId = edge.data('target');
            const eq = cy.getElementById(eqId);
            if (eq.length > 0 && eq.data('kind') === 'equipment') {
              const eqSide = isLeft ? -1 : 1;
              const eqX = busPos.x + xOffset + eqSide * (equipmentOffset - busThickness / 2);
              eq.position({ x: eqX, y: newY });
            }
          });
        });
      };

      // Redistribute both sides after the flip
      redistributeTerminals('left');
      redistributeTerminals('right');

      // 17.47: Recalculate edge routing after terminal flip
      // Use recalculateEdgeRoutingOnly to avoid further terminal repositioning
      recalculateEdgeRoutingOnly(cy, parentBusId);
    });

    // Equipment drag handler - moves terminal with equipment to maintain perpendicular connection
    // Allows switching to the opposite side of the bus based on drag position
    cy.on('drag', 'node[kind="equipment"]', (evt) => {
      const equipment = evt.target;
      const equipmentPos = equipment.position();

      // Find connected terminal via equipment_link edge
      const connectedEdges = equipment.connectedEdges('[kind="equipment_link"]');
      if (connectedEdges.length === 0) return;

      const edge = connectedEdges[0];
      const terminalId = edge.data('source');
      const terminal = cy.getElementById(terminalId);
      if (terminal.length === 0) return;

      const parentBusId = terminal.data('parentBusId');
      if (!parentBusId) return;

      const parentBus = cy.getElementById(parentBusId);
      if (parentBus.length === 0) return;

      const busPos = parentBus.position();
      const busLength = parentBus.data('busbarLength') || 60;
      const busThickness = 8;
      const busMinY = busPos.y - busLength / 2;
      const busMaxY = busPos.y + busLength / 2;

      // Constrain equipment Y to bus bounds
      const constrainedY = Math.max(busMinY, Math.min(busMaxY, equipmentPos.y));

      // Determine which side based on where the user is dragging the equipment
      // If equipment is dragged to the left of bus center, put it on left side
      // If equipment is dragged to the right of bus center, put it on right side
      const isLeftSide = equipmentPos.x < busPos.x;

      // Calculate terminal and equipment X positions
      const terminalX = isLeftSide
        ? busPos.x - busThickness / 2 - 2  // LEFT side of bus
        : busPos.x + busThickness / 2 + 2; // RIGHT side of bus
      const equipmentOffset = 25; // Should match EQUIPMENT_OFFSET in sldLayout.ts
      const equipmentX = isLeftSide
        ? terminalX - equipmentOffset  // Further left
        : terminalX + equipmentOffset; // Further right

      // Update both positions - terminal and equipment at SAME Y for perpendicular line
      terminal.position({ x: terminalX, y: constrainedY });
      equipment.position({ x: equipmentX, y: constrainedY });

      // Update attachSide data for proper symbol orientation
      equipment.data('attachSide', isLeftSide ? 'LEFT' : 'RIGHT');
    });

    // Equipment free handler - redistribute terminals on the same side to enforce slot positions
    cy.on('free', 'node[kind="equipment"]', (evt) => {
      const equipment = evt.target;

      // Find connected terminal
      const connectedEdges = equipment.connectedEdges('[kind="equipment_link"]');
      if (connectedEdges.length === 0) return;

      const edge = connectedEdges[0];
      const terminalId = edge.data('source');
      const terminal = cy.getElementById(terminalId);
      if (terminal.length === 0) return;

      const parentBusId = terminal.data('parentBusId');
      if (!parentBusId) return;

      const parentBus = cy.getElementById(parentBusId);
      if (parentBus.length === 0) return;

      const busPos = parentBus.position();
      const termX = terminal.position('x');
      const isLeftSide = termX < busPos.x;

      // Get all terminals on the same side of this bus and redistribute them
      const allTerminals = cy.nodes(`[kind="terminal"][parentBusId="${parentBusId}"]`);
      const sameSideTerminals: NodeSingular[] = [];
      allTerminals.forEach((t: NodeSingular) => {
        const tX = t.position('x');
        if (isLeftSide ? tX < busPos.x : tX >= busPos.x) {
          sameSideTerminals.push(t);
        }
      });

      // Sort by current Y position to preserve relative order
      sameSideTerminals.sort((a, b) => a.position('y') - b.position('y'));

      // Redistribute terminals evenly along the bus (discrete slot positions)
      if (sameSideTerminals.length > 0) {
        const busLength = parentBus.data('busbarLength') || 60;
        // Use margin from bus edges (8px default)
        const terminalEdgeMargin = 8;
        const usableLength = busLength - 2 * terminalEdgeMargin;
        const spacing = usableLength / (sameSideTerminals.length + 1);
        const busThickness = 8;
        const equipmentOffset = 25;

        sameSideTerminals.forEach((t, idx) => {
          const newY = busPos.y - busLength / 2 + terminalEdgeMargin + spacing * (idx + 1);
          const xOffset = isLeftSide ? -busThickness / 2 - 2 : busThickness / 2 + 2;
          t.position({ x: busPos.x + xOffset, y: newY });

          // Also move connected equipment to maintain perpendicular connection
          const eqEdges = t.connectedEdges('[kind="equipment_link"]');
          eqEdges.forEach((eqEdge: EdgeSingular) => {
            const eqId = eqEdge.data('target');
            const eq = cy.getElementById(eqId);
            if (eq.length > 0 && eq.data('kind') === 'equipment') {
              const eqX = isLeftSide
                ? busPos.x + xOffset - equipmentOffset
                : busPos.x + xOffset + equipmentOffset;
              eq.position({ x: eqX, y: newY });
            }
          });
        });
      }

      // Recalculate edge routing after redistribution
      recalculateEdgeRoutingOnly(cy, parentBusId);
    });

    // Clean up drag data after release and optionally snap to grid
    cy.on('free', 'node[kind="bus"]', (evt) => {
      const bus = evt.target;
      const busId = bus.id();

      // Helper to snap a position to grid
      const snapPos = (pos: { x: number; y: number }) => {
        if (!snapToGridRef.current) return pos;
        const gridSz = 20; // Must match gridSize
        return {
          x: Math.round(pos.x / gridSz) * gridSz,
          y: Math.round(pos.y / gridSz) * gridSz,
        };
      };

      // Helper to snap a bus and move its children accordingly
      const snapBusAndChildren = (targetBus: NodeSingular) => {
        if (!snapToGridRef.current) return;
        const targetBusId = targetBus.id();
        const oldPos = targetBus.position();
        const newPos = snapPos(oldPos);
        const dx = newPos.x - oldPos.x;
        const dy = newPos.y - oldPos.y;

        targetBus.position(newPos);

        // Also move children by the same delta
        if (lockEquipmentRef.current) {
          cy.nodes(`[parentBusId="${targetBusId}"], [busId="${targetBusId}"]`).forEach((node) => {
            const nodePos = node.position();
            node.position({ x: nodePos.x + dx, y: nodePos.y + dy });
          });
        }
      };

      // Snap this bus to grid
      snapBusAndChildren(bus);

      // Clean up drag data
      bus.removeData('_dragStartX');
      bus.removeData('_dragStartY');
      // Note: terminals use parentBusId, equipment uses busId
      cy.nodes(`[parentBusId="${busId}"], [busId="${busId}"]`).forEach((node) => {
        node.removeData('_dragStartX');
        node.removeData('_dragStartY');
      });

      // Clean up and snap for all selected buses if multi-select
      const selectedBuses = cy.nodes('[kind="bus"]:selected');
      if (selectedBuses.length > 1) {
        selectedBuses.forEach((otherBus) => {
          if (otherBus.id() !== bus.id()) {
            snapBusAndChildren(otherBus);
          }
          otherBus.removeData('_dragStartX');
          otherBus.removeData('_dragStartY');
          const otherBusId = otherBus.id();
          cy.nodes(`[parentBusId="${otherBusId}"], [busId="${otherBusId}"]`).forEach((node) => {
            node.removeData('_dragStartX');
            node.removeData('_dragStartY');
          });
        });

        cy.nodes('[kind="transformer"]:selected, [kind="transformer2"]:selected, [kind="transformer3"]:selected').forEach((xfmr) => {
          // Snap transformers to grid too
          if (snapToGridRef.current) {
            const gridSz = 20;
            const pos = xfmr.position();
            xfmr.position({
              x: Math.round(pos.x / gridSz) * gridSz,
              y: Math.round(pos.y / gridSz) * gridSz,
            });
          }
          xfmr.removeData('_dragStartX');
          xfmr.removeData('_dragStartY');
        });
      }
    });


    cyRef.current = cy;

    return () => {
      cy.destroy();
      cyRef.current = null;
    };
  }, [onNodeSelect, onEdgeSelect]);

  // Load view when fileId or centerBusNumber changes
  useEffect(() => {
    if (!fileId || centerBusNumber === null) {
      return;
    }

    const loadView = async () => {
      setLoading(true);
      setError(null);
      console.log('%c[GraphViewer] ===== LOAD VIEW STARTING =====', 'color: purple; font-weight: bold');
      const totalStart = performance.now();

      try {
        const spec: ViewSpec = defaultViewSpec({
          mode: 'bus',
          center_bus_numbers: [centerBusNumber],
          max_depth: 2, // Start with small depth to enable incremental expansion
        });

        const apiStart = performance.now();
        const payload = await generateView(fileId, spec);
        console.log(`%c[TIMING] API generateView: ${(performance.now() - apiStart).toFixed(1)}ms`, 'color: #0066cc; font-weight: bold');
        console.log(`%c[TIMING] Payload: ${payload.elements.nodes.length} nodes, ${payload.elements.edges.length} edges`, 'color: orange');

        const renderStart = performance.now();
        await renderPayload(payload, centerBusNumber);
        console.log(`%c[TIMING] renderPayload: ${(performance.now() - renderStart).toFixed(1)}ms`, 'color: #0066cc; font-weight: bold');

        setMeta(payload.meta);
        console.log(`%c[GraphViewer] ===== LOAD VIEW COMPLETE: ${(performance.now() - totalStart).toFixed(1)}ms =====`, 'color: purple; font-weight: bold');
      } catch (err) {
        if (err instanceof ApiError) {
          setError(`${err.code}: ${err.message}`);
        } else {
          setError('Failed to load view');
        }
      } finally {
        setLoading(false);
      }
    };

    loadView();
  }, [fileId, centerBusNumber]);

  // Update visibility based on displayDepth (also runs when dataVersion changes)
  useEffect(() => {
    if (!cyRef.current) return;

    const cy = cyRef.current;

    // First pass: Hide/show buses based on bfs_depth
    cy.nodes('[kind="bus"]').forEach((node) => {
      const depth = node.data('bfs_depth');
      if (depth !== undefined && depth > displayDepth) {
        node.addClass('hidden');
      } else {
        node.removeClass('hidden');
      }
    });

    // Second pass: Terminals and equipment follow their parent bus
    cy.nodes('[kind="terminal"], [kind="equipment"]').forEach((node) => {
      const parentBusId = node.data('parentBusId') || node.data('busId');
      if (parentBusId) {
        const parentBus = cy.getElementById(parentBusId);
        if (parentBus.length > 0 && parentBus.hasClass('hidden')) {
          node.addClass('hidden');
        } else {
          node.removeClass('hidden');
        }
      }
    });

    // Third pass: Transformers - show if ANY connected bus is visible
    // When a transformer bridges a visible bus to a bus beyond depth, show BOTH sides
    cy.nodes('[kind="transformer"], [kind="transformer2"], [kind="transformer3"]').forEach((xfmr) => {
      // Find connected terminals via edges
      const connectedTerminals = xfmr.connectedEdges().connectedNodes().filter(
        (n) => n.data('kind') === 'terminal'
      );

      // Check if ANY connected bus is visible (not hidden)
      const anyVisible = connectedTerminals.some((term) => {
        const parentBusId = term.data('parentBusId');
        if (!parentBusId) return false;
        const parentBus = cy.getElementById(parentBusId);
        return parentBus.length > 0 && !parentBus.hasClass('hidden');
      });

      if (anyVisible && connectedTerminals.length > 0) {
        // Show the transformer
        xfmr.removeClass('hidden');

        // Also unhide all connected buses (both sides of transformer)
        // This is the special transformer exception: if one side is within depth,
        // we show the other side too (even if it's beyond depth)
        connectedTerminals.forEach((term) => {
          const parentBusId = term.data('parentBusId');
          if (parentBusId) {
            const parentBus = cy.getElementById(parentBusId);
            if (parentBus.length > 0) {
              parentBus.removeClass('hidden');
              // Also unhide the terminal itself
              term.removeClass('hidden');
            }
          }
        });
      } else {
        xfmr.addClass('hidden');
      }
    });

    // Fourth pass: Hide edges if either endpoint is hidden
    cy.edges().forEach((edge) => {
      const source = cy.getElementById(edge.data('source'));
      const target = cy.getElementById(edge.data('target'));
      if ((source.length > 0 && source.hasClass('hidden')) ||
          (target.length > 0 && target.hasClass('hidden'))) {
        edge.addClass('hidden');
      } else {
        edge.removeClass('hidden');
      }
    });
  }, [displayDepth, dataVersion]);

  // Apply diagnostics when state changes
  useEffect(() => {
    if (cyRef.current) {
      applyDiagnostics(cyRef.current, diagnostics);
    }
  }, [diagnostics]);

  const renderPayload = useCallback(async (payload: CytoscapePayload, centerOnBusNumber?: number) => {
    const cy = cyRef.current;
    if (!cy) return;

    // Clear existing elements
    cy.elements().remove();

    // Convert payload to Cytoscape format
    const elements: ElementDefinition[] = [
      ...payload.elements.nodes.map((n) => ({ data: n.data, group: 'nodes' as const })),
      ...payload.elements.edges.map((e) => ({ data: e.data, group: 'edges' as const })),
    ];

    cy.add(elements);

    // Run SLD layout
    try {
      const result = await runSldLayout(cy, layoutDirection);
      setLayoutResult(result);
    } catch (err) {
      console.error('Layout failed:', err);
      // Fallback to simple layout
      cy.layout({
        name: 'breadthfirst',
        directed: false,
        spacingFactor: 1.5,
        animate: false,
      }).run();
    }

    // Apply diagnostics if enabled
    applyDiagnostics(cy, diagnostics);

    // Equipment IS now grabbable so users can reposition it
    // Terminals ARE grabbable so users can reorder them along their bus
    // Transformers ARE grabbable so users can adjust their position between buses
    // All node types can be dragged by the user

    // Center on the specified bus if provided, otherwise fit to all
    if (centerOnBusNumber !== undefined) {
      // Find the center bus node
      const centerBusNode = cy.nodes('[kind="bus"]').filter((node) => {
        return node.data('psse_number') === centerOnBusNumber;
      });

      if (centerBusNode.length > 0) {
        // Center on the bus and zoom to a reasonable level
        cy.center(centerBusNode);
        cy.zoom({ level: 1.5, position: centerBusNode.position() });
      } else {
        // Fallback: fit to all visible elements
        cy.fit(undefined, 50);
      }
    } else {
      // Fit to viewport
      cy.fit(undefined, 50);
    }

    // Increment data version to trigger depth filtering
    setDataVersion((v) => v + 1);
  }, [layoutDirection, diagnostics]);

  /**
   * Expand from a specific bus - adds new elements to existing view instead of replacing.
   * This allows incremental exploration of the network.
   */
  const expandFromBus = useCallback(async (
    expansionBusPsseNumber: number,
    depth: number
  ) => {
    const cy = cyRef.current;
    if (!cy || !fileId) return;

    setLoading(true);
    setError(null);

    try {
      // Step 1: Save positions of all existing nodes
      const existingPositions = new Map<string, { x: number; y: number }>();
      const existingNodeIds = new Set<string>();
      const existingEdgeIds = new Set<string>();

      cy.nodes().forEach((node) => {
        existingNodeIds.add(node.id());
        existingPositions.set(node.id(), { ...node.position() });
      });
      cy.edges().forEach((edge) => {
        existingEdgeIds.add(edge.id());
      });

      // Find the expansion bus position (new nodes will be placed near it)
      const expansionBus = cy.nodes('[kind="bus"]').filter((node) =>
        node.data('psse_number') === expansionBusPsseNumber
      );
      const expansionPos = expansionBus.length > 0
        ? expansionBus.position()
        : { x: 0, y: 0 };

      // Step 2: Fetch new data centered on the expansion bus
      const spec: ViewSpec = defaultViewSpec({
        mode: 'bus',
        center_bus_numbers: [expansionBusPsseNumber],
        max_depth: depth,
      });

      console.log('[Expand] Fetching view for bus', expansionBusPsseNumber, 'with depth', depth);
      console.log('[Expand] ViewSpec:', spec);

      const payload = await generateView(fileId, spec);
      console.log('[Expand] Received payload with', payload.elements.nodes.length, 'nodes and', payload.elements.edges.length, 'edges');

      // Step 3: Filter to only new elements
      const newNodes: ElementDefinition[] = [];
      const newEdges: ElementDefinition[] = [];

      for (const node of payload.elements.nodes) {
        if (!existingNodeIds.has(node.data.id)) {
          newNodes.push({ data: node.data, group: 'nodes' as const });
        }
      }

      for (const edge of payload.elements.edges) {
        if (!existingEdgeIds.has(edge.data.id)) {
          // Only add edge if both endpoints exist (either already in graph or being added)
          const sourceExists = existingNodeIds.has(edge.data.source) ||
            newNodes.some(n => n.data?.id === edge.data.source);
          const targetExists = existingNodeIds.has(edge.data.target) ||
            newNodes.some(n => n.data?.id === edge.data.target);

          if (sourceExists && targetExists) {
            newEdges.push({ data: edge.data, group: 'edges' as const });
          }
        }
      }

      console.log(`[Expand] Adding ${newNodes.length} new nodes and ${newEdges.length} new edges from bus ${expansionBusPsseNumber}`);

      if (newNodes.length === 0 && newEdges.length === 0) {
        console.log('[Expand] No new elements to add - all elements already in view');
        // Show user-friendly message
        setError(`No new elements found within depth ${depth} from bus ${expansionBusPsseNumber}. Try increasing the depth or the elements may already be in the view.`);
        // Clear error after 3 seconds
        setTimeout(() => setError(null), 3000);
        setLoading(false);
        return;
      }

      // Step 4: Add new elements to the graph
      // Position new nodes initially near the expansion bus (spread out)
      const newBuses = newNodes.filter(n => n.data?.kind === 'bus');
      const spreadRadius = 150;

      newBuses.forEach((node, idx) => {
        const angle = (idx / newBuses.length) * 2 * Math.PI;
        const x = expansionPos.x + spreadRadius * Math.cos(angle);
        const y = expansionPos.y + spreadRadius * Math.sin(angle);
        (node as ElementDefinition & { position?: { x: number; y: number } }).position = { x, y };
      });

      cy.add([...newNodes, ...newEdges]);

      // Show success feedback
      console.log(`[Expand] Successfully added ${newNodes.length} nodes and ${newEdges.length} edges`);

      // Step 5: Lock existing nodes and run layout only on new nodes
      // First, lock all existing buses
      existingNodeIds.forEach((nodeId) => {
        const node = cy.getElementById(nodeId);
        if (node.length > 0) {
          node.lock();
        }
      });

      // Run layout (will only move unlocked nodes)
      try {
        const result = await runSldLayout(cy, layoutDirection);
        setLayoutResult(result);
      } catch (err) {
        console.error('Layout failed during expansion:', err);
      }

      // Unlock all nodes
      cy.nodes().unlock();

      // Restore original positions for existing nodes (in case layout moved them)
      existingPositions.forEach((pos, nodeId) => {
        const node = cy.getElementById(nodeId);
        if (node.length > 0) {
          node.position(pos);
        }
      });

      // Position terminals and equipment for new buses
      // (they should have been positioned by layout, but let's ensure they're correct)

      // Apply diagnostics if enabled
      applyDiagnostics(cy, diagnostics);

      // Center on the expansion bus
      if (expansionBus.length > 0) {
        cy.center(expansionBus);
        cy.zoom({ level: 1.5, position: expansionBus.position() });
      }

      // Trigger depth filtering update
      setDataVersion((v) => v + 1);

    } catch (err) {
      if (err instanceof ApiError) {
        setError(`${err.code}: ${err.message}`);
      } else {
        setError('Failed to expand view');
      }
      console.error('Expansion failed:', err);
    } finally {
      setLoading(false);
    }
  }, [fileId, layoutDirection, diagnostics]);

  const handleFit = useCallback(() => {
    cyRef.current?.fit(undefined, 50);
  }, []);

  const handleZoomIn = useCallback(() => {
    const cy = cyRef.current;
    if (cy) cy.zoom(cy.zoom() * 1.5);
  }, []);

  const handleZoomOut = useCallback(() => {
    const cy = cyRef.current;
    if (cy) cy.zoom(cy.zoom() / 1.5);
  }, []);

  const handleResetZoom = useCallback(() => {
    const cy = cyRef.current;
    if (cy) {
      cy.zoom(1);
      cy.center();
    }
  }, []);

  const handleRelayout = useCallback(async () => {
    const cy = cyRef.current;
    if (!cy) return;

    setLoading(true);
    try {
      const result = await runSldLayout(cy, layoutDirection);
      setLayoutResult(result);
      applyDiagnostics(cy, diagnostics);
      cy.fit(undefined, 50);
    } catch (err) {
      console.error('Re-layout failed:', err);
    } finally {
      setLoading(false);
    }
  }, [layoutDirection, diagnostics]);

  const handleToggleDiagnostics = useCallback(() => {
    setDiagnostics((prev) => ({ ...prev, enabled: !prev.enabled }));
  }, []);

  // Handle bus resize from slider
  const handleBusResize = useCallback((newLength: number) => {
    const cy = cyRef.current;
    if (!cy || !selectedBus) return;

    const busNode = cy.getElementById(selectedBus.id);
    if (busNode.length === 0) return;

    // Update the bus bar size
    const orientation = selectedBus.orientation;
    if (orientation === 'horizontal') {
      busNode.style('width', newLength);
    } else {
      busNode.style('height', newLength);
    }

    // Store user-specified length in node data
    busNode.data('userBusbarLength', newLength);

    // Update selected bus state
    setSelectedBus(prev => prev ? { ...prev, currentLength: newLength } : null);

    // Reposition terminals to fit the new bus bar length
    const busId = selectedBus.id;
    const busPos = busNode.position();
    const terminals = cy.nodes(`[parentBusId="${busId}"][kind="terminal"]`);

    // Group terminals by side
    const leftTerminals: NodeSingular[] = [];
    const rightTerminals: NodeSingular[] = [];

    terminals.forEach((term) => {
      const termX = term.position('x');
      if (termX < busPos.x) {
        leftTerminals.push(term);
      } else {
        rightTerminals.push(term);
      }
    });

    // Reposition terminals along the resized bus
    const repositionTerminals = (terms: NodeSingular[], xOffset: number) => {
      if (terms.length === 0) return;

      // Sort by current Y position to maintain order
      terms.sort((a, b) => a.position('y') - b.position('y'));

      const spacing = newLength / (terms.length + 1);
      terms.forEach((term, idx) => {
        const y = busPos.y - newLength / 2 + spacing * (idx + 1);
        term.position({ x: busPos.x + xOffset, y });
      });
    };

    const busThickness = 8; // from config
    repositionTerminals(leftTerminals, -busThickness / 2 - 2);
    repositionTerminals(rightTerminals, busThickness / 2 + 2);
  }, [selectedBus]);

  // Keyboard shortcuts
  useKeyboardShortcuts(cyRef.current, {
    onZoomIn: handleZoomIn,
    onZoomOut: handleZoomOut,
    onFit: handleFit,
    onResetZoom: handleResetZoom,
    onRelayout: handleRelayout,
    onToggleDiagnostics: handleToggleDiagnostics,
  });

  // Box selection handlers for area zoom (Shift) and multi-select (Ctrl)
  const handleBoxMouseDown = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    // Shift = zoom mode, Ctrl = select mode
    if (!e.shiftKey && !e.ctrlKey && !e.metaKey) return;

    const container = containerRef.current;
    if (!container) return;

    const rect = container.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    setBoxSelectActive(true);
    setBoxSelectMode(e.shiftKey ? 'zoom' : 'select');
    setBoxStart({ x, y });
    setBoxEnd({ x, y });
    e.preventDefault();
  }, []);

  const handleBoxMouseMove = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if (!boxSelectActive || !boxStart) return;

    const container = containerRef.current;
    if (!container) return;

    const rect = container.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    setBoxEnd({ x, y });
  }, [boxSelectActive, boxStart]);

  const handleBoxMouseUp = useCallback(() => {
    if (!boxSelectActive || !boxStart || !boxEnd || !cyRef.current) {
      setBoxSelectActive(false);
      setBoxStart(null);
      setBoxEnd(null);
      return;
    }

    const cy = cyRef.current;

    // Calculate the selection box in rendered coordinates
    const minX = Math.min(boxStart.x, boxEnd.x);
    const maxX = Math.max(boxStart.x, boxEnd.x);
    const minY = Math.min(boxStart.y, boxEnd.y);
    const maxY = Math.max(boxStart.y, boxEnd.y);

    // Only process if box is at least 20px in both dimensions
    if (maxX - minX > 20 && maxY - minY > 20) {
      // Convert rendered coordinates to model coordinates
      const pan = cy.pan();
      const zoom = cy.zoom();

      const modelMinX = (minX - pan.x) / zoom;
      const modelMaxX = (maxX - pan.x) / zoom;
      const modelMinY = (minY - pan.y) / zoom;
      const modelMaxY = (maxY - pan.y) / zoom;

      if (boxSelectMode === 'zoom') {
        // Zoom to the selected area
        const boxWidth = modelMaxX - modelMinX;
        const boxHeight = modelMaxY - modelMinY;
        const containerWidth = cy.width();
        const containerHeight = cy.height();

        const newZoom = Math.min(
          containerWidth / boxWidth,
          containerHeight / boxHeight,
          cy.maxZoom()
        ) * 0.9; // 90% to add some padding

        const centerX = (modelMinX + modelMaxX) / 2;
        const centerY = (modelMinY + modelMaxY) / 2;

        cy.zoom({
          level: newZoom,
          position: { x: centerX, y: centerY },
        });
      } else {
        // Multi-select mode: select all buses in the box
        cy.$(':selected').unselect(); // Clear previous selection

        cy.nodes('[kind="bus"]').forEach((node) => {
          const pos = node.position();
          if (pos.x >= modelMinX && pos.x <= modelMaxX &&
              pos.y >= modelMinY && pos.y <= modelMaxY) {
            node.select();
          }
        });

        // Also select transformers in the box
        cy.nodes('[kind="transformer"], [kind="transformer2"], [kind="transformer3"]').forEach((node) => {
          const pos = node.position();
          if (pos.x >= modelMinX && pos.x <= modelMaxX &&
              pos.y >= modelMinY && pos.y <= modelMaxY) {
            node.select();
          }
        });

        const selectedCount = cy.$(':selected').length;
        setMultiSelectActive(selectedCount > 1);
        setSelectedBus(null); // Disable bus resize panel in multi-select mode
      }
    }

    setBoxSelectActive(false);
    setBoxStart(null);
    setBoxEnd(null);
  }, [boxSelectActive, boxStart, boxEnd, boxSelectMode]);

  // Calculate box selection rect style (different colors for zoom vs select mode)
  const getBoxStyle = (): React.CSSProperties | null => {
    if (!boxStart || !boxEnd) return null;

    const minX = Math.min(boxStart.x, boxEnd.x);
    const minY = Math.min(boxStart.y, boxEnd.y);
    const width = Math.abs(boxEnd.x - boxStart.x);
    const height = Math.abs(boxEnd.y - boxStart.y);

    const isSelect = boxSelectMode === 'select';
    return {
      position: 'absolute',
      left: minX,
      top: minY,
      width,
      height,
      border: `2px dashed ${isSelect ? '#28a745' : '#007bff'}`,
      backgroundColor: isSelect ? 'rgba(40, 167, 69, 0.1)' : 'rgba(0, 123, 255, 0.1)',
      pointerEvents: 'none',
      zIndex: 1000,
    };
  };

  // Get diagnostics info when enabled
  const diagInfo = diagnostics.enabled && cyRef.current
    ? getDiagnosticsInfo(cyRef.current)
    : null;

  return (
    <div style={styles.container}>
      <div style={styles.controls}>
        <div style={styles.depthControl}>
          <label htmlFor="depth-slider">Depth: {displayDepth}</label>
          <input
            id="depth-slider"
            type="range"
            min={0}
            max={15}
            value={displayDepth}
            onChange={(e) => setDisplayDepth(parseInt(e.target.value, 10))}
            style={styles.slider}
          />
        </div>

        <div style={styles.directionControl}>
          <label htmlFor="direction-select">Direction:</label>
          <select
            id="direction-select"
            value={layoutDirection}
            onChange={(e) => setLayoutDirection(e.target.value as LayoutDirection)}
            style={styles.select}
          >
            <option value="AUTO">Auto</option>
            <option value="RIGHT">Right</option>
            <option value="DOWN">Down</option>
          </select>
        </div>

        {/* 17.18: Edit Mode Toggle */}
        <div style={styles.editModeControl}>
          <label style={{
            ...styles.checkboxLabel,
            backgroundColor: editMode ? '#e8f5e9' : '#ffebee',
            padding: '4px 8px',
            borderRadius: '4px',
            border: editMode ? '1px solid #4caf50' : '1px solid #f44336',
          }}>
            <input
              type="checkbox"
              checked={editMode}
              onChange={(e) => setEditMode(e.target.checked)}
            />
            {editMode ? '✏️ Edit Mode' : '🔒 Locked'}
          </label>
        </div>

        <div style={styles.lockControl}>
          <label style={styles.checkboxLabel}>
            <input
              type="checkbox"
              checked={lockEquipmentToBus}
              onChange={(e) => setLockEquipmentToBus(e.target.checked)}
            />
            Lock equipment
          </label>
        </div>

        <div style={styles.gridControl}>
          <label style={styles.checkboxLabel}>
            <input
              type="checkbox"
              checked={showGrid}
              onChange={(e) => setShowGrid(e.target.checked)}
            />
            Grid
          </label>
          <label style={{ ...styles.checkboxLabel, marginLeft: '8px' }}>
            <input
              type="checkbox"
              checked={snapToGrid}
              onChange={(e) => setSnapToGrid(e.target.checked)}
            />
            Snap
          </label>
        </div>

        <div style={styles.zoomControls}>
          <button onClick={handleZoomIn} style={styles.button} title="Zoom in (+)">+</button>
          <button onClick={handleZoomOut} style={styles.button} title="Zoom out (-)">-</button>
          <button onClick={handleFit} style={styles.button} title="Fit to view (F)">Fit</button>
          <button onClick={handleRelayout} style={styles.button} title="Re-layout (R)">Layout</button>
          <button
            onClick={handleToggleDiagnostics}
            style={{
              ...styles.button,
              backgroundColor: diagnostics.enabled ? '#e7f3ff' : '#f0f0f0',
            }}
            title="Toggle diagnostics (D)"
          >
            Diag
          </button>
          <button
            onClick={() => setShowShortcuts(!showShortcuts)}
            style={styles.button}
            title="Show keyboard shortcuts"
          >
            ?
          </button>
        </div>

        {meta && (
          <span style={styles.meta}>
            Nodes: {meta.node_count as number} | Edges: {meta.edge_count as number}
            {layoutResult && !layoutResult.fallback && (
              <> | Dir: {layoutResult.direction}</>
            )}
            {layoutResult?.fallback && (
              <span style={{ color: '#dc3545' }}> | Fallback layout</span>
            )}
          </span>
        )}
      </div>

      {/* Diagnostics panel */}
      {diagnostics.enabled && diagInfo && (
        <div style={styles.diagPanel}>
          <strong>Diagnostics</strong>
          <div>Buses: {diagInfo.busCount}</div>
          <div>Terminals: {diagInfo.terminalCount}</div>
          <div>Equipment: {diagInfo.equipmentCount}</div>
          <div>Transformers: {diagInfo.transformerCount}</div>
          <div style={diagInfo.collisionStats.equipmentCollisions > 0 ? { color: '#dc3545' } : {}}>
            Equipment collisions: {diagInfo.collisionStats.equipmentCollisions}
          </div>
          <div style={diagInfo.collisionStats.busCollisions > 0 ? { color: '#dc3545' } : {}}>
            Bus collisions: {diagInfo.collisionStats.busCollisions}
          </div>
          {diagInfo.nodesAtOrigin > 0 && (
            <div style={{ color: '#fd7e14' }}>
              Nodes at origin: {diagInfo.nodesAtOrigin}
            </div>
          )}
        </div>
      )}

      {/* Bus resize panel - shown when a bus is selected */}
      {selectedBus && (
        <div style={styles.busResizePanel}>
          <strong>Bus: {selectedBus.psseNumber}</strong>
          <div style={{ fontSize: '11px', color: '#666', marginBottom: '8px' }}>{selectedBus.name}</div>
          <div style={styles.resizeControl}>
            <label htmlFor="bus-size-slider">Size: {Math.round(selectedBus.currentLength)}px</label>
            <input
              id="bus-size-slider"
              type="range"
              min={30}
              max={400}
              value={selectedBus.currentLength}
              onChange={(e) => handleBusResize(parseInt(e.target.value, 10))}
              style={styles.resizeSlider}
            />
          </div>
          <div style={{ fontSize: '10px', color: '#999', marginTop: '4px' }}>
            Click elsewhere to deselect
          </div>
        </div>
      )}

      {/* Shortcuts panel */}
      {showShortcuts && (
        <div style={styles.shortcutsPanel}>
          <strong>Keyboard Shortcuts</strong>
          {getShortcutsList().map(({ key, description }) => (
            <div key={key}>
              <span style={styles.shortcutKey}>{key}</span> {description}
            </div>
          ))}
        </div>
      )}

      <div
        style={styles.graphWrapper}
        onMouseDown={handleBoxMouseDown}
        onMouseMove={handleBoxMouseMove}
        onMouseUp={handleBoxMouseUp}
        onMouseLeave={handleBoxMouseUp}
      >
        {/* Cytoscape container - must have no React children */}
        <div ref={containerRef} style={styles.graphContainer} />
        {/* Grid overlay - rendered as SVG pattern */}
        {showGrid && (
          <svg
            style={styles.gridOverlay}
            xmlns="http://www.w3.org/2000/svg"
          >
            <defs>
              <pattern
                id="grid-pattern"
                width={gridSize}
                height={gridSize}
                patternUnits="userSpaceOnUse"
              >
                <path
                  d={`M ${gridSize} 0 L 0 0 0 ${gridSize}`}
                  fill="none"
                  stroke="rgba(0,0,0,0.1)"
                  strokeWidth="0.5"
                />
              </pattern>
              <pattern
                id="grid-pattern-major"
                width={gridSize * 5}
                height={gridSize * 5}
                patternUnits="userSpaceOnUse"
              >
                <rect width={gridSize * 5} height={gridSize * 5} fill="url(#grid-pattern)" />
                <path
                  d={`M ${gridSize * 5} 0 L 0 0 0 ${gridSize * 5}`}
                  fill="none"
                  stroke="rgba(0,0,0,0.2)"
                  strokeWidth="1"
                />
              </pattern>
            </defs>
            <rect width="100%" height="100%" fill="url(#grid-pattern-major)" />
          </svg>
        )}
        {/* Box selection overlay */}
        {boxSelectActive && boxStart && boxEnd && (
          <div style={getBoxStyle() || undefined} ref={boxOverlayRef} />
        )}
        {/* Overlays rendered separately */}
        {loading && <div style={styles.overlay}>Loading...</div>}
        {error && <div style={styles.errorOverlay}>{error}</div>}
        {!fileId && <div style={styles.placeholder}>Upload a case file to begin</div>}
        {fileId && centerBusNumber === null && (
          <div style={styles.placeholder}>Enter a bus number to view the diagram</div>
        )}
        {/* Box selection hint */}
        {fileId && centerBusNumber !== null && !loading && !error && (
          <div style={styles.boxSelectHint}>
            Shift+Drag: Zoom | Ctrl+Drag: Select | Ctrl+Click: Toggle | Dbl-click terminal: Flip side
          </div>
        )}
        {/* Multi-select indicator */}
        {multiSelectActive && cyRef.current && (
          <div style={styles.multiSelectIndicator}>
            {cyRef.current.$(':selected').length} items selected - Drag any to move all
          </div>
        )}
        {/* Context menu */}
        {contextMenu && contextMenu.visible && (
          <div
            style={{
              ...styles.contextMenu,
              left: contextMenu.x,
              top: contextMenu.y,
            }}
            onClick={() => setContextMenu(null)}
          >
            <div style={styles.contextMenuHeader}>
              Bus {contextMenu.busNumber}
            </div>
            <div
              style={styles.contextMenuItem}
              onClick={(e) => {
                e.stopPropagation();
                // Store the target bus info before closing context menu
                setExpandTargetBus({
                  id: contextMenu.busId,
                  number: contextMenu.busNumber,
                  name: contextMenu.busName,
                });
                setShowExpandDialog(true);
                setContextMenu(null);
              }}
            >
              Expand from this bus...
            </div>
            <div
              style={styles.contextMenuItem}
              onClick={(e) => {
                e.stopPropagation();
                // Center on this bus
                const busNode = cyRef.current?.getElementById(contextMenu.busId);
                if (busNode && busNode.length > 0) {
                  cyRef.current?.center(busNode);
                  cyRef.current?.zoom({ level: 2, position: busNode.position() });
                }
                setContextMenu(null);
              }}
            >
              Center on bus
            </div>
            <div
              style={styles.contextMenuItem}
              onClick={(e) => {
                e.stopPropagation();
                // Toggle bus shape between circle and busbar
                const busNode = cyRef.current?.getElementById(contextMenu.busId);
                if (busNode && busNode.length > 0) {
                  const currentForce = busNode.data('forceShape') as string | undefined;
                  const connectionCount = busNode.data('connectionCount') as number || 0;

                  // Cycle through: auto -> opposite of current -> back to auto
                  if (currentForce === 'circle') {
                    busNode.data('forceShape', 'busbar');
                  } else if (currentForce === 'busbar') {
                    busNode.removeData('forceShape');
                  } else {
                    // Auto mode: toggle to opposite of what would be shown
                    const isCircle = connectionCount <= 2;
                    busNode.data('forceShape', isCircle ? 'busbar' : 'circle');
                  }
                }
                setContextMenu(null);
              }}
            >
              {(() => {
                const busNode = cyRef.current?.getElementById(contextMenu.busId);
                if (!busNode || busNode.length === 0) return 'Toggle bus shape';
                const forceShape = busNode.data('forceShape') as string | undefined;
                const connectionCount = busNode.data('connectionCount') as number || 0;
                const isCurrentlyCircle = forceShape === 'circle' || (!forceShape && connectionCount <= 2);
                return isCurrentlyCircle ? 'Show as busbar' : 'Show as circle';
              })()}
            </div>
          </div>
        )}
        {/* Expand depth dialog */}
        {showExpandDialog && expandTargetBus && (
          <div style={styles.dialogOverlay} onClick={() => { setShowExpandDialog(false); setExpandTargetBus(null); }}>
            <div style={styles.dialog} onClick={(e) => e.stopPropagation()}>
              <div style={styles.dialogHeader}>
                Expand from Bus {expandTargetBus.number}
              </div>
              <div style={styles.dialogBody}>
                <label htmlFor="expand-depth">Expansion depth:</label>
                <input
                  id="expand-depth"
                  type="number"
                  min={1}
                  max={10}
                  value={expandDepthInput}
                  onChange={(e) => setExpandDepthInput(parseInt(e.target.value, 10) || 1)}
                  style={styles.dialogInput}
                />
                <div style={{ fontSize: '12px', color: '#666', marginTop: '8px' }}>
                  Number of hops from this bus to add to the view
                </div>
              </div>
              <div style={styles.dialogActions}>
                <button
                  style={styles.dialogButton}
                  onClick={() => { setShowExpandDialog(false); setExpandTargetBus(null); }}
                >
                  Cancel
                </button>
                <button
                  style={{ ...styles.dialogButton, ...styles.dialogButtonPrimary }}
                  onClick={() => {
                    // Call incremental expansion - adds new elements to existing view
                    expandFromBus(expandTargetBus.number, expandDepthInput);
                    setShowExpandDialog(false);
                    setExpandTargetBus(null);
                  }}
                >
                  Expand
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    width: '100%',
    height: '100%',
    position: 'relative',
  },
  controls: {
    display: 'flex',
    alignItems: 'center',
    gap: '20px',
    padding: '10px 20px',
    borderBottom: '1px solid #ddd',
    backgroundColor: '#fff',
    flexWrap: 'wrap',
  },
  depthControl: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    fontSize: '14px',
  },
  directionControl: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    fontSize: '14px',
  },
  slider: {
    width: '120px',
  },
  select: {
    padding: '4px 8px',
    borderRadius: '4px',
    border: '1px solid #ccc',
    fontSize: '14px',
  },
  lockControl: {
    display: 'flex',
    alignItems: 'center',
    fontSize: '14px',
  },
  editModeControl: {
    display: 'flex',
    alignItems: 'center',
    fontSize: '14px',
  },
  checkboxLabel: {
    display: 'flex',
    alignItems: 'center',
    gap: '4px',
    cursor: 'pointer',
  },
  zoomControls: {
    display: 'flex',
    gap: '5px',
  },
  button: {
    padding: '5px 10px',
    backgroundColor: '#f0f0f0',
    border: '1px solid #ccc',
    borderRadius: '4px',
    cursor: 'pointer',
    fontSize: '14px',
  },
  meta: {
    marginLeft: 'auto',
    fontSize: '12px',
    color: '#666',
  },
  graphWrapper: {
    flex: 1,
    position: 'relative',
    minHeight: '400px',
  },
  graphContainer: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: '#fafafa',
  },
  overlay: {
    position: 'absolute',
    top: '50%',
    left: '50%',
    transform: 'translate(-50%, -50%)',
    padding: '20px',
    backgroundColor: 'rgba(255,255,255,0.9)',
    borderRadius: '8px',
    fontSize: '16px',
    boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
  },
  errorOverlay: {
    position: 'absolute',
    top: '50%',
    left: '50%',
    transform: 'translate(-50%, -50%)',
    padding: '20px',
    backgroundColor: 'rgba(255,255,255,0.9)',
    borderRadius: '8px',
    fontSize: '16px',
    color: '#dc3545',
    boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
  },
  placeholder: {
    position: 'absolute',
    top: '50%',
    left: '50%',
    transform: 'translate(-50%, -50%)',
    color: '#999',
    fontSize: '16px',
  },
  diagPanel: {
    position: 'absolute',
    top: '60px',
    right: '10px',
    padding: '10px',
    backgroundColor: 'rgba(255,255,255,0.95)',
    borderRadius: '4px',
    boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
    fontSize: '12px',
    zIndex: 100,
    lineHeight: 1.6,
  },
  shortcutsPanel: {
    position: 'absolute',
    top: '60px',
    left: '10px',
    padding: '10px',
    backgroundColor: 'rgba(255,255,255,0.95)',
    borderRadius: '4px',
    boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
    fontSize: '12px',
    zIndex: 100,
    lineHeight: 1.6,
  },
  shortcutKey: {
    display: 'inline-block',
    padding: '2px 6px',
    backgroundColor: '#eee',
    borderRadius: '3px',
    fontFamily: 'monospace',
    marginRight: '8px',
    minWidth: '24px',
    textAlign: 'center',
  },
  boxSelectHint: {
    position: 'absolute',
    bottom: '10px',
    right: '10px',
    padding: '4px 8px',
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    color: '#fff',
    borderRadius: '4px',
    fontSize: '11px',
    pointerEvents: 'none',
    zIndex: 50,
  },
  busResizePanel: {
    position: 'absolute',
    top: '60px',
    left: '50%',
    transform: 'translateX(-50%)',
    padding: '12px 16px',
    backgroundColor: 'rgba(255,255,255,0.98)',
    borderRadius: '8px',
    boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
    fontSize: '13px',
    zIndex: 100,
    minWidth: '200px',
    border: '1px solid #ddd',
  },
  resizeControl: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '6px',
  },
  resizeSlider: {
    width: '100%',
    cursor: 'pointer',
  },
  multiSelectIndicator: {
    position: 'absolute',
    top: '10px',
    left: '50%',
    transform: 'translateX(-50%)',
    padding: '8px 16px',
    backgroundColor: 'rgba(40, 167, 69, 0.9)',
    color: '#fff',
    borderRadius: '4px',
    fontSize: '13px',
    fontWeight: 500,
    pointerEvents: 'none',
    zIndex: 100,
    boxShadow: '0 2px 8px rgba(0,0,0,0.2)',
  },
  gridControl: {
    display: 'flex',
    alignItems: 'center',
    fontSize: '14px',
  },
  gridOverlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    width: '100%',
    height: '100%',
    pointerEvents: 'none',
    zIndex: 1,
  },
  contextMenu: {
    position: 'absolute',
    backgroundColor: '#fff',
    border: '1px solid #ddd',
    borderRadius: '4px',
    boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
    zIndex: 1000,
    minWidth: '160px',
    overflow: 'hidden',
  },
  contextMenuHeader: {
    padding: '8px 12px',
    backgroundColor: '#f5f5f5',
    borderBottom: '1px solid #ddd',
    fontWeight: 600,
    fontSize: '13px',
  },
  contextMenuItem: {
    padding: '8px 12px',
    cursor: 'pointer',
    fontSize: '13px',
    transition: 'background-color 0.15s',
  },
  dialogOverlay: {
    position: 'fixed',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0,0,0,0.5)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 2000,
  },
  dialog: {
    backgroundColor: '#fff',
    borderRadius: '8px',
    boxShadow: '0 8px 32px rgba(0,0,0,0.25)',
    minWidth: '300px',
    overflow: 'hidden',
  },
  dialogHeader: {
    padding: '16px',
    backgroundColor: '#f5f5f5',
    borderBottom: '1px solid #ddd',
    fontWeight: 600,
    fontSize: '15px',
  },
  dialogBody: {
    padding: '16px',
  },
  dialogInput: {
    width: '80px',
    padding: '8px 12px',
    borderRadius: '4px',
    border: '1px solid #ccc',
    fontSize: '14px',
    marginLeft: '8px',
  },
  dialogActions: {
    padding: '12px 16px',
    borderTop: '1px solid #ddd',
    display: 'flex',
    justifyContent: 'flex-end',
    gap: '8px',
  },
  dialogButton: {
    padding: '8px 16px',
    borderRadius: '4px',
    border: '1px solid #ccc',
    backgroundColor: '#fff',
    cursor: 'pointer',
    fontSize: '14px',
  },
  dialogButtonPrimary: {
    backgroundColor: '#007bff',
    borderColor: '#007bff',
    color: '#fff',
  },
};
