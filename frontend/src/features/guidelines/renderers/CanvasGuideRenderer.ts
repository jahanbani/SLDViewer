/**
 * Canvas Guide Renderer - Renders alignment guides on a canvas overlay.
 */

import type { IGuideRenderer, Guide, GuideStyle } from "../types";

export class CanvasGuideRenderer implements IGuideRenderer {
  readonly name = "canvas";

  private canvas: HTMLCanvasElement | null = null;
  private ctx: CanvasRenderingContext2D | null = null;
  private container: HTMLElement | null = null;
  private resizeObserver: ResizeObserver | null = null;

  initialize(container: HTMLElement): void {
    this.container = container;

    this.canvas = document.createElement("canvas");
    this.canvas.style.position = "absolute";
    this.canvas.style.top = "0";
    this.canvas.style.left = "0";
    this.canvas.style.width = "100%";
    this.canvas.style.height = "100%";
    this.canvas.style.pointerEvents = "none";
    this.canvas.style.zIndex = "1000";

    this.ctx = this.canvas.getContext("2d");

    const containerStyle = window.getComputedStyle(container);
    if (containerStyle.position === "static") {
      container.style.position = "relative";
    }
    container.appendChild(this.canvas);

    this.updateCanvasSize();

    this.resizeObserver = new ResizeObserver(() => {
      this.updateCanvasSize();
    });
    this.resizeObserver.observe(container);
  }

  private updateCanvasSize(): void {
    if (!this.canvas || !this.container) return;

    const rect = this.container.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;

    this.canvas.width = rect.width * dpr;
    this.canvas.height = rect.height * dpr;

    if (this.ctx) {
      this.ctx.scale(dpr, dpr);
    }
  }

  render(guides: Guide[], style: GuideStyle): void {
    if (!this.ctx || !this.canvas || !this.container) return;

    this.clear();

    if (guides.length === 0) return;

    const rect = this.container.getBoundingClientRect();
    const ctx = this.ctx;

    ctx.strokeStyle = style.color;
    ctx.lineWidth = style.width;
    ctx.globalAlpha = style.opacity;

    if (style.dashPattern.length > 0) {
      ctx.setLineDash(style.dashPattern);
    } else {
      ctx.setLineDash([]);
    }

    let pan = { x: 0, y: 0 };
    let zoom = 1;

    const cy = (this.container as any).__cy;
    if (cy) {
      pan = cy.pan();
      zoom = cy.zoom();
    }

    for (const guide of guides) {
      if (!guide.visible) continue;

      ctx.beginPath();

      if (guide.orientation === "vertical") {
        const canvasX = guide.position * zoom + pan.x;
        ctx.moveTo(canvasX, 0);
        ctx.lineTo(canvasX, rect.height);
      } else {
        const canvasY = guide.position * zoom + pan.y;
        ctx.moveTo(0, canvasY);
        ctx.lineTo(rect.width, canvasY);
      }

      ctx.stroke();
    }

    ctx.globalAlpha = 1;
  }

  clear(): void {
    if (!this.ctx || !this.canvas) return;

    const dpr = window.devicePixelRatio || 1;
    this.ctx.clearRect(0, 0, this.canvas.width / dpr, this.canvas.height / dpr);
  }

  destroy(): void {
    if (this.resizeObserver) {
      this.resizeObserver.disconnect();
      this.resizeObserver = null;
    }

    if (this.canvas && this.canvas.parentNode) {
      this.canvas.parentNode.removeChild(this.canvas);
    }

    this.canvas = null;
    this.ctx = null;
    this.container = null;
  }
}
