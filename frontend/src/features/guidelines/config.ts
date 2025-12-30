/**
 * Guidelines Module - Default Configuration
 */

import type { GuidelineConfig, GuideStyle, AlignmentConfig } from "./types";

/**
 * Default style for guide lines.
 */
export const DEFAULT_GUIDE_STYLE: GuideStyle = {
  color: "#3498db",      // Blue color (similar to PowerPoint)
  width: 1,
  dashPattern: [4, 4],   // Dashed line
  opacity: 0.8,
};

/**
 * Default alignment detection settings.
 */
export const DEFAULT_ALIGNMENT_CONFIG: AlignmentConfig = {
  centerAlignment: true,
  edgeAlignment: true,
  distributionAlignment: false, // More complex, disabled by default
};

/**
 * Default configuration for the guidelines system.
 */
export const DEFAULT_GUIDELINE_CONFIG: GuidelineConfig = {
  enabled: true,
  snapThreshold: 8,       // Snap when within 8 pixels
  showThreshold: 15,      // Show guide when within 15 pixels
  snapEnabled: true,
  alignments: DEFAULT_ALIGNMENT_CONFIG,
  style: DEFAULT_GUIDE_STYLE,
  excludeNodeKinds: [
    "terminal",           // Invisible connection points
    "substation_group",   // Compound parent nodes
  ],
};

/**
 * Create a configuration by merging with defaults.
 * @param overrides - Partial configuration to override defaults
 * @returns Complete configuration
 */
export function createConfig(overrides?: Partial<GuidelineConfig>): GuidelineConfig {
  if (!overrides) {
    return { ...DEFAULT_GUIDELINE_CONFIG };
  }

  return {
    ...DEFAULT_GUIDELINE_CONFIG,
    ...overrides,
    alignments: {
      ...DEFAULT_ALIGNMENT_CONFIG,
      ...overrides.alignments,
    },
    style: {
      ...DEFAULT_GUIDE_STYLE,
      ...overrides.style,
    },
  };
}
