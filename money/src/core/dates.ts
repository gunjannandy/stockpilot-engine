// Plain `YYYY-MM-DD` dates. Money code never touches `Date`: it counts days as integers (the
// proleptic Gregorian day number), so there is no clock and no time zone to go wrong.
export type Day = string;

const DAY_RE = /^(\d{4})-(\d{2})-(\d{2})$/;

/** Days from 0001-01-01 (day 1), like Python's `date.toordinal()`. */
export function toOrdinal(day: Day): number {
  const m = DAY_RE.exec(day);
  if (!m) throw new Error(`not a YYYY-MM-DD day: ${day}`);
  const y = Number(m[1]);
  const mo = Number(m[2]);
  const d = Number(m[3]);
  if (mo < 1 || mo > 12 || d < 1 || d > daysInMonth(y, mo)) throw new Error(`no such day: ${day}`);
  const py = y - 1;
  return (
    py * 365 +
    Math.floor(py / 4) -
    Math.floor(py / 100) +
    Math.floor(py / 400) +
    daysBefore(y, mo) +
    d
  );
}

export function fromOrdinal(n: number): Day {
  // the standard 400/100/4/1-year cycle walk
  let rest = n - 1;
  const n400 = Math.floor(rest / 146097);
  rest -= n400 * 146097;
  const n100 = Math.min(Math.floor(rest / 36524), 3);
  rest -= n100 * 36524;
  const n4 = Math.floor(rest / 1461);
  rest -= n4 * 1461;
  const n1 = Math.min(Math.floor(rest / 365), 3);
  rest -= n1 * 365;
  const year = n400 * 400 + n100 * 100 + n4 * 4 + n1 + 1;
  let month = 1;
  while (month < 12 && rest >= daysInMonth(year, month)) {
    rest -= daysInMonth(year, month);
    month += 1;
  }
  return fmt(year, month, rest + 1);
}

export function isLeap(y: number): boolean {
  return y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0);
}

export function daysInMonth(y: number, m: number): number {
  return [31, isLeap(y) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1] as number;
}

function daysBefore(y: number, m: number): number {
  let n = 0;
  for (let i = 1; i < m; i++) n += daysInMonth(y, i);
  return n;
}

function fmt(y: number, m: number, d: number): Day {
  return `${String(y).padStart(4, "0")}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}

export const addDays = (day: Day, n: number): Day => fromOrdinal(toOrdinal(day) + n);

/** `a - b` in whole days, like Python's `(a - b).days`. */
export const daysBetween = (a: Day, b: Day): number => toOrdinal(a) - toOrdinal(b);

/** Monday is 0 and Sunday is 6, like Python's `date.weekday()`. */
export const weekday = (day: Day): number => (toOrdinal(day) + 6) % 7;

export const month = (day: Day): string => day.slice(0, 7);

/** The same calendar day `years` later; 29 February becomes 1 March (what tax code expects). */
export function addYears(day: Day, years: number): Day {
  const y = Number(day.slice(0, 4)) + years;
  const m = Number(day.slice(5, 7));
  const d = Number(day.slice(8, 10));
  return m === 2 && d === 29 && !isLeap(y) ? fmt(y, 3, 1) : fmt(y, m, d);
}

export const compareDays = (a: Day, b: Day): number => (a < b ? -1 : a > b ? 1 : 0);
