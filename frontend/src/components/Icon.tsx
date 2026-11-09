import type { SVGProps } from "react";

const paths = {
  dashboard: "M3 3h8v8H3zM13 3h8v5h-8zM13 10h8v11h-8zM3 13h8v8H3z",
  form: "M6 2h9l5 5v15H6zM14 2v6h6M9 13h8M9 17h8M9 9h3",
  list: "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01",
  car: "M5 11l1.5-4.5A2 2 0 0 1 8.4 5h7.2a2 2 0 0 1 1.9 1.5L19 11M3 16v-3a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v3h-2M3 16h2M7 16h10M7 18.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3zM17 18.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z",
  policy: "M12 2l8 3v6c0 5-3.5 9-8 11-4.5-2-8-6-8-11V5zM9 12l2 2 4-4",
  audit: "M12 8v4l3 2M21 12a9 9 0 1 1-9-9 9 9 0 0 1 9 9z",
  puzzle:
    "M10 3a2 2 0 1 1 4 0v2h4v4h2a2 2 0 1 1 0 4h-2v6h-5v-2a2 2 0 1 0-4 0v2H4v-5h2a2 2 0 1 0 0-4H4V5h6z",
  doc: "M6 2h9l5 5v15H6zM14 2v6h6M9 13h6M9 17h6",
  cap: "M2 9l10-5 10 5-10 5zM6 11v5c3 2 9 2 12 0v-5",
  chat: "M4 4h12v9H8l-4 3zM10 16h6l4 3v-9h-2",
  dice: "M4 4h16v16H4zM9 9h.01M15 15h.01M15 9h.01M9 15h.01M12 12h.01",
  coin: "M12 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM3 21c2-4 6-5 9-5s7 1 9 5M12 6v2",
  bag: "M4 8h16v11H4zM9 8V5h6v3M15 14l1.5 1.5L19 13",
  wallet: "M3 7h15a3 3 0 0 1 3 3v8H3zM3 7l12-3v3M16 13h2",
  tag: "M3 12l9-9h8v8l-9 9zM15 8h.01",
  search: "M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16zM21 21l-4.3-4.3",
  bell: "M6 8a6 6 0 1 1 12 0c0 7 3 8 3 8H3s3-1 3-8M10 20a2 2 0 0 0 4 0",
  mail: "M3 5h18v14H3zM3 5l9 8 9-8",
  globe:
    "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18",
  menu: "M4 6h16M4 12h16M4 18h16",
  chevron: "M9 6l6 6-6 6",
  down: "M6 9l6 6 6-6",
  check: "M5 12l5 5 9-10",
  x: "M6 6l12 12M18 6L6 18",
  alert: "M12 3l10 18H2zM12 10v5M12 18h.01",
  refresh: "M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7",
  sparkle: "M12 3l2 6 6 2-6 2-2 6-2-6-6-2 6-2z",
  logout: "M15 4h4v16h-4M10 8l-4 4 4 4M6 12h10",
  upload: "M12 16V4M7 9l5-5 5 5M4 20h16",
  settings:
    "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9L7 7M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1",
} as const;

export type IconName = keyof typeof paths;

export function Icon({
  name,
  ...rest
}: { name: IconName } & SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...rest}
    >
      <path d={paths[name]} />
    </svg>
  );
}
