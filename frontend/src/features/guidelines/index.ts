/**
 * Guidelines Module - Public API
 *
 * This module provides PowerPoint-style alignment guidelines (smart guides)
 * for the SLD Viewer graph.
 *
 * Architecture:
 * - GuidelineManager: Main orchestrator and public API
 * - Detectors: Find alignments between nodes (pluggable)
 * - Renderers: Draw guide lines on screen (swappable)
 *
 * Usage:
 * ```typescript
 * import { GuidelineManager } from "@/features/guidelines";
 *
 * // Create manager
 * const guidelines = new GuidelineManager(cy, container, {
 *   snapEnabled: true,
 *   snapThreshold: 8,
 * });
 *
 * // During drag operations (typically in Cytoscape event handlers):
 * cy.on("grab", "node", (evt) => {
 *   guidelines.onDragStart(evt.target);
 * });
 *
 * cy.on("drag", "node", (evt) => {
 *   const node = evt.target;
 *   const snappedPos = guidelines.onDrag(node, node.position());
 *   if (snappedPos) {
 *     node.position(snappedPos);
 *   }
 * });
 *
 * cy.on("free", "node", (evt) => {
 *   guidelines.onDragEnd(evt.target);
 * });
 *
 * // Cleanup when done
 * guidelines.destroy();
 * ```
 */

// Main manager class
export { GuidelineManager } from "./GuidelineManager";

// Configuration
export { createConfig, DEFAULT_GUIDELINE_CONFIG } from "./config";

// Types
export type {
  // Core types
  Guide,
  GuideType,
  GuideOrientation,
  AlignmentMatch,
  // Configuration types
  GuidelineConfig,
  GuideStyle,
  AlignmentConfig,
  // Interface types (for extension)
  IGuidelineManager,
  IAlignmentDetector,
  IGuideRenderer,
  // Event types
  GuidelineEvents,
  GuidelineEventHandlers,
} from "./types";

// Detectors (for creating custom detectors or extending)
export { AlignmentDetector } from "./detectors";

// Renderers (for creating custom renderers)
export { CanvasGuideRenderer } from "./renderers";
