// Python's number rules, so a ported figure is the same figure: `round` to even, `//` and `int`,
// and `sum` as CPython 3.12+ does it (compensated for floats).

const TIE_DIGITS = 60;

/** Python's `round(x, ndigits)`: correctly rounded from the exact value of the double, ties to even. */
export function pyRound(x: number, ndigits = 0): number {
  if (!Number.isFinite(x)) return x;
  if (ndigits < 0) {
    const p = 10 ** -ndigits;
    return pyRound(x / p, 0) * p;
  }
  const exact = Math.abs(x).toFixed(Math.min(100, ndigits + TIE_DIGITS)); // exact decimal expansion
  const dot = exact.indexOf(".");
  const kept = exact.slice(0, dot + 1 + ndigits);
  const tail = exact.slice(dot + 1 + ndigits);
  const isTie = /^50*$/.test(tail);
  const up = tail[0] !== undefined && (tail[0] > "5" || (tail[0] === "5" && !isTie) || false);
  let digits = kept.replace(".", "");
  if (isTie) {
    const last = Number(digits[digits.length - 1]);
    if (last % 2 === 1) digits = bump(digits);
  } else if (up) {
    digits = bump(digits);
  }
  const text =
    ndigits === 0
      ? digits
      : `${digits.slice(0, digits.length - ndigits)}.${digits.slice(digits.length - ndigits)}`;
  const out = Number(text);
  return x < 0 ? -out : out;
}

function bump(digits: string): string {
  const a = digits.split("");
  let i = a.length - 1;
  while (i >= 0) {
    if (a[i] === "9") {
      a[i] = "0";
      i -= 1;
    } else {
      a[i] = String(Number(a[i]) + 1);
      return a.join("");
    }
  }
  return `1${a.join("")}`;
}

/** Python's `a // b` for numbers: the floor of the quotient. */
export function floorDiv(a: number, b: number): number {
  if (b === 0) throw new Error("division by zero");
  return Math.floor(a / b);
}

/** Python's `int(x)`: toward zero. */
export function pyInt(x: number): number {
  return Math.trunc(x);
}

/** Python's `sum(values)` over floats (CPython 3.12+: Neumaier compensation, then one final add). */
export function pySum(values: readonly number[]): number {
  let result = 0;
  let c = 0;
  for (const x of values) {
    const t = result + x;
    if (!Number.isFinite(t)) {
      result = t;
      c = 0;
      continue;
    }
    if (Math.abs(result) >= Math.abs(x)) c += result - t + x;
    else c += x - t + result;
    result = t;
  }
  return c !== 0 && Number.isFinite(c) ? result + c : result;
}

/** Python's `math.prod` over floats (a plain left-to-right product from 1). */
export function pyProd(values: readonly number[]): number {
  let p = 1;
  for (const v of values) p *= v;
  return p;
}
