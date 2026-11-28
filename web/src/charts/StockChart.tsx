// The stock chart, v2's behaviour in the new theme: price line with fill, volume, 2- and 10-month
// averages, levels, forecast bands, our buys and sells. Drag moves it; Ctrl or Cmd + scroll zooms; plain scroll never does.
import {
  AreaSeries,
  ColorType,
  CrosshairMode,
  createChart,
  createSeriesMarkers,
  HistogramSeries,
  type IChartApi,
  type ISeriesApi,
  LineSeries,
  LineStyle,
  type MouseEventParams,
  type SeriesMarker,
  type Time,
} from "lightweight-charts";
import { useCallback, useEffect, useRef, useState } from "react";
import { useWords } from "../words";
import { bandPrimitive } from "./bandPrimitive";
import {
  addDays,
  bandsOf,
  type Call,
  monthLabel,
  type Ohlc,
  RANGES,
  type RangeId,
  rangeStart,
  sma,
  wheelZoom,
} from "./series";

export type Layer = "vol" | "avg" | "band" | "levels" | "trades";
export const LAYERS: Layer[] = ["vol", "avg", "band", "levels", "trades"];
export type ChartTrade = { date: string; kind: "buy" | "sell"; qty: number };
const css = (n: string) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const inr = (v: number) => `₹${v.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

function load<T>(k: string, d: T): T {
  try {
    const v = localStorage.getItem(k);
    return v ? ({ ...d, ...JSON.parse(v) } as T) : d;
  } catch {
    return d;
  }
}
function save(k: string, v: unknown) {
  try {
    localStorage.setItem(k, JSON.stringify(v));
  } catch {}
}

export function StockChart(props: {
  bars: Ohlc[];
  call: Call | null;
  trades: ChartTrade[];
  extra?: React.ReactNode;
}) {
  const { bars, call, trades, extra } = props;
  const t = useWords();
  const host = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const [range, setRange] = useState<RangeId | null>(
    () => load<{ r: RangeId }>("sk-range", { r: "1Y" }).r,
  );
  const [layers, setLayers] = useState<Record<Layer, boolean>>(() =>
    load("sk-layers", { vol: true, avg: true, band: true, levels: true, trades: true }),
  );
  const [menu, setMenu] = useState(false);
  const [theme, setTheme] = useState(0);
  const [readout, setReadout] = useState("");
  const apiRef = useRef<{
    apply: (l: Record<Layer, boolean>) => void;
    setRange: (r: RangeId | null) => void;
  } | null>(null);

  useEffect(() => {
    const mo = new MutationObserver(() => setTheme((n) => n + 1));
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => mo.disconnect();
  }, []);

  // biome-ignore lint/correctness/useExhaustiveDependencies: theme re-colours; layers and range are applied through apiRef
  useEffect(() => {
    const el = host.current;
    const lastBar = bars[bars.length - 1];
    if (!el || !lastBar) return;
    const c = {
      surface: css("--surface"),
      text: css("--text"),
      text2: css("--text-2"),
      line: css("--line-2"),
      primary: css("--primary"),
      avg2: css("--warn"),
      avg10: css("--text-2"),
      gain: css("--gain"),
      loss: css("--loss"),
    };
    const chart = createChart(el, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: c.surface },
        textColor: c.text2,
        fontFamily: css("--font"),
        fontSize: 13,
        attributionLogo: true,
      },
      grid: { vertLines: { visible: false }, horzLines: { color: c.line } },
      rightPriceScale: { visible: false },
      leftPriceScale: {
        visible: true,
        borderVisible: false,
        scaleMargins: { top: 0.06, bottom: 0.22 },
      },
      timeScale: {
        borderVisible: false,
        rightOffset: 1,
        minBarSpacing: 0.02,
        timeVisible: false,
        tickMarkFormatter: (time: Time) => monthLabel(String(time)),
      },
      crosshair: { mode: CrosshairMode.Normal },
      handleScale: {
        mouseWheel: false,
        pinch: true,
        axisPressedMouseMove: true,
        axisDoubleClickReset: false,
      },
      handleScroll: {
        mouseWheel: false,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: false,
      },
      localization: {
        priceFormatter: (p: number) => p.toLocaleString("en-IN", { maximumFractionDigits: 0 }),
      },
    });
    chartRef.current = chart;
    const none = {
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    };
    const price = chart.addSeries(AreaSeries, {
      priceScaleId: "left",
      lineColor: c.primary,
      lineWidth: 2,
      topColor: `${c.primary}33`,
      bottomColor: `${c.primary}00`,
      priceLineVisible: false,
      lastValueVisible: true,
    });
    const vol = chart.addSeries(HistogramSeries, {
      priceScaleId: "vol",
      priceFormat: { type: "volume" },
      lastValueVisible: false,
      priceLineVisible: false,
    });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    const a2 = chart.addSeries(LineSeries, {
      priceScaleId: "left",
      lineWidth: 2,
      color: c.avg2,
      ...none,
    });
    const a10 = chart.addSeries(LineSeries, {
      priceScaleId: "left",
      lineWidth: 2,
      lineStyle: LineStyle.Dashed,
      color: c.avg10,
      ...none,
    });
    vol.setData(
      bars.map((b) => ({
        time: b.time,
        value: b.volume,
        color: b.close >= b.open ? `${c.gain}73` : `${c.loss}73`,
      })) as never,
    );
    a2.setData(sma(bars, 42) as never);
    a10.setData(sma(bars, 210) as never);
    const bands = bandsOf(call, lastBar.time, lastBar.close);
    price.setData([
      ...bars.map((b) => ({ time: b.time, value: b.close })),
      ...(bands ? bands.points.slice(1).map((p) => ({ time: p.time })) : []),
    ] as never);
    const state = bands
      ? {
          points: bands.points,
          nodes: bands.nodes,
          show: true,
          c: {
            band80: `color-mix(in srgb, ${c.primary} 13%, transparent)`,
            band50: `color-mix(in srgb, ${c.primary} 30%, transparent)`,
            primary: c.primary,
            text2: c.text2,
          },
        }
      : null;
    const prim = bandPrimitive(() => state);
    price.attachPrimitive(prim);
    const dates = bars.map((b) => b.time);
    const markers = createSeriesMarkers(price, []);
    let lines: ReturnType<ISeriesApi<"Area">["createPriceLine"]>[] = [];

    const apply = (L: Record<Layer, boolean>) => {
      vol.applyOptions({ visible: L.vol });
      a2.applyOptions({ visible: L.avg });
      a10.applyOptions({ visible: L.avg });
      if (state) state.show = L.band;
      prim.redraw();
      for (const l of lines) price.removePriceLine(l);
      lines = [];
      if (L.levels && call) {
        lines.push(
          price.createPriceLine({
            price: call.high[1] as number,
            color: c.gain,
            lineWidth: 1,
            lineStyle: LineStyle.Dotted,
            axisLabelVisible: true,
            title: t("stock.up"),
          }),
        );
        lines.push(
          price.createPriceLine({
            price: call.low[0] as number,
            color: c.loss,
            lineWidth: 1,
            lineStyle: LineStyle.Dotted,
            axisLabelVisible: true,
            title: t("stock.down"),
          }),
        );
      }
      const mk: SeriesMarker<Time>[] = L.trades
        ? trades.flatMap((tr): SeriesMarker<Time>[] => {
            const time = dates.find((d) => d >= tr.date);
            if (!time) return [];
            return tr.kind === "buy"
              ? [
                  {
                    time,
                    position: "belowBar" as const,
                    shape: "arrowUp" as const,
                    color: c.gain,
                    text: `${t("stock.bought")} ${tr.qty}`,
                    size: 1.4,
                  },
                ]
              : [
                  {
                    time,
                    position: "aboveBar" as const,
                    shape: "arrowDown" as const,
                    color: c.loss,
                    text: `${t("stock.sold")} ${tr.qty}`,
                    size: 1.4,
                  },
                ];
          })
        : [];
      markers.setMarkers(mk);
    };
    const setR = (r: RangeId | null) => {
      if (!r) return;
      const to = bands
        ? (bands.points[bands.points.length - 1]?.time ?? lastBar.time)
        : lastBar.time;
      chart.timeScale().setVisibleRange({ from: rangeStart(r, dates) as Time, to: to as Time });
    };
    apiRef.current = { apply, setRange: setR };
    apply(layers);
    setR(range);

    chart.subscribeCrosshairMove((p: MouseEventParams<Time>) => {
      const tm = p.time ? String(p.time) : null;
      const b = tm ? bars.find((x) => x.time === tm) : undefined;
      if (b)
        setReadout(
          `${b.time}  ${t("stock.open")} ${inr(b.open)} · ${t("stock.high")} ${inr(b.high)} · ${t("stock.low")} ${inr(b.low)} · ${t("stock.close")} ${inr(b.close)}`,
        );
      else if (tm && bands) {
        const f = bands.points.find((x) => x.time === tm);
        setReadout(
          f
            ? `${tm}  ${t("stock.ahead")}: ${t("stock.likely")} ${inr(f.mid)} · ${t("stock.range50")} ${inr(f.lo50)}–${inr(f.hi50)} · ${t("stock.range80")} ${inr(f.lo80)}–${inr(f.hi80)}`
            : "",
        );
      } else setReadout("");
    });
    const onWheel = (e: WheelEvent) => {
      const f = wheelZoom(e);
      if (f === null) return; // plain scroll: the page scrolls, the chart stays
      e.preventDefault();
      zoom(chart, f, e.clientX - el.getBoundingClientRect().left);
      setRange(null);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => {
      el.removeEventListener("wheel", onWheel);
      chart.remove();
      chartRef.current = null;
      apiRef.current = null;
    };
  }, [bars, call, trades, theme, t]);

  useEffect(() => {
    apiRef.current?.apply(layers);
    save("sk-layers", layers);
  }, [layers]);
  useEffect(() => {
    if (range) {
      apiRef.current?.setRange(range);
      save("sk-range", { r: range });
    }
  }, [range]);

  const step = useCallback((f: number) => {
    if (chartRef.current) zoom(chartRef.current, f);
    setRange(null);
  }, []);
  const last = bars[bars.length - 1];
  const legend = (cls: string, color: string, word: string) => (
    <span key={word}>
      <i
        className={cls}
        style={{
          borderColor: color,
          background: cls.includes("bx") || cls.includes("dot") ? color : undefined,
        }}
      />
      {t(word)}
    </span>
  );
  return (
    <div className="sk-chart">
      <div className="sk-tools">
        <fieldset className="sk-seg" aria-label={t("stock.chart")}>
          {RANGES.map((r) => (
            <button
              key={r}
              type="button"
              className="sk-sg"
              aria-pressed={range === r}
              onClick={() => setRange(r)}
            >
              {r === "All" ? t("stock.rall") : r}
            </button>
          ))}
        </fieldset>
        <span className="sk-zm">
          <button
            type="button"
            className="sk-ib"
            aria-label={t("stock.zoomIn")}
            onClick={() => step(0.7)}
          >
            +
          </button>
          <button
            type="button"
            className="sk-ib"
            aria-label={t("stock.zoomOut")}
            onClick={() => step(1.4)}
          >
            −
          </button>
          <button type="button" className="sk-btn" onClick={() => setRange(range ?? "1Y")}>
            {t("stock.reset")}
          </button>
        </span>
        <span className="sk-tr">
          <span className="sk-lyr">
            <button
              type="button"
              className="sk-btn"
              aria-expanded={menu}
              onClick={() => setMenu((m) => !m)}
            >
              <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
                <path
                  d="M12 3 2 8l10 5 10-5-10-5Zm0 12L4.6 11.3 2 12.6l10 5 10-5-2.6-1.3L12 15Zm0 4-7.4-3.7L2 16.6l10 5 10-5-2.6-1.3L12 19Z"
                  fill="currentColor"
                />
              </svg>
              {t("stock.layers")}
            </button>
            {menu && (
              <div className="sk-menu">
                {LAYERS.map((k) => (
                  <label key={k} className="sk-mi">
                    <input
                      type="checkbox"
                      checked={layers[k]}
                      onChange={(e) => setLayers((l) => ({ ...l, [k]: e.target.checked }))}
                    />
                    <span>{t(`stock.layer.${k}`)}</span>
                  </label>
                ))}
              </div>
            )}
          </span>
          {extra}
        </span>
      </div>
      <div className="sk-cvw">
        <div className="sk-cv" ref={host} data-testid="chart" />
        <div className="sk-readout" aria-live="off">
          {readout}
        </div>
      </div>
      <div className="sk-legend">
        {legend("ln", "var(--primary)", "stock.price")}
        {layers.avg && legend("ln", "var(--warn)", "stock.avg2")}
        {layers.avg && legend("ln dash", "var(--text-2)", "stock.avg10")}
        {layers.vol && legend("bx", "var(--c3)", "stock.layer.vol")}
        {layers.band &&
          call &&
          legend("bx", "color-mix(in srgb, var(--primary) 30%, transparent)", "stock.range50")}
        {layers.band &&
          call &&
          legend("bx", "color-mix(in srgb, var(--primary) 13%, transparent)", "stock.range80")}
        {layers.trades && legend("dot", "var(--gain)", "stock.bought")}
        {layers.trades && legend("dot", "var(--loss)", "stock.sold")}
      </div>
      <p className="note">
        {t("stock.hint")}
        {last ? "" : ""}
      </p>
    </div>
  );
}

function zoom(chart: IChartApi, k: number, x?: number) {
  const ts = chart.timeScale();
  const r = ts.getVisibleLogicalRange();
  if (!r) return;
  const at = x === undefined ? null : ts.coordinateToLogical(x);
  const mid = at ?? (r.from + r.to) / 2;
  const from = mid - (mid - r.from) * k;
  const to = mid + (r.to - mid) * k;
  if (to - from < 8) return;
  ts.setVisibleLogicalRange({ from, to });
}
export { addDays };
