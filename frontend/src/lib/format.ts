// Presentation-only formatting helpers.

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/** "HOT_DESK" -> "Hot desk" */
export function humanize(value: string | null | undefined): string {
  if (!value) return "—";
  const text = value.replace(/_/g, " ").toLowerCase();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** ISO weekday numbers -> "Tue, Wed, Thu" */
export function weekdays(days: number[]): string {
  return days.map((d) => WEEKDAYS[d - 1] ?? `?${d}`).join(", ");
}

export function percent(share: number, digits = 0): string {
  return `${(share * 100).toFixed(digits)}%`;
}

export function number(value: number): string {
  return value.toLocaleString("en-US");
}
