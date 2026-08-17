import { useId } from "react";

export function Logo({ compact = false }: { compact?: boolean }) {
  const gradientId = `ov-grad-${useId().replace(/:/g, "")}`;
  return (
    <span className="logo">
      <svg
        className="logo-mark"
        viewBox="0 0 32 32"
        width="30"
        height="30"
        role="img"
        aria-label="OneVideo"
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
            <stop offset="0" stopColor="#8b5cf6" />
            <stop offset="1" stopColor="#22d3ee" />
          </linearGradient>
        </defs>
        <rect width="32" height="32" rx="8" fill="#0d0d16" />
        <rect
          x="1.5"
          y="1.5"
          width="29"
          height="29"
          rx="6.5"
          fill="none"
          stroke={`url(#${gradientId})`}
          strokeWidth="2"
        />
        <path d="M12.5 10.5v11l9.5-5.5z" fill={`url(#${gradientId})`} />
      </svg>
      {!compact && (
        <span className="logo-word">
          One<span className="logo-accent">Video</span>
        </span>
      )}
    </span>
  );
}
