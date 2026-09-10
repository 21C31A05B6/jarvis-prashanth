"use client";

import React, { useEffect, useRef } from "react";

export function HologramSphere({
  width = 380,
  height = 240,
}: {
  width?: number;
  height?: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animId: number;
    let angleY = 0;
    let angleX = 0.2; // Slight tilt towards viewer

    const radius = Math.min(width, height) * 0.38;
    const cx = width / 2;
    const cy = height / 2;

    // Generate fixed sphere points for wireframe
    const numLat = 10;
    const numLon = 16;

    // Generate orbiting satellite nodes
    const satellites = [
      { orbitRadius: radius * 1.35, tilt: 0.35, speed: 0.015, phase: 0, size: 3.5 },
      { orbitRadius: radius * 1.5, tilt: -0.42, speed: -0.011, phase: 2.1, size: 2.8 },
      { orbitRadius: radius * 1.25, tilt: 0.65, speed: 0.02, phase: 4.2, size: 3.0 },
    ];

    // Background floating holographic dust
    const stars = Array.from({ length: 45 }, () => ({
      x: (Math.random() - 0.5) * width * 1.1,
      y: (Math.random() - 0.5) * height * 1.1,
      z: (Math.random() - 0.5) * 200,
      brightness: Math.random() * 0.7 + 0.3,
      speed: (Math.random() * 0.2 + 0.1) * (Math.random() > 0.5 ? 1 : -1),
    }));

    const render = () => {
      angleY += 0.008;

      ctx.clearRect(0, 0, width, height);

      // 1. Draw subtle background glow
      const bgGlow = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius * 1.6);
      bgGlow.addColorStop(0, "rgba(0, 180, 255, 0.09)");
      bgGlow.addColorStop(0.5, "rgba(0, 120, 255, 0.04)");
      bgGlow.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.fillStyle = bgGlow;
      ctx.fillRect(0, 0, width, height);

      // 2. Draw stars / particles
      stars.forEach((s) => {
        s.x += s.speed;
        if (s.x > width / 2) s.x = -width / 2;
        if (s.x < -width / 2) s.x = width / 2;
        const px = cx + s.x;
        const py = cy + s.y;
        ctx.fillStyle = `rgba(0, 229, 255, ${s.brightness * 0.6})`;
        ctx.beginPath();
        ctx.arc(px, py, 1.2, 0, Math.PI * 2);
        ctx.fill();
      });

      // 3. Draw tilted orbital rings
      satellites.forEach((sat, satIdx) => {
        ctx.save();
        ctx.translate(cx, cy);
        ctx.rotate(sat.tilt);

        // Draw ring ellipse
        ctx.beginPath();
        ctx.ellipse(0, 0, sat.orbitRadius, sat.orbitRadius * 0.38, 0, 0, Math.PI * 2);
        ctx.strokeStyle = satIdx === 0 ? "rgba(0, 229, 255, 0.35)" : "rgba(0, 150, 255, 0.22)";
        ctx.lineWidth = 1;
        ctx.setLineDash(satIdx === 1 ? [4, 6] : []);
        ctx.stroke();
        ctx.setLineDash([]);

        // Calculate satellite position
        const satAngle = angleY * (sat.speed / 0.008) + sat.phase;
        const sx = Math.cos(satAngle) * sat.orbitRadius;
        const sy = Math.sin(satAngle) * (sat.orbitRadius * 0.38);

        // Satellite glow
        const satGlow = ctx.createRadialGradient(sx, sy, 0, sx, sy, sat.size * 3.5);
        satGlow.addColorStop(0, "rgba(255, 255, 255, 1)");
        satGlow.addColorStop(0.3, "rgba(0, 229, 255, 0.8)");
        satGlow.addColorStop(1, "rgba(0, 229, 255, 0)");
        ctx.fillStyle = satGlow;
        ctx.beginPath();
        ctx.arc(sx, sy, sat.size * 3.5, 0, Math.PI * 2);
        ctx.fill();

        ctx.restore();
      });

      // 4. Draw 3D wireframe sphere (latitudes and longitudes)
      // Latitudes (horizontal slices)
      for (let i = 1; i < numLat; i++) {
        const phi = (i / numLat) * Math.PI - Math.PI / 2;
        const rSlice = radius * Math.cos(phi);
        const ySlice = radius * Math.sin(phi);

        // Project 3D circle with tilt angleX
        const py = cy + ySlice * Math.cos(angleX);
        const ry = Math.abs(rSlice * Math.sin(angleX));

        ctx.beginPath();
        ctx.ellipse(cx, py, rSlice, Math.max(ry, 1), 0, 0, Math.PI * 2);
        ctx.strokeStyle = "rgba(0, 210, 255, 0.22)";
        ctx.lineWidth = 0.9;
        ctx.stroke();
      }

      // Longitudes (vertical rings rotated by angleY)
      for (let i = 0; i < numLon; i++) {
        const theta = (i / numLon) * Math.PI + angleY;
        const rx = radius * Math.abs(Math.sin(theta));

        ctx.beginPath();
        ctx.ellipse(cx, cy, rx, radius, 0, 0, Math.PI * 2);

        // Front vs back shading
        const cosVal = Math.cos(theta);
        const alpha = cosVal > 0 ? 0.32 : 0.12;
        ctx.strokeStyle = `rgba(0, 229, 255, ${alpha})`;
        ctx.lineWidth = cosVal > 0 ? 1.1 : 0.7;
        ctx.stroke();
      }

      // 5. Draw outer bounding glow circle
      ctx.beginPath();
      ctx.arc(cx, cy, radius, 0, Math.PI * 2);
      ctx.strokeStyle = "rgba(0, 229, 255, 0.5)";
      ctx.lineWidth = 1.4;
      ctx.stroke();

      animId = requestAnimationFrame(render);
    };

    render();

    return () => {
      cancelAnimationFrame(animId);
    };
  }, [width, height]);

  return (
    <div className="relative w-full h-full flex items-center justify-center overflow-hidden">
      <canvas
        ref={canvasRef}
        width={width}
        height={height}
        className="block"
        style={{
          filter: "drop-shadow(0 0 16px rgba(0, 229, 255, 0.35))",
        }}
      />

      {/* Holographic Text Overlay */}
      <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none select-none z-10">
        <h1
          className="text-2xl md:text-3xl font-extrabold tracking-[0.22em] text-cyan-300 uppercase leading-none font-mono"
          style={{
            textShadow: "0 0 14px rgba(0, 229, 255, 0.8), 0 0 28px rgba(0, 160, 255, 0.5)",
          }}
        >
          JARVIS
        </h1>
        <span
          className="text-[11px] md:text-[12px] font-semibold tracking-[0.35em] text-cyan-400 uppercase mt-1.5 font-mono"
          style={{
            textShadow: "0 0 8px rgba(0, 229, 255, 0.6)",
          }}
        >
          AI CORE
        </span>
        <span className="text-[9px] md:text-[10px] tracking-wider text-cyan-400/80 font-mono mt-1">
          v3.0.0
        </span>
      </div>
    </div>
  );
}
