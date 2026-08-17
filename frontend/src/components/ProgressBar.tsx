export function ProgressBar({ value, max }: { value: number; max: number | null }) {
  if (max === null) {
    return (
      <div className="progress">
        <div className="progress-fill progress-unlimited" style={{ width: "100%" }} />
      </div>
    );
  }
  const percent = max > 0 ? Math.min(100, (value / max) * 100) : 100;
  const level = percent >= 95 ? "danger" : percent >= 80 ? "warn" : "ok";
  return (
    <div className="progress">
      <div className={`progress-fill progress-${level}`} style={{ width: `${percent}%` }} />
    </div>
  );
}
