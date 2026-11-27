// Python's number rules, so a ported figure is the same figure: `round` to even, `//` and `int`,
// and `sum` as CPython 3.12+ does it (compensated for floats).

const TIE_DIGITS = 60;

/** The decimal text of `|x|` rounded to `nd` places the way Python does: from the exact value of the double,
 *  ties to even. Used by `round` and by `f"{x:.2f}"`. */
function roundedDigits(ax: number, nd: number): string {
  const exact = ax.toFixed(Math.min(100, nd + TIE_DIGITS)); // exact decimal expansion of the double
  const dot = exact.indexOf(".");
  const tail = exact.slice(dot + 1 + nd);
  let digits = exact.slice(0, dot + 1 + nd).replace(".", "");
  const first = tail[0] ?? "0";
  const isTie = /^50*$/.test(tail);
  const roundUp =
    first > "5" ||
    (first === "5" && !isTie) ||
    (isTie && Number(digits[digits.length - 1]) % 2 === 1);
  if (roundUp) digits = bump(digits);
  return nd === 0
    ? digits
    : `${digits.slice(0, digits.length - nd) || "0"}.${digits.slice(digits.length - nd)}`;
}

/** Python's `round(x, ndigits)`: correctly rounded from the exact value of the double, ties to even. */
export function pyRound(x: number, ndigits = 0): number {
  if (!Number.isFinite(x)) return x;
  if (ndigits < 0) {
    const p = 10 ** -ndigits;
    return pyRound(x / p, 0) * p;
  }
  const out = Number(roundedDigits(Math.abs(x), ndigits));
  return x < 0 || Object.is(x, -0) ? -out : out;
}

/** Python's `f"{x:.{nd}f}"`. */
export function pyFixed(x: number, nd: number): string {
  if (!Number.isFinite(x)) return String(x);
  const text = roundedDigits(Math.abs(x), nd);
  return x < 0 || Object.is(x, -0) ? `-${text}` : text;
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

/** Python's `a // b` for floats: CPython's `float_divmod`, so a quotient that is only just under a whole
 *  number floors the way Python does (`-1.5 // 0.3` is -6, not -5). */
export function floorDiv(a: number, b: number): number {
  if (b === 0) throw new Error("division by zero");
  const mod = a % b; // C fmod
  let div = (a - mod) / b;
  if (mod) {
    if (b < 0 !== mod < 0) div -= 1.0;
  }
  if (div) {
    const floored = Math.floor(div);
    return div - floored > 0.5 ? floored + 1.0 : floored;
  }
  return Object.is(a / b, -0) || a / b < 0 ? -0 : 0;
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
