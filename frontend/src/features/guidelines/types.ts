/**
 * Guidelines Module - Type Definitions
 */

import type { Core, NodeSingular, Position } from "cytoscape";

export type GuideType =
  | "center-x" | "center-y"
  | "edge-left" | "edge-right" | "edge-top" | "edge-bottom"
  | "distribution" | "custom";

export type GuideOrientation = "horizontal" | "vertical";

export interface Guide {
  id: string;
  type: GuideType;
  orientation: GuideOrientation;
  position: number;
  sourceNodeId: string;
  targetNodeId?: string;
  visible: boolean;
  priority: number;
}

export interface AlignmentMatch {
  guide: Guide;
  distance: number;
  snapPosition: Position;
  axis: "x" | "y";
}

export interface GuideStyle {
  color: string;
  width: number;
  dashPattern: number[];
  opacity: number;
}

export interface AlignmentConfig {
  centerAlignment: boolean;
  edgeAlignment: boolean;
  distributionAlignment: boolean;
}

export interface GuidelineConfig {
  enabled: boolean;
  snapThreshold: number;
  showThreshold: number;
  snapEnabled: boolean;
  alignments: AlignmentConfig;
  style: GuideStyle;
  excludeNodeKinds: string[];
}

export interface IAlignmentDetector {
  readonly name: string;
  detect(
    cy: Core,
    draggedNode: NodeSingular,
    currentPosition: Position,
    config: GuidelineConfig
  ): AlignmentMatch[];
  destroy?(): void;
}

export interface IGuideRenderer {
  readonly name: string;
  initialize(container: HTMLElement): void;
  render(guides: Guide[], style: GuideStyle): void;
  clear(): void;
  destroy(): void;
}

export interface GuidelineEvents {
  onGuidesShown: (guides: Guide[]) => void;
  onGuidesHidden: () => void;
  onSnap: (node: NodeSingular, guide: Guide, position: Position) => void;
  onConfigChange: (config: GuidelineConfig) => void;
}

export type GuidelineEventHandlers = Partial<GuidelineEvents>;

export interface IGuidelineManager {
  readonly config: GuidelineConfig;
  readonly isEnabled: boolean;
  enable(): void;
  disable(): void;
  configure(config: Partial<GuidelineConfig>): void;
  onDragStart(node: NodeSingular): void;
  onDrag(node: NodeSingular, position: Position): Position;
  onDragEnd(node: NodeSingular): void;
  on(handlers: GuidelineEventHandlers): void;
  addDetector(detector: IAlignmentDetector): void;
  removeDetector(name: string): void;
  destroy(): void;
}
