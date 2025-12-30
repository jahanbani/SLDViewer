/**
 * Edge Routing Module - Type Definitions
 *
 * Provides multi-bend orthogonal edge routing with waypoints.
 */

import type { Core, Position } from "cytoscape";

/**
 * A waypoint (bend point) on an edge path.
 */
export interface Waypoint {
  /** Unique ID for this waypoint */
  id: string;
  /** Position of the waypoint */
  position: Position;
  /** Index in the path (0 = first waypoint after source) */
  index: number;
}

/**
 * Complete path for an edge including waypoints.
 */
export interface EdgePath {
  /** The logical edge ID this path belongs to */
  edgeId: string;
  /** Source node ID */
  sourceId: string;
  /** Target node ID */
  targetId: string;
  /** Ordered waypoints between source and target */
  waypoints: Waypoint[];
  /** Whether this path was auto-generated or manually edited */
  isManual: boolean;
}

/**
 * Configuration for the edge routing system.
 */
export interface EdgeRoutingConfig {
  /** Whether edge routing is enabled */
  enabled: boolean;
  /** Maximum number of bends for auto-routing */
  maxBends: number;
  /** Grid size for snapping (0 = no grid) */
  gridSize: number;
  /** Margin around obstacles for routing */
  obstacleMargin: number;
  /** Node kinds to consider as obstacles */
  obstacleNodeKinds: string[];
}

/**
 * Result of an auto-routing calculation.
 */
export interface RoutingResult {
  /** Whether a valid path was found */
  success: boolean;
  /** The calculated waypoints */
  waypoints: Position[];
  /** Number of bends in the path */
  bendCount: number;
  /** Whether the path has any collisions */
  hasCollisions: boolean;
}

/**
 * Segment of an edge path (between two points).
 */
export interface PathSegment {
  start: Position;
  end: Position;
  orientation: "horizontal" | "vertical";
}

/**
 * Bounding box for collision detection.
 */
export interface BoundingBox {
  left: number;
  right: number;
  top: number;
  bottom: number;
}

/**
 * Interface for the edge routing manager.
 */
export interface IEdgeRoutingManager {
  /** Current configuration */
  readonly config: EdgeRoutingConfig;

  /**
   * Initialize the manager with a Cytoscape instance.
   */
  initialize(cy: Core, container: HTMLElement): void;

  /**
   * Get the path for an edge.
   */
  getEdgePath(edgeId: string): EdgePath | null;

  /**
   * Set waypoints for an edge (manual override).
   */
  setEdgeWaypoints(edgeId: string, waypoints: Position[]): void;

  /**
   * Auto-route an edge to avoid obstacles.
   */
  autoRouteEdge(edgeId: string): RoutingResult;

  /**
   * Auto-route all edges.
   */
  autoRouteAll(): void;

  /**
   * Add a waypoint to an edge at a position.
   */
  addWaypoint(edgeId: string, position: Position, index?: number): Waypoint;

  /**
   * Remove a waypoint from an edge.
   */
  removeWaypoint(edgeId: string, waypointId: string): void;

  /**
   * Move a waypoint to a new position.
   */
  moveWaypoint(edgeId: string, waypointId: string, position: Position): void;

  /**
   * Clear all waypoints for an edge (reset to auto-route).
   */
  clearWaypoints(edgeId: string): void;

  /**
   * Update configuration.
   */
  configure(config: Partial<EdgeRoutingConfig>): void;

  /**
   * Clean up resources.
   */
  destroy(): void;
}
