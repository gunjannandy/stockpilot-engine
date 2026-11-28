// Forecast bands drawn behind the price, as v2 did: 80% and 50% ranges, a dashed likely line, a "today" divider.
import type { IChartApi, ISeriesApi, ISeriesPrimitive, SeriesType, Time } from "lightweight-charts";
import type { BandPoint } from "./series";

export type BandState = {
  points: BandPoint[];
  nodes: { time: string; mid: number }[];
  show: boolean;
  c: { band80: string; band50: string; primary: string; text2: string };
};

export function bandPrimitive(getState: () => BandState | null) {
  let chart: IChartApi | null = null;
  let series: ISeriesApi<SeriesType> | null = null;
  let request: (() => void) | null = null;
  const renderer = {
    draw(target: { useBitmapCoordinateSpace: (cb: (s: never) => void) => void }) {
      const st = getState();
      if (!st?.show || !chart || !series) return;
      // biome-ignore lint/correctness/useHookAtTopLevel: a Lightweight Charts method, not a React hook
      target.useBitmapCoordinateSpace(((scope: {
        context: CanvasRenderingContext2D;
        horizontalPixelRatio: number;
        verticalPixelRatio: number;
      }) => {
        const { context: g, horizontalPixelRatio: hr, verticalPixelRatio: vr } = scope;
        const ts = chart?.timeScale();
        const X = (t: string): number | null =>
          (ts?.timeToCoordinate(t as Time) as number | null | undefined) ?? null;
        const Y = (p: number) => series?.priceToCoordinate(p) ?? 0;
        const pts = st.points
          .map((p) => ({ x: X(p.time), p }))
          .filter((o): o is { x: number; p: BandPoint } => o.x !== null);
        if (pts.length < 2) return;
        const poly = (a: "hi80" | "hi50", b: "lo80" | "lo50", fill: string) => {
          g.beginPath();
          pts.forEach((o, i) => {
            const x = o.x * hr;
            const y = Y(o.p[a]) * vr;
            if (i) g.lineTo(x, y);
            else g.moveTo(x, y);
          });
          for (let i = pts.length - 1; i >= 0; i--) {
            const o = pts[i] as (typeof pts)[number];
            g.lineTo(o.x * hr, Y(o.p[b]) * vr);
          }
          g.closePath();
          g.fillStyle = fill;
          g.fill();
        };
        poly("hi80", "lo80", st.c.band80);
        poly("hi50", "lo50", st.c.band50);
        g.beginPath();
        pts.forEach((o, i) => {
          const x = o.x * hr;
          const y = Y(o.p.mid) * vr;
          if (i) g.lineTo(x, y);
          else g.moveTo(x, y);
        });
        g.strokeStyle = st.c.primary;
        g.lineWidth = 1.5 * hr;
        g.setLineDash([5 * hr, 4 * hr]);
        g.stroke();
        g.setLineDash([]);
        const x0 = (pts[0] as (typeof pts)[number]).x * hr;
        g.strokeStyle = st.c.text2;
        g.lineWidth = hr;
        g.setLineDash([2 * hr, 4 * hr]);
        g.beginPath();
        g.moveTo(x0, 0);
        g.lineTo(x0, g.canvas.height);
        g.stroke();
        g.setLineDash([]);
        for (const n of st.nodes) {
          const x = X(n.time);
          if (x === null) continue;
          g.beginPath();
          g.arc(x * hr, Y(n.mid) * vr, 3.2 * hr, 0, 7);
          g.fillStyle = st.c.primary;
          g.fill();
        }
      }) as never);
    },
  };
  const view = { zOrder: () => "bottom" as const, renderer: () => renderer } as never;
  const prim: ISeriesPrimitive<Time> & { redraw: () => void } = {
    attached(p) {
      chart = p.chart;
      series = p.series;
      request = p.requestUpdate;
    },
    detached() {
      chart = null;
      series = null;
    },
    updateAllViews() {},
    paneViews: () => [view],
    redraw() {
      request?.();
    },
  };
  return prim;
}
