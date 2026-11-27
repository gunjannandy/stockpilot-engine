// The stock chart: Lightweight Charts with the zoom rules of Kite. Plain scroll scrolls the page.
import {
  AreaSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  LineSeries,
  LineStyle,
  type Time,
} from "lightweight-charts";
import { useCallback, useEffect, useRef, useState } from "react";
import { useWords } from "../words";
import { type Bar, band, type RangeId, rangeStart, sma, wheelZoom } from "./series";

const FORECAST_DAYS = 120;
const css = (n: string) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const addDays = (iso: string, n: number) => {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
};

export function StockChart(props: { bars: Bar[]; buys: string[]; vol?: number }) {
  const { bars, buys, vol = 0.012 } = props;
  const t = useWords();
  const host = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const [range, setRange] = useState<RangeId>("1y");
  const [theme, setTheme] = useState(0);
  const rangeRef = useRef(range);
  rangeRef.current = range;

  const apply = useCallback(
    (r: RangeId) => {
      const first = bars[0];
      const lastBar = bars[bars.length - 1];
      if (!first || !lastBar) return;
      const last = lastBar.time;
      chartRef.current?.timeScale().setVisibleRange({
        from: rangeStart(last, r, first.time) as Time,
        to: addDays(last, FORECAST_DAYS) as Time,
      });
    },
    [bars],
  );

  useEffect(() => {
    const mo = new MutationObserver(() => setTheme((n) => n + 1));
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => mo.disconnect();
  }, []);

  // biome-ignore lint/correctness/useExhaustiveDependencies: theme is a re-colour trigger
  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const chart = createChart(el, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: css("--surface") || "#fff" },
        textColor: css("--text-2") || "#333",
        fontFamily: css("--font"),
        attributionLogo: true,
      },
      grid: { vertLines: { visible: false }, horzLines: { color: css("--line-2") } },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false },
      handleScale: { mouseWheel: false, pinch: true, axisPressedMouseMove: true },
      handleScroll: {
        mouseWheel: false,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: false,
      },
    });
    chartRef.current = chart;
    const last = bars[bars.length - 1];
    if (!last) return;
    const primary = css("--primary");
    const sub = { lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false };

    // forecast band: fill the high edge, then paint the low edge back in the surface colour
    const fc = band(last.close, FORECAST_DAYS, vol, 5).map((p) => ({
      ...p,
      time: addDays(last.time, p.time),
    }));
    const hi = chart.addSeries(AreaSeries, {
      lineVisible: false,
      topColor: `${primary}33`,
      bottomColor: `${primary}33`,
      ...sub,
    });
    hi.setData([
      { time: last.time, value: last.close },
      ...fc.map((p) => ({ time: p.time, value: p.hi })),
    ] as never);
    const lo = chart.addSeries(AreaSeries, {
      lineVisible: false,
      topColor: css("--surface"),
      bottomColor: css("--surface"),
      ...sub,
    });
    lo.setData([
      { time: last.time, value: last.close },
      ...fc.map((p) => ({ time: p.time, value: p.lo })),
    ] as never);

    const avg = (days: number, color: string, style: LineStyle) => {
      const s = chart.addSeries(LineSeries, { color, lineWidth: 1, lineStyle: style, ...sub });
      s.setData(sma(bars, days) as never);
    };
    avg(10 * 21, css("--text-2"), LineStyle.Dashed);
    avg(2 * 21, css("--warn"), LineStyle.Solid);

    const price = chart.addSeries(LineSeries, { color: primary, lineWidth: 2, ...sub });
    price.setData(bars.map((b) => ({ time: b.time, value: b.close })) as never);
    price.createPriceLine({
      price: +(last.close * 1.12).toFixed(2),
      color: css("--gain"),
      lineStyle: LineStyle.Dotted,
      lineWidth: 1,
      axisLabelVisible: true,
      title: t("stock.up"),
    });
    price.createPriceLine({
      price: +(last.close * 0.9).toFixed(2),
      color: css("--loss"),
      lineStyle: LineStyle.Dotted,
      lineWidth: 1,
      axisLabelVisible: true,
      title: t("stock.down"),
    });
    const dates = new Set(bars.map((b) => b.time));
    createSeriesMarkers(
      price,
      buys
        .filter((d) => dates.has(d))
        .map((d) => ({
          time: d as Time,
          position: "belowBar" as const,
          shape: "circle" as const,
          color: css("--gain"),
          text: "",
        })),
    );
    apply(rangeRef.current);

    const onWheel = (e: WheelEvent) => {
      const f = wheelZoom(e);
      if (f === null) return; // plain scroll: the page scrolls, the chart stays
      e.preventDefault();
      zoom(chart, f, e.clientX - el.getBoundingClientRect().left);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => {
      el.removeEventListener("wheel", onWheel);
      chart.remove();
      chartRef.current = null;
    };
  }, [bars, buys, vol, theme, apply, t]);

  const pick = (r: RangeId) => {
    setRange(r);
    apply(r);
  };
  const ranges: [RangeId, string][] = [
    ["6m", "stock.r6m"],
    ["1y", "stock.r1y"],
    ["all", "stock.rall"],
  ];
  return (
    <div className="sc">
      <div className="sc-bar">
        <fieldset className="sc-seg" aria-label={t("stock.chart")}>
          {ranges.map(([id, k]) => (
            <button key={id} type="button" aria-pressed={range === id} onClick={() => pick(id)}>
              {t(k)}
            </button>
          ))}
        </fieldset>
        <button
          type="button"
          className="sc-btn"
          aria-label={t("stock.zoomIn")}
          onClick={() => chartRef.current && zoom(chartRef.current, 1.4)}
        >
          +
        </button>
        <button
          type="button"
          className="sc-btn"
          aria-label={t("stock.zoomOut")}
          onClick={() => chartRef.current && zoom(chartRef.current, 1 / 1.4)}
        >
          −
        </button>
        <button type="button" className="sc-btn sc-reset" onClick={() => apply(range)}>
          {t("stock.reset")}
        </button>
      </div>
      <div className="sc-plot" ref={host} data-testid="chart" />
      <ul className="sc-legend">
        <li>
          <i className="k-price" />
          {t("stock.price")}
        </li>
        <li>
          <i className="k-a2" />
          {t("stock.avg2")}
        </li>
        <li>
          <i className="k-a10" />
          {t("stock.avg10")}
        </li>
        <li>
          <i className="k-buy" />
          {t("stock.buys")}
        </li>
      </ul>
      <p className="note">{t("stock.hint")}</p>
    </div>
  );
}

function zoom(chart: IChartApi, f: number, x?: number) {
  const ts = chart.timeScale();
  const lr = ts.getVisibleLogicalRange();
  if (!lr) return;
  const at = x === undefined ? null : ts.coordinateToLogical(x);
  const c = at ?? (lr.from + lr.to) / 2;
  ts.setVisibleLogicalRange({ from: c - (c - lr.from) / f, to: c + (lr.to - c) / f });
}
