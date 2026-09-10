"use client";

import React from "react";

interface RadialGaugeProps {
  label: string;
  value: number; // percentage 0-100
  size?: number;
  color?: string;
}

export function RadialGauge({
  label,
  value,
  size = 90,
  color = "#00e5ff",
}: RadialGaugeProps) {
  const strokeWidth = 7;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (value / 100) * circumference;

  return (
    <div className="flex flex-col items-center justify-center">
      <div className="relative flex items-center justify-center" style={{ width: size, height: size }}>
        <svg
          className="transform -rotate-90"
          width={size}
          height={size}
          style={{ filter: "drop-shadow(0 0 6px rgba(0, 229, 255, 0.45))" }}
        >
          {/* Background circle track */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            stroke="#0a2540"
            strokeWidth={strokeWidth}
            fill="transparent"
          />
          {/* Outer glow track */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            stroke={color}
            strokeWidth={strokeWidth}
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
            strokeLinecap="round"
            fill="transparent"
            style={{
              transition: "stroke-dashoffset 0.8s ease-in-out",
            }}
          />
        </svg>

        {/* Center label & percentage */}
        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
          <span className="text-[10px] tracking-wider text-cyan-400/70 font-mono uppercase">{label}</span>
          <span className="text-[14px] font-bold text-cyan-200 font-mono leading-none mt-0.5">{value}%</span>
        </div>
      </div>
    </div>
  );
}
