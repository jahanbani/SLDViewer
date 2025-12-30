/**
 * Guideline Manager
 *
 * Main orchestrator for the alignment guidelines system.
 * Coordinates detectors and renderers to provide smart guide functionality.
 *
 * Usage:
 *   const manager = new GuidelineManager(cy, container, config);
 *   // During drag operations:
 *   manager.onDragStart(node);
 *   const snappedPos = manager.onDrag(node, currentPos);
 *   manager.onDragEnd(node);
 *   // Cleanup:
 *   manager.destroy();
 */

import type { Core, NodeSingular, Position } from "cytoscape";
import type {
  IGuidelineManager,
  IAlignmentDetector,
  IGuideRenderer,
  GuidelineConfig,
  GuidelineEventHandlers,
  AlignmentMatch,
  Guide,
} from "./types";
import { createConfig } from "./config";
import { AlignmentDetector } from "./detectors";
import { CanvasGuideRenderer } from "./renderers";

/**
 * GuidelineManager - Orchestrates alignment detection and guide rendering.
 */
export class GuidelineManager implements IGuidelineManager {
  private _config: GuidelineConfig;
  private _enabled: boolean;
  private cy: Core;
  private container: HTMLElement;
  private detectors: Map<string, IAlignmentDetector> = new Map();
  private renderer: IGuideRenderer;
  private eventHandlers: GuidelineEventHandlers = {};
  private _currentMatches: AlignmentMatch[] = [];
  private isDragging: boolean = false;

  /**
   * Create a new GuidelineManager.
   * @param cy - Cytoscape instance
   * @param container - Container element for rendering guides
   * @param config - Optional configuration overrides
   */
  constructor(cy: Core, container: HTMLElement, config?: Partial<GuidelineConfig>) {
    this.cy = cy;
    this.container = container;
    this._config = createConfig(config);
    this._enabled = this._config.enabled;

    // Store reference to cy on container for renderer coordinate transformation
    (container as any).__cy = cy;

    // Initialize default detector
    const alignmentDetector = new AlignmentDetector();
    this.detectors.set(alignmentDetector.name, alignmentDetector);

    // Initialize renderer
    this.renderer = new CanvasGuideRenderer();
    this.renderer.initialize(container);
  }

  // ============================================================================
  // Public API - Properties
  // ============================================================================

  get config(): GuidelineConfig {
    return { ...this._config };
  }

  get currentMatches(): AlignmentMatch[] {
    return this._currentMatches;
  }

  get isEnabled(): boolean {
    return this._enabled;
  }

  // ============================================================================
  // Public API - Control Methods
  // ============================================================================

  enable(): void {
    this._enabled = true;
  }

  disable(): void {
    this._enabled = false;
    this.clearGuides();
  }

  configure(config: Partial<GuidelineConfig>): void {
    this._config = createConfig({ ...this._config, ...config });
    this._enabled = this._config.enabled;

    // Notify listeners
    if (this.eventHandlers.onConfigChange) {
      this.eventHandlers.onConfigChange(this._config);
    }
  }

  // ============================================================================
  // Public API - Drag Event Handlers
  // ============================================================================

  onDragStart(_node: NodeSingular): void {
    if (!this._enabled) return;

    this.isDragging = true;
    this._currentMatches = [];
  }

  onDrag(node: NodeSingular, position: Position): Position {
    if (!this._enabled || !this.isDragging) {
      return position;
    }

    // Detect alignments from all detectors
    const allMatches: AlignmentMatch[] = [];

    for (const detector of this.detectors.values()) {
      const matches = detector.detect(this.cy, node, position, this._config);
      allMatches.push(...matches);
    }

    // Store current matches
    this._currentMatches = allMatches;

    // Render guides
    const guides = allMatches.map((m) => m.guide);
    this.renderGuides(guides);

    // Calculate snapped position if snapping is enabled
    if (this._config.snapEnabled && allMatches.length > 0) {
      return this.calculateSnappedPosition(position, allMatches);
    }

    return position;
  }

  onDragEnd(_node: NodeSingular): void {
    this.isDragging = false;
    this._currentMatches = [];
    this.clearGuides();

    // Notify listeners
    if (this.eventHandlers.onGuidesHidden) {
      this.eventHandlers.onGuidesHidden();
    }
  }

  // ============================================================================
  // Public API - Event Registration
  // ============================================================================

  on(handlers: GuidelineEventHandlers): void {
    this.eventHandlers = { ...this.eventHandlers, ...handlers };
  }

  // ============================================================================
  // Public API - Detector Management
  // ============================================================================

  addDetector(detector: IAlignmentDetector): void {
    this.detectors.set(detector.name, detector);
  }

  removeDetector(name: string): void {
    const detector = this.detectors.get(name);
    if (detector) {
      detector.destroy?.();
      this.detectors.delete(name);
    }
  }

  // ============================================================================
  // Public API - Cleanup
  // ============================================================================

  destroy(): void {
    // Clear any rendered guides
    this.clearGuides();

    // Destroy all detectors
    for (const detector of this.detectors.values()) {
      detector.destroy?.();
    }
    this.detectors.clear();

    // Destroy renderer
    this.renderer.destroy();

    // Clear container reference
    delete (this.container as any).__cy;
  }

  // ============================================================================
  // Private Methods
  // ============================================================================

  /**
   * Calculate the snapped position based on alignment matches.
   */
  private calculateSnappedPosition(
    currentPosition: Position,
    matches: AlignmentMatch[]
  ): Position {
    const snapThreshold = this._config.snapThreshold;
    let snappedX = currentPosition.x;
    let snappedY = currentPosition.y;

    // Find best X alignment (closest)
    const xMatches = matches.filter((m) => m.axis === "x" && m.distance <= snapThreshold);
    if (xMatches.length > 0) {
      // Sort by priority then distance
      xMatches.sort((a, b) => {
        if (a.guide.priority !== b.guide.priority) {
          return b.guide.priority - a.guide.priority;
        }
        return a.distance - b.distance;
      });
      snappedX = xMatches[0].snapPosition.x;

      // Notify snap event
      if (this.eventHandlers.onSnap) {
        // We'd need the node here, but we can skip for now
      }
    }

    // Find best Y alignment (closest)
    const yMatches = matches.filter((m) => m.axis === "y" && m.distance <= snapThreshold);
    if (yMatches.length > 0) {
      yMatches.sort((a, b) => {
        if (a.guide.priority !== b.guide.priority) {
          return b.guide.priority - a.guide.priority;
        }
        return a.distance - b.distance;
      });
      snappedY = yMatches[0].snapPosition.y;
    }

    return { x: snappedX, y: snappedY };
  }

  /**
   * Render guides using the renderer.
   */
  private renderGuides(guides: Guide[]): void {
    if (guides.length === 0) {
      this.clearGuides();
      return;
    }

    this.renderer.render(guides, this._config.style);

    // Notify listeners
    if (this.eventHandlers.onGuidesShown) {
      this.eventHandlers.onGuidesShown(guides);
    }
  }

  /**
   * Clear all rendered guides.
   */
  private clearGuides(): void {
    this.renderer.clear();
  }
}
