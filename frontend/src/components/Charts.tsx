// Smooth SVG line/area charts in the dashboard theme (no chart library needed).

function smoothPath(points: [number, number][]): string {
  if (points.length === 0) return "";
  const first = points[0]!;
  let d = `M${first[0]},${first[1]}`;
  for (let i = 1; i < points.length; i++) {
    const [x0, y0] = points[i - 1]!;
    const [x1, y1] = points[i]!;
    const cx = (x0 + x1) / 2;
    d += ` C${cx},${y0} ${cx},${y1} ${x1},${y1}`;
  }
  return d;
}

function scale(
  values: number[],
  width: number,
  height: number,
  pad = 6,
): [number, number][] {
  const series = values.length > 1 ? values : [values[0] ?? 0, values[0] ?? 0];
  const max = Math.max(...series, 1);
  const min = Math.min(...series, 0);
  const span = max - min || 1;
  return series.map((v, i) => [
    (i / (series.length - 1)) * width,
    height - pad - ((v - min) / span) * (height - pad * 2),
  ]);
}

export function Sparkline({
  values,
  color,
  marker = true,
  label,
}: {
  values: number[];
  color: string;
  marker?: boolean;
  label: string;
}) {
  const w = 240;
  const h = 60;
  const pts = scale(values, w, h);
  const mid = pts[Math.floor(pts.length / 2)];
  return (
    <svg
      className="spark"
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={label}
    >
      <path d={smoothPath(pts)} fill="none" stroke={color} strokeWidth={2} />
      {marker && mid && <circle cx={mid[0]} cy={mid[1]} r={4} fill={color} />}
    </svg>
  );
}

export function AreaWave({
  values,
  color,
  label,
}: {
  values: number[];
  color: string;
  label: string;
}) {
  const w = 240;
  const h = 80;
  const pts = scale(values, w, h, 8);
  const line = smoothPath(pts);
  const id = `g-${color.replace(/[^a-z0-9]/gi, "")}`;
  return (
    <svg
      className="wave"
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={label}
    >
      <defs>
        <linearGradient id={id} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.35} />
          <stop offset="100%" stopColor={color} stopOpacity={0.02} />
        </linearGradient>
      </defs>
      <path d={`${line} L${w},${h} L0,${h} Z`} fill={`url(#${id})`} />
      <path d={line} fill="none" stroke={color} strokeWidth={2} />
    </svg>
  );
}
