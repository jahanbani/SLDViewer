/**
 * Alignment Detector - Detects center and edge alignments between nodes.
 */

import type { Core, NodeSingular, Position } from "cytoscape";
import type { IAlignmentDetector, AlignmentMatch, Guide, GuidelineConfig, GuideType } from "../types";

interface NodeBounds {
  id: string;
  centerX: number;
  centerY: number;
  left: number;
  right: number;
  top: number;
  bottom: number;
  width: number;
  height: number;
}

function getNodeBounds(node: NodeSingular, position?: Position): NodeBounds {
  const pos = position || node.position();
  const width = node.outerWidth();
  const height = node.outerHeight();

  return {
    id: node.id(),
    centerX: pos.x,
    centerY: pos.y,
    left: pos.x - width / 2,
    right: pos.x + width / 2,
    top: pos.y - height / 2,
    bottom: pos.y + height / 2,
    width,
    height,
  };
}

function createGuideId(type: GuideType, sourceId: string, position: number): string {
  return `${type}-${sourceId}-${Math.round(position)}`;
}

export class AlignmentDetector implements IAlignmentDetector {
  readonly name = "alignment";

  detect(
    cy: Core,
    draggedNode: NodeSingular,
    currentPosition: Position,
    config: GuidelineConfig
  ): AlignmentMatch[] {
    const matches: AlignmentMatch[] = [];
    const draggedBounds = getNodeBounds(draggedNode, currentPosition);
    const threshold = config.showThreshold;

    const candidateNodes = cy.nodes().filter((node) => {
      if (node.id() === draggedNode.id()) return false;
      const kind = node.data("kind") as string;
      if (config.excludeNodeKinds.includes(kind)) return false;
      if (!node.visible()) return false;
      return true;
    });

    candidateNodes.forEach((candidateNode) => {
      const candidateBounds = getNodeBounds(candidateNode);

      if (config.alignments.centerAlignment) {
        const xCenterDiff = Math.abs(draggedBounds.centerX - candidateBounds.centerX);
        if (xCenterDiff <= threshold) {
          matches.push(this.createMatch(
            "center-x", "vertical", candidateBounds.centerX, candidateNode.id(),
            xCenterDiff, { x: candidateBounds.centerX, y: currentPosition.y }, "x"
          ));
        }

        const yCenterDiff = Math.abs(draggedBounds.centerY - candidateBounds.centerY);
        if (yCenterDiff <= threshold) {
          matches.push(this.createMatch(
            "center-y", "horizontal", candidateBounds.centerY, candidateNode.id(),
            yCenterDiff, { x: currentPosition.x, y: candidateBounds.centerY }, "y"
          ));
        }
      }

      if (config.alignments.edgeAlignment) {
        // Left edge alignments
        const leftToLeftDiff = Math.abs(draggedBounds.left - candidateBounds.left);
        if (leftToLeftDiff <= threshold) {
          const snapX = candidateBounds.left + draggedBounds.width / 2;
          matches.push(this.createMatch("edge-left", "vertical", candidateBounds.left, candidateNode.id(), leftToLeftDiff, { x: snapX, y: currentPosition.y }, "x"));
        }

        // Right edge alignments
        const rightToRightDiff = Math.abs(draggedBounds.right - candidateBounds.right);
        if (rightToRightDiff <= threshold) {
          const snapX = candidateBounds.right - draggedBounds.width / 2;
          matches.push(this.createMatch("edge-right", "vertical", candidateBounds.right, candidateNode.id(), rightToRightDiff, { x: snapX, y: currentPosition.y }, "x"));
        }

        // Top edge alignments
        const topToTopDiff = Math.abs(draggedBounds.top - candidateBounds.top);
        if (topToTopDiff <= threshold) {
          const snapY = candidateBounds.top + draggedBounds.height / 2;
          matches.push(this.createMatch("edge-top", "horizontal", candidateBounds.top, candidateNode.id(), topToTopDiff, { x: currentPosition.x, y: snapY }, "y"));
        }

        // Bottom edge alignments
        const bottomToBottomDiff = Math.abs(draggedBounds.bottom - candidateBounds.bottom);
        if (bottomToBottomDiff <= threshold) {
          const snapY = candidateBounds.bottom - draggedBounds.height / 2;
          matches.push(this.createMatch("edge-bottom", "horizontal", candidateBounds.bottom, candidateNode.id(), bottomToBottomDiff, { x: currentPosition.x, y: snapY }, "y"));
        }
      }
    });

    return this.deduplicateMatches(matches);
  }

  private createMatch(
    type: GuideType,
    orientation: "horizontal" | "vertical",
    position: number,
    sourceNodeId: string,
    distance: number,
    snapPosition: Position,
    axis: "x" | "y"
  ): AlignmentMatch {
    const guide: Guide = {
      id: createGuideId(type, sourceNodeId, position),
      type,
      orientation,
      position,
      sourceNodeId,
      visible: true,
      priority: type.startsWith("center") ? 10 : 5,
    };

    return { guide, distance, snapPosition, axis };
  }

  private deduplicateMatches(matches: AlignmentMatch[]): AlignmentMatch[] {
    matches.sort((a, b) => a.distance - b.distance);
    const seen = new Map<string, AlignmentMatch>();

    for (const match of matches) {
      const key = `${match.guide.orientation}-${Math.round(match.guide.position)}`;
      if (!seen.has(key)) {
        seen.set(key, match);
      }
    }

    return Array.from(seen.values());
  }

  destroy(): void {}
}
