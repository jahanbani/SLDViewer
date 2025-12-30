/**
 * Orthogonal Router - Calculates orthogonal paths with minimal bends.
 *
 * Finds paths between two points that:
 * 1. Only use horizontal and vertical segments (90° turns)
 * 2. Avoid obstacles (nodes)
 * 3. Minimize the number of bends (up to maxBends)
 */

import type { Position } from "cytoscape";
import type { BoundingBox, RoutingResult } from "./types";

/**
 * Check if a point is inside a bounding box (with margin).
 */
function pointInBox(point: Position, box: BoundingBox, margin: number = 0): boolean {
  return (
    point.x >= box.left - margin &&
    point.x <= box.right + margin &&
    point.y >= box.top - margin &&
    point.y <= box.bottom + margin
  );
}

/**
 * Check if a horizontal segment intersects a bounding box.
 */
function horizontalSegmentIntersectsBox(
  y: number,
  x1: number,
  x2: number,
  box: BoundingBox,
  margin: number
): boolean {
  const minX = Math.min(x1, x2);
  const maxX = Math.max(x1, x2);

  // Check if y is within box's vertical range
  if (y < box.top - margin || y > box.bottom + margin) {
    return false;
  }

  // Check if segment overlaps box's horizontal range
  return !(maxX < box.left - margin || minX > box.right + margin);
}

/**
 * Check if a vertical segment intersects a bounding box.
 */
function verticalSegmentIntersectsBox(
  x: number,
  y1: number,
  y2: number,
  box: BoundingBox,
  margin: number
): boolean {
  const minY = Math.min(y1, y2);
  const maxY = Math.max(y1, y2);

  // Check if x is within box's horizontal range
  if (x < box.left - margin || x > box.right + margin) {
    return false;
  }

  // Check if segment overlaps box's vertical range
  return !(maxY < box.top - margin || minY > box.bottom + margin);
}

/**
 * Check if a path (sequence of points) collides with any obstacle.
 */
function pathCollidesWithObstacles(
  points: Position[],
  obstacles: BoundingBox[],
  margin: number
): boolean {
  for (let i = 0; i < points.length - 1; i++) {
    const p1 = points[i];
    const p2 = points[i + 1];

    for (const box of obstacles) {
      // Check if segment is horizontal or vertical
      if (p1.y === p2.y) {
        // Horizontal segment
        if (horizontalSegmentIntersectsBox(p1.y, p1.x, p2.x, box, margin)) {
          return true;
        }
      } else if (p1.x === p2.x) {
        // Vertical segment
        if (verticalSegmentIntersectsBox(p1.x, p1.y, p2.y, box, margin)) {
          return true;
        }
      }
    }
  }

  return false;
}

/**
 * Generate a path with 0 bends (direct horizontal or vertical).
 */
function tryZeroBends(
  source: Position,
  target: Position,
  obstacles: BoundingBox[],
  margin: number
): Position[] | null {
  // Only possible if source and target are aligned
  if (source.x === target.x || source.y === target.y) {
    const path = [source, target];
    if (!pathCollidesWithObstacles(path, obstacles, margin)) {
      return path;
    }
  }
  return null;
}

/**
 * Generate a path with 1 bend (L-shape).
 */
function tryOneBend(
  source: Position,
  target: Position,
  obstacles: BoundingBox[],
  margin: number
): Position[] | null {
  // Try horizontal-first: source → (target.x, source.y) → target
  const corner1: Position = { x: target.x, y: source.y };
  const path1 = [source, corner1, target];
  if (!pathCollidesWithObstacles(path1, obstacles, margin)) {
    return path1;
  }

  // Try vertical-first: source → (source.x, target.y) → target
  const corner2: Position = { x: source.x, y: target.y };
  const path2 = [source, corner2, target];
  if (!pathCollidesWithObstacles(path2, obstacles, margin)) {
    return path2;
  }

  return null;
}

/**
 * Generate a path with 2 bends (S-shape or Z-shape).
 */
function tryTwoBends(
  source: Position,
  target: Position,
  obstacles: BoundingBox[],
  margin: number
): Position[] | null {
  const midX = (source.x + target.x) / 2;
  const midY = (source.y + target.y) / 2;

  // Try going around horizontally (S-shape horizontal)
  // source → (midX, source.y) → (midX, target.y) → target
  const path1 = [
    source,
    { x: midX, y: source.y },
    { x: midX, y: target.y },
    target,
  ];
  if (!pathCollidesWithObstacles(path1, obstacles, margin)) {
    return path1;
  }

  // Try going around vertically (S-shape vertical)
  // source → (source.x, midY) → (target.x, midY) → target
  const path2 = [
    source,
    { x: source.x, y: midY },
    { x: target.x, y: midY },
    target,
  ];
  if (!pathCollidesWithObstacles(path2, obstacles, margin)) {
    return path2;
  }

  // Try offset paths (go further out to avoid obstacles)
  const offsets = [50, 100, 150, -50, -100, -150];

  for (const offset of offsets) {
    // Horizontal offset path
    const path3 = [
      source,
      { x: source.x + offset, y: source.y },
      { x: source.x + offset, y: target.y },
      target,
    ];
    if (!pathCollidesWithObstacles(path3, obstacles, margin)) {
      return path3;
    }

    // Vertical offset path
    const path4 = [
      source,
      { x: source.x, y: source.y + offset },
      { x: target.x, y: source.y + offset },
      target,
    ];
    if (!pathCollidesWithObstacles(path4, obstacles, margin)) {
      return path4;
    }
  }

  return null;
}

/**
 * Generate a path with 3 bends (more complex routing).
 */
function tryThreeBends(
  source: Position,
  target: Position,
  obstacles: BoundingBox[],
  margin: number
): Position[] | null {
  const offsets = [50, 100, 150, 200, -50, -100, -150, -200];

  for (const offsetX of offsets) {
    for (const offsetY of offsets) {
      // Path: source → out → across → in → target
      // Horizontal out, vertical across, horizontal in
      const path1 = [
        source,
        { x: source.x + offsetX, y: source.y },
        { x: source.x + offsetX, y: target.y + offsetY },
        { x: target.x, y: target.y + offsetY },
        target,
      ];
      if (!pathCollidesWithObstacles(path1, obstacles, margin)) {
        return path1;
      }

      // Vertical out, horizontal across, vertical in
      const path2 = [
        source,
        { x: source.x, y: source.y + offsetY },
        { x: target.x + offsetX, y: source.y + offsetY },
        { x: target.x + offsetX, y: target.y },
        target,
      ];
      if (!pathCollidesWithObstacles(path2, obstacles, margin)) {
        return path2;
      }
    }
  }

  return null;
}

/**
 * Calculate an orthogonal route between two points avoiding obstacles.
 */
export function calculateOrthogonalRoute(
  source: Position,
  target: Position,
  obstacles: BoundingBox[],
  maxBends: number = 3,
  margin: number = 10
): RoutingResult {
  // Filter out obstacles that contain source or target
  const filteredObstacles = obstacles.filter(
    (box) => !pointInBox(source, box, 0) && !pointInBox(target, box, 0)
  );

  // Try paths with increasing number of bends
  let path: Position[] | null = null;

  // Try 0 bends (direct line)
  path = tryZeroBends(source, target, filteredObstacles, margin);
  if (path) {
    return { success: true, waypoints: path.slice(1, -1), bendCount: 0, hasCollisions: false };
  }

  // Try 1 bend (L-shape)
  if (maxBends >= 1) {
    path = tryOneBend(source, target, filteredObstacles, margin);
    if (path) {
      return { success: true, waypoints: path.slice(1, -1), bendCount: 1, hasCollisions: false };
    }
  }

  // Try 2 bends (S-shape)
  if (maxBends >= 2) {
    path = tryTwoBends(source, target, filteredObstacles, margin);
    if (path) {
      return { success: true, waypoints: path.slice(1, -1), bendCount: 2, hasCollisions: false };
    }
  }

  // Try 3 bends
  if (maxBends >= 3) {
    path = tryThreeBends(source, target, filteredObstacles, margin);
    if (path) {
      return { success: true, waypoints: path.slice(1, -1), bendCount: 3, hasCollisions: false };
    }
  }

  // Fallback: return simple L-path even if it collides
  const fallbackCorner: Position = { x: target.x, y: source.y };
  return {
    success: false,
    waypoints: [fallbackCorner],
    bendCount: 1,
    hasCollisions: true,
  };
}

/**
 * Snap a position to a grid.
 */
export function snapToGrid(position: Position, gridSize: number): Position {
  if (gridSize <= 0) return position;

  return {
    x: Math.round(position.x / gridSize) * gridSize,
    y: Math.round(position.y / gridSize) * gridSize,
  };
}

/**
 * Get bounding box from node position and dimensions.
 */
export function getBoundingBox(
  position: Position,
  width: number,
  height: number
): BoundingBox {
  return {
    left: position.x - width / 2,
    right: position.x + width / 2,
    top: position.y - height / 2,
    bottom: position.y + height / 2,
  };
}
