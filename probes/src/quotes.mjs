export function parseYahooChart(json, nowSeconds) {
  const meta = json?.chart?.result?.[0]?.meta;
  if (!meta || typeof meta.regularMarketPrice !== "number") return null;
  return {
    symbol: meta.symbol,
    price: meta.regularMarketPrice,
    prevClose: meta.chartPreviousClose ?? null,
    asOf: meta.regularMarketTime,
    ageSeconds: nowSeconds - meta.regularMarketTime,
  };
}

export function parseNseQuote(json) {
  const p = json?.priceInfo;
  if (!p || typeof p.lastPrice !== "number") return null;
  return { symbol: json.info?.symbol ?? null, price: p.lastPrice, prevClose: p.previousClose ?? null, asOfText: p.lastUpdateTime ?? null };
}
