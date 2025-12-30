/**
 * Edge Routing Manager
 *
 * Manages multi-bend orthogonal edge routing with waypoints.
 * Provides auto-routing and manual waypoint editing.
 */

import type { Core, EdgeSingular, Position } from "cytoscape";
import type {
  IEdgeRoutingManager,
  EdgeRoutingConfig,
  EdgePath,
  Waypoint,
  RoutingResult,
  BoundingBox,
} from "./types";
import { calculateOrthogonalRoute, snapToGrid, getBoundingBox } from "./OrthogonalRouter";

const DEFAULT_CONFIG: EdgeRoutingConfig = {
  enabled: true,
  maxBends: 3,
  gridSize: 10,
  obstacleMargin: 15,
  obstacleNodeKinds: ["bus", "transformer", "equipment", "substation"],
};

/**
 * Generate a unique waypoint ID.
 */
function generateWaypointId(edgeId: string, index: number): string {
  return `${edgeId}-wp-${index}-${Date.now()}`;
}

export class EdgeRoutingManager implements IEdgeRoutingManager {
  private _config: EdgeRoutingConfig;
  private cy: Core | null = null;
  // Container stored for potential future use (e.g., overlay rendering for waypoint handles)
  private _container: HTMLElement | null = null;
  private edgePaths: Map<string, EdgePath> = new Map();

  constructor(config?: Partial<EdgeRoutingConfig>) {
    this._config = { ...DEFAULT_CONFIG, ...config };
  }

  get config(): EdgeRoutingConfig {
    return { ...this._config };
  }

  /** Get the container element (for future use in overlay rendering) */
  get container(): HTMLElement | null {
    return this._container;
  }

  initialize(cy: Core, container: HTMLElement): void {
    this.cy = cy;
    this._container = container;
  }

  getEdgePath(edgeId: string): EdgePath | null {
    return this.edgePaths.get(edgeId) || null;
  }

  setEdgeWaypoints(edgeId: string, waypoints: Position[]): void {
    if (!this.cy) return;

    const edge = this.cy.getElementById(edgeId);
    if (edge.empty() || !edge.isEdge()) return;

    const edgeData = edge.data();
    const sourceId = edgeData.source;
    const targetId = edgeData.target;

    const waypointObjects: Waypoint[] = waypoints.map((pos, index) => ({
      id: generateWaypointId(edgeId, index),
      position: this._config.gridSize > 0 ? snapToGrid(pos, this._config.gridSize) : pos,
      index,
    }));

    const path: EdgePath = {
      edgeId,
      sourceId,
      targetId,
      waypoints: waypointObjects,
      isManual: true,
    };

    this.edgePaths.set(edgeId, path);
    this.updateEdgeRendering(edgeId);
  }

  autoRouteEdge(edgeId: string): RoutingResult {
    if (!this.cy) {
      return { success: false, waypoints: [], bendCount: 0, hasCollisions: true };
    }

    const edge = this.cy.getElementById(edgeId);
    if (edge.empty() || !edge.isEdge()) {
      return { success: false, waypoints: [], bendCount: 0, hasCollisions: true };
    }

    const sourceNode = edge.source();
    const targetNode = edge.target();
    const sourcePos = sourceNode.position();
    const targetPos = targetNode.position();

    // Get obstacles (excluding source and target)
    const obstacles = this.getObstacles([sourceNode.id(), targetNode.id()]);

    // Calculate route
    const result = calculateOrthogonalRoute(
      sourcePos,
      targetPos,
      obstacles,
      this._config.maxBends,
      this._config.obstacleMargin
    );

    // Store the path
    const waypointObjects: Waypoint[] = result.waypoints.map((pos, index) => ({
      id: generateWaypointId(edgeId, index),
      position: pos,
      index,
    }));

    const path: EdgePath = {
      edgeId,
      sourceId: sourceNode.id(),
      targetId: targetNode.id(),
      waypoints: waypointObjects,
      isManual: false,
    };

    this.edgePaths.set(edgeId, path);
    this.updateEdgeRendering(edgeId);

    return result;
  }

  autoRouteAll(): void {
    if (!this.cy) return;

    // Get all edges that should be routed
    const edges = this.cy.edges().filter((edge) => {
      const kind = edge.data("kind");
      return kind === "branch" || kind === "transformer_link";
    });

    edges.forEach((edge) => {
      // Only auto-route if not manually edited
      const existingPath = this.edgePaths.get(edge.id());
      if (!existingPath || !existingPath.isManual) {
        this.autoRouteEdge(edge.id());
      }
    });
  }

  addWaypoint(edgeId: string, position: Position, index?: number): Waypoint {
    const path = this.edgePaths.get(edgeId);
    const snappedPosition = this._config.gridSize > 0
      ? snapToGrid(position, this._config.gridSize)
      : position;

    const waypointIndex = index ?? (path?.waypoints.length ?? 0);
    const waypoint: Waypoint = {
      id: generateWaypointId(edgeId, waypointIndex),
      position: snappedPosition,
      index: waypointIndex,
    };

    if (path) {
      // Insert at index
      path.waypoints.splice(waypointIndex, 0, waypoint);
      // Re-index waypoints
      path.waypoints.forEach((wp, i) => {
        wp.index = i;
      });
      path.isManual = true;
    } else {
      // Create new path with single waypoint
      if (!this.cy) {
        return waypoint;
      }

      const edge = this.cy.getElementById(edgeId);
      if (edge.empty()) return waypoint;

      const edgeData = edge.data();
      const newPath: EdgePath = {
        edgeId,
        sourceId: edgeData.source,
        targetId: edgeData.target,
        waypoints: [waypoint],
        isManual: true,
      };
      this.edgePaths.set(edgeId, newPath);
    }

    this.updateEdgeRendering(edgeId);
    return waypoint;
  }

  removeWaypoint(edgeId: string, waypointId: string): void {
    const path = this.edgePaths.get(edgeId);
    if (!path) return;

    const index = path.waypoints.findIndex((wp) => wp.id === waypointId);
    if (index >= 0) {
      path.waypoints.splice(index, 1);
      // Re-index
      path.waypoints.forEach((wp, i) => {
        wp.index = i;
      });
      path.isManual = true;
      this.updateEdgeRendering(edgeId);
    }
  }

  moveWaypoint(edgeId: string, waypointId: string, position: Position): void {
    const path = this.edgePaths.get(edgeId);
    if (!path) return;

    const waypoint = path.waypoints.find((wp) => wp.id === waypointId);
    if (waypoint) {
      waypoint.position = this._config.gridSize > 0
        ? snapToGrid(position, this._config.gridSize)
        : position;
      path.isManual = true;
      this.updateEdgeRendering(edgeId);
    }
  }

  clearWaypoints(edgeId: string): void {
    this.edgePaths.delete(edgeId);
    this.autoRouteEdge(edgeId);
  }

  configure(config: Partial<EdgeRoutingConfig>): void {
    this._config = { ...this._config, ...config };
  }

  destroy(): void {
    this.edgePaths.clear();
    this.cy = null;
    this._container = null;
  }

  // ============================================================================
  // Private Methods
  // ============================================================================

  /**
   * Get obstacle bounding boxes for routing.
   */
  private getObstacles(excludeIds: string[]): BoundingBox[] {
    if (!this.cy) return [];

    const obstacles: BoundingBox[] = [];
    const excludeSet = new Set(excludeIds);

    this.cy.nodes().forEach((node) => {
      if (excludeSet.has(node.id())) return;

      const kind = node.data("kind") as string;
      if (!this._config.obstacleNodeKinds.includes(kind)) return;
      if (!node.visible()) return;

      const pos = node.position();
      const width = node.outerWidth();
      const height = node.outerHeight();

      obstacles.push(getBoundingBox(pos, width, height));
    });

    return obstacles;
  }

  /**
   * Update edge rendering with waypoints.
   * This uses Cytoscape's segment edge style.
   */
  private updateEdgeRendering(edgeId: string): void {
    if (!this.cy) return;

    const edge = this.cy.getElementById(edgeId) as EdgeSingular;
    if (edge.empty()) return;

    const path = this.edgePaths.get(edgeId);

    if (!path || path.waypoints.length === 0) {
      // Reset to taxi routing
      edge.style({
        "curve-style": "taxi",
        "taxi-direction": "auto",
      });
      return;
    }

    // For multi-bend paths, we need to use segment style or create waypoint nodes
    // Cytoscape's segment style doesn't support orthogonal-only segments,
    // so we'll store the path data and use it for custom rendering

    // Store path data on edge for custom rendering
    edge.data("_waypoints", path.waypoints.map((wp) => wp.position));
    edge.data("_hasWaypoints", true);

    // For now, keep taxi style but store the data
    // A more complete implementation would use custom edge rendering
    // or insert invisible waypoint nodes
    edge.style({
      "curve-style": "taxi",
      "taxi-direction": "auto",
    });
  }
}
