/**
 * Edge Routing Module - Public API
 *
 * Provides multi-bend orthogonal edge routing with waypoints.
 */

export { EdgeRoutingManager } from "./EdgeRoutingManager";
export { calculateOrthogonalRoute, snapToGrid, getBoundingBox } from "./OrthogonalRouter";
export type {
  Waypoint,
  EdgePath,
  EdgeRoutingConfig,
  RoutingResult,
  PathSegment,
  BoundingBox,
  IEdgeRoutingManager,
} from "./types";
