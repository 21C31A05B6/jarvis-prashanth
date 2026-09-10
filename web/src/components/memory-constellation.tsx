"use client";

import React, { useEffect, useRef } from "react";

export function MemoryConstellation({ width = 160, height = 90 }: { width?: number; height?: number }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animId: number;
    let t = 0;

    // Fixed realistic constellation nodes based on the screenshot
    const baseNodes = [
      { x: 0.15, y: 0.75, r: 2.2 },
      { x: 0.22, y: 0.70, r: 2.0 },
      { x: 0.30, y: 0.62, r: 2.4 },
      { x: 0.38, y: 0.58, r: 2.6 },
      { x: 0.48, y: 0.52, r: 2.5 },
      { x: 0.58, y: 0.65, r: 2.2 },
      { x: 0.68, y: 0.68, r: 2.3 },
      { x: 0.78, y: 0.82, r: 2.0 },
      { x: 0.88, y: 0.86, r: 2.1 },
      // Secondary branches
      { x: 0.32, y: 0.42, r: 1.8 },
      { x: 0.44, y: 0.38, r: 2.2 },
      { x: 0.54, y: 0.45, r: 1.9 },
    ];

    const connections = [
      [0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [5, 6], [6, 7], [7, 8],
      [2, 9], [9, 10], [10, 4], [10, 11], [11, 5]
    ];

    const render = () => {
      t += 0.02;
      ctx.clearRect(0, 0, width, height);

      // Draw faint connections
      ctx.lineWidth = 1;
      connections.forEach(([i, j]) => {
        const n1 = baseNodes[i];
        const n2 = baseNodes[j];
        if (!n1 || !n2) return;

        const x1 = (n1.x + Math.sin(t + i) * 0.015) * width;
        const y1 = (n1.y + Math.cos(t + i) * 0.02) * height;
        const x2 = (n2.x + Math.sin(t + j) * 0.015) * width;
        const y2 = (n2.y + Math.cos(t + j) * 0.02) * height;

        ctx.strokeStyle = "rgba(0, 229, 255, 0.35)";
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();
      });

      // Draw nodes
      baseNodes.forEach((n, idx) => {
        const x = (n.x + Math.sin(t + idx) * 0.015) * width;
        const y = (n.y + Math.cos(t + idx) * 0.02) * height;
        const pulse = 1 + Math.sin(t * 2 + idx) * 0.25;

        // Glow
        const grad = ctx.createRadialGradient(x, y, 0, x, y, n.r * 3 * pulse);
        grad.addColorStop(0, "rgba(0, 229, 255, 0.9)");
        grad.addColorStop(0.4, "rgba(0, 180, 255, 0.4)");
        grad.addColorStop(1, "rgba(0, 229, 255, 0)");
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(x, y, n.r * 3 * pulse, 0, Math.PI * 2);
        ctx.fill();

        // Core dot
        ctx.fillStyle = "#ffffff";
        ctx.beginPath();
        ctx.arc(x, y, n.r * 0.8, 0, Math.PI * 2);
        ctx.fill();
      });

      animId = requestAnimationFrame(render);
    };

    render();

    return () => {
      cancelAnimationFrame(animId);
    };
  }, [width, height]);

  return (
    <canvas
      ref={canvasRef}
      width={width}
      height={height}
      className="pointer-events-none"
      style={{ filter: "drop-shadow(0 0 8px rgba(0, 229, 255, 0.4))" }}
    />
  );
}
