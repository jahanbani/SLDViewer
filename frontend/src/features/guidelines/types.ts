/**
 * Guidelines Module - Type Definitions
 *
 * This module provides alignment guidelines (smart guides) similar to PowerPoint.
 * Architecture is designed to be modular, extensible, and API-based.
 */

import type { Core, NodeSingular, Position } from "cytoscape";

// ============================================================================
// Guide Types
// ============================================================================

/**
 * Types of alignment guides the system can detect and display.
 */
export type GuideType =
  | "center-x"      // Vertical line through node center X
  | "center-y"      // Horizontal line through node center Y
  | "edge-left"     // Vertical line at node left edge
  | "edge-right"    // Vertical line at node right edge
  | "edge-top"      // Horizontal line at node top edge
  | "edge-bottom"   // Horizontal line at node bottom edge
  | "distribution"  // Equal spacing between nodes
  | "custom";       // User-defined guides

/**
 * Orientation of a guide line.
 */
export type GuideOrientation = "horizontal" | "vertical";

/**
 * A single guide line that can be displayed.
 */
export interface Guide {
  /** Unique identifier for this guide */
  id: string;
  /** Type of alignment this guide represents */
  type: GuideType;
  /** Whether line is horizontal or vertical */
  orientation: GuideOrientation;
  /** Position on the perpendicular axis (x for vertical, y for horizontal) */
  position: number;
  /** Node ID that this guide aligns with */
  sourceNodeId: string;
  /** Optional: second node for distribution guides */
  targetNodeId?: string;
  /** Whether this guide should be rendered */
  visible: boolean;
  /** Priority for when multiple guides compete (higher = more important) */
  priority: number;
}

/**
 * Result of detecting alignment matches for a dragged node.
 */
export interface AlignmentMatch {
  /** The guide that matches */
  guide: Guide;
  /** Distance from the dragged node to this alignment (pixels) */
  distance: number;
  /** Position to snap to if snapping is enabled */
  snapPosition: Position;
  /** Which axis this affects */
  axis: "x" | "y";
}

// ============================================================================
// Configuration
// ============================================================================

/**
 * Visual style configuration for guide lines.
 */
export interface GuideStyle {
  /** Color of the guide line */
  color: string;
  /** Width of the guide line in pixels */
  width: number;
  /** Dash pattern [dash, gap] - empty for solid line */
  dashPattern: number[];
  /** Opacity (0-1) */
  opacity: number;
}

/**
 * Configuration for alignment detection behavior.
 */
export interface AlignmentConfig {
  /** Detect center-to-center alignments */
  centerAlignment: boolean;
  /** Detect edge-to-edge alignments */
  edgeAlignment: boolean;
  /** Detect equal distribution/spacing */
  distributionAlignment: boolean;
}

/**
 * Main configuration for the guidelines system.
 */
export interface GuidelineConfig {
  /** Whether guidelines are enabled */
  enabled: boolean;
  /** Distance threshold for snapping (pixels) */
  snapThreshold: number;
  /** Distance threshold for showing guides (pixels) */
  showThreshold: number;
  /** Whether to snap nodes to guides */
  snapEnabled: boolean;
  /** Which alignment types to detect */
  alignments: AlignmentConfig;
  /** Visual style for guides */
  style: GuideStyle;
  /** Node kinds to exclude from alignment detection */
  excludeNodeKinds: string[];
}

// ============================================================================
// Detector Interface
// ============================================================================

/**
 * Interface for alignment detectors.
 * Detectors are responsible for finding alignments between nodes.
 * New detector types can be created by implementing this interface.
 */
export interface IAlignmentDetector {
  /** Unique name for this detector */
  readonly name: string;

  /**
   * Detect alignments for a node being dragged.
   * @param cy - Cytoscape instance
   * @param draggedNode - The node being dragged
   * @param currentPosition - Current position of the dragged node
   * @param config - Configuration settings
   * @returns Array of alignment matches found
   */
  detect(
    cy: Core,
    draggedNode: NodeSingular,
    currentPosition: Position,
    config: GuidelineConfig
  ): AlignmentMatch[];

  /**
   * Optional cleanup when detector is destroyed.
   */
  destroy?(): void;
}

// ============================================================================
// Renderer Interface
// ============================================================================

/**
 * Interface for guide renderers.
 * Renderers are responsible for visually displaying guides.
 * Different renderers can use canvas, SVG, or CSS-based approaches.
 */
export interface IGuideRenderer {
  /** Unique name for this renderer */
  readonly name: string;

  /**
   * Initialize the renderer.
   * @param container - The container element (typically the Cytoscape container)
   */
  initialize(container: HTMLElement): void;

  /**
   * Render the given guides.
   * @param guides - Array of guides to render
   * @param style - Style configuration for rendering
   */
  render(guides: Guide[], style: GuideStyle): void;

  /**
   * Clear all rendered guides.
   */
  clear(): void;

  /**
   * Clean up resources when renderer is destroyed.
   */
  destroy(): void;
}

// ============================================================================
// Manager Events
// ============================================================================

/**
 * Events emitted by the GuidelineManager.
 */
export interface GuidelineEvents {
  /** Fired when guides are shown */
  onGuidesShown: (guides: Guide[]) => void;
  /** Fired when guides are hidden */
  onGuidesHidden: () => void;
  /** Fired when a node is snapped to a guide */
  onSnap: (node: NodeSingular, guide: Guide, position: Position) => void;
  /** Fired when configuration changes */
  onConfigChange: (config: GuidelineConfig) => void;
}

/**
 * Partial event handlers (all optional).
 */
export type GuidelineEventHandlers = Partial<GuidelineEvents>;

// ============================================================================
// Manager Interface
// ============================================================================

/**
 * Public API for the GuidelineManager.
 * This is the main entry point for using the guidelines system.
 */
export interface IGuidelineManager {
  /** Current configuration */
  readonly config: GuidelineConfig;

  /** Whether guidelines are currently enabled */
  readonly isEnabled: boolean;

  /**
   * Enable guidelines.
   */
  enable(): void;

  /**
   * Disable guidelines.
   */
  disable(): void;

  /**
   * Update configuration.
   * @param config - Partial configuration to merge with current
   */
  configure(config: Partial<GuidelineConfig>): void;

  /**
   * Called when a drag operation starts.
   * @param node - The node being dragged
   */
  onDragStart(node: NodeSingular): void;

  /**
   * Called during drag operation.
   * @param node - The node being dragged
   * @param position - Current position
   * @returns Position to use (may be snapped)
   */
  onDrag(node: NodeSingular, position: Position): Position;

  /**
   * Called when drag operation ends.
   * @param node - The node that was dragged
   */
  onDragEnd(node: NodeSingular): void;

  /**
   * Register event handlers.
   * @param handlers - Event handlers to register
   */
  on(handlers: GuidelineEventHandlers): void;

  /**
   * Add a custom detector.
   * @param detector - Detector instance to add
   */
  addDetector(detector: IAlignmentDetector): void;

  /**
   * Remove a detector.
   * @param name - Name of the detector to remove
   */
  removeDetector(name: string): void;

  /**
   * Clean up all resources.
   */
  destroy(): void;
}
