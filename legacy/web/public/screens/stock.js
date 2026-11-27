/* T22: the stock screen. One component, used as the full page (phone, and from search) and as the right-hand pane beside a list.
   Chart (Lightweight Charts), facts in four groups, and the forecast pane with the model's nine-part form.
   Pure functions come first so tests can run them in Node; the browser part (html, mount) comes last.
   Data: chart/<SYM>.json and stock/<SYM>.json (published files), /api/v2/calls/<SYM>, /api/v2/quotes, /api/v2/jobs (see docs/contract/live-data-v2.md). */
(function (root) {
  "use strict";

  /* ---------- words: plain English; Bengali keeps trade words in English letters ---------- */
  const words = {
    en: {
      skBack: "Back", skChartH: "Price chart", skChartP: "Every day since listing, with our forecast ahead.", skFull: "Full view", skFullClose: "Close", skLayers: "Layers",
      skZoomIn: "Zoom in", skZoomOut: "Zoom out", skReset: "Reset", skZoomHint: "Ctrl or ⌘ + scroll to zoom, drag to move.",
      skR1M: "1M", skR6M: "6M", skR1Y: "1Y", skR5Y: "5Y", skRAll: "All",
      skLvVol: "Volume", skLv50: "50-day average", skLv200: "200-day average", skLvBand: "Forecast range", skLvLevels: "Levels that change our view", skLvTrades: "Your buys and sells", skLvCalls: "Our past calls",
      skLgPrice: "Price", skLg50: "50-day average", skLg200: "200-day average", skLgVol: "Volume", skLgMid: "Likely price", skLg50b: "Likely range (50%)", skLg80b: "Wide range (80%)", skLgBuy: "You bought", skLgSell: "You sold", skLgCall: "We made a call",
      skBought: "Bought", skSold: "Sold", skWeSaid: "We said", skCallBuy: "Buy", skCallHold: "Keep", skCallSell: "Sell", skCallWait: "Watch", skCallNone: "No view yet",
      skNoChart: "We have no price history for this stock yet.", skNoChartP: "Press Analyse and we will fetch it.", skChartFail: "The chart did not load.", skRetry: "Try again", skNoLib: "The chart tool did not load. Reload the page.",
      skOpen: "Open", skHigh: "High", skLow: "Low", skClose: "Close", skVolume: "Volume", skAvg50: "50-day", skAvg200: "200-day", skLikely: "Likely", skRange50: "50% range", skRange80: "80% range", skAhead: "Forecast",
      skFcH: "Our forecast", skFcP: "The code screen and the model each judge on their own.", skAnalyse: "Analyse", skAnalyseAgain: "Analyse again", skUpdate: "Update forecast",
      skStaleChip: "Out of date", skStaleText: "The price moved outside our forecast range, or the forecast is old. Update it before you decide.",
      skNoFc: "No forecast yet", skNoFcP: "We have never forecast this stock. Press Analyse and we will read the numbers and write one, usually within minutes.",
      skCall: "Our call", skChance6: "Chance it beats the Nifty, 6 months", skChance3: "In 3 months", skConf: "How sure we are", skConfLow: "Not very", skConfMedium: "Fairly", skConfHigh: "Very",
      skCallLine: (c, p6, p3) => `We say ${c}. The chance this stock beats the Nifty is ${p6}% over 6 months and ${p3}% over 3 months.`,
      skRoute: "Based on", skRouteCode: "The code screen", skRouteNews: "News (labelled, scored apart)", skModel: "Written by", skAsOf: "Prices as of",
      skRangeH: "Where the price could go", skR1: "In 1 month", skR3: "In 3 months", skR6: "In 6 months", skRangeS: (a, b) => `${a} to ${b}`, skRangeW: (a, b) => `wide ${a} to ${b}`,
      skFor: "What helps", skAgainst: "What hurts", skChange: "What would change our view", skRisks: "Risks", skHistory: "How the company has done", skMarket: "How the market sees it", skNews: "News",
      skNone: "Nothing to say here.", skWeight: n => `weight ${n}`, skNewsHelps: "Helps us", skNewsHurts: "Hurts us", skNewsNeutral: "No real effect", skSmall: "small", skMedium: "medium", skLarge: "large",
      skNewsLine: (e, s) => `A news item that ${e} (${s})`, skHelpsV: "helps", skHurtsV: "hurts", skNeutralV: "does not move it",
      skLevel: "At", skChanged: "Our view changed",
      skJobWorking: "Working on it", skJobDone: "Forecast is ready", skJobFail: "That did not work", skJobStarted: "Started. This usually takes a few minutes.",
      skFactsH: "Today's numbers", skFactsP: "Four groups. Each number has one plain sentence.", skGPrice: "Price", skGValue: "Cheap or dear", skGQuality: "Quality", skGEvents: "Coming up",
      skLast: "Last price", skToday: "Today", skRange52: "52-week range", skVolUsual: "Trading vs usual", skDelivery: "Bought to keep (delivery)",
      skPE: "P/E", skPB: "P/B", skYield: "Dividend yield", skMcap: "Market size",
      skSales: "Sales growth", skProfit: "Profit growth", skROE: "ROE", skROCE: "ROCE", skDebt: "Debt to equity", skPromoter: "Promoter holding", skPledge: "Pledged by promoters",
      skNA: "Not available", skNoEvents: "Nothing announced", skCrore: "crore", skAYear: "a year", skUsual: "usual",
      skEvResults: "Results", skEvDividend: "Dividend", skEvSplit: "Split", skEvBulk_deal: "Bulk deal", skEvBlock_deal: "Block deal", skEvAsm: "ASM list", skEvGsm: "GSM list",
      skSLast: "The latest price we hold.", skSToday: "How the price moved in the last day.", skS52: "Where today's price sits between the lowest and highest of the last year.",
      skSVol: "How busy trading is compared with a normal day.", skSDelivery: "Share of buyers who take the shares home instead of selling the same day. Not available for every stock.",
      skSPE: "What you pay for ₹1 of yearly profit. Lower is cheaper.", skSPB: "Price compared with what the company owns on paper.", skSYield: "Cash paid out each year as a share of the price.", skSMcap: "What the whole company is worth on the market.",
      skSSales: "How much more the company sold than a year ago.", skSProfit: "How much more profit it made than a year ago.", skSROE: "Profit for every ₹100 of the owners' money. 15 or more is good.", skSROCE: "Profit for every ₹100 put into the business, with loans counted.",
      skSDebt: "Loans compared with the owners' money. Under 1 is comfortable.", skSPromoter: "Share of the company the founders and their family hold.", skSPledge: "Share of their holding the promoters have pledged for loans. Lower is safer.",
      skSEvent: "Worth knowing before you decide.", skSNoEvent: "No result date, dividend or exchange alert is on record.",
      skLoadingFacts: "Loading the numbers", skFactsFail: "The numbers did not load.",
      skPriceFresh: "price just now", skEntag: "Not translated yet",
    },
    bn: {
      skBack: "ফিরে যান", skChartH: "দামের chart", skChartP: "listing-এর পর থেকে প্রতিদিন, সামনে আমাদের forecast সহ।", skFull: "বড় করে দেখুন", skFullClose: "বন্ধ করুন", skLayers: "Layer",
      skZoomIn: "বড় করুন", skZoomOut: "ছোট করুন", skReset: "আগের মতো", skZoomHint: "Ctrl বা ⌘ চেপে scroll করলে zoom হবে, টেনে সরান।",
      skR1M: "1M", skR6M: "6M", skR1Y: "1Y", skR5Y: "5Y", skRAll: "সব",
      skLvVol: "Volume", skLv50: "50 দিনের গড়", skLv200: "200 দিনের গড়", skLvBand: "Forecast-এর সীমা", skLvLevels: "যে দামে আমাদের মত বদলায়", skLvTrades: "আপনার কেনা-বেচা", skLvCalls: "আমাদের আগের call",
      skLgPrice: "দাম", skLg50: "50 দিনের গড়", skLg200: "200 দিনের গড়", skLgVol: "Volume", skLgMid: "সম্ভাব্য দাম", skLg50b: "সম্ভাব্য সীমা (50%)", skLg80b: "বড় সীমা (80%)", skLgBuy: "আপনি কিনেছেন", skLgSell: "আপনি বেচেছেন", skLgCall: "আমরা call দিয়েছি",
      skBought: "কেনা", skSold: "বেচা", skWeSaid: "আমরা বলেছি", skCallBuy: "কিনুন", skCallHold: "রাখুন", skCallSell: "বিক্রি", skCallWait: "নজরে", skCallNone: "এখনও মত নেই",
      skNoChart: "এই stock-এর দামের ইতিহাস এখনও আমাদের কাছে নেই।", skNoChartP: "Analyse চাপুন, আমরা এনে দেব।", skChartFail: "Chart আসেনি।", skRetry: "আবার চেষ্টা করুন", skNoLib: "Chart-এর tool আসেনি। পাতাটা আবার খুলুন।",
      skOpen: "খোলা", skHigh: "সর্বোচ্চ", skLow: "সর্বনিম্ন", skClose: "বন্ধ", skVolume: "Volume", skAvg50: "50 দিন", skAvg200: "200 দিন", skLikely: "সম্ভাব্য", skRange50: "50% সীমা", skRange80: "80% সীমা", skAhead: "Forecast",
      skFcH: "আমাদের forecast", skFcP: "Code-এর হিসেব আর model-এর বিচার, দুটো আলাদা করে করা।", skAnalyse: "Analyse", skAnalyseAgain: "আবার Analyse", skUpdate: "Forecast নতুন করুন",
      skStaleChip: "পুরনো", skStaleText: "দাম আমাদের forecast-এর সীমার বাইরে গেছে, নয়তো forecast পুরনো। সিদ্ধান্তের আগে নতুন করে নিন।",
      skNoFc: "এখনও forecast নেই", skNoFcP: "এই stock আমরা কখনও forecast করিনি। Analyse চাপুন, আমরা সংখ্যা পড়ে একটা লিখে দেব, সাধারণত কয়েক মিনিটে।",
      skCall: "আমাদের call", skChance6: "6 মাসে Nifty-কে হারানোর chance", skChance3: "3 মাসে", skConf: "আমরা কতটা নিশ্চিত", skConfLow: "খুব নয়", skConfMedium: "মোটামুটি", skConfHigh: "খুব",
      skCallLine: (c, p6, p3) => `আমরা বলছি ${c}। এই stock Nifty-কে হারানোর chance 6 মাসে ${p6}% আর 3 মাসে ${p3}%।`,
      skRoute: "ভিত্তি", skRouteCode: "Code-এর হিসেব", skRouteNews: "খবর (আলাদা করে চিহ্নিত ও নম্বর দেওয়া)", skModel: "লিখেছে", skAsOf: "দামের তারিখ",
      skRangeH: "দাম কোথায় যেতে পারে", skR1: "1 মাসে", skR3: "3 মাসে", skR6: "6 মাসে", skRangeS: (a, b) => `${a} থেকে ${b}`, skRangeW: (a, b) => `বড় সীমা ${a} থেকে ${b}`,
      skFor: "যা সাহায্য করছে", skAgainst: "যা ক্ষতি করছে", skChange: "কী হলে আমাদের মত বদলাবে", skRisks: "ঝুঁকি", skHistory: "company এতদিন কেমন চলেছে", skMarket: "বাজার একে কীভাবে দেখে", skNews: "খবর",
      skNone: "এখানে বলার মতো কিছু নেই।", skWeight: n => `ওজন ${n}`, skNewsHelps: "আমাদের পক্ষে", skNewsHurts: "আমাদের বিপক্ষে", skNewsNeutral: "বিশেষ প্রভাব নেই", skSmall: "ছোট", skMedium: "মাঝারি", skLarge: "বড়",
      skNewsLine: (e, s) => `একটা খবর যা ${e} (${s})`, skHelpsV: "সাহায্য করছে", skHurtsV: "ক্ষতি করছে", skNeutralV: "দামে প্রভাব ফেলছে না",
      skLevel: "দাম", skChanged: "আমাদের মত বদলেছে",
      skJobWorking: "কাজ চলছে", skJobDone: "Forecast তৈরি", skJobFail: "কাজ হয়নি", skJobStarted: "শুরু হয়েছে। সাধারণত কয়েক মিনিট লাগে।",
      skFactsH: "আজকের সংখ্যা", skFactsP: "চারটে ভাগ। প্রতিটা সংখ্যার পাশে একটা সহজ বাক্য।", skGPrice: "দাম", skGValue: "সস্তা না দামি", skGQuality: "মান", skGEvents: "সামনে যা আসছে",
      skLast: "শেষ দাম", skToday: "আজ", skRange52: "52 সপ্তাহের সীমা", skVolUsual: "লেনদেন, সাধারণের তুলনায়", skDelivery: "রেখে দেওয়ার জন্য কেনা (delivery)",
      skPE: "P/E", skPB: "P/B", skYield: "Dividend yield", skMcap: "বাজারে আকার",
      skSales: "বিক্রি বৃদ্ধি", skProfit: "লাভ বৃদ্ধি", skROE: "ROE", skROCE: "ROCE", skDebt: "ধার আর মালিকের টাকা", skPromoter: "Promoter-এর অংশ", skPledge: "Promoter যা বন্ধক রেখেছে",
      skNA: "পাওয়া যায়নি", skNoEvents: "কিছু ঘোষণা হয়নি", skCrore: "কোটি", skAYear: "বছরে", skUsual: "সাধারণ",
      skEvResults: "ফল", skEvDividend: "Dividend", skEvSplit: "Split", skEvBulk_deal: "Bulk deal", skEvBlock_deal: "Block deal", skEvAsm: "ASM তালিকা", skEvGsm: "GSM তালিকা",
      skSLast: "আমাদের কাছে থাকা সবচেয়ে নতুন দাম।", skSToday: "গত একদিনে দাম কতটা নড়েছে।", skS52: "গত এক বছরের সবচেয়ে কম আর বেশির মধ্যে আজকের দাম কোথায়।",
      skSVol: "একটা সাধারণ দিনের তুলনায় আজ লেনদেন কত জমজমাট।", skSDelivery: "যাঁরা একই দিনে বেচে না দিয়ে শেয়ার ঘরে রাখছেন তাঁদের অংশ। সব stock-এর জন্য পাওয়া যায় না।",
      skSPE: "বছরের ₹1 লাভের জন্য আপনি কত দেন। কম মানে সস্তা।", skSPB: "কাগজে company-র যা আছে তার তুলনায় দাম।", skSYield: "প্রতি বছর নগদে যা দেয়, দামের অংশ হিসেবে।", skSMcap: "পুরো company-র বাজারদর।",
      skSSales: "এক বছর আগের চেয়ে company কতটা বেশি বিক্রি করেছে।", skSProfit: "এক বছর আগের চেয়ে কতটা বেশি লাভ করেছে।", skSROE: "মালিকের প্রতি ₹100-তে লাভ। 15 বা তার বেশি ভালো।", skSROCE: "ব্যবসায় ঢালা প্রতি ₹100-তে লাভ, ধার ধরে।",
      skSDebt: "মালিকের টাকার তুলনায় ধার। 1-এর নিচে স্বস্তির।", skSPromoter: "founder আর তাঁদের পরিবারের হাতে company-র যে অংশ।", skSPledge: "promoter-দের অংশের যতটা ধারের জন্য বন্ধক রাখা। কম হলে নিরাপদ।",
      skSEvent: "সিদ্ধান্তের আগে জেনে রাখা ভালো।", skSNoEvent: "কোনো ফলের দিন, dividend বা exchange-এর সতর্কতা নেই।",
      skLoadingFacts: "সংখ্যা আসছে", skFactsFail: "সংখ্যা আসেনি।",
      skPriceFresh: "দাম এইমাত্র", skEntag: "এখনও অনুবাদ হয়নি",
    },
  };
  const wd = (lang, k, ...a) => { const v = (words[lang] && words[lang][k]) ?? words.en[k]; return typeof v === "function" ? v(...a) : (v ?? k); };

  /* ---------- small helpers ---------- */
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const isoOf = d => d.toISOString().slice(0, 10);
  const parse = s => new Date(s + "T00:00:00Z");
  const addDays = (s, n) => { const d = parse(s); d.setUTCDate(d.getUTCDate() + n); return isoOf(d); };
  const isWeekday = s => parse(s).getUTCDay() % 6 !== 0;
  const dmy = s => { const d = parse(s); return isNaN(d) ? "" : `${d.getUTCDate()} ${MON[d.getUTCMonth()]}`; };
  const dmyy = s => { const d = parse(s); return isNaN(d) ? "" : `${d.getUTCDate()} ${MON[d.getUTCMonth()]} ${d.getUTCFullYear()}`; };
  const num = v => v != null && v !== "" && isFinite(v);
  const inr = (v, d = 0) => !num(v) ? "–" : "₹" + Number(v).toLocaleString("en-IN", { maximumFractionDigits: d, minimumFractionDigits: d });
  const px = v => !num(v) ? "–" : inr(v, v < 100 ? 2 : v < 1000 ? 1 : 0);
  const pc = (v, d = 1) => !num(v) ? "–" : Number(v).toFixed(d).replace(/\.0+$/, "") + "%";
  const spc = (v, d = 1) => !num(v) ? "–" : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(d).replace(/\.0+$/, "") + "%";

  /* ---------- ranges ---------- */
  const RANGES = ["1M", "6M", "1Y", "5Y", "All"];
  const BACK = { "1M": [0, 1], "6M": [0, 6], "1Y": [1, 0], "5Y": [5, 0] };   // [years, months]
  function rangeStart(key, dates) {
    if (!dates || !dates.length) return null;
    if (key === "All" || !BACK[key]) return dates[0];
    const d = parse(dates[dates.length - 1]);
    d.setUTCFullYear(d.getUTCFullYear() - BACK[key][0]); d.setUTCMonth(d.getUTCMonth() - BACK[key][1]);
    const from = isoOf(d);
    return dates.find(x => x >= from) || dates[0];
  }

  /* ---------- series ---------- */
  function seriesOf(chart) {
    const out = { candles: [], volume: [], dma50: [], dma200: [] };
    if (!chart || !chart.dates) return out;
    chart.dates.forEach((t, i) => {
      const o = chart.open?.[i], h = chart.high?.[i], l = chart.low?.[i], c = chart.close?.[i];
      if (![o, h, l, c].every(num)) return;
      out.candles.push({ time: t, open: o, high: h, low: l, close: c });
      const v = chart.volume?.[i];
      if (num(v)) out.volume.push({ time: t, value: v, color: c >= o ? "rgba(31,164,99,.45)" : "rgba(229,72,77,.45)" });
      if (num(chart.dma50?.[i])) out.dma50.push({ time: t, value: chart.dma50[i] });
      if (num(chart.dma200?.[i])) out.dma200.push({ time: t, value: chart.dma200[i] });
    });
    return out;
  }

  /* ---------- markers: the father's buys and sells, and our past calls ---------- */
  const CALL_COLOR = { buy: "#1fa463", sell: "#e5484d", hold: "#7d8aa3", wait: "#7d8aa3", watch: "#7d8aa3" };
  const CALLKEY = { buy: "skCallBuy", hold: "skCallHold", sell: "skCallSell", wait: "skCallWait", watch: "skCallWait", weak: "skCallSell", review: "skCallSell", trim: "skCallSell" };
  function markersOf(events, dates, lang) {
    if (!events || !dates || !dates.length) return [];
    const first = dates[0], last = dates[dates.length - 1], by = new Map();
    for (const e of events) {
      if (!e || !e.date || e.date < first || e.date > last) continue;
      const time = dates.find(d => d >= e.date); if (!time) continue;
      const k = time + "|" + e.kind, cur = by.get(k);
      if (e.kind === "call") by.set(k, { time, kind: "call", call: e.call });
      else by.set(k, { time, kind: e.kind, qty: (cur?.qty || 0) + (Number(e.qty) || 0) });
    }
    const q = n => Math.round(n * 1000) / 1000;
    return [...by.values()].sort((a, b) => (a.time < b.time ? -1 : a.time > b.time ? 1 : a.kind < b.kind ? -1 : 1)).map(m => {
      if (m.kind === "buy") return { time: m.time, position: "belowBar", shape: "arrowUp", color: "#1fa463", text: `${wd(lang, "skBought")}${m.qty ? " " + q(m.qty) : ""}`, size: 1.4 };
      if (m.kind === "sell") return { time: m.time, position: "aboveBar", shape: "arrowDown", color: "#e5484d", text: `${wd(lang, "skSold")}${m.qty ? " " + q(m.qty) : ""}`, size: 1.4 };
      return { time: m.time, position: "inBar", shape: "circle", color: CALL_COLOR[m.call] || "#7d8aa3", text: `${wd(lang, "skWeSaid")} ${wd(lang, CALLKEY[m.call] || "skCallWait")}`, size: 1 };
    });
  }

  /* ---------- forecast bands ahead of today ---------- */
  // The row holds the 10th, 50th and 90th percentile at 1, 3 and 6 months: the lighter 80% band is low to high.
  // The darker 50% band is worked out from the same three numbers (0.674 / 1.282 of each side), so no extra figure is invented.
  const HZ = [["1m", 30], ["3m", 91], ["6m", 182]], K50 = 0.674 / 1.282;
  function bandsOf(call, lastDate, lastClose) {
    if (!call || !lastDate || !num(lastClose)) return null;
    const nodes = [];
    for (const [key, days] of HZ) {
      let lo = call["low_" + key], mid = call["likely_" + key], hi = call["high_" + key];
      if (![lo, mid, hi].every(num)) { const b = call.form?.bands?.[key]; if (Array.isArray(b)) [lo, mid, hi] = b; }
      if (![lo, mid, hi].every(num) || !(lo <= mid && mid <= hi) || lo < 0) return null;
      nodes.push({ key, days, time: addDays(lastDate, days), lo80: lo, hi80: hi, mid, lo50: mid - (mid - lo) * K50, hi50: mid + (hi - mid) * K50 });
    }
    const start = { days: 0, lo80: lastClose, hi80: lastClose, mid: lastClose, lo50: lastClose, hi50: lastClose };
    const all = [start, ...nodes], at = (d, f) => {
      const u = Math.sqrt(d);   // price spread grows with the square root of time
      for (let i = 1; i < all.length; i++) {
        const a = all[i - 1], b = all[i];
        if (d <= b.days) { const t = (u - Math.sqrt(a.days)) / (Math.sqrt(b.days) - Math.sqrt(a.days)); return a[f] + (b[f] - a[f]) * t; }
      }
      return all[all.length - 1][f];
    };
    const fields = ["lo80", "hi80", "lo50", "hi50", "mid"], points = [{ time: lastDate, lo80: lastClose, hi80: lastClose, lo50: lastClose, hi50: lastClose, mid: lastClose }];
    for (let d = 1; d <= 182; d++) {
      const t = addDays(lastDate, d); if (!isWeekday(t)) continue;
      const p = { time: t }; fields.forEach(f => { p[f] = at(d, f); }); points.push(p);
    }
    return { nodes, points };
  }

  /* ---------- facts: four groups, one plain sentence for each number ---------- */
  function factGroups(facts, lang) {
    const f = facts && !facts.failed ? facts : null, T = f?.today || {}, V = f?.valuation || {}, Q = f?.quality || {};
    const sent = k => { const s = (f?.sentences || []).find(x => x.key === k); if (!s) return null; if (lang === "bn") return s.bn ? { text: s.bn, en: false } : { text: s.en, en: !!s.en }; return { text: s.en, en: false }; };
    const row = (key, labelK, value, sentK) => {
      const have = value != null && value !== "–";
      const own = sent(key), text = own?.text || (have || key === "delivery" ? wd(lang, sentK) : wd(lang, sentK));
      return { key, label: wd(lang, labelK), value: have ? value : wd(lang, "skNA"), na: !have, sentence: text, en: !!own?.en };
    };
    const rng = num(T.low_52w) && num(T.high_52w) ? `${px(T.low_52w)} – ${px(T.high_52w)}` : null;
    const ev = (f?.events || []).slice().sort((a, b) => (a.date < b.date ? -1 : 1)).map((e, i) => {
      const bn = lang === "bn" && e.text_bn;
      return { key: "ev" + i, label: wd(lang, "skEv" + e.kind[0].toUpperCase() + e.kind.slice(1)), value: dmy(e.date), na: false, sentence: bn ? e.text_bn : e.text || wd(lang, "skSEvent"), en: lang === "bn" && !e.text_bn, date: e.date };
    });
    const noEv = [{ key: "noev", label: wd(lang, "skGEvents"), value: wd(lang, "skNoEvents"), na: !f, sentence: wd(lang, "skSNoEvent"), en: false }];
    return [
      { key: "price", title: wd(lang, "skGPrice"), rows: [
        row("last", "skLast", num(T.last) ? px(T.last) : null, "skSLast"),
        row("day", "skToday", num(T.day_change_pct) ? spc(T.day_change_pct, 2) : null, "skSToday"),
        row("range52", "skRange52", rng, "skS52"),
        row("volume", "skVolUsual", num(T.volume_vs_usual) ? `${Number(T.volume_vs_usual).toFixed(1).replace(/\.0$/, "")}×` : null, "skSVol"),
        row("delivery", "skDelivery", num(T.delivery_pct) ? pc(T.delivery_pct, 0) : null, "skSDelivery")] },
      { key: "value", title: wd(lang, "skGValue"), rows: [
        row("pe", "skPE", num(V.pe) ? Number(V.pe).toFixed(1) : null, "skSPE"),
        row("pb", "skPB", num(V.pb) ? Number(V.pb).toFixed(1) : null, "skSPB"),
        row("yield", "skYield", num(V.dividend_yield_pct) ? pc(V.dividend_yield_pct, 1) : null, "skSYield"),
        row("mcap", "skMcap", num(V.market_cap_cr) ? `${inr(V.market_cap_cr)} ${wd(lang, "skCrore")}` : null, "skSMcap")] },
      { key: "quality", title: wd(lang, "skGQuality"), rows: [
        row("sales", "skSales", num(Q.sales_growth_yoy_pct) ? `${spc(Q.sales_growth_yoy_pct, 1)} ${wd(lang, "skAYear")}` : null, "skSSales"),
        row("profit", "skProfit", num(Q.profit_growth_yoy_pct) ? `${spc(Q.profit_growth_yoy_pct, 1)} ${wd(lang, "skAYear")}` : null, "skSProfit"),
        row("roe", "skROE", num(Q.roe_pct) ? pc(Q.roe_pct, 1) : null, "skSROE"),
        row("roce", "skROCE", num(Q.roce_pct) ? pc(Q.roce_pct, 1) : null, "skSROCE"),
        row("debt", "skDebt", num(Q.debt_to_equity) ? Number(Q.debt_to_equity).toFixed(2) : null, "skSDebt"),
        row("promoter", "skPromoter", num(Q.promoter_pct) ? pc(Q.promoter_pct, 1) : null, "skSPromoter"),
        row("pledge", "skPledge", num(Q.pledge_pct) ? pc(Q.pledge_pct, 1) : null, "skSPledge")] },
      { key: "events", title: wd(lang, "skGEvents"), rows: ev.length ? ev : noEv },
    ];
  }

  /* ---------- the model's form, in the order the father reads it ---------- */
  function formView(call, lang) {
    if (!call) return null;
    const form = call.form || {}, bn = lang === "bn", B = form.bengali || {};
    const say = (key, en) => { const b = B[key]; return bn ? (b ? { text: b, en: false } : { text: en || "", en: !!en }) : { text: en || "", en: false }; };
    const items = (arr, f) => (arr || []).map(x => { const o = f(x); return bn && o.bn !== undefined ? { ...o, text: o.bn || o.text, en: !o.bn } : { ...o, en: false }; });
    const h = say("history", form.history), m = say("market_weight", form.market_weight);
    return {
      call: call.call, route: call.route || "code", newsBuy: !!call.news_buy, stale: !!call.out_of_date, confidence: call.confidence,
      chance3: num(call.chance_3m) ? Math.round(call.chance_3m * 100) : null, chance6: num(call.chance_6m) ? Math.round(call.chance_6m * 100) : null,
      model: call.model, asOf: call.as_of, writtenAt: call.written_at,
      bengaliSummary: bn ? (B.summary || null) : null,
      parts: [
        { key: "history", title: "skHistory", text: h.text, en: h.en },
        { key: "market", title: "skMarket", text: m.text, en: m.en },
        { key: "news", title: "skNews", items: items(form.news, n => ({ id: n.item_id, effect: n.effect, size: n.size, text: "", bn: undefined })) },
        { key: "for", title: "skFor", items: items(form.reasons_for, r => ({ text: r.text, weight: r.weight, evidence: r.evidence, bn: r.text_bn })) },
        { key: "against", title: "skAgainst", items: items(form.reasons_against, r => ({ text: r.text, weight: r.weight, evidence: r.evidence, bn: r.text_bn })) },
        { key: "change", title: "skChange", items: items(form.what_would_change, r => ({ level: r.level, text: r.text, bn: r.text_bn })) },
        { key: "risks", title: "skRisks", items: items(form.risks, r => typeof r === "string" ? { text: r, bn: undefined } : { text: r.text, bn: r.text_bn }) },
      ],
    };
  }

  const API = { words, wd, RANGES, rangeStart, seriesOf, markersOf, bandsOf, factGroups, formView, _u: { esc, px, inr, pc, spc, dmy, dmyy, addDays, isWeekday, num } };
  root.SPStock = API;

  /* ================= browser part ================= */
  const LS = { get(k, d) { try { const v = localStorage.getItem("sp-" + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } }, set(k, v) { try { localStorage.setItem("sp-" + k, JSON.stringify(v)); } catch (e) { /* private window */ } } };
  const LAYERS = ["vol", "a50", "a200", "band", "levels", "trades", "calls"];
  const LAYER_WORD = { vol: "skLvVol", a50: "skLv50", a200: "skLv200", band: "skLvBand", levels: "skLvLevels", trades: "skLvTrades", calls: "skLvCalls" };
  const CALLCLASS = { buy: "v-buy", hold: "v-hold", sell: "v-sell", wait: "v-watch", watch: "v-watch" };
  const enTag = lang => lang === "bn" ? ` <span class="entag" title="${esc(wd(lang, "skEntag"))}">EN</span>` : "";
  
  function factsHTML(groups, lang, loading) {
    return `<div class="sk-facts${loading ? " is-loading" : ""}">${groups.map(g => `<div class="sk-grp" data-grp="${g.key}"><h4>${esc(g.title)}</h4>${g.rows.map(r =>
      `<div class="sk-fact${r.na ? " na" : ""}"><span class="k">${esc(r.label)}</span><b class="num">${esc(r.value)}</b><small>${esc(r.sentence)}${r.en ? enTag(lang) : ""}</small></div>`).join("")}</div>`).join("")}</div>`;
  }

  function sec(icon, title, sub, action, body, id) {
    return `<section class="sk-sec"${id ? ` id="${id}"` : ""}><div class="sk-sh"><span class="sk-ic ms" aria-hidden="true">${icon}</span><div class="sk-stt"><h3>${esc(title)}</h3><p>${esc(sub)}</p></div>${action ? `<div class="sk-sa">${action}</div>` : ""}</div><div class="sk-sb">${body}</div></section>`;
  }

  // The frame. Every box has its height from the first paint, so nothing moves when the data arrives.
  function html(ctx) {
    const lang = ctx.lang || "en", sym = ctx.symbol, T = k => wd(lang, k);
    const tools = `<div class="sk-tools"><span class="sk-seg" role="group" aria-label="Range">${RANGES.map(r => `<button class="sk-sg" data-sk-range="${r}" aria-pressed="false">${T("skR" + r)}</button>`).join("")}</span>
      <span class="sk-zm"><button class="sk-ib" data-sk-zoom="in" aria-label="${esc(T("skZoomIn"))}">+</button><button class="sk-ib" data-sk-zoom="out" aria-label="${esc(T("skZoomOut"))}">−</button><button class="sk-btn" data-sk-reset>${T("skReset")}</button></span>
      <span class="sk-lyr"><button class="sk-btn" data-sk-layers aria-expanded="false"><span class="ms">layers</span>${T("skLayers")}</button><div class="sk-menu" data-sk-menu hidden>${LAYERS.map(k => `<label class="sk-mi"><input type="checkbox" data-sk-layer="${k}"><span>${T(LAYER_WORD[k])}</span></label>`).join("")}</div></span><button class="sk-btn sk-fill sk-shut" data-sk-full>${T("skFullClose")}</button></div>`;
    const chart = `<div class="sk-chart" data-sk-chart="${esc(sym)}">${tools}
      <div class="sk-cvw"><div class="sk-cv" data-sk-cv><div class="sk-skel" aria-hidden="true"></div></div><div class="sk-readout" data-sk-readout aria-live="off"></div></div>
      <div class="sk-legend" data-sk-legend></div><p class="sk-hint">${T("skZoomHint")}</p></div>`;
    const fc = `<div data-sk-fc="${esc(sym)}"><div class="sk-skel sk-skel-fc" aria-hidden="true"></div></div>`;
    const head = `<header class="sk-head"><div class="sk-hl"><div class="sk-chips" data-sk-chips>${ctx.tagsHtml || ""}</div><h2 class="disp">${esc(ctx.name || sym)}</h2><div class="muted num sk-sub" data-sk-sub>${esc(sym)}${ctx.exchange ? " · " + esc(ctx.exchange) : ""}</div></div>
      <div class="sk-hr"><div class="px num" data-sk-px>${ctx.price != null ? px(ctx.price) : ""}</div><div class="sk-pl muted" data-sk-pl></div></div></header>
      ${ctx.actionsHtml ? `<div class="sk-acts">${ctx.actionsHtml}</div>` : ""}<div data-sk-band></div>`;
    return `<div class="sk${ctx.pane ? " sk-pane" : ""}" data-sk-root="${esc(sym)}" data-sk-lang="${esc(lang)}">
      ${ctx.back || ""}${head}
      ${sec("show_chart", T("skChartH"), T("skChartP"), `<button class="sk-btn sk-tonal" data-sk-full><span class="ms">open_in_full</span><span class="sk-fl">${T("skFull")}</span></button>`, chart, "s-chart")}
      ${sec("query_stats", T("skFcH"), T("skFcP"), `<button class="sk-btn sk-fill" data-sk-analyse><span class="ms">query_stats</span><span data-sk-an-l>${T("skAnalyse")}</span></button>`, fc, "s-forecast")}
      ${sec("grid_view", T("skFactsH"), T("skFactsP"), "", `<div data-sk-facts="${esc(sym)}">${factsHTML(factGroups(null, lang), lang, true)}</div>`, "s-nums")}
      ${ctx.afterHtml || ""}</div>`;
  }

  /* ---------- the chart band, drawn behind the candles ---------- */
  function bandPrimitive(getState) {
    let chart, series, req;
    const renderer = {
      draw(target) {
        const st = getState(); if (!st.bands || !st.show) return;
        target.useBitmapCoordinateSpace(({ context: g, horizontalPixelRatio: hr, verticalPixelRatio: vr }) => {
          const ts = chart.timeScale(), X = t => ts.timeToCoordinate(t), Y = p => series.priceToCoordinate(p);
          const pts = st.bands.points.map(p => ({ x: X(p.time), p })).filter(o => o.x != null);
          if (pts.length < 2) return;
          const poly = (a, b, fill) => {
            g.beginPath();
            pts.forEach((o, i) => { const x = o.x * hr, y = Y(o.p[a]) * vr; i ? g.lineTo(x, y) : g.moveTo(x, y); });
            for (let i = pts.length - 1; i >= 0; i--) g.lineTo(pts[i].x * hr, Y(pts[i].p[b]) * vr);
            g.closePath(); g.fillStyle = fill; g.fill();
          };
          poly("hi80", "lo80", st.c.band80); poly("hi50", "lo50", st.c.band50);
          g.beginPath(); pts.forEach((o, i) => { const x = o.x * hr, y = Y(o.p.mid) * vr; i ? g.lineTo(x, y) : g.moveTo(x, y); });
          g.strokeStyle = st.c.pri; g.lineWidth = 1.5 * hr; g.setLineDash([5 * hr, 4 * hr]); g.stroke(); g.setLineDash([]);
          const x0 = pts[0].x * hr; g.strokeStyle = st.c.on2; g.lineWidth = hr; g.setLineDash([2 * hr, 4 * hr]);
          g.beginPath(); g.moveTo(x0, 0); g.lineTo(x0, g.canvas.height); g.stroke(); g.setLineDash([]);
          st.bands.nodes.forEach(n => { const x = X(n.time); if (x == null) return; g.beginPath(); g.arc(x * hr, Y(n.mid) * vr, 3.2 * hr, 0, 7); g.fillStyle = st.c.pri; g.fill(); });
        });
      },
    };
    const view = { zOrder: () => "bottom", renderer: () => renderer };
    return { attached(p) { chart = p.chart; series = p.series; req = p.requestUpdate; }, detached() { chart = series = null; }, updateAllViews() {}, paneViews: () => [view], redraw() { req && req(); } };
  }

  const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const colors = () => ({ surf: css("--surf") || "#fff", on: css("--on") || "#000", on2: css("--on2") || "#555", line: css("--line2") || "#e3e8ef", pri: css("--pri") || "#0b57d0", l50: css("--l50") || "#d35f00", l200: css("--l200") || "#5a6578",
    gain: css("--gain") || "#0a7a3d", loss: css("--loss") || "#c42525", band50: "", band80: "" });
  function withBands(c) { const p = c.pri; c.band80 = `color-mix(in srgb, ${p} 13%, transparent)`; c.band50 = `color-mix(in srgb, ${p} 30%, transparent)`; return c; }

  const jget = async (url, init) => { const r = await fetch(url, init); if (r.status === 401) { location.href = "/login"; throw new Error("401"); } if (!r.ok) { const e = new Error("HTTP " + r.status); e.status = r.status; throw e; } return r.json(); };
  const jsonOrNull = async url => { try { return await jget(url); } catch (e) { return e.status === 404 ? null : { failed: true }; } };

  function mount(rootEl, ctx) {
    if (!rootEl) return null;
    const host = rootEl.matches?.("[data-sk-root]") ? rootEl : rootEl.querySelector("[data-sk-root]");
    if (!host) return null;
    if (host.__sk) { if (host.__sk.sym === ctx.symbol && host.__sk.lang === (ctx.lang || "en")) return host.__sk; host.__sk.destroy(); }
    const sym = ctx.symbol, exch = ctx.exchange || "NSE", $ = s => host.querySelector(s), $$ = s => [...host.querySelectorAll(s)];
    const S = { lang: ctx.lang || "en", chartData: null, facts: null, call: null, quote: null, refreshing: false, range: LS.get("sk-range", "1Y"), layers: Object.assign({ vol: true, a50: true, a200: true, band: true, levels: true, trades: true, calls: true }, LS.get("sk-layers", {})), dead: false, job: null };
    const cleanups = [], T = k => wd(S.lang, k);
    let chart = null, series = {}, prim = null, priceLines = [], cvEl = $("[data-sk-cv]"), pending = 0, lastSeries = null;
    const state = { bands: null, show: true, c: withBands(colors()) };

    /* ----- chart ----- */
    function applyTheme() {
      state.c = withBands(colors()); if (!chart) return;
      chart.applyOptions({ layout: { background: { type: "solid", color: state.c.surf }, textColor: state.c.on2, fontFamily: getComputedStyle(document.body).fontFamily }, grid: { vertLines: { visible: false }, horzLines: { color: state.c.line } }, crosshair: { vertLine: { color: state.c.on2, labelBackgroundColor: state.c.on2 }, horzLine: { color: state.c.on2, labelBackgroundColor: state.c.on2 } }, leftPriceScale: { borderColor: state.c.line }, timeScale: { borderColor: state.c.line } });
      series.line50?.applyOptions({ color: state.c.l50 }); series.line200?.applyOptions({ color: state.c.l200 });
      series.candle?.applyOptions({ upColor: state.c.gain, downColor: state.c.loss, wickUpColor: state.c.gain, wickDownColor: state.c.loss, borderVisible: false });
      prim?.redraw();
    }
    function buildChart() {
      if (!window.LightweightCharts) { cvEl.innerHTML = `<p class="muted sk-note">${esc(T("skNoLib"))}</p>`; return; }
      cvEl.innerHTML = "";
      const LW = window.LightweightCharts, s = seriesOf(S.chartData), dates = S.chartData.dates;
      chart = LW.createChart(cvEl, { width: cvEl.clientWidth, height: cvEl.clientHeight, autoSize: false, rightPriceScale: { visible: false }, leftPriceScale: { visible: true, scaleMargins: { top: 0.06, bottom: 0.2 } },
        timeScale: { rightOffset: 1, minBarSpacing: 0.02, fixLeftEdge: false, timeVisible: false }, crosshair: { mode: LW.CrosshairMode.Normal },
        handleScale: { mouseWheel: false, pinch: true, axisPressedMouseMove: true, axisDoubleClickReset: false }, handleScroll: { mouseWheel: false, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false }, localization: { priceFormatter: p => Number(p).toLocaleString("en-IN", { maximumFractionDigits: 2 }) } });
      series.candle = chart.addCandlestickSeries({ priceScaleId: "left", priceLineVisible: false, lastValueVisible: true });
      series.vol = chart.addHistogramSeries({ priceScaleId: "vol", priceFormat: { type: "volume" }, lastValueVisible: false, priceLineVisible: false });
      chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
      series.line50 = chart.addLineSeries({ priceScaleId: "left", lineWidth: 2, color: state.c.l50, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
      series.line200 = chart.addLineSeries({ priceScaleId: "left", lineWidth: 2, lineStyle: 2, color: state.c.l200, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
      series.vol.setData(s.volume); series.line50.setData(s.dma50); series.line200.setData(s.dma200);
      const last = dates[dates.length - 1], close = s.candles.length ? s.candles[s.candles.length - 1].close : null;
      state.bands = bandsOf(S.call, last, close);
      series.candle.setData(s.candles.concat(state.bands ? state.bands.points.slice(1).map(p => ({ time: p.time })) : []));
      prim = bandPrimitive(() => state); series.candle.attachPrimitive(prim);
      lastSeries = s; applyTheme(); applyLayers(); setRange(S.range, true);
      chart.subscribeCrosshairMove(onMove);
      const ro = new ResizeObserver(() => { if (chart && cvEl.clientWidth) chart.applyOptions({ width: cvEl.clientWidth, height: cvEl.clientHeight }); }); ro.observe(cvEl); cleanups.push(() => ro.disconnect());
      showReadout(null); legend();
    }
    function applyLayers() {
      if (!chart) return; const L = S.layers;
      series.vol.applyOptions({ visible: !!L.vol }); series.line50.applyOptions({ visible: !!L.a50 }); series.line200.applyOptions({ visible: !!L.a200 });
      state.show = !!L.band; prim?.redraw();
      priceLines.forEach(l => series.candle.removePriceLine(l)); priceLines = [];
      if (L.levels) (S.call?.form?.what_would_change || []).forEach(c => { if (num(c.level)) priceLines.push(series.candle.createPriceLine({ price: c.level, color: state.c.on2, lineWidth: 1, lineStyle: 3, axisLabelVisible: true, title: "" })); });
      const ev = typeof ctx.events === "function" ? ctx.events() || [] : [];
      const mk = markersOf(ev.filter(e => (e.kind === "call" ? L.calls : L.trades)), S.chartData.dates, S.lang);
      series.candle.setMarkers(mk); S.markerCount = mk.length;
      $$("[data-sk-layer]").forEach(i => { i.checked = !!L[i.dataset.skLayer]; });
      legend();
    }
    function legend() {
      const L = S.layers, el = $("[data-sk-legend]"); if (!el) return;
      const i = (cls, style, t) => `<span><i class="${cls}" style="${style}"></i>${esc(T(t))}</span>`;
      el.innerHTML = i("ln", `border-color:${state.c.pri}`, "skLgPrice") + (L.a50 ? i("ln", `border-color:${state.c.l50}`, "skLg50") : "") + (L.a200 ? i("ln dash", `border-color:${state.c.l200}`, "skLg200") : "") + (L.vol ? i("bx", "background:var(--on2);opacity:.4", "skLgVol") : "")
        + (state.bands && L.band ? i("ln dash", `border-color:${state.c.pri}`, "skLgMid") + i("bx", `background:${state.c.band50}`, "skLg50b") + i("bx", `background:${state.c.band80}`, "skLg80b") : "")
        + (L.trades && S.markerCount ? i("dot", "background:#1fa463", "skLgBuy") + i("dot", "background:#e5484d", "skLgSell") : "") + (L.calls && S.markerCount ? i("dot", "background:#7d8aa3", "skLgCall") : "");
    }
    function setRange(key, quiet) {
      if (!chart || !S.chartData) return; S.range = key; if (!quiet) LS.set("sk-range", key);
      const dates = S.chartData.dates, from = rangeStart(key, dates), to = state.bands ? state.bands.points[state.bands.points.length - 1].time : dates[dates.length - 1];
      chart.timeScale().setVisibleRange({ from, to }); markRange();
    }
    const markRange = () => $$("[data-sk-range]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.skRange === S.range)));
    function zoom(k, cx) {
      if (!chart) return; const ts = chart.timeScale(), r = ts.getVisibleLogicalRange(); if (!r) return;
      const mid = cx != null ? (ts.coordinateToLogical(cx) ?? (r.from + r.to) / 2) : (r.from + r.to) / 2;
      const from = mid - (mid - r.from) * k, to = mid + (r.to - mid) * k; if (to - from < 8) return;
      ts.setVisibleLogicalRange({ from, to }); S.range = null; markRange();
    }
    function onWheel(e) { if (!(e.ctrlKey || e.metaKey)) return; e.preventDefault(); zoom(e.deltaY > 0 ? 1.15 : 0.87, e.clientX - cvEl.getBoundingClientRect().left); }
    cvEl.addEventListener("wheel", onWheel, { passive: false }); cleanups.push(() => cvEl.removeEventListener("wheel", onWheel));
    function showReadout(p) {
      const el = $("[data-sk-readout]"); if (!el || !lastSeries) return;
      const sc = p && p.seriesData && p.seriesData.get(series.candle), t = p && p.time;
      let h = "";
      if (t && state.bands && t > S.chartData.dates[S.chartData.dates.length - 1]) {
        const b = state.bands.points.find(x => x.time === t);
        if (b) h = `<b>${esc(dmyy(t))}</b> ${esc(T("skAhead"))}: ${esc(T("skLikely"))} <b class="num">${px(b.mid)}</b> · ${esc(T("skRange50"))} <span class="num">${px(b.lo50)}–${px(b.hi50)}</span> · ${esc(T("skRange80"))} <span class="num">${px(b.lo80)}–${px(b.hi80)}</span>`;
      } else {
        const d = sc || lastSeries.candles[lastSeries.candles.length - 1], tt = t || d?.time; if (!d) return;
        const v = (p && p.seriesData.get(series.vol)) || lastSeries.volume.find(x => x.time === tt), a = (p && p.seriesData.get(series.line50)) || lastSeries.dma50.find(x => x.time === tt), b = (p && p.seriesData.get(series.line200)) || lastSeries.dma200.find(x => x.time === tt);
        h = `<b>${esc(dmyy(tt))}</b> ${esc(T("skOpen"))} <span class="num">${px(d.open)}</span> ${esc(T("skHigh"))} <span class="num">${px(d.high)}</span> ${esc(T("skLow"))} <span class="num">${px(d.low)}</span> ${esc(T("skClose"))} <b class="num">${px(d.close)}</b><span class="xtra">${v ? ` · ${esc(T("skVolume"))} <span class="num">${Number(v.value).toLocaleString("en-IN")}</span>` : ""}${a ? ` · ${esc(T("skAvg50"))} <span class="num">${px(a.value)}</span>` : ""}${b ? ` · ${esc(T("skAvg200"))} <span class="num">${px(b.value)}</span>` : ""}</span>`;
      }
      el.innerHTML = h;
    }
    const onMove = p => showReadout(p && p.time ? p : null);

    /* ----- header, stale band, forecast ----- */
    function paintHeader() {
      const q = S.quote, f = S.facts && !S.facts.failed ? S.facts : null, price = q?.price ?? f?.today?.last ?? ctx.price;
      const pxEl = $("[data-sk-px]"); if (pxEl && num(price)) pxEl.textContent = px(price);
      const day = q && num(q.prev_close) ? (q.price / q.prev_close - 1) * 100 : f?.today?.day_change_pct;
      const lab = root.SPLive && q ? root.SPLive.priceLabel(q, S.refreshing) : (q ? "" : (ctx.priceNote || ""));
      const pl = $("[data-sk-pl]"); if (pl) pl.innerHTML = `${num(day) ? `<span class="num ${day >= 0 ? "up" : "dn"}">${spc(day, 2)} ${esc(T("skToday").toLowerCase())}</span>` : ""}${lab ? ` <span>· ${esc(lab)}</span>` : ""}`;
      const sub = $("[data-sk-sub]"); if (sub && f) sub.textContent = `${sym}${f.sector ? " · " + f.sector : ""}${f.exchange || ctx.exchange ? " · " + (f.exchange || ctx.exchange) : ""}`;
      const chips = $("[data-sk-chips]"); if (chips) { const c = S.call?.call; chips.innerHTML = (ctx.tagsHtml || "") + (c ? `<span class="chip ${CALLCLASS[c] || "v-none"}">${esc(T("skCall" + (c === "hold" ? "Hold" : c === "buy" ? "Buy" : c === "sell" ? "Sell" : "Wait")))}</span>` : (ctx.chipHtml || `<span class="chip v-none">${esc(T("skCallNone"))}</span>`)); }
    }
    function paintBand() {
      const el = $("[data-sk-band]"), c = (S.changes || [])[0]; if (!el) return;
      el.innerHTML = c && root.SPLive ? root.SPLive.changeBandHtml(c, S.lang) : "";
    }
    const staleHtml = v => v && v.stale ? `<div class="sk-ood" role="status"><span class="ms" aria-hidden="true">info</span><span class="chip amber">${esc(T("skStaleChip"))}</span><span class="sk-oodt">${esc(T("skStaleText"))}</span><button class="sk-btn sk-tonal" data-sk-update ${S.job && S.job.status !== "failed" ? "disabled" : ""}>${esc(T("skUpdate"))}</button></div>` : "";
    const parts = (v, lang) => v.parts.map(p => {
      const title = esc(wd(lang, p.title));
      if (p.items) {
        if (!p.items.length) return "";
        const li = p.items.map(i => {
          if (p.key === "news") return `<li>${esc(wd(lang, "skNewsLine", wd(lang, i.effect === "helps" ? "skHelpsV" : i.effect === "hurts" ? "skHurtsV" : "skNeutralV"), wd(lang, "sk" + String(i.size || "small")[0].toUpperCase() + String(i.size || "small").slice(1))))}</li>`;
          if (p.key === "for" || p.key === "against") { const w = Number(i.weight) || 0; return `<li class="sk-w"><span class="k">${esc(i.text)}${i.en ? enTag(lang) : ""}</span><b class="num ${p.key === "for" ? "up" : "dn"}">${p.key === "for" ? "▲ +" : "▼ −"}${Math.abs(w)}</b></li>`; }
          if (p.key === "change") return `<li class="sk-w"><span class="k">${esc(i.text)}${i.en ? enTag(lang) : ""}</span>${num(i.level) ? `<b class="num">${esc(px(i.level))}</b>` : ""}</li>`;
          return `<li>${esc(i.text)}${i.en ? enTag(lang) : ""}</li>`;
        }).join("");
        return `<div class="sk-part" data-part="${p.key}"><h4>${title}</h4><ul>${li}</ul></div>`;
      }
      return p.text ? `<div class="sk-part" data-part="${p.key}"><h4>${title}</h4><p>${esc(p.text)}${p.en ? enTag(lang) : ""}</p></div>` : "";
    }).join("");
    function paintForecast() {
      const el = $("[data-sk-fc]"); if (!el) return; const lang = S.lang, v = formView(S.call, lang);
      const an = host.querySelector("[data-sk-analyse]"); if (an) { const busy = S.job && S.job.status !== "failed"; an.disabled = !!busy; const l = an.querySelector("[data-sk-an-l]"); if (l) l.textContent = T(S.call ? "skAnalyseAgain" : "skAnalyse"); }
      const jobHtml = S.job ? `<div class="sk-job" data-state="${esc(S.job.status)}">${S.job.html}</div>` : "";
      if (!v) { el.innerHTML = `<div class="sk-nofc"><div><h4>${esc(T("skNoFc"))}</h4><p>${esc(T("skNoFcP"))}</p></div></div>${jobHtml}`; return; }
      const b = state.bands, cl = word => esc(wd(lang, word)), callWord = wd(lang, { buy: "skCallBuy", hold: "skCallHold", sell: "skCallSell" }[v.call] || "skCallWait");
      const rangeRow = (k, n) => `<div class="sk-row"><span class="k">${cl(k)}</span><b class="num">${esc(wd(lang, "skRangeS", px(n.lo50), px(n.hi50)))}</b><small>${esc(wd(lang, "skRangeW", px(n.lo80), px(n.hi80)))}</small></div>`;
      const say = v.bengaliSummary || (v.chance6 != null ? wd(lang, "skCallLine", callWord, v.chance6, v.chance3 ?? "–") : "");
      el.innerHTML = `${staleHtml(v)}<p class="sk-view">${esc(say)}</p>
        <div class="sk-fc2"><div class="sk-fcl"><span class="sk-sl">${cl("skChance6")}</span><div class="sk-chance"><span class="bigp num">${v.chance6 ?? "–"}%</span><div class="sk-cbar" role="img" aria-label="${v.chance6 ?? 0}%"><span style="width:${Math.max(0, Math.min(100, v.chance6 || 0))}%"></span><i></i></div></div>
          <span class="sk-sm muted">${cl("skChance3")}: <b class="num">${v.chance3 ?? "–"}%</b> · ${cl("skConf")}: <b>${cl("skConf" + String(v.confidence || "medium")[0].toUpperCase() + String(v.confidence || "medium").slice(1))}</b></span>
          <span class="sk-sm muted">${cl("skRoute")}: ${cl(v.route === "news" || v.newsBuy ? "skRouteNews" : "skRouteCode")}${v.asOf ? ` · ${cl("skAsOf")} ${esc(dmyy(v.asOf))}` : ""}</span></div>
          <div class="sk-fcr"><span class="sk-sl">${cl("skRangeH")}</span>${b ? b.nodes.slice().reverse().map(n => rangeRow({ "1m": "skR1", "3m": "skR3", "6m": "skR6" }[n.key], n)).join("") : ""}</div></div>
        ${jobHtml}
        <div class="sk-parts">${parts(v, lang)}</div>`;
    }

    /* ----- jobs: Analyse any stock, Update forecast ----- */
    async function startJob(kind) {
      const payload = kind === "refresh_call" ? { symbol: sym, exchange: exch, reason: "owner or father pressed Update forecast" } : { symbol: sym, exchange: exch };
      S.job = { status: "queued", html: `<p class="sk-jobp">${esc(T("skJobStarted"))}</p>` }; paintForecast();
      try { const r = await jget("/api/v2/jobs", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ kind, payload }) }); pollJob(r.id); }
      catch (e) { S.job = { status: "failed", html: `<p class="job-err">${esc(T("skJobFail"))}</p><button class="sk-btn" data-sk-analyse>${esc(T("skRetry"))}</button>` }; paintForecast(); }
    }
    async function pollJob(id) {
      if (S.dead) return;
      if (document.hidden) { const f = () => { if (!document.hidden) { document.removeEventListener("visibilitychange", f); pollJob(id); } }; document.addEventListener("visibilitychange", f); return; }
      let r = null; try { r = await jget("/api/v2/jobs/" + encodeURIComponent(id)); } catch (e) { /* try again next tick */ }
      if (S.dead) return;
      if (r) {
        const st = r.job.status, lines = (r.lines || []).slice().sort((a, b) => a.seq - b.seq).map(l => `<li data-state="${esc(l.state)}">${esc(S.lang === "bn" && l.text_bn ? l.text_bn : l.text)}</li>`).join("");
        if (st === "done") { S.job = null; await loadCall(); redrawAll(); return; }
        if (st === "failed") { S.job = { status: "failed", html: `<p class="job-err">${esc(S.lang === "bn" && r.job.error_bn ? r.job.error_bn : r.job.error || T("skJobFail"))}</p><button class="sk-btn" data-sk-analyse>${esc(T("skRetry"))}</button>` }; paintForecast(); return; }
        S.job = { status: st, html: `<p class="sk-jobp">${esc(T("skJobWorking"))}</p><ul class="sk-lines">${lines}</ul>` }; paintForecast();
      }
      setTimeout(() => pollJob(id), 3000);
    }

    /* ----- loading ----- */
    async function loadCall() { try { const r = await jget("/api/v2/calls/" + encodeURIComponent(sym)); S.call = r.call || null; S.changes = (r.changes || []).filter(c => !c.seen_at); } catch (e) { S.call = null; S.changes = []; } }
    function redrawAll() { if (chart) { chart.remove(); chart = null; series = {}; priceLines = []; } if (S.chartData) buildChart(); paintHeader(); paintBand(); paintForecast(); }
    function chartMessage(h) { cvEl.innerHTML = `<div class="sk-note">${h}</div>`; }
    function loadAll() {
      const chartP = jsonOrNull(`chart/${encodeURIComponent(sym)}.json`), factsP = jsonOrNull(`stock/${encodeURIComponent(sym)}.json`), callP = loadCall();
      const quoteP = jget("/api/v2/quotes?symbols=" + encodeURIComponent(sym)).then(r => (r.quotes || [])[0] || null).catch(() => null);
      Promise.all([chartP, factsP, callP]).then(([c, f]) => {
        if (S.dead) return; S.facts = f;
        const fEl = $("[data-sk-facts]"); if (fEl) fEl.innerHTML = f && f.failed ? `<p class="muted sk-note">${esc(T("skFactsFail"))} <button class="sk-btn" data-sk-retry>${esc(T("skRetry"))}</button></p>` : factsHTML(factGroups(f, S.lang), S.lang, false);
        if (c && c.failed) chartMessage(`<p>${esc(T("skChartFail"))}</p><button class="sk-btn" data-sk-retry>${esc(T("skRetry"))}</button>`);
        else if (!c || !c.dates || c.dates.length < 2) chartMessage(`<p><b>${esc(T("skNoChart"))}</b></p><p class="muted">${esc(T("skNoChartP"))}</p>`);
        else { S.chartData = c; buildChart(); }
        paintHeader(); paintBand(); paintForecast();
        if (S.changes && S.changes.length) fetch("/api/v2/changes/seen", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ symbol: sym }) }).catch(() => {});
      });
      S.refreshing = true; quoteP.then(q => { if (S.dead) return; S.quote = q; paintHeader();
        return jget("/api/v2/quotes?symbols=" + encodeURIComponent(sym) + "&refresh=1").then(r => (r.quotes || [])[0] || q).catch(() => q).then(q2 => { S.refreshing = false; if (!S.dead) { S.quote = q2; paintHeader(); } }); });
    }

    /* ----- events ----- */
    function full(on) { const box = $(".sk-chart"); on = on ?? !box.classList.contains("is-full"); box.classList.toggle("is-full", on); document.documentElement.classList.toggle("sk-noscroll", on); const b = $("[data-sk-full]"); if (b) b.innerHTML = `<span class="ms">${on ? "close_fullscreen" : "open_in_full"}</span><span class="sk-fl">${esc(T(on ? "skFullClose" : "skFull"))}</span>`; requestAnimationFrame(() => { if (chart) { chart.applyOptions({ width: cvEl.clientWidth, height: cvEl.clientHeight }); setRange(S.range || "1Y", true); } }); }
    function onClick(e) {
      const t = e.target.closest("button,input"); if (!t || !host.contains(t)) { closeMenu(e); return; }
      if (t.dataset.skRange) return setRange(t.dataset.skRange);
      if (t.dataset.skZoom) return zoom(t.dataset.skZoom === "in" ? 0.7 : 1.4);
      if ("skReset" in t.dataset) return setRange(LS.get("sk-range", "1Y") || "1Y");
      if ("skLayers" in t.dataset) { const m = $("[data-sk-menu]"); m.hidden = !m.hidden; t.setAttribute("aria-expanded", String(!m.hidden)); return; }
      if (t.dataset.skLayer) { S.layers[t.dataset.skLayer] = t.checked; LS.set("sk-layers", S.layers); return applyLayers(); }
      if ("skFull" in t.dataset) return full();
      if ("skAnalyse" in t.dataset) return startJob("analyse");
      if ("skUpdate" in t.dataset) return startJob("refresh_call");
      if ("skRetry" in t.dataset) { STK_RELOAD(); }
    }
    function closeMenu(e) { const m = $("[data-sk-menu]"); if (m && !m.hidden && !e.target.closest?.(".sk-lyr")) { m.hidden = true; $("[data-sk-layers]")?.setAttribute("aria-expanded", "false"); } }
    const STK_RELOAD = () => { cvEl.innerHTML = `<div class="sk-skel"></div>`; loadAll(); };
    host.addEventListener("click", onClick); cleanups.push(() => host.removeEventListener("click", onClick));
    const onDoc = e => { if (!host.isConnected) return; closeMenu(e); };
    document.addEventListener("click", onDoc); cleanups.push(() => document.removeEventListener("click", onDoc));
    const onKey = e => { if (e.key === "Escape" && $(".sk-chart")?.classList.contains("is-full")) full(false); };
    document.addEventListener("keydown", onKey); cleanups.push(() => document.removeEventListener("keydown", onKey));
    const mo = new MutationObserver(() => applyTheme()); mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] }); cleanups.push(() => mo.disconnect());
    const mq = matchMedia("(prefers-color-scheme: dark)"), onMq = () => applyTheme(); mq.addEventListener?.("change", onMq); cleanups.push(() => mq.removeEventListener?.("change", onMq));
    const qT = setInterval(() => { if (document.hidden || S.dead) return; S.refreshing = true; jget("/api/v2/quotes?symbols=" + encodeURIComponent(sym) + "&refresh=1").then(r => { S.quote = (r.quotes || [])[0] || S.quote; }).catch(() => {}).then(() => { S.refreshing = false; paintHeader(); }); }, 5 * 60 * 1000);
    cleanups.push(() => clearInterval(qT));

    markRange(); $$("[data-sk-layer]").forEach(i => { i.checked = !!S.layers[i.dataset.skLayer]; });
    const api = { destroy() { S.dead = true; document.documentElement.classList.remove("sk-noscroll"); cleanups.splice(0).forEach(f => f()); if (chart) { chart.remove(); chart = null; } delete host.__sk; }, sym, lang: S.lang, state: S, setLang(l) { S.lang = l; }, full, setRange };
    host.__sk = api; loadAll(); return api;
  }

  API.html = html; API.mount = mount; API.factsHTML = factsHTML;
})(typeof window !== "undefined" ? window : globalThis);
