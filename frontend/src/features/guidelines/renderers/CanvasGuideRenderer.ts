/**
 * Canvas Guide Renderer
 *
 * Renders alignment guides on a canvas overlay.
 * Uses HTML5 Canvas for high-performance rendering.
 */

import type { IGuideRenderer, Guide, GuideStyle } from "../types";

/**
 * CanvasGuideRenderer - Renders guides using HTML5 Canvas.
 */
export class CanvasGuideRenderer implements IGuideRenderer {
  readonly name = "canvas";

  private canvas: HTMLCanvasElement | null = null;
  private ctx: CanvasRenderingContext2D | null = null;
  private container: HTMLElement | null = null;
  private resizeObserver: ResizeObserver | null = null;

  /**
   * Initialize the canvas overlay.
   */
  initialize(container: HTMLElement): void {
    this.container = container;

    // Create canvas element
    this.canvas = document.createElement("canvas");
    this.canvas.style.position = "absolute";
    this.canvas.style.top = "0";
    this.canvas.style.left = "0";
    this.canvas.style.width = "100%";
    this.canvas.style.height = "100%";
    this.canvas.style.pointerEvents = "none"; // Allow clicks to pass through
    this.canvas.style.zIndex = "1000"; // Above Cytoscape but below UI

    // Get 2D context
    this.ctx = this.canvas.getContext("2d");

    // Insert canvas into container
    // Cytoscape container typically has position: relative
    const containerStyle = window.getComputedStyle(container);
    if (containerStyle.position === "static") {
      container.style.position = "relative";
    }
    container.appendChild(this.canvas);

    // Set initial size
    this.updateCanvasSize();

    // Watch for container resizes
    this.resizeObserver = new ResizeObserver(() => {
      this.updateCanvasSize();
    });
    this.resizeObserver.observe(container);
  }

  /**
   * Update canvas size to match container.
   */
  private updateCanvasSize(): void {
    if (!this.canvas || !this.container) return;

    const rect = this.container.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;

    // Set actual canvas dimensions (accounting for device pixel ratio)
    this.canvas.width = rect.width * dpr;
    this.canvas.height = rect.height * dpr;

    // Scale context for high DPI displays
    if (this.ctx) {
      this.ctx.scale(dpr, dpr);
    }
  }

  /**
   * Render the given guides.
   */
  render(guides: Guide[], style: GuideStyle): void {
    if (!this.ctx || !this.canvas || !this.container) return;

    // Clear previous guides
    this.clear();

    if (guides.length === 0) return;

    const rect = this.container.getBoundingClientRect();
    const ctx = this.ctx;

    // Set up drawing style
    ctx.strokeStyle = style.color;
    ctx.lineWidth = style.width;
    ctx.globalAlpha = style.opacity;

    if (style.dashPattern.length > 0) {
      ctx.setLineDash(style.dashPattern);
    } else {
      ctx.setLineDash([]);
    }

    // Get Cytoscape pan and zoom for coordinate transformation
    // We need to convert graph coordinates to canvas coordinates
    let pan = { x: 0, y: 0 };
    let zoom = 1;

    // Try to get Cytoscape instance from container
    // The container should have a __cy property set by Cytoscape
    const cy = (this.container as any).__cy;
    if (cy) {
      pan = cy.pan();
      zoom = cy.zoom();
    }

    // Draw each guide
    for (const guide of guides) {
      if (!guide.visible) continue;

      ctx.beginPath();

      if (guide.orientation === "vertical") {
        // Convert graph X to canvas X
        const canvasX = guide.position * zoom + pan.x;
        ctx.moveTo(canvasX, 0);
        ctx.lineTo(canvasX, rect.height);
      } else {
        // Convert graph Y to canvas Y
        const canvasY = guide.position * zoom + pan.y;
        ctx.moveTo(0, canvasY);
        ctx.lineTo(rect.width, canvasY);
      }

      ctx.stroke();
    }

    // Reset alpha
    ctx.globalAlpha = 1;
  }

  /**
   * Clear all rendered guides.
   */
  clear(): void {
    if (!this.ctx || !this.canvas) return;

    const dpr = window.devicePixelRatio || 1;
    this.ctx.clearRect(0, 0, this.canvas.width / dpr, this.canvas.height / dpr);
  }

  /**
   * Clean up resources.
   */
  destroy(): void {
    // Stop observing resize
    if (this.resizeObserver) {
      this.resizeObserver.disconnect();
      this.resizeObserver = null;
    }

    // Remove canvas from DOM
    if (this.canvas && this.canvas.parentNode) {
      this.canvas.parentNode.removeChild(this.canvas);
    }

    this.canvas = null;
    this.ctx = null;
    this.container = null;
  }
}
