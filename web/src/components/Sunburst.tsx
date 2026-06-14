// Claude's sunburst mark — a clean 12-spoke burst in the accent clay.
export default function Sunburst({ size = 28, className = "" }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" className={`text-accent-terracotta shrink-0 ${className}`} aria-hidden="true">
      {Array.from({ length: 12 }).map((_, i) => (
        <rect key={i} x="46" y="6" width="8" height="36" rx="4" fill="currentColor" transform={`rotate(${i * 30} 50 50)`} />
      ))}
    </svg>
  );
}
