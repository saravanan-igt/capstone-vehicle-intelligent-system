const inr = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 2,
});

export function money(
  value: string | null | undefined,
  currency = "INR",
): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return value;
  return currency === "INR"
    ? inr.format(n)
    : new Intl.NumberFormat("en", { style: "currency", currency }).format(n);
}

export function percent(rate: string | null | undefined): string {
  if (!rate) return "—";
  return `${(Number(rate) * 100).toFixed(2)}%`;
}

export function dateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export function humanize(code: string): string {
  return code
    .replace(/[_.]/g, " ")
    .toLowerCase()
    .replace(/^\w/, (c) => c.toUpperCase());
}
