/**
 * Guidelines Module - Public API
 */

export { GuidelineManager } from "./GuidelineManager";
export { createConfig, DEFAULT_GUIDELINE_CONFIG } from "./config";
export type {
  Guide,
  GuideType,
  GuideOrientation,
  AlignmentMatch,
  GuidelineConfig,
  GuideStyle,
  AlignmentConfig,
  IGuidelineManager,
  IAlignmentDetector,
  IGuideRenderer,
  GuidelineEvents,
  GuidelineEventHandlers,
} from "./types";
export { AlignmentDetector } from "./detectors";
export { CanvasGuideRenderer } from "./renderers";
