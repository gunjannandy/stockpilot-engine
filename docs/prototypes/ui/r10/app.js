/* stockpilot dashboard, round 8. Reads data/<name>.json (what `sp build-site` writes) and posts every edit to /api/queue.
   Plain JS, no build step. One page scroll: every tab and every stock is its own page. Anything marked TODO(backend)
   is worked out here only until site.py ships it. */
(() => {
"use strict";
const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const store = {
  get(k, d) { try { const v = localStorage.getItem("sp-" + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem("sp-" + k, JSON.stringify(v)); } catch {} },
};
const root = document.documentElement;
const LIVE = !!document.querySelector('meta[name="sp-live"]');   // the real site sets it; the prototype artifact does not
const vt = fn => fn();
const TABS = ["today", "calls", "follow", "watchlist", "ideas", "portfolio", "market", "record", "settings", "feedback", "health", "stock"];
const S = { lang: store.get("lang", "en"), tab: "today", sym: store.get("sym", null), back: "today", chip: {}, q: "", sort: {}, open: new Set(), more: new Set(), addMode: false, scroll: {}, sub: {} };

/* ---------- words: plain English, and Kolkata Bengali that keeps English words in English ---------- */
const W = {
en: {
  today: "Today", followS: "Following", marketS: "Market", recordS: "Record", follow: "Worth following", watchlist: "Watchlist", ideas: "Ideas", portfolio: "Portfolio", market: "Market & news", record: "Our record", feedback: "Feedback", health: "Health", moreNav: "More",
  search: "Search any stock", searchAdd: "Type a stock to add to the watchlist", recent: "Recent", noMatch: "No stock matches that.",
  sell: "Sell", weak: "Weak", hold: "Hold", watch: "Watch", buy: "Buy", trim: "Trim", none: "No view yet",
  head: (s, w, b) => [s && `${s} of your stocks look like sells`, w && `${w} look weak`].filter(Boolean).join(" and ") + (s || w ? ". " : "") + (b ? `${b} to buy tonight.` : "Nothing new to buy tonight."),
  tLeft: "Left to invest this month", tLeftS: (t) => `of ${t} for the month`, tRise: "Stocks going up", tRiseS: "of all stocks are above their 10-month average price",
  tNifty: "Nifty direction", up: "Rising", down: "Falling", tNiftyS: u => u ? "It is above its 10-month average price" : "It is below its 10-month average price",
  tLevel: "Is the market cheap?", tLevelS: p => `Cheaper than ${p}% of days in the last 10 years`, tLevelD: p => `Dearer than ${p}% of days in the last 10 years`, cheapW: "Cheap", fairW: "Fair", dearW: "Dear",
  tPort: "Your portfolio", tPortS: n => `${n} holdings`,
  secSell: "Sell", secSellP: "We think these will do worse than the Nifty, or the reason to own them has gone.",
  secWeak: "Weak", secWeakP: "Our forecast is low, but nothing has broken. Worth a look; no hurry.",
  secKeep: "Fine, keep", secKeepP: "Nothing to do.",
  secNear: "Close to a buy", secNearP: "Stocks you do not own whose chance is near the buy line. All of them are on the Worth following page.",
  secOdd: "Unusual today", secOddP: "Something out of the ordinary happened in these watchlist stocks today. This is not a forecast.",
  showAll: n => `Show all ${n}`, showLess: "Show fewer", seeAll: "See all",
  why: "Why", whatWrong: "What could go wrong", money: "If you act", chance: "Chance it beats the Nifty",
  chanceL: p => `${p} chance it does better than the Nifty over the next few months.`, similar: (p, n) => `Stocks like this in the past: ${p} did better${n ? ` (${n} cases)` : ""}.`,
  second: p => `A second check, done separately, says ${p}.`, sellBelow: "Sell below 40%", even: "Even", buyAbove: "Buy above 57%",
  callSell: (q, v) => `Our call: sell ${q} shares, about ${v}.`, callHold: "Our call: keep it.", callWatch: "Not a buy yet.",
  taxL: "Tax", wouldBuy: "We would buy if", fallTo: "Sell at once if it falls to", riseTo: "It could rise to", newsL: "In the news",
  youHold: (q, v, g) => `You hold ${q} shares, worth ${v} (${g}).`, youHoldT: "You hold it", inWl: "In watchlist", addWl: "Add to watchlist", remWl: "Remove from watchlist", snooze: "Hide for 30 days", dismiss: "Never show again",
  noView: "No forecast yet", noViewL: "Our analyst has not looked at this stock. Ask, and a forecast appears here in about 15 minutes. Up to 5 a day.", ask: "Ask the analyst",
  ourView: "Our view", whySell: "Why sell", price6: "Price, last 6 months", price1y: "Nifty, last 1 year (through the Nifty BeES fund)", price: "Price", a50: "2-month average", a200: "10-month average", target: "Could rise to", stop: "Sell if it falls to", now: "Now",
  facts: "The numbers, in plain words", compare: "Against its sector", back: "Back",
  fPe: "Price for ₹1 of yearly profit", fPeS: (m, l, h) => `Similar companies: ₹${m} (from ₹${l} to ₹${h}). Lower is cheaper.`, fRoe: "Profit on the owners' money", fRoeS: "15% or more a year is good.",
  fDe: "Borrowing for each ₹1 the owners put in", fDeS: "Under ₹1 is comfortable.", fGr: "Profit growth, last 3 years", fR12: "Price change, last 1 year",
  f200: "Price against its 10-month average", f200S: "Below means the price has been falling for months.", fVol: "How much the price swings", fVolS: "Above 40% a year is bumpy.",
  fDd: "Biggest fall in the last year", fAdv: "Traded each day", fAdvS: v => v > 10 ? "Easy to buy and sell." : "Thin trading; large orders can move the price.", aYear: "a year", below: "below", above: "above",
  rq: p => `A better business than ${p}% of its sector`, rv: p => `Cheaper than ${p}% of its sector`, rm: p => `Price rising faster than ${p}% of its sector`, rr: p => `Steadier than ${p}% of its sector`,
  rankHow: "Every evening we compare about 1,600 stocks with others in the same business on four things: how good the business is, how cheap it is, how strongly its price is rising, and how steady it is.",
  followP: "Stocks our analyst looked at tonight that you do not own. None reached the buy line; these are the closest.",
  wlP: "The stocks you chose to watch. Our view shows where the analyst looked at one tonight.",
  ideasP: "The code's top 10 out of about 1,600 stocks tonight, and 10 that just missed. These are not forecasts until the analyst looks at them.",
  all: "All", fView: "Has our view", fHeld: "You hold", fFall: "Falling for months", fBusy: "Busy trading today", fTop: "Top 10", fNear: "Just missed", filt: "Filter by name", addStock: "Add a stock",
  cStock: "Stock", cView: "Our view", cChance: "Chance", cPrice: "Price", cTrend: "Long-term trend", cToday: "Trading today", c6: "6 months", cWhy: "Why look now", cRank: "#", cWhyR: "Why it ranks high", cIf: "Would make the list if",
  trendT: (v) => `${Math.abs(v)}% ${v < 0 ? "below" : "above"}`, normal: "Normal", usualX: x => `${x}× usual`,
  pTotal: "Value now", pGain: "Gain on what you paid", pYear: "Gains booked this year", pRoom: "Tax-free room left", pRoomS: "Long-term gains you can still book this year without tax.",
  pMix: "What you own", pMixTarget: "No target mix approved yet.", pHold: "Holdings", pOpp: "Worth a look for the portfolio", pSc: "Smallcase against your own trades", pTax: "Tax", pPack: "Download the ITR pack",
  hHolding: "Holding", hValue: "Value", hGain: "Gain", hShare: "Of portfolio", hHeld: "Tax status", lots: "Bought", lotQ: "Shares", lotC: "Cost", lotLT: "Long-term from",
  mSect: "Sectors, last 6 months", mSectS: p => `${p} of its stocks going up`, mVal: "Is the market cheap?", mValS: (v, l, h) => `The Nifty costs ₹${v} for each ₹1 of yearly profit. In 10 years it ranged from ₹${l} to ₹${h}.`, mEvents: "Coming up", mFlows: "Money from big funds",
  rOurs: "Our forecasts", rMine: "Your own trading", rClosed: "Trades closed", rWin: "Made money", rHeldW: "Winners held", rHeldL: "Losers held", rEarly: "Sold too early", rEarlyS: "of winners rose further within 3 months", rBeat: "Beat the Nifty", days: "days", rMonth: "Gains booked each month",
  hNeeds: "Needs you", hFresh: "How fresh the data is", hRuns: "Recent job runs", hProb: "Problems", hQueue: "Requests waiting", hNone: "Nothing waiting.", hJob: "Job", hStart: "Started", hTook: "Took", hStatus: "Status", min: "min",
  fbT: "Tell us what you think", fbS: "Write anything: what you want, what you like, what you do not. Every evening the app reads it and shows below what it did.", send: "Send", fbList: "What happened to your feedback", fbChanged: "Changed after feedback",
  fbSt: { applied: "Done", backlog: "Waiting for the owner", queued: "Planned", new: "New", auto: "Planned" },
  sent: "Sent. Tomorrow evening you will see what we did with it.", added: "Added to the watchlist.", removed: "Removed from the watchlist.", snoozed: "Hidden for 30 days.", dismissed: "You will not see it again.", asked: "Asked. The forecast appears here in about 15 minutes.",
  undo: "Undo", undone: "Undone.", proto: "(Prototype: nothing was sent.)", fail: "That did not go through. Please try again in a minute.",
  theme: "Light or dark", langB: "বাংলায় দেখুন", noHist: "No price history for this stock yet.", load: "Loading…", noData: "We have no numbers for this stock yet.",
  upd: "Updated", synced: "Kite synced", ago: d => d === 0 ? "today" : d === 1 ? "yesterday" : `${d} days ago`,
  in6: "in 6 months", volX: x => `Traded ${x} times its usual amount`, at200: "At its 10-month average price",
},
bn: {
  today: "আজ", followS: "নজরে", marketS: "Market", recordS: "Record", follow: "নজরে রাখার মতো", watchlist: "Watchlist", ideas: "Ideas", portfolio: "Portfolio", market: "Market ও খবর", record: "আমাদের record", feedback: "Feedback", health: "Health", moreNav: "আরও",
  search: "যেকোনো stock খুঁজুন", searchAdd: "Watchlist-এ যোগ করতে stock-এর নাম লিখুন", recent: "আগে খুঁজেছেন", noMatch: "এই নামে কোনো stock নেই।",
  sell: "Sell", weak: "Weak", hold: "Hold", watch: "Watch", buy: "Buy", trim: "Trim", none: "এখনও মত নেই",
  head: (s, w, b) => [s && `আপনার ${s}টা stock sell করার মতো`, w && `${w}টা weak`].filter(Boolean).join(", ") + (s || w ? "। " : "") + (b ? `আজ ${b}টা কেনার মতো।` : "আজ নতুন কিছু কেনার মতো নেই।"),
  tLeft: "এ মাসে invest করার বাকি", tLeftS: t => `মাসের ${t}-এর মধ্যে`, tRise: "যত stock উঠছে", tRiseS: "stock 10 মাসের গড় দামের উপরে",
  tNifty: "Nifty কোন দিকে", up: "উঠছে", down: "নামছে", tNiftyS: u => u ? "10 মাসের গড় দামের উপরে" : "10 মাসের গড় দামের নিচে",
  tLevel: "বাজার কি সস্তা?", tLevelS: p => `গত 10 বছরের ${p}% দিনের চেয়ে সস্তা`, tLevelD: p => `গত 10 বছরের ${p}% দিনের চেয়ে দামি`, cheapW: "সস্তা", fairW: "ঠিকঠাক", dearW: "দামি",
  tPort: "আপনার Portfolio", tPortS: n => `${n}টা holding`,
  secSell: "Sell", secSellP: "আমাদের মনে হচ্ছে এগুলো Nifty-র চেয়ে খারাপ করবে, বা রাখার কারণটা আর নেই।",
  secWeak: "Weak", secWeakP: "Forecast কম, কিন্তু কিছু ভাঙেনি। একবার দেখে নিন; তাড়া নেই।",
  secKeep: "ঠিক আছে, রেখে দিন", secKeepP: "কিছু করার নেই।",
  secNear: "কেনার কাছাকাছি", secNearP: "যেগুলো আপনার নেই, কিন্তু chance buy line-এর কাছে। সবগুলো 'নজরে রাখার মতো' পাতায়।",
  secOdd: "আজ অস্বাভাবিক", secOddP: "Watchlist-এর এই stock-গুলোতে আজ অন্যরকম কিছু হয়েছে। এটা forecast নয়।",
  showAll: n => `সব ${n}টা দেখুন`, showLess: "কম দেখান", seeAll: "সব দেখুন",
  why: "কেন", whatWrong: "কী ভুল হতে পারে", money: "করলে কী হবে", chance: "Nifty-কে হারানোর chance",
  chanceL: p => `সামনের কয়েক মাসে Nifty-র চেয়ে ভালো করার chance ${p}।`, similar: (p, n) => `আগে এরকম stock-এ ${p} ভালো করেছিল${n ? ` (${n} বার দেখা)` : ""}।`,
  second: p => `আলাদা করে দ্বিতীয়বার যাচাই: ${p}।`, sellBelow: "40%-এর নিচে Sell", even: "সমান", buyAbove: "57%-এর উপরে Buy",
  callSell: (q, v) => `আমাদের মত: ${q}টা share sell করুন, মোটামুটি ${v}।`, callHold: "আমাদের মত: রেখে দিন।", callWatch: "এখনও কেনার মতো নয়।",
  taxL: "Tax", wouldBuy: "কিনব যদি", fallTo: "এর নিচে নামলে সঙ্গে সঙ্গে sell", riseTo: "উঠতে পারে", newsL: "খবরে",
  youHold: (q, v, g) => `আপনার ${q}টা share আছে, দাম ${v} (${g})।`, youHoldT: "আপনার আছে", inWl: "Watchlist-এ আছে", addWl: "Watchlist-এ যোগ করুন", remWl: "Watchlist থেকে সরান", snooze: "30 দিন লুকান", dismiss: "আর দেখাবেন না",
  noView: "এখনও forecast নেই", noViewL: "Analyst এই stock এখনও দেখেনি। জিজ্ঞেস করলে মোটামুটি 15 মিনিটে forecast এখানে আসবে। দিনে 5টা পর্যন্ত।", ask: "Analyst-কে জিজ্ঞেস করুন",
  ourView: "আমাদের মত", whySell: "কেন sell", price6: "দাম, গত 6 মাস", price1y: "Nifty, গত 1 বছর (Nifty BeES fund দিয়ে)", price: "দাম", a50: "2 মাসের গড়", a200: "10 মাসের গড়", target: "উঠতে পারে", stop: "এর নিচে নামলে sell", now: "এখন",
  facts: "সংখ্যাগুলো সহজ কথায়", compare: "নিজের sector-এর তুলনায়", back: "ফিরে যান",
  fPe: "বছরের ₹1 লাভের জন্য দাম", fPeS: (m, l, h) => `একই রকম company: ₹${m} (₹${l} থেকে ₹${h})। কম মানে সস্তা।`, fRoe: "মালিকের টাকায় লাভ", fRoeS: "বছরে 15% বা বেশি ভালো।",
  fDe: "মালিকের ₹1-এ কত ধার", fDeS: "₹1-এর কম হলে চিন্তা নেই।", fGr: "লাভ বৃদ্ধি, গত 3 বছর", fR12: "দামের বদল, গত 1 বছর",
  f200: "10 মাসের গড় দামের তুলনায়", f200S: "নিচে মানে কয়েক মাস ধরে দাম পড়ছে।", fVol: "দাম কতটা ওঠানামা করে", fVolS: "বছরে 40%-এর বেশি মানে বেশ ঝাঁকুনি।",
  fDd: "গত 1 বছরে সবচেয়ে বড় পতন", fAdv: "রোজ লেনদেন", fAdvS: v => v > 10 ? "কেনাবেচা সহজ।" : "লেনদেন কম; বড় order দিলে দাম নড়ে যায়।", aYear: "বছরে", below: "নিচে", above: "উপরে",
  rq: p => `Sector-এর ${p}% company-র চেয়ে ভালো business`, rv: p => `Sector-এর ${p}%-এর চেয়ে সস্তা`, rm: p => `Sector-এর ${p}%-এর চেয়ে দ্রুত দাম বাড়ছে`, rr: p => `Sector-এর ${p}%-এর চেয়ে স্থির`,
  rankHow: "প্রতি সন্ধ্যায় প্রায় 1,600 stock-কে একই business-এর অন্যদের সঙ্গে চারটে জিনিসে মেলানো হয়: business কত ভালো, কত সস্তা, দাম কত জোরে বাড়ছে, আর কত স্থির।",
  followP: "আজ analyst যেগুলো দেখেছে আর আপনার নেই। কোনোটাই buy line ছোঁয়নি; এগুলো সবচেয়ে কাছে।",
  wlP: "আপনার বেছে নেওয়া stock। আজ analyst যেগুলো দেখেছে, সেখানে আমাদের মত আছে।",
  ideasP: "আজ প্রায় 1,600 stock থেকে code-এর সেরা 10টা, আর 10টা যেগুলো অল্পের জন্য বাদ। Analyst না দেখা পর্যন্ত এগুলো forecast নয়।",
  all: "সব", fView: "মত আছে", fHeld: "আপনার আছে", fFall: "কয়েক মাস ধরে পড়ছে", fBusy: "আজ বেশি লেনদেন", fTop: "সেরা 10", fNear: "অল্পের জন্য বাদ", filt: "নাম দিয়ে খুঁজুন", addStock: "Stock যোগ করুন",
  cStock: "Stock", cView: "আমাদের মত", cChance: "Chance", cPrice: "দাম", cTrend: "লম্বা সময়ের দিক", cToday: "আজ লেনদেন", c6: "6 মাস", cWhy: "কেন দেখবেন", cRank: "#", cWhyR: "কেন উপরে", cIf: "List-এ আসবে যদি",
  trendT: v => `${Math.abs(v)}% ${v < 0 ? "নিচে" : "উপরে"}`, normal: "স্বাভাবিক", usualX: x => `স্বাভাবিকের ${x} গুণ`,
  pTotal: "এখন দাম", pGain: "যা দিয়েছিলেন তার উপর লাভ", pYear: "এ বছর লাভ নেওয়া হয়েছে", pRoom: "Tax ছাড়া আর যত লাভ নেওয়া যায়", pRoomS: "এ বছর আর এতটা long-term লাভ tax ছাড়া নেওয়া যাবে।",
  pMix: "কী কী আছে", pMixTarget: "এখনও কোনো target mix ঠিক হয়নি।", pHold: "Holdings", pOpp: "Portfolio-র জন্য দেখার মতো", pSc: "Smallcase বনাম আপনার নিজের trade", pTax: "Tax", pPack: "ITR pack download করুন",
  hHolding: "Holding", hValue: "Value", hGain: "লাভ", hShare: "Portfolio-র", hHeld: "Tax অবস্থা", lots: "কেনা", lotQ: "Shares", lotC: "দাম", lotLT: "Long-term হবে",
  mSect: "Sector, গত 6 মাস", mSectS: p => `${p} stock উঠছে`, mVal: "বাজার কি সস্তা?", mValS: (v, l, h) => `Nifty-র দাম বছরের ₹1 লাভের জন্য ₹${v}। 10 বছরে ₹${l} থেকে ₹${h}-এর মধ্যে ছিল।`, mEvents: "সামনে", mFlows: "বড় fund-এর টাকা",
  rOurs: "আমাদের forecast", rMine: "আপনার নিজের trading", rClosed: "শেষ হওয়া trade", rWin: "লাভ হয়েছে", rHeldW: "লাভের trade রাখা", rHeldL: "লোকসানের trade রাখা", rEarly: "আগে বেচে দেওয়া", rEarlyS: "লাভের trade 3 মাসে আরও উঠেছিল", rBeat: "Nifty-কে হারিয়েছে", days: "দিন", rMonth: "প্রতি মাসে নেওয়া লাভ",
  hNeeds: "আপনার দরকার", hFresh: "Data কত নতুন", hRuns: "সাম্প্রতিক job", hProb: "সমস্যা", hQueue: "অপেক্ষায় থাকা request", hNone: "কিছু অপেক্ষায় নেই।", hJob: "Job", hStart: "শুরু", hTook: "সময়", hStatus: "অবস্থা", min: "মিনিট",
  fbT: "আপনার মত জানান", fbS: "যা খুশি লিখুন: কী চান, কী ভালো লাগে, কী লাগে না। প্রতি সন্ধ্যায় app পড়ে নিচে জানায় কী করা হল।", send: "পাঠান", fbList: "আপনার feedback-এর কী হল", fbChanged: "Feedback-এর পরে যা বদলেছে",
  fbSt: { applied: "হয়ে গেছে", backlog: "Owner-এর অপেক্ষায়", queued: "পরিকল্পনায়", new: "নতুন", auto: "পরিকল্পনায়" },
  sent: "পাঠানো হয়েছে। কাল সন্ধ্যায় দেখবেন কী করা হল।", added: "Watchlist-এ যোগ হল।", removed: "Watchlist থেকে সরানো হল।", snoozed: "30 দিনের জন্য লুকানো হল।", dismissed: "আর দেখাবে না।", asked: "জিজ্ঞেস করা হল। মোটামুটি 15 মিনিটে forecast আসবে।",
  undo: "Undo", undone: "ফেরানো হল।", proto: "(Prototype: কিছু পাঠানো হয়নি।)", fail: "হল না। এক মিনিট পরে আবার চেষ্টা করুন।",
  theme: "আলো বা অন্ধকার", langB: "Show in English", noHist: "এই stock-এর দামের ইতিহাস এখনও নেই।", load: "আসছে…", noData: "এই stock-এর সংখ্যা এখনও নেই।",
  upd: "হালনাগাদ", synced: "Kite sync", ago: d => d === 0 ? "আজ" : d === 1 ? "কাল" : `${d} দিন আগে`,
  in6: "6 মাসে", volX: x => `স্বাভাবিকের ${x} গুণ লেনদেন`, at200: "10 মাসের গড় দামে",
}};
Object.assign(W.en, {
  settings: "Settings", settingsS: "Settings", calls: "All calls",
  doWhat: "What to do", unusual: "Unusual", youHoldS: (q, g) => `you hold ${q} (${g})`, doNow: "Do something", doNowP: n => n ? "The calls that matter most today, biggest money first. Click one to see the full reasoning." : "Nothing to do today.",
  eye: "Keep an eye on", eyeP: "Not calls. Stocks that came close to a buy, or did something unusual today.",
  seeCalls: n => `See all ${n} calls`, allCallsP: "Every call from tonight's run. Click a row for the full reasoning.",
  since: d => `Since ${d}`, sNew: n => `${n} new ${n === 1 ? "call" : "calls"}`, sChanged: n => `${n} changed`, sDropped: n => `${n} dropped`, sMoved: n => `${n} forecast${n === 1 ? "" : "s"} moved 5 points or more`, sNone: "Nothing changed.",
  ageNew: "New today", ageOn: d => `On the list since ${d}`, moveSince: p => `${p} since then`,
  theMarket: "The market", yourMoney: "Your money", open: "Open",
  sell1: (q, v) => `Sell ${q} shares`, sell2: v => `about ${v}`,
  jRisk: "Risks", jChart: "Price", jNums: "Numbers", jWhy: "Why", jAct: "If you act", jHold: "Your holding", jNews: "News",
  yourHold: "Your holding", hQty: "Shares", hVal: "Worth now", hGainL: "Gain on what you paid", hShareL: "Share of portfolio", hTaxL: "Tax", moreLots: n => `${n} more purchases not shown`,
  tabHold: "Holdings", tabFunds: "Mutual funds", tabTax: "Tax", tabOurs: "Our forecasts", tabMine: "Your own trading",
  fundsP: "Mutual funds you hold. The weekly fund review ranks them against similar funds.", noFunds: "No mutual funds in your holdings.", fUnits: "Units", fCost: "Bought at",
  rCalls: "Calls made so far", rCallsS: "Not scored yet: the first results arrive about 3 months after a call.",
  setP: "The few things you can change. Everything else runs by itself.",
  setLook: "Language and look", setLang: "Language", setTheme: "Colours", themeAuto: "Auto", themeLight: "Light", themeDark: "Dark",
  setBudget: "Monthly budget", setBudgetP: "The most we suggest you put into new buys this month.", change: "Change", budgetSet: "Budget changed. It applies from the next run.",
  setHidden: "Hidden for now", setHiddenNone: "Nothing is hidden. Use the clock icon on a call to hide a stock for 30 days, or the cross to stop seeing it.",
  setLearned: "What we learned from your choices", setLearnedNone: "Nothing yet. When you remove several similar stocks for good, we show fewer like them and list it here.", forget: "Forget",
  setAlertsX: "Price alerts", setAlertsP: "A notice when a stock reaches a price you choose. Planned; not built yet.",
  setData: "Data", setDataP: "Everything refreshes by itself every evening. Use these only if a number looks old.", refreshDocs: "Refresh my documents", rerunNow: "Run tonight's analysis again", signOut: "Sign out",
  asked2: "Asked.", queued: "Sent. It runs within a few minutes.", hideSoon: "Back to normal.",
  ladder: "Where the price could go", cWhyL: "In short", snoozeShort: "Hide for 30 days", cross: "Never show this again",
});
Object.assign(W.bn, {
  settings: "Settings", settingsS: "Settings", calls: "সব call",
  doWhat: "কী করবেন", unusual: "অস্বাভাবিক", youHoldS: (q, g) => `আছে ${q}টা (${g})`, doNow: "যা করতে হবে", doNowP: n => n ? "আজ সবচেয়ে জরুরি call, বেশি টাকার আগে। পুরো কারণ দেখতে একটায় click করুন।" : "আজ কিছু করার নেই।",
  eye: "নজরে রাখুন", eyeP: "Call নয়। কেনার কাছাকাছি এসেছে বা আজ অস্বাভাবিক কিছু করেছে।",
  seeCalls: n => `সব ${n}টা call দেখুন`, allCallsP: "আজ রাতের run-এর প্রতিটা call। পুরো কারণ দেখতে row-তে click করুন।",
  since: d => `${d} থেকে`, sNew: n => `${n}টা নতুন call`, sChanged: n => `${n}টা বদলেছে`, sDropped: n => `${n}টা বাদ`, sMoved: n => `${n}টা forecast 5 পয়েন্ট বা বেশি নড়েছে`, sNone: "কিছু বদলায়নি।",
  ageNew: "আজ নতুন", ageOn: d => `${d} থেকে list-এ`, moveSince: p => `তার পর ${p}`,
  theMarket: "বাজার", yourMoney: "আপনার টাকা", open: "খুলুন",
  sell1: (q, v) => `${q}টা share sell করুন`, sell2: v => `মোটামুটি ${v}`,
  jRisk: "ঝুঁকি", jChart: "দাম", jNums: "সংখ্যা", jWhy: "কেন", jAct: "করলে", jHold: "আপনার holding", jNews: "খবর",
  yourHold: "আপনার holding", hQty: "Shares", hVal: "এখন দাম", hGainL: "যা দিয়েছিলেন তার উপর লাভ", hShareL: "Portfolio-র অংশ", hTaxL: "Tax", moreLots: n => `আরও ${n}টা কেনা দেখানো হয়নি`,
  tabHold: "Holdings", tabFunds: "Mutual fund", tabTax: "Tax", tabOurs: "আমাদের forecast", tabMine: "আপনার নিজের trading",
  fundsP: "আপনার mutual fund। সাপ্তাহিক fund review এদের একই রকম fund-এর সঙ্গে মেলায়।", noFunds: "আপনার holding-এ mutual fund নেই।", fUnits: "Units", fCost: "কেনা দাম",
  rCalls: "এ পর্যন্ত করা call", rCallsS: "এখনও নম্বর দেওয়া হয়নি: call-এর প্রায় 3 মাস পরে প্রথম ফল আসে।",
  setP: "আপনি যে কয়েকটা জিনিস বদলাতে পারেন। বাকি সব নিজে চলে।",
  setLook: "ভাষা ও চেহারা", setLang: "ভাষা", setTheme: "রং", themeAuto: "Auto", themeLight: "আলো", themeDark: "অন্ধকার",
  setBudget: "মাসের budget", setBudgetP: "এ মাসে নতুন কেনায় সবচেয়ে বেশি যত দিতে বলব।", change: "বদলান", budgetSet: "Budget বদলেছে। পরের run থেকে চলবে।",
  setHidden: "এখনকার মতো লুকানো", setHiddenNone: "কিছু লুকানো নেই। Call-এর ঘড়ি icon-এ 30 দিন লুকাতে পারেন, ক্রস-এ আর দেখবেন না।",
  setLearned: "আপনার বাছাই থেকে যা শিখেছি", setLearnedNone: "এখনও কিছু নেই। একই রকম কয়েকটা stock চিরতরে সরালে সেরকম কম দেখাব, আর এখানে লিখে রাখব।", forget: "ভুলে যান",
  setAlerts: "দামের alert", setAlertsP: "আপনার ঠিক করা দামে পৌঁছলে খবর। পরিকল্পনায় আছে; এখনও হয়নি।",
  setData: "Data", setDataP: "সব প্রতি সন্ধ্যায় নিজে হালনাগাদ হয়। কোনো সংখ্যা পুরনো লাগলে তবেই এগুলো চাপুন।", refreshDocs: "আমার document নতুন করুন", rerunNow: "আজকের analysis আবার চালান", signOut: "Sign out",
  ladder: "দাম কোথায় যেতে পারে", cWhyL: "সংক্ষেপে", snoozeShort: "30 দিন লুকান", cross: "আর দেখাবেন না",
});
const w = (k, ...a) => { const v = (W[S.lang] && W[S.lang][k]) ?? W.en[k]; return typeof v === "function" ? v(...a) : (v ?? k); };

/* ---------- format ---------- */
const inr = (v, d = 0) => v == null ? "–" : "₹" + Number(v).toLocaleString("en-IN", { maximumFractionDigits: d, minimumFractionDigits: d });
const px = v => v == null ? "–" : inr(v, v < 100 ? 2 : v < 1000 ? 1 : 0);
const pct = (v, d = 0) => v == null ? "–" : (v * 100).toFixed(d) + "%";
const spct = (v, d = 1) => v == null ? "–" : (v > 0 ? "+" : "") + (v * 100).toFixed(d) + "%";
const lakh = v => v >= 1e7 ? "₹" + (v / 1e7).toFixed(2) + " crore" : v >= 1e5 ? "₹" + (v / 1e5).toFixed(1) + " lakh" : inr(v);
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const mdate = d => { const x = new Date(String(d).slice(0, 10) + "T00:00"); return isNaN(x) ? String(d) : x.getDate() + " " + MON[x.getMonth()] + (x.getFullYear() !== 2026 ? " " + x.getFullYear() : ""); };
const clean = n => String(n || "").replace(/\s+(Limited|Ltd\.?)$/i, "");
const n0 = v => Number(v).toLocaleString("en-IN");

/* ---------- data ---------- */
const D = {};
const SIG = {};   // a fingerprint of each data file, so a tab can show a dot when its content changed since you last opened it
const fp = t => { let h = 5381; for (let i = 0; i < t.length; i++) h = ((h << 5) + h + t.charCodeAt(i)) | 0; return String(h); };
const getJSON = n => fetch(`data/${n}.json`, { cache: "no-cache" }).then(r => { if (!r.ok) throw new Error(`${n}: ${r.status}`); return r.text(); }).then(t => { SIG[n] = fp(t); return JSON.parse(t); });
const DOTS = { today: ["today", "calls", "record"], follow: ["calls"], watchlist: ["watchlist"], ideas: ["ideas"], portfolio: ["portfolio"], market: ["market"], record: ["record", "own_record"], feedback: ["feedback"], health: ["health"] };
const sigOf = t => (DOTS[t] || []).map(n => SIG[n] || "").join("|");
const seen = (t, set) => { const m = store.get("seen", {}); if (set) { m[t] = sigOf(t); store.set("seen", m); } return m[t]; };
const changed = t => { const v = seen(t); return v != null && v !== sigOf(t); };
const HIST = new Map();
const hist = sym => { if (!HIST.has(sym)) HIST.set(sym, fetch(`data/history/${encodeURIComponent(sym)}.json`).then(r => r.ok ? r.json() : null).catch(() => null)); return HIST.get(sym); };
let LOOKUP = null; const lookup = () => (LOOKUP ||= getJSON("lookup").catch(() => ({})));
let ITEMS = [], BY = new Map(), HELD = new Map(), WL = new Map(), SMAP = new Map(), ODD = [];
const VORD = { sell: 0, weak: 1, trim: 1, buy: 2, hold: 3, watch: 4, none: 5 };

// TODO(backend): calls.json should say which kind of sell a call is (decided 2026-11-23); until then read the reason text.
const sellKind = why => /broken|limit|stop/i.test(why || "") ? "sell" : "weak";
// TODO(backend): the "unusual today" signals belong in today.json.
function signals(r) {
  const s = [];
  if ((r.volume_spike || 0) >= 2) s.push(w("volX", r.volume_spike.toFixed(1)));
  if (r.dist_200dma != null && Math.abs(r.dist_200dma) < 0.015) s.push(w("at200"));
  if (r.results_date_note) s.push(r.results_date_note);
  return s;
}
function model() {
  const c = D.calls || {}, t = D.today || {};
  const cm = new Map([...(c.sells || []), ...(c.follow || []), ...(c.buys || [])].map(x => [x.symbol, x]));
  HELD = new Map((D.portfolio?.holdings || []).map(h => [h.symbol, h]));
  WL = new Map((D.watchlist?.rows || []).map(r => [r.symbol, r]));
  SMAP = new Map((D.search || []).map(s => [s.symbol, s]));
  ITEMS = [];
  const add = (arr, g) => (arr || []).forEach(x => {
    const k = cm.get(x.symbol) || {};
    ITEMS.push({ sym: x.symbol, name: clean(x.name), v: g === "sell" ? sellKind(k.why) : g, p: x.probability, br: x.base_rate, n: k.base_rate_n,
      entry: x.entry, stop: x.stop, target: x.target, stopPct: k.stop_pct, targetPct: k.target_pct, qty: x.quantity,
      summary: x.summary, summary_bn: k.summary_bn || x.skeptic?.summary_bn, why: k.why, reasons: (x.moved_by || []).map(m => m.reason), risks: x.risks || [],
      news: (x.news || []).map(n => typeof n === "string" ? "" : (n.title || n.text || "")).filter(Boolean), sk: x.skeptic || {}, tax: k.tax_line, whyToday: x.why_today, would: x.skeptic?.would_buy_if || k.would_buy_if });
  });
  add(t.buy, "buy"); add(t.sell, "sell"); add(t.watch_triggers, "watch"); add(t.not_yet, "watch"); add(t.keep, "hold");
  BY = new Map(ITEMS.map(i => [i.sym, i]));
  ODD = [...WL.values()].map(r => ({ r, sig: signals(r) })).filter(o => o.sig.length)
    .sort((a, b) => b.sig.length - a.sig.length || (b.r.volume_spike || 0) - (a.r.volume_spike || 0)).slice(0, 8);
}
const nameOf = sym => BY.get(sym)?.name || clean(WL.get(sym)?.name || HELD.get(sym)?.name || SMAP.get(sym)?.name || sym);
const say = it => (S.lang === "bn" && it.summary_bn) ? it.summary_bn : it.summary;
function whyBits(why) {   // the code's reason line, without what the chance bar already says
  if (!why) return [];
  const s = why.replace(/Its chance is \d+%, at or below the \d+% sell line\.?\s*/i, "").replace(/The reason for owning it has broken:\s*/i, "").replace(/\s*\((ST|LT)ASM Stage [IV]+\)/g, "");
  return s.split(/;\s*|\.\s+/).map(x => x.trim().replace(/\.$/, "")).filter(Boolean).map(x => x[0].toUpperCase() + x.slice(1));
}

/* ---------- charts ---------- */
const CH = new Map(); let cid = 0;
const tail = (h, n) => { const k = Math.min(n, h.close.length), o = h.close.length - k; return { d: h.dates.slice(o), c: h.close.slice(o), m50: (h.dma50 || []).slice(o), m200: (h.dma200 || []).slice(o) }; };
function priceChart(it, raw, width, days = 130, Hov) {
  const W0 = Math.max(300, Math.round(width || 600)), H = Hov || Math.round(Math.min(320, Math.max(220, W0 * .48))), h = tail(raw, days), n = h.c.length;
  const id = "c" + (cid++);
  const vals = [...h.c, ...h.m50, ...h.m200].filter(v => v != null); if (it?.stop) vals.push(it.stop); if (it?.target) vals.push(it.target);
  let lo = Math.min(...vals), hi = Math.max(...vals); const pd = (hi - lo) * .06 || 1; lo -= pd; hi += pd;
  const lvOn = !!it?.stop, L = 6, R = lvOn ? 118 : 10, T = 10, B = 24, x = i => L + (W0 - L - R) * i / (n - 1), y = v => T + (H - T - B) * (1 - (v - lo) / (hi - lo));
  const line = a => { let s = "", on = false; a.forEach((v, i) => { if (v == null) { on = false; return; } s += (on ? "L" : "M") + x(i).toFixed(1) + " " + y(v).toFixed(1); on = true; }); return s; };
  const lc = line(h.c), area = lc + `L${x(n - 1).toFixed(1)} ${H - B}L${x(0).toFixed(1)} ${H - B}Z`;
  const grid = [1, 2].map(k => lo + (hi - lo) / 3 * k).map(v => `<line class="grd" x1="${L}" x2="${W0 - R}" y1="${y(v)}" y2="${y(v)}"/><text class="ax" x="${L + 2}" y="${y(v) - 4}">${Math.round(v).toLocaleString("en-IN")}</text>`).join("");
  const xs = [0, n >> 1, n - 1].map(i => `<text class="ax" x="${x(i)}" y="${H - 6}" text-anchor="${i === 0 ? "start" : i === n - 1 ? "end" : "middle"}">${mdate(h.d[i])}</text>`).join("");
  const lv = []; if (it?.target) lv.push({ v: it.target, k: "t", l: `${w("target")} ${px(it.target)}` }); if (it?.stop) lv.push({ v: it.stop, k: "s", l: `${w("stop")} ${px(it.stop)}` });
  lv.forEach(o => o.y = y(o.v)); lv.sort((a, b) => a.y - b.y); for (let i = 1; i < lv.length; i++) if (lv[i].y - lv[i - 1].y < 30) lv[i].y = lv[i - 1].y + 30;
  const lvs = lv.map(o => { const [a, b] = o.l.split(/ (?=₹)/); return `<line class="lv ${o.k}" x1="${L}" x2="${W0 - R + 4}" y1="${y(o.v)}" y2="${y(o.v)}"/><text class="lvl ${o.k}" x="${W0 - R + 8}" y="${o.y - 2}">${esc(a)}</text><text class="lvl ${o.k}" x="${W0 - R + 8}" y="${o.y + 12}">${esc(b || "")}</text>`; }).join("");
  CH.set(id, { type: "pc", h, x, y, n, W: W0, L, R });
  return `<svg class="pc" data-id="${id}" viewBox="0 0 ${W0} ${H}" role="img" aria-label="${esc(w("price6"))}">${grid}<path class="la" d="${area}"/><path class="l200" d="${line(h.m200)}"/><path class="l50" d="${line(h.m50)}"/><path class="lc" d="${lc}"/>${lvs}${xs}<circle class="end" cx="${x(n - 1)}" cy="${y(h.c[n - 1])}" r="4.5"/><line class="xh" y1="${T}" y2="${H - B}"/><circle class="hd" r="5"/></svg>
  <div class="legend"><span><i style="border-color:var(--pri)"></i>${w("price")}</span><span><i style="border-color:var(--l50)"></i>${w("a50")}</span><span><i style="border-color:var(--l200);border-top-style:dashed"></i>${w("a200")}</span></div>`;
}
function spark(raw, W0 = 100, H = 30) {
  if (!raw) return "";
  const h = tail(raw, 130); const pts = h.c.map((v, i) => [v, i]).filter(p => p[0] != null); if (pts.length < 2) return "";
  const c = pts.map(p => p[0]), d = pts.map(p => h.d[p[1]]), n = c.length, lo = Math.min(...c), hi = Math.max(...c);
  const x = i => 2 + (W0 - 6) * i / (n - 1), y = v => 3 + (H - 6) * (1 - (v - lo) / ((hi - lo) || 1));
  const p = c.map((v, i) => (i ? "L" : "M") + x(i).toFixed(1) + " " + y(v).toFixed(1)).join(""); const id = "s" + (cid++);
  CH.set(id, { type: "sp", h: { d, c }, x, y, n, W: W0, L: 2, R: 4 });
  return `<svg class="sp ${c[n - 1] >= c[0] ? "up" : "dn"}" data-id="${id}" viewBox="0 0 ${W0} ${H}" preserveAspectRatio="none" aria-hidden="true"><path class="a" d="${p}L${x(n - 1)} ${H}L${x(0)} ${H}Z"/><path class="l" d="${p}" vector-effect="non-scaling-stroke"/><line class="xh" y1="0" y2="${H}" vector-effect="non-scaling-stroke"/></svg>`;
}
function bars(rows, width, H = 220) {   // rows: [{label, v, tip}]
  const W0 = Math.max(300, Math.round(width || 600)), n = rows.length; if (!n) return "";
  const max = Math.max(...rows.map(r => Math.abs(r.v)), 1), hasNeg = rows.some(r => r.v < 0), T = 12, B = 24, zero = hasNeg ? T + (H - T - B) / 2 : H - B, sc = (hasNeg ? (H - T - B) / 2 : H - T - B) / max;
  const bw = (W0 - 8) / n, g = Math.min(6, bw * .25);
  const r = rows.map((d, i) => { const h = Math.abs(d.v) * sc, y = d.v >= 0 ? zero - h : zero; return `<rect class="${d.v >= 0 ? "pos" : "neg"}" x="${(4 + i * bw + g / 2).toFixed(1)}" y="${y.toFixed(1)}" width="${(bw - g).toFixed(1)}" height="${Math.max(1, h).toFixed(1)}" data-tip="${esc(d.tip)}"/>`; }).join("");
  const lab = rows.map((d, i) => (i % Math.ceil(n / 8) === 0) ? `<text class="ax" x="${(4 + i * bw + bw / 2).toFixed(1)}" y="${H - 6}" text-anchor="middle">${esc(d.label)}</text>` : "").join("");
  return `<svg class="bc" viewBox="0 0 ${W0} ${H}" role="img"><line class="grd" x1="0" x2="${W0}" y1="${zero}" y2="${zero}"/>${r}${lab}</svg>`;
}
const lsp = (sym, wd = 100, ht = 30) => `<span class="lsp" data-sym="${esc(sym)}" data-w="${wd}" data-h="${ht}"></span>`;
const io = "IntersectionObserver" in window ? new IntersectionObserver(es => es.forEach(e => {
  if (!e.isIntersecting) return; const el = e.target; io.unobserve(el);
  hist(el.dataset.sym).then(h => { if (h && el.isConnected) el.outerHTML = spark(h, +el.dataset.w, +el.dataset.h); else el.style.visibility = "hidden"; });
}), { rootMargin: "300px" }) : null;
const hydrateSince = () => $$(".mv:not([data-on])").forEach(el => { el.dataset.on = 1; const [sym, d] = el.dataset.since.split("|");
  hist(sym).then(h => { if (!h || !el.isConnected) return; const i = h.dates.findIndex(x => x >= d); if (i < 0 || h.close[i] == null) return; const last = h.close[h.close.length - 1], v = last / h.close[i] - 1; el.innerHTML = `<b class="${v >= 0 ? "up" : "dn"}">${w("moveSince", spct(v))}</b>`; }); });
const hydrate = () => $$(".lsp:not([data-on])").forEach(el => { el.dataset.on = 1; io ? io.observe(el) : hist(el.dataset.sym).then(h => { if (h) el.outerHTML = spark(h, +el.dataset.w, +el.dataset.h); }); });
const P = v => Math.max(0, Math.min(100, (v - .2) / .6 * 100));
const mini = it => `<span class="mini"><span class="z" style="width:${P(.4)}%"></span><span class="z zb" style="left:${P(.57)}%"></span><span class="u" style="left:${P(it.br)}%"></span><span class="d" style="left:${P(it.p)}%"></span></span>`;
const chanceTip = it => `${w("chanceL", pct(it.p))} ${w("similar", pct(it.br), it.n ? n0(it.n) : "")}`;
const chanceCell = it => `<span class="chance" data-tip="${esc(chanceTip(it))}"><span class="p num">${pct(it.p)}</span>${mini(it)}</span>`;
const chip = v => `<span class="chip v-${v}">${w(v)}</span>`;
const bar12 = it => `<div class="cb" data-tip="${esc(chanceTip(it))}"><span class="zs" style="width:${P(.4)}%"></span><span class="zb" style="left:${P(.57)}%"></span><span class="mid" style="left:${P(.5)}%"></span><span class="us" style="left:${P(it.br)}%"></span><span class="pd" style="left:${P(it.p)}%"></span></div><div class="cbk"><span>${w("sellBelow")}</span><span>${w("even")}</span><span>${w("buyAbove")}</span></div>`;
const info = t => `<span class="ms i" data-tip="${esc(t)}" aria-label="${esc(t)}" role="img">info</span>`;

/* hover layer: chart crosshairs and data-tip */
function showTip(html, cx, cy) { const t = $("#tip"); t.innerHTML = html; t.classList.add("on"); const r = t.getBoundingClientRect(); let L = cx + 14, T = cy - r.height - 12; if (L + r.width > innerWidth - 8) L = cx - r.width - 14; if (T < 8) T = cy + 18; t.style.left = L + "px"; t.style.top = T + "px"; }
const hideTip = () => $("#tip")?.classList.remove("on");
document.addEventListener("pointermove", e => {
  const s = e.target.closest?.("svg.pc,svg.sp");
  $$("svg.on").forEach(o => { if (o !== s) o.classList.remove("on"); });
  if (s) {
    const c = CH.get(s.dataset.id); if (!c) return; const r = s.getBoundingClientRect(); const vx = (e.clientX - r.left) / r.width * c.W;
    const i = Math.max(0, Math.min(c.n - 1, Math.round((vx - c.L) / (c.W - c.L - c.R) * (c.n - 1)))); const v = c.h.c[i]; if (v == null) return;
    s.classList.add("on"); const xl = $(".xh", s); xl.setAttribute("x1", c.x(i)); xl.setAttribute("x2", c.x(i));
    const hd = $(".hd", s); if (hd) { hd.setAttribute("cx", c.x(i)); hd.setAttribute("cy", c.y(v)); }
    let html = `<div>${mdate(c.h.d[i])}</div><div>${c.lab || w("price")} <b class="num">${(c.fmt || px)(v)}</b></div>`;
    if (c.type === "pc") html += `<div>${w("a50")} <b class="num">${px(c.h.m50[i])}</b></div><div>${w("a200")} <b class="num">${px(c.h.m200[i])}</b></div>`;
    showTip(html, e.clientX, e.clientY); return;
  }
  const d = e.target.closest?.("[data-tip]"); d ? showTip(esc(d.dataset.tip), e.clientX, e.clientY) : hideTip();
}, { passive: true });
addEventListener("scroll", hideTip, { passive: true });

/* ---------- queue (the same requests the real site sends) ---------- */
function toast(text, undo) {
  const el = document.createElement("div"); el.className = "toast"; el.innerHTML = `<span>${esc(text)}</span>`;
  if (undo) { const b = document.createElement("button"); b.textContent = w("undo"); b.onclick = async () => { el.remove(); await undo(); }; el.append(b); }
  $("#toasts").append(el); setTimeout(() => el.remove(), 8000);
}
async function queue(kind, payload, done, revert) {
  if (!LIVE) { toast(`${done} ${w("proto")}`, revert && (async () => { revert(); toast(w("undone")); })); return true; }
  try {
    const r = await fetch("/api/queue", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ kind, payload }) });
    if (r.status === 401) { location.href = "/login"; return false; }
    if (!r.ok) throw new Error(String(r.status));
    const { id } = await r.json();
    toast(done, async () => { const d = await fetch(`/api/queue/${id}`, { method: "DELETE" }); if (d.ok) { revert?.(); toast(w("undone")); } else toast(w("fail")); });
    return true;
  } catch { revert?.(); toast(w("fail")); return false; }
}

/* ---------- calls: one row each; the full reasoning is on the stock page ---------- */
const stockLink = (sym, text) => `<a href="#stock" data-open="${esc(sym)}">${esc(text)}</a>`;
function moneyLines(it) {
  const out = [];
  if ((it.v === "sell" || it.v === "weak") && it.qty) out.push(`<div><span>${w("callSell", n0(it.qty), inr(it.qty * it.entry))}</span></div>`);
  else if (it.v === "hold") out.push(`<div><span>${w("callHold")}</span></div>`); else if (it.v === "watch") out.push(`<div><span>${w("callWatch")}</span></div>`);
  if (it.tax) out.push(`<div><span>${w("taxL")}: ${esc(it.tax.replace(/^Selling [\d,.]+ today: /, ""))}</span></div>`);
  if (it.target) out.push(`<div><span>${w("riseTo")}</span><b class="num up">${px(it.target)}${it.targetPct != null ? ` (+${it.targetPct}%)` : ""}</b></div>`);
  if (it.stop) out.push(`<div><span>${w("fallTo")}</span><b class="num dn">${px(it.stop)}${it.stopPct != null ? ` (${it.stopPct}%)` : ""}</b></div>`);
  if (it.v === "watch" && it.would) out.push(`<div><span>${w("wouldBuy")}: ${esc(it.would)}</span></div>`);
  return out.join("");
}
// TODO(backend): the age of a call and the previous run's forecast should come in calls.json ("since" is there but empty).
const ACT = { sell: "sell", weak: "sell", trim: "trim", buy: "buy", hold: "hold", watch: "watch" };
function callAge(it) {
  const rc = (D.record?.calls || []).filter(c => c.symbol === it.sym && c.action === ACT[it.v]);
  const dates = [...new Set(rc.map(c => c.made_on))].sort();
  return dates.length > 1 ? { first: dates[0] } : null;
}
function moneyCell(it) {
  if ((it.v === "sell" || it.v === "weak") && it.qty) return `<b class="num">${w("sell1", n0(it.qty))}</b><small class="num">${w("sell2", inr(it.qty * it.entry))}</small>`;
  if (it.v === "buy" && it.target) return `<b class="num up">${px(it.target)}</b><small>${w("riseTo")}</small>`;
  return "";
}
const rowBtns = it => `<span class="cx"><button class="icb" data-snooze="${esc(it.sym)}" data-tip="${esc(w("snoozeShort"))}" aria-label="${esc(w("snoozeShort"))}"><span class="ms">schedule</span></button><button class="icb" data-dismiss="${esc(it.sym)}" data-tip="${esc(w("cross"))}" aria-label="${esc(w("cross"))}"><span class="ms">block</span></button></span>`;
function crow(it) {
  const h = HELD.get(it.sym), age = callAge(it);
  const ageTxt = age ? `${w("ageOn", mdate(age.first))} <span class="mv" data-since="${esc(it.sym)}|${esc(age.first)}"></span>` : w("ageNew");
  return `<article class="crow state r-${it.v}" data-open="${esc(it.sym)}" tabindex="0">
   ${chip(it.v)}
   <div class="cm"><div class="cn"><b class="trunc">${esc(it.name)}</b></div>
    <div class="cw trunc">${esc(say(it))}</div><div class="ca muted trunc">${esc(it.sym)} · ${px(it.entry)}${h ? ` · ${w("youHoldS", n0(h.quantity), spct(h.gain_pct))}` : ""} · ${ageTxt}</div></div>
   <div class="hs">${lsp(it.sym, 96, 30)}</div>
   ${chanceCell(it)}
   <div class="cmn">${moneyCell(it)}</div>
   ${rowBtns(it)}</article>`;
}
function eyeRow(o) {
  const it = BY.get(o.r.symbol);
  return `<article class="crow state eye" data-open="${esc(o.r.symbol)}" tabindex="0">${it ? chip(it.v) : `<span class="chip v-none">${w("unusual")}</span>`}
   <div class="cm"><div class="cn"><b class="trunc">${esc(clean(o.r.name))}</b></div><div class="ca muted trunc">${esc(o.r.symbol)} · ${px(o.r.close)}</div><div class="signals">${o.sig.map(s => `<span class="tag">${esc(s)}</span>`).join("")}</div></div>
   <div class="hs">${lsp(o.r.symbol, 96, 30)}</div>${it ? chanceCell(it) : `<span class="muted">–</span>`}<div class="cmn"></div><span class="cx"></span></article>`;
}
function nearRow(it) {
  return `<article class="crow state eye" data-open="${esc(it.sym)}" tabindex="0">${chip(it.v)}
   <div class="cm"><div class="cn"><b class="trunc">${esc(it.name)}</b></div><div class="cw trunc">${esc(say(it))}</div><div class="ca muted trunc">${esc(it.sym)} · ${px(it.entry)}${it.would ? ` · ${w("wouldBuy")}: ${esc(it.would)}` : ""}</div></div>
   <div class="hs">${lsp(it.sym, 96, 30)}</div>${chanceCell(it)}<div class="cmn"></div>${rowBtns(it)}</article>`;
}
const crowHead = () => `<div class="crow-h" aria-hidden="true"><span></span><span>${w("cStock")}</span><span class="hs"></span><span>${w("cChance")}</span><span>${w("doWhat")}</span><span></span></div>`;

/* ---------- Today: a short triage list beside the market and the money ---------- */
const dayLine = () => { const d = new Date((D.meta?.calls_on || D.today?.as_of || "") + "T00:00"); if (isNaN(d)) return "";
  return d.toLocaleDateString(S.lang === "bn" ? "bn-IN-u-nu-latn" : "en-IN", { weekday: "long", day: "numeric", month: "long", year: "numeric" }); };
const kv = (k, v, s, cls = "") => `<div class="kv"><span class="k">${k}</span><b class="${cls}">${v}</b>${s ? `<small>${s}</small>` : ""}</div>`;
function marketPanel(self) {
  const m = D.market || {}, v = m.valuation || {}, cheapP = v.percentile != null ? 100 - v.percentile : null;
  return `<section class="panel"><h3 class="ph"><span>${w("theMarket")}</span>${self ? "" : `<a class="lk" href="#market">${w("open")}<span class="ms">chevron_right</span></a>`}</h3>
    ${kv(w("tNifty"), w(m.nifty_above_200dma ? "up" : "down"), w("tNiftyS", m.nifty_above_200dma), m.nifty_above_200dma ? "up" : "dn")}
    ${m.breadth != null ? kv(w("tRise"), pct(m.breadth), w("tRiseS")) : ""}
    ${cheapP != null ? kv(w("tLevel"), w(cheapP > 60 ? "cheapW" : cheapP < 30 ? "dearW" : "fairW"), cheapP >= 50 ? w("tLevelS", cheapP) : w("tLevelD", 100 - cheapP), cheapP > 60 ? "up" : cheapP < 30 ? "dn" : "") : ""}
   </section>`;
}
function moneyPanel() {
  const b = D.today?.budget, port = D.portfolio, t = port?.tax || {};
  return `<section class="panel"><h3 class="ph"><span>${w("yourMoney")}</span><a class="lk" href="#portfolio">${w("open")}<span class="ms">chevron_right</span></a></h3>
    ${port ? kv(w("tPort"), lakh(port.total_value), w("tPortS", port.holdings.length)) : ""}
    ${b ? kv(w("tLeft"), inr(b.left), w("tLeftS", inr(b.total))) + `<div class="meter"><i style="width:${Math.round(b.left / b.total * 100)}%"></i></div>` : ""}
    ${t.harvest_room != null ? kv(w("pRoom"), inr(t.harvest_room), w("pRoomS")) : ""}
   </section>`;
}
const sidePanel = () => `<aside class="side">${marketPanel()}${moneyPanel()}</aside>`;
// TODO(backend): "since last time" should be a field in today.json; it is worked out here from the record's last two dates.
function sinceStrip(actionable) {
  const ds = D.record?.dates || [], rc = D.record?.calls || []; if (ds.length < 2) return "";
  const prev = new Map(rc.filter(c => c.made_on === ds[1]).map(c => [c.symbol, c]));
  let nw = 0, ch = 0, mv = 0; const cur = new Set(actionable.map(i => i.sym));
  actionable.forEach(i => { const p = prev.get(i.sym); if (!p) nw++; else if (p.action !== ACT[i.v]) ch++; if (p && Math.abs((i.p || 0) - p.probability) >= .05) mv++; });
  const dr = [...prev.values()].filter(c => ["sell", "buy"].includes(c.action) && !cur.has(c.symbol)).length;
  const bits = [nw && w("sNew", nw), ch && w("sChanged", ch), dr && w("sDropped", dr), mv && w("sMoved", mv)].filter(Boolean);
  return `<div class="since"><span class="eyebrow">${w("since", mdate(ds[1]))}</span>${bits.length ? bits.map(b => `<span class="tag">${esc(b)}</span>`).join("") : `<span class="muted">${w("sNone")}</span>`}</div>`;
}
const sec2 = (t, p, n) => `<div class="secttl"><h2>${t}</h2>${n != null ? `<span class="n num">${n}</span>` : ""}</div>${p ? `<p class="muted secp">${p}</p>` : ""}`;
function pageToday() {
  const mine = ITEMS.filter(i => HELD.has(i.sym) || ["sell", "weak", "hold"].includes(i.v));
  const worth = i => (i.qty || 0) * (i.entry || 0);
  const action = mine.filter(i => i.v === "sell" || i.v === "weak").sort((a, b) => (a.v === b.v ? 0 : a.v === "sell" ? -1 : 1) || worth(b) - worth(a) || a.p - b.p);
  const buys = ITEMS.filter(i => i.v === "buy").sort((a, b) => b.p - a.p), todo = [...buys, ...action];
  const near = ITEMS.filter(i => !mine.includes(i) && i.v === "watch").sort((a, b) => b.p - a.p).slice(0, 3);
  const eye = [...near.map(nearRow), ...ODD.slice(0, 3).map(eyeRow)];
  const sells = action.filter(i => i.v === "sell").length, weaks = action.length - sells;
  return `<div class="two">
    <div class="col">
     <header class="page-h rise"><div class="eyebrow">${esc(dayLine())}</div><h1 class="disp">${esc(w("head", sells, weaks, buys.length))}</h1>
     <p>${esc(S.lang === "bn" && D.calls?.market_view_bn ? D.calls.market_view_bn : (D.today?.market_mood || ""))}</p></header>
     ${sinceStrip([...ITEMS.filter(i => ["sell", "weak", "buy", "trim"].includes(i.v))])}
     ${sec2(w("doNow"), w("doNowP", todo.length), Math.min(5, todo.length))}
     ${todo.length ? `<div class="clist">${crowHead()}${todo.slice(0, 5).map(crow).join("")}</div>` : ""}
     ${ITEMS.length > 5 || todo.length > 5 ? `<div class="more"><a class="btn t" href="#calls">${w("seeCalls", ITEMS.length)}<span class="ms">chevron_right</span></a></div>` : ""}
     ${eye.length ? sec2(w("eye"), w("eyeP")) + `<div class="clist">${eye.join("")}</div>` : ""}
    </div>${sidePanel()}</div>`;
}
function pageCalls() {
  const rows = ITEMS.map(i => ({ sym: i.sym, name: i.name, it: i }));
  return `<header class="page-h rise"><h1 class="disp">${w("calls")}</h1><p>${w("allCallsP")}</p></header>
   ${table("calls", rows, [["all", r => true], ["sell", r => r.it.v === "sell"], ["weak", r => r.it.v === "weak"], ["buy", r => r.it.v === "buy"], ["hold", r => r.it.v === "hold"], ["watch", r => r.it.v === "watch"]], [
     { l: "cStock", v: r => r.name, h: stockCell },
     { l: "cView", v: r => VORD[r.it.v], h: viewCell },
     { l: "cChance", v: r => r.it.p, h: r => chanceCell(r.it), t: w("chance") },
     { l: "cWhyL", h: r => `<span class="msg">${esc(say(r.it))}</span>`, c: "h2" },
     { l: "money", h: r => `<div class="mc">${moneyCell(r.it)}</div>`, c: "h1" },
     { l: "c6", h: r => lsp(r.sym), c: "h3" }])}`;
}

function followCard(it) {
  return `<a class="fcard state" href="#stock" data-open="${esc(it.sym)}">
   <div class="top"><div style="min-width:0"><h3 class="trunc">${esc(it.name)}</h3><div class="muted num" style="font-size:13px">${esc(it.sym)} · ${px(it.entry)}</div></div>
     <div style="text-align:right" data-tip="${esc(chanceTip(it))}"><div class="bigp num">${pct(it.p)}</div><div class="muted" style="font-size:12px">${w("chance")}</div></div></div>
   <p style="font-size:15px">${esc(say(it))}</p>
   ${lsp(it.sym, 320, 56)}
   <dl>${it.would ? `<dt>${w("wouldBuy")}</dt><dd>${esc(it.would)}</dd>` : ""}${it.target ? `<dt>${w("riseTo")}</dt><dd class="num up">${px(it.target)}${it.targetPct != null ? ` (+${it.targetPct}%)` : ""}</dd>` : ""}${it.stop ? `<dt>${w("fallTo")}</dt><dd class="num dn">${px(it.stop)}</dd>` : ""}</dl>
   <div class="muted" style="font-size:13px">${esc(w("similar", pct(it.br), it.n ? n0(it.n) : ""))}</div></a>`;
}
function pageFollow() {
  const list = ITEMS.filter(i => !HELD.has(i.sym) && i.v === "watch").sort((a, b) => b.p - a.p);
  return `<header class="page-h rise"><h1 class="disp">${w("follow")}</h1><p>${w("followP")}</p></header><div class="fcards">${list.map(followCard).join("")}</div>`;
}

/* tables with sort, chips and a name filter */
function table(key, rows, chips, cols, opts = {}) {
  const cur = S.chip[key] || "all", counts = chips.map(([k, f]) => [k, rows.filter(f).length]);
  rows = rows.filter((chips.find(c => c[0] === cur) || chips[0])[1]);
  const q = S.q.trim().toLowerCase(); if (q) rows = rows.filter(r => r.sym.toLowerCase().includes(q) || r.name.toLowerCase().includes(q));
  const so = S.sort[key]; if (so) { const col = cols[so.i]; if (col?.v) rows = [...rows].sort((a, b) => { const x = col.v(a), y = col.v(b); return (x == null) - (y == null) || (x < y ? -1 : x > y ? 1 : 0) * so.d; }); }
  return `<div class="tools">${counts.map(([k, n]) => `<button class="fchip" data-chip="${key}:${k}" aria-pressed="${cur === k}">${w(k)} <span class="num">${n}</span></button>`).join("")}
    <label class="qf"><span class="ms" style="font-size:18px">search</span><input id="qf" value="${esc(S.q)}" placeholder="${esc(w("filt"))}" autocomplete="off"></label>${opts.tools || ""}</div>
   ${rows.length ? `<table class="grid rise"><thead><tr>${cols.map((c, i) => `<th class="${c.c || ""} ${c.r ? "r" : ""}" ${so?.i === i ? `aria-sort="${so.d > 0 ? "ascending" : "descending"}"` : ""}>${c.v ? `<button data-sort="${key}:${i}">${c.l ? w(c.l) : ""}${c.t ? info(c.t) : ""}<span class="ms">${so?.i === i && so.d < 0 ? "arrow_downward" : "arrow_upward"}</span></button>` : `<button tabindex="-1" style="cursor:default">${c.l ? w(c.l) : ""}</button>`}</th>`).join("")}</tr></thead>
    <tbody>${rows.map(r => `<tr class="r" ${opts.rowAttr ? opts.rowAttr(r) : `data-open="${esc(r.sym)}"`} tabindex="0">${cols.map(c => `<td class="${c.c || ""} ${c.r ? "r" : ""}">${c.h(r)}</td>`).join("")}</tr>${opts.after ? opts.after(r) : ""}`).join("")}</tbody></table>` : `<p class="empty">${w("noMatch")}</p>`}`;
}
const stockCell = r => `<div class="nm trunc">${esc(r.name)}</div><div class="sy num trunc">${esc(r.sym)}${r.sector ? " · " + esc(r.sector) : ""}</div>`;
const viewCell = r => r.it ? chip(r.it.v) : chip("none");
function pageWatchlist() {
  const rows = [...WL.values()].map(r => ({ sym: r.symbol, name: clean(r.name), it: BY.get(r.symbol), held: HELD.has(r.symbol), w: r }));
  const t200 = v => v == null ? "–" : `<span class="num ${v >= 0 ? "up" : "dn"}">${w("trendT", Math.round(v * 100))}</span>`;
  return `<header class="page-h rise"><h1 class="disp">${w("watchlist")}</h1><p>${w("wlP")}</p></header>
   ${table("wl", rows, [["all", r => true], ["fView", r => !!r.it], ["fHeld", r => r.held], ["fFall", r => (r.w.dist_200dma ?? 0) < -0.05], ["fBusy", r => (r.w.volume_spike || 0) >= 2]], [
      { l: "cStock", v: r => r.name, h: stockCell },
      { l: "cView", v: r => r.it ? VORD[r.it.v] : 9, h: viewCell },
      { l: "cChance", v: r => r.it?.p ?? -1, h: r => r.it ? chanceCell(r.it) : `<span class="muted">–</span>`, t: w("chance") },
      { l: "cPrice", v: r => r.w.close, h: r => `<span class="num">${px(r.w.close)}</span>`, r: 1, c: "h1" },
      { l: "cTrend", v: r => r.w.dist_200dma, h: r => t200(r.w.dist_200dma), r: 1, c: "h2", t: w("f200") + ". " + w("f200S") },
      { l: "cToday", v: r => r.w.volume_spike, h: r => `<span class="num">${r.w.volume_spike == null ? "–" : r.w.volume_spike >= 1.5 ? w("usualX", r.w.volume_spike.toFixed(1)) : w("normal")}</span>`, r: 1, c: "h3" },
      { l: "c6", h: r => lsp(r.sym), c: "h2" },
      { l: "cWhy", v: r => (r.w.why || []).join(), h: r => `<div class="signals">${(r.w.why || []).filter(x => !/^Today's call/i.test(x)).slice(0, 2).map(x => `<span class="tag">${esc(x)}</span>`).join("")}</div>`, c: "h3" },
      { l: "", c: "h1", h: r => `<button class="icb rm" data-unwatch="${esc(r.sym)}" data-tip="${esc(w("remWl"))}" aria-label="${esc(w("remWl"))}"><span class="ms">close</span></button>` }],
     { tools: `<button class="btn t" data-addmode><span class="ms">add</span>${w("addStock")}</button>` })}`;
}
function rankLines(s, x) {
  const L = [["quality", "rq"], ["value", "rv"], ["momentum", "rm"], ["risk", "rr"]].map(([k, f]) => ({ k, v: s?.[k] ?? 0, t: w(f, Math.round((s?.[k] ?? 0) * 100)) })).sort((a, b) => b.v - a.v);
  return L;
}
function pageIdeas() {
  const rows = [...(D.ideas?.ranking || []), ...(D.ideas?.near_misses || [])].map(x => ({ sym: x.symbol, name: clean(x.name), sector: x.industry, x, it: BY.get(x.symbol), near: !!x.trigger }));
  return `<header class="page-h rise"><h1 class="disp">${w("ideas")}</h1><p>${w("ideasP")}</p><p>${w("rankHow")}</p></header>
   ${table("ideas", rows, [["all", r => true], ["fTop", r => !r.near], ["fNear", r => r.near]], [
      { l: "cRank", v: r => r.x.rank, h: r => `<b class="num">${r.x.rank}</b>` },
      { l: "cStock", v: r => r.name, h: stockCell },
      { l: "cWhyR", h: r => { const L = rankLines(r.x.scores); return `<div class="idea-why"><span><b>${esc(L[0].t)}</b></span><span>${esc(L[1].t)}</span>${r.x.trigger ? `<span>${w("cIf")}: ${esc(r.x.trigger)}</span>` : ""}</div>`; }, c: "h1" },
      { l: "cPrice", v: r => r.x.close, h: r => `<span class="num">${px(r.x.close)}</span>`, r: 1, c: "h2" },
      { l: "c6", v: r => r.x.ret_6m, h: r => `<span class="num ${r.x.ret_6m >= 0 ? "up" : "dn"}">${spct(r.x.ret_6m, 0)}</span>`, r: 1, c: "h2" },
      { l: "cView", v: r => r.it ? VORD[r.it.v] : 9, h: viewCell }])}`;
}
/* ---------- sub-tabs inside a page (real tabs, not dropdowns) ---------- */
const seg = (base, cur, items) => `<div class="seg" role="tablist">${items.map(([k, l], i) => `<a role="tab" href="#${base}${i ? "/" + k : ""}" aria-selected="${cur === k}">${w(l)}</a>`).join("")}</div>`;
const sub = (t, d) => S.sub[t] || d;

/* ---------- portfolio: Holdings | Mutual funds | Tax ---------- */
const isFund = h => /^INF/.test(h.symbol);
function pagePortfolio() {
  const p = D.portfolio; if (!p) return `<p class="empty">${w("noData")}</p>`;
  const cur = S.tab === "tax" ? "tax" : "holdings", t = p.tax || {};
  const cost = p.holdings.reduce((a, h) => a + (h.avg_cost || 0) * (h.quantity || 0), 0), gain = p.total_value - cost;
  const mix = Object.entries(p.allocation?.current || {}), colors = ["var(--pri)", "var(--l50)", "var(--gain)", "var(--warn)", "var(--l200)", "var(--loss)"];
  const band = `<section class="pband card rise"><div class="pb-main"><span class="k">${w("pTotal")}</span><span class="bignum num">${lakh(p.total_value)}</span>
     <span class="num ${gain >= 0 ? "up" : "dn"}" style="font-weight:700">${gain >= 0 ? "+" : "−"}${lakh(Math.abs(gain))} <span class="muted" style="font-weight:500">(${spct(gain / cost)} ${w("pGain").toLowerCase()})</span></span></div>
    <div class="pb-mix"><div class="alloc">${mix.map(([k, v], i) => `<i style="width:${v * 100}%;background:${colors[i % colors.length]}" data-tip="${esc(p.allocation.labels?.[k] || k)}: ${pct(v)}"></i>`).join("")}</div>
     <div class="legend2">${mix.map(([k, v], i) => `<span><i style="background:${colors[i % colors.length]}"></i>${esc(p.allocation.labels?.[k] || k)} <b class="num">${pct(v)}</b></span>`).join("")}</div>
     ${p.allocation?.approved ? "" : `<p class="muted" style="font-size:13.5px">${w("pMixTarget")}</p>`}</div>
    <div class="pb-kv">${kv(w("pYear") + (t.fy ? ` (${esc(t.fy)})` : ""), inr(t.realised_gain))}${kv(w("pRoom"), inr(t.harvest_room), w("pRoomS"))}</div></section>`;
  const tabs = "";
  let body = "";
  if (cur === "holdings") {
    const rows = p.holdings.map(h => ({ sym: h.symbol, name: clean(h.name), h, it: BY.get(h.symbol), sector: h.group }));
    body = table("port", rows, [["all", r => true], ["sell", r => r.it?.v === "sell" || r.h.verdict === "sell"], ["weak", r => r.it?.v === "weak"], ["fView", r => !!r.it]], [
      { l: "hHolding", v: r => r.name, h: r => `<div class="nm trunc">${esc(r.name)}</div><div class="sy num">${esc(r.sym)} · ${n0(r.h.quantity)} shares</div>` },
      { l: "cView", v: r => r.it ? VORD[r.it.v] : 9, h: r => r.it ? chip(r.it.v) : r.h.verdict ? chip(r.h.verdict) : chip("none") },
      { l: "hValue", v: r => r.h.value, h: r => `<span class="num">${inr(r.h.value)}</span>`, r: 1 },
      { l: "hGain", v: r => r.h.gain_pct, h: r => `<span class="num ${r.h.gain_pct >= 0 ? "up" : "dn"}">${spct(r.h.gain_pct)}</span>`, r: 1, c: "h1" },
      { l: "hShare", v: r => r.h.share, h: r => `<span class="num">${pct(r.h.share, 1)}</span>`, r: 1, c: "h2" },
      { l: "hHeld", v: r => r.h.tax_note, h: r => `<span class="muted">${esc(r.h.tax_note || "")}</span>`, c: "h3" },
      { l: "", c: "h1", h: () => `<span class="ms muted">chevron_right</span>` }],
      { rowAttr: r => isFund(r.h) ? `data-go="portfolio/funds"` : `data-open="${esc(r.sym)}"` })
     + ((p.opportunities || []).length ? sec2(w("pOpp")) + `<div class="card" style="padding:6px">${p.opportunities.map(o => { const s = [...SMAP.values()].find(x => clean(x.name) === clean(o.name)); return `<${s ? `a href="#stock" data-open="${esc(s.symbol)}"` : "div"} class="mrow state" style="grid-template-columns:minmax(0,1fr) minmax(0,2fr);text-decoration:none"><span class="nm">${esc(clean(o.name))}</span><span class="say">${esc(o.why)}</span></${s ? "a" : "div"}>`; }).join("")}</div>` : "");
  } else if (cur === "funds") {
    const fs = p.holdings.filter(isFund), F = D.funds || {};
    body = `<p class="muted secp">${w("fundsP")} ${esc(F.headline || "")}</p>` + (fs.length ? `<table class="grid rise"><thead><tr><th><button tabindex="-1">${w("hHolding")}</button></th><th class="r h1"><button tabindex="-1">${w("fUnits")}</button></th><th class="r"><button tabindex="-1">${w("hValue")}</button></th><th class="r"><button tabindex="-1">${w("hGain")}</button></th><th class="h2"><button tabindex="-1">${w("hHeld")}</button></th></tr></thead><tbody>${fs.map(h => `<tr><td><div class="nm trunc">${esc(clean(h.name))}</div><div class="sy num trunc">${esc(h.symbol)}</div></td><td class="r num h1">${n0(Math.round(h.quantity * 1000) / 1000)}</td><td class="r num">${inr(h.value)}</td><td class="r num ${h.gain_pct >= 0 ? "up" : "dn"}">${spct(h.gain_pct)}</td><td class="h2 muted">${esc(h.tax_note || "")}</td></tr>`).join("")}</tbody></table>` : `<p class="empty">${w("noFunds")}</p>`)
      + (F.base_rate_caveat ? `<p class="muted" style="margin-top:12px;font-size:13.5px">${esc(F.base_rate_caveat)}</p>` : "");
  } else {
    const sc = D.smallcase;
    body = `<div class="card" style="padding:18px 20px;display:grid;gap:10px">${(t.notes || []).map(n => `<p>${esc(n)}</p>`).join("")}${t.itr_pack ? `<div><a class="btn t" href="${esc(t.itr_pack)}"><span class="ms">arrow_downward</span>${w("pPack")}</a></div>` : ""}</div>`
      + (sc ? sec2(w("pSc")) + `<div class="card" style="padding:18px 20px"><div class="lines">${sc.lines.map(l => `<p>${esc(l)}</p>`).join("")}</div><p class="muted" style="margin-top:10px;font-size:13.5px">${esc(sc.notes.join(" "))}</p></div>` : "");
  }
  return `<header class="page-h rise"><h1 class="disp">${w("tax")}</h1><p>${esc(p.headline || "")}</p></header>${band}${tabs}${body}`;
}

/* ---------- market & news: the chart and sectors beside the numbers ---------- */
function pageMarket() {
  const m = D.market || {}, v = m.valuation || {}, secs = [...(m.sectors || [])].sort((a, b) => b.ret_6m - a.ret_6m);
  const pos = v.pe_now ? (v.pe_now - v.low) / (v.high - v.low) * 100 : 0;
  return `<header class="page-h rise"><h1 class="disp">${w("market")}</h1><p>${esc(m.headline || "")}</p><p>${esc(S.lang === "bn" && D.calls?.market_view_bn ? D.calls.market_view_bn : (D.today?.market_mood || ""))}</p></header>
   <div class="two"><div class="col">
    <section class="pane"><div class="blk"><h3>${w("price1y")}</h3><div data-chart="NIFTYBEES" data-days="250"><div class="skel"></div></div></div></section>
    ${sec2(w("mSect"))}
    <div class="sectors">${secs.map(s => `<div style="background:color-mix(in oklab,${s.ret_6m >= 0 ? "var(--gain)" : "var(--loss)"} ${Math.round(Math.min(55, Math.abs(s.ret_6m) * 150))}%,var(--surf));border:1px solid var(--line2)" data-tip="${esc(`${s.industry}: ${spct(s.ret_6m)} ${w("in6")}. ${w("mSectS", pct(s.above_200dma))}. ${s.n} stocks.`)}"><span class="trunc" style="font-weight:600">${esc(s.industry)}</span><b class="num">${spct(s.ret_6m, 0)}</b><span class="muted">${w("mSectS", pct(s.above_200dma))}</span></div>`).join("")}</div>
    ${sec2(w("mFlows"))}<div class="card" style="padding:18px 20px"><p class="muted">${esc(m.flows_note || "")}</p></div>
   </div>
   <aside class="side">
    ${marketPanel(true)}
    ${v.pe_now ? `<section class="panel"><h3 class="ph"><span>${w("mVal")}</span></h3><p style="font-size:14px">${esc(w("mValS", v.pe_now, v.low, v.high))} ${esc(v.verdict || "")}</p>
      <div class="rb" style="--sp:${pos}%;background:linear-gradient(90deg,var(--gain),var(--c3),var(--loss))"><span class="now" style="left:${pos}%"></span><span class="c num" style="left:${pos}%">₹${v.pe_now}</span><span class="l num">₹${v.low}</span><span class="r num">₹${v.high}</span></div></section>` : ""}
    <section class="panel"><h3 class="ph"><span>${w("mEvents")}</span></h3>${(m.events || []).map(e => `<div class="ev"><b class="num">${mdate(e.date)}</b><span>${esc(e.text)}</span></div>`).join("")}</section>
   </aside></div>`;
}

/* ---------- our record: Our forecasts | Your own trading ---------- */
function pageRecord() {
  const r = D.record || {}, o = D.own_record || {}, cur = S.tab === "tradrec" ? "mine" : "ours";
  const mons = (o.by_month || []).slice(-24).map(x => ({ label: x.month.slice(2).replace("-", "/"), v: x.gain, tip: `${x.month}: ${x.closed} trades closed, ${x.winners} made money; ${x.gain >= 0 ? "gain" : "loss"} ${inr(Math.abs(x.gain))}` }));
  const cnt = {}; (r.calls || []).forEach(c => { cnt[c.action] = (cnt[c.action] || 0) + 1; });
  const tabs = "";
  const body = cur === "ours"
    ? `<div class="two"><div class="col"><div class="card" style="padding:18px 20px"><div class="lines">${(r.learning_lines || []).map(l => `<p>${esc(l)}</p>`).join("") || `<p class="muted">${esc(r.headline || "")}</p>`}</div></div></div>
       <aside class="side"><section class="panel"><h3 class="ph"><span>${w("rCalls")}</span></h3>${Object.entries(cnt).sort((a, b) => b[1] - a[1]).map(([k, n]) => kv(w(k), n)).join("")}<p class="muted" style="font-size:13.5px">${w("rCallsS")}</p></section></aside></div>`
    : `<div class="tiles">
      <div class="tile"><span class="k">${w("rClosed")}</span><span class="v num">${o.closed ?? "–"}</span></div>
      <div class="tile"><span class="k">${w("rWin")}</span><span class="v num">${o.win_rate ?? "–"}%</span><span class="s num">${o.winners} / ${o.closed}</span></div>
      <div class="tile"><span class="k">${w("rHeldW")}</span><span class="v num">${Math.round(o.avg_days_winners || 0)} ${w("days")}</span><span class="s">${w("rHeldL")}: ${Math.round(o.avg_days_losers || 0)} ${w("days")}</span></div>
      <div class="tile"><span class="k">${w("rEarly")}</span><span class="v num">${o.sold_early?.share ?? "–"}%</span><span class="s">${w("rEarlyS")}</span></div>
      <div class="tile"><span class="k">${w("rBeat")}</span><span class="v num">${o.vs_nifty?.share ?? "–"}%</span><span class="s num">${o.vs_nifty?.beat} / ${o.vs_nifty?.checked}</span></div></div>
     <div class="two" style="margin-top:14px"><div class="col"><div class="card" style="padding:18px 20px"><h3 class="eyebrow" style="margin-bottom:8px">${w("rMonth")}</h3><div data-bars="1">${bars(mons, 900)}</div></div></div>
     <aside class="side"><section class="panel"><div class="lines">${(o.lines || []).map(l => `<p>${esc(l)}</p>`).join("")}</div></section></aside></div>`;
  return `<header class="page-h rise"><h1 class="disp">${w(S.tab === "tradrec" ? "tradrec" : "record")}</h1><p>${esc(r.headline || "")}</p></header>${tabs}${body}`;
}

/* ---------- settings ---------- */
function pageSettings() {
  const st = D.settings || {}, b = st.budget || D.today?.budget || {}, L = D.learned || {}, th = store.get("theme", null);
  const btn = (attr, val, on, label) => `<button class="sg" ${attr}="${val}" aria-pressed="${on}">${label}</button>`;
  const hid = st.not_now || [];
  return `<header class="page-h rise"><h1 class="disp">${w("settings")}</h1><p>${w("setP")}</p></header>
   <div class="set-grid">
    <section class="pane"><h3 class="ph">${w("setLook")}</h3>
     <div class="srow"><span>${w("setLang")}</span><span class="seg2">${btn("data-lang", "en", S.lang === "en", "English")}${btn("data-lang", "bn", S.lang === "bn", "বাংলা")}</span></div>
     <div class="srow"><span>${w("setTheme")}</span><span class="seg2">${btn("data-themeset", "auto", !th, w("themeAuto"))}${btn("data-themeset", "light", th === "light", w("themeLight"))}${btn("data-themeset", "dark", th === "dark", w("themeDark"))}</span></div></section>
    <section class="pane"><h3 class="ph">${w("setBudget")}</h3><p class="muted">${w("setBudgetP")}</p>
     <div class="srow"><label class="qf" style="margin:0"><span>₹</span><input id="bud" inputmode="numeric" value="${b.total ?? ""}" aria-label="${esc(w("setBudget"))}"></label><button class="btn f" data-budget="${esc(b.month || "")}">${w("change")}</button></div>
     ${b.total ? `<div class="meter"><i style="width:${Math.round((b.left ?? 0) / b.total * 100)}%"></i></div><p class="muted num" style="font-size:13.5px">${w("tLeftS", inr(b.total)).replace(/^/, inr(b.left) + " ")}</p>` : ""}</section>
    <section class="pane"><h3 class="ph">${w("setHidden")}</h3>${hid.length ? hid.map(x => `<div class="srow"><span><b>${esc(x.symbol || x.scope || "")}</b> <span class="muted">${esc(x.until || x.for || "")}</span></span><button class="btn x" data-nnundo="${esc(x.id ?? "")}">${w("undo")}</button></div>`).join("") : `<p class="muted">${w("setHiddenNone")}</p>`}</section>
    <section class="pane"><h3 class="ph">${w("setLearned")}</h3>${(L.patterns || []).length ? L.patterns.map(x => `<div class="srow"><span>${esc(x.label || x.pattern || x.text || "")}</span><button class="btn x" data-forget="${esc(x.pattern || x.id || "")}">${w("forget")}</button></div>`).join("") : `<p class="muted">${w("setLearnedNone")}</p>`}</section>
    <section class="pane"><h3 class="ph">${w("setData")}</h3><p class="muted">${w("setDataP")}</p>
     <div class="srow" style="justify-content:flex-start;flex-wrap:wrap"><button class="btn t" data-refresh><span class="ms">arrow_downward</span>${w("refreshDocs")}</button><button class="btn o" data-rerun="daily"><span class="ms">schedule</span>${w("rerunNow")}</button>${LIVE ? `<a class="btn x" href="/logout">${w("signOut")}</a>` : ""}</div></section>
   </div>`;
}

function pageHealth() {
  const h = D.health || {}, dur = r => { const a = new Date(r.started_at.replace(" ", "T")), b = r.finished_at ? new Date(r.finished_at.replace(" ", "T")) : null; return b ? Math.max(1, Math.round((b - a) / 60000)) + " " + w("min") : "–"; };
  const st = s => `<span class="status ${s === "ok" ? "st-ok" : s === "failed" || s === "error" ? "st-bad" : "st-warn"}">${esc(s)}</span>`;
  return `<header class="page-h rise"><h1 class="disp">${w("health")}</h1><p>${esc(h.headline || "")}</p></header>
   ${(h.needs || []).length ? `<div class="secttl"><h2>${w("hNeeds")}</h2></div>${h.needs.map(n => `<div class="flag"><span class="ms" style="color:var(--warn)">info</span><span>${esc(n)}</span></div>`).join("")}` : ""}
   <div class="secttl"><h2>${w("hFresh")}</h2></div><div class="tiles">${(h.freshness || []).map(f => `<div class="tile"><span class="k">${esc(f.name)}</span><span class="v" style="font-size:20px">${w("ago", f.days_old)}</span><span class="s num">${esc(String(f.when).slice(0, 16))}</span></div>`).join("")}</div>
   <div class="secttl"><h2>${w("hRuns")}</h2></div><table class="grid"><thead><tr><th><button>${w("hJob")}</button></th><th><button>${w("hStart")}</button></th><th class="h1"><button>${w("hTook")}</button></th><th><button>${w("hStatus")}</button></th></tr></thead><tbody>${(h.runs || []).slice(0, 15).map(r => `<tr><td>${esc(r.job)}${r.error ? `<div class="msg">${esc(String(r.error).slice(0, 140))}</div>` : ""}</td><td class="num">${esc(r.started_at.slice(5, 16))}</td><td class="num h1">${dur(r)}</td><td>${st(r.status)}</td></tr>`).join("")}</tbody></table>
   <div class="secttl"><h2>${w("hProb")}</h2><span class="n num">${(h.problems || []).length}</span></div><table class="grid"><tbody>${(h.problems || []).slice(0, 15).map(p => `<tr><td class="num" style="width:120px">${esc(p.seen_at.slice(5, 16))}</td><td><b>${esc(p.job)}</b> ${st(p.severity)}${p.count > 1 ? ` <span class="muted">×${p.count}</span>` : ""}<div class="msg">${esc(String(p.message).slice(0, 220))}</div></td></tr>`).join("")}</tbody></table>
   <div class="secttl"><h2>${w("hQueue")}</h2></div><div class="card" style="padding:18px 20px"><p class="muted">${(h.queue || []).length ? h.queue.map(q => esc(q.kind)).join(", ") : w("hNone")}</p></div>`;
}
function pageFeedback() {
  const f = D.feedback || {}, stw = W[S.lang].fbSt || W.en.fbSt;
  return `<header class="page-h rise"><h1 class="disp">${w("fbT")}</h1><p>${w("fbS")}</p></header>
   <div class="fb-box"><textarea id="fbt" aria-label="${esc(w("fbT"))}"></textarea><div><button class="btn f" data-fbsend><span class="ms">rate_review</span>${w("send")}</button></div></div>
   ${(f.changed || []).length ? `<div class="secttl"><h2>${w("fbChanged")}</h2></div><div class="card" style="padding:18px 20px"><div class="lines">${f.changed.map(c => `<p>${esc(c)}</p>`).join("")}</div></div>` : ""}
   <div class="secttl"><h2>${w("fbList")}</h2></div><div class="calls">${(f.items || []).map(i => `<div class="card" style="padding:16px 20px;display:grid;gap:6px"><div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap"><span class="chip ${i.status === "applied" ? "v-buy" : i.status === "backlog" ? "v-weak" : "v-watch"}">${esc(stw[i.status] || i.status)}</span><span class="muted num">${mdate(i.at)}</span></div><p style="font-weight:600">${esc(i.said_as || i.text)}</p>${i.plan ? `<p class="muted">${esc(i.plan)}</p>` : ""}</div>`).join("")}</div>`;
}

/* ---------- stock page: a verdict band on top, then evidence in two columns; the jump bar only scrolls ---------- */
const factRow = (k, v, s) => v == null ? "" : `<div class="fact"><span>${k}</span><b class="num">${v}</b>${s ? `<small>${esc(s)}</small>` : ""}</div>`;
function facts(L) {
  if (!L) return `<p class="muted">${w("noData")}</p>`;
  const m = L.metrics || {}, r = L.pe_range, f = (k, val, sub) => factRow(w(k), val, sub);
  return `<div class="facts">
   ${f("fPe", m.pe != null ? "₹" + m.pe.toFixed(1) : null, r ? w("fPeS", r.median, r.low, r.high) : null)}
   ${f("fRoe", m.roe != null ? pct(m.roe, 0) + " " + w("aYear") : null, w("fRoeS"))}
   ${f("fDe", m.debt_to_equity != null ? "₹" + m.debt_to_equity.toFixed(2) : null, w("fDeS"))}
   ${f("fGr", m.profit_cagr_3y != null ? spct(m.profit_cagr_3y, 0) + " " + w("aYear") : null)}
   ${f("fR12", m.ret_12m != null ? spct(m.ret_12m, 0) : null)}
   ${f("f200", m.dist_200dma != null ? w("trendT", Math.round(m.dist_200dma * 100)) : null, w("f200S"))}
   ${f("fVol", m.vol_1y != null ? pct(m.vol_1y, 0) + " " + w("aYear") : null, w("fVolS"))}
   ${f("fDd", m.max_dd_1y != null ? pct(Math.abs(m.max_dd_1y), 0) : null)}
   ${f("fAdv", m.adv_3m_cr != null ? inr(m.adv_3m_cr) + " crore" : null, m.adv_3m_cr != null ? w("fAdvS", m.adv_3m_cr) : null)}</div>`;
}
function compareBlock(L) { if (!L?.scores) return ""; return `<div class="blk"><h3>${w("compare")}</h3><ul>${rankLines(L.scores).map(x => `<li>${esc(x.t)}</li>`).join("")}</ul></div>`; }
function holdBlock(h) {
  const lots = h.lots || [];
  return `<section class="pane" id="s-hold"><div class="blk"><h3>${w("yourHold")}</h3><div class="facts">
    ${factRow(w("hQty"), n0(h.quantity))}${factRow(w("hVal"), inr(h.value))}${factRow(w("hGainL"), `<span class="${h.gain_pct >= 0 ? "up" : "dn"}">${spct(h.gain_pct)}</span>`)}${factRow(w("hShareL"), pct(h.share, 1))}${factRow(w("hTaxL"), h.tax_note ? esc(h.tax_note) : null)}</div>
    ${lots.length ? `<table class="lots2"><thead><tr><th>${w("lots")}</th><th>${w("lotQ")}</th><th>${w("lotC")}</th><th>${w("lotLT")}</th></tr></thead><tbody>${lots.slice(0, 6).map(l => `<tr><td class="num">${mdate(l.acquired_on)}</td><td class="num">${n0(l.quantity)}</td><td class="num">${px(l.cost)}</td><td class="num">${l.long_term ? "✓ " : ""}${mdate(l.turns_long_term_on)}</td></tr>`).join("")}</tbody></table>${lots.length > 6 ? `<p class="muted" style="font-size:13px">${w("moreLots", lots.length - 6)}</p>` : ""}` : ""}</div></section>`;
}
function pageStock() {
  const sym = S.sym; if (!sym) return pageToday();
  const it = BY.get(sym), h = HELD.get(sym), inWl = WL.has(sym), bits = it ? whyBits(it.why) : [];
  const price = it?.entry ?? WL.get(sym)?.close;
  const reasons = it ? [...new Set([...(it.reasons.length ? it.reasons : bits)])] : [];
  const ladder = it?.stop && it?.target && it?.entry ? (() => { const sp = Math.max(4, Math.min(96, (it.entry - it.stop) / (it.target - it.stop) * 100)); return `<div class="rb" style="--sp:${sp}%"><span class="now" style="left:${sp}%"></span><span class="c num" style="left:${sp}%">${w("now")} ${px(it.entry)}</span><span class="l num dn">${w("stop")} ${px(it.stop)}</span><span class="r num up">${w("target")} ${px(it.target)}</span></div>`; })() : "";
  const jump = [["s-chart", "jChart"], ["s-nums", "jNums"], it && ["s-why", "jWhy"], it && (it.risks.length || it.sk?.level_flag) && ["s-risk", "jRisk"], it && ["s-act", "jAct"], h && ["s-hold", "jHold"], it?.news.length && ["s-news", "jNews"]].filter(Boolean);
  const mid = it ? `<div class="sb-mid">
     <div class="sb-say" id="s-why"><span class="eyebrow">${w("ourView")}</span><p class="bigview">${esc(say(it))}</p>${it.whyToday ? `<p class="muted">${esc(it.whyToday)}</p>` : ""}
      ${reasons.length ? `<div class="why ${it.v === "sell" || it.v === "weak" ? it.v : "hold"}">${reasons.map(b => `<span>${esc(b)}</span>`).join("")}</div>` : ""}</div>
     <div class="sb-ch"><span class="eyebrow">${w("chance")}</span><span class="bigp num" style="font-size:46px">${pct(it.p)}</span>${bar12(it)}<p class="muted" style="font-size:13.5px">${esc(w("similar", pct(it.br), it.n ? n0(it.n) : ""))}${it.sk?.probability != null ? " " + esc(w("second", pct(it.sk.probability))) : ""}</p></div>
     ${ladder ? `<div class="sb-lv"><span class="eyebrow">${w("ladder")}</span>${ladder}</div>` : ""}</div>`
    : `<div class="sb-mid"><div class="ask"><h3>${w("noView")}</h3><p>${w("noViewL")}</p><div><button class="btn f" data-ask="${esc(sym)}"><span class="ms">query_stats</span>${w("ask")}</button></div></div></div>`;
  return `<a class="btn x back" href="#${esc(S.back)}" data-back><span class="ms">arrow_back</span>${w("back")}</a>
   <header class="sband card rise"><div class="sb-top"><div style="min-width:0"><div class="sb-chips">${it ? chip(it.v) : chip("none")}${h ? `<span class="tag">${w("youHoldT")}</span>` : ""}${inWl ? `<span class="tag">${w("inWl")}</span>` : ""}</div>
     <h1 class="disp">${esc(nameOf(sym))}</h1><div class="muted num">${esc(sym)}${SMAP.get(sym)?.exchange ? " · " + esc(SMAP.get(sym).exchange) : ""}</div></div>
     <div class="sb-r"><div class="px num" id="pxv">${price != null ? px(price) : ""}</div>
      <div class="sb-btns">${inWl ? `<button class="btn o" data-unwatch="${esc(sym)}"><span class="ms">check</span>${w("inWl")}</button>` : `<button class="btn t" data-watch="${esc(sym)}"><span class="ms">add</span>${w("addWl")}</button>`}
      ${it ? `<button class="icb" data-snooze="${esc(sym)}" data-tip="${esc(w("snoozeShort"))}" aria-label="${esc(w("snoozeShort"))}"><span class="ms">schedule</span></button><button class="icb" data-dismiss="${esc(sym)}" data-tip="${esc(w("cross"))}" aria-label="${esc(w("cross"))}"><span class="ms">block</span></button>` : ""}</div></div></div>${mid}</header>
   <nav class="jump" aria-label="On this page">${jump.map(([id, k]) => `<a href="#${id}" data-jump="${id}">${w(k)}</a>`).join("")}</nav>
   <div class="sp-grid">
    <div class="col">
     <section class="pane" id="s-chart"><div class="blk"><h3>${w("price6")}</h3><div data-chart="${esc(sym)}"><div class="skel"></div></div></div></section>
     <section class="pane" id="s-nums"><div class="blk"><h3>${w("facts")}</h3><div id="facts"><div class="skel" style="height:200px"></div></div></div><div id="cmp"></div><div id="peers"></div></section>
    </div>
    <div class="col">
     ${it ? `${it.risks.length || it.sk?.level_flag ? `<section class="pane" id="s-risk">
       ${it.risks.length ? `<div class="blk"><h3>${w("whatWrong")}</h3><ul>${it.risks.map(r => `<li>${esc(r)}</li>`).join("")}</ul></div>` : ""}
       ${it.sk?.level_flag ? `<div class="flag"><span class="ms" style="color:var(--warn)">info</span><span>${esc(it.sk.level_flag)}</span></div>` : ""}</section>` : ""}
      <section class="pane" id="s-act"><div class="blk"><h3>${w("money")}</h3><div class="money">${moneyLines(it).replace(/<div>/g, '<div class="mline">')}</div></div></section>` : ""}
     ${h ? holdBlock(h) : ""}
     ${it?.news.length ? `<section class="pane" id="s-news"><div class="blk"><h3>${w("newsL")}</h3><ul>${it.news.map(n => `<li>${esc(n)}</li>`).join("")}</ul></div></section>` : ""}
    </div></div>`;
}

function fillStock() {
  const sym = S.sym; if (!sym) return; const it = BY.get(sym);
  hist(sym).then(h => {
    const box = $(`[data-chart="${CSS.escape(sym)}"]`); if (!box || S.sym !== sym) return;
    if (!h) { box.innerHTML = `<p class="muted">${w("noHist")}</p>`; return; }
    const draw = () => { box.dataset.w = box.clientWidth; box.innerHTML = priceChart(it, h, box.clientWidth); }; draw(); watchSize(box, draw);
  });
  lookup().then(L => {
    if (S.sym !== sym || S.tab !== "stock") return; const x = L[sym];
    const f = $("#facts"); if (f) f.innerHTML = facts(x);
    const c = $("#cmp"); if (c) c.innerHTML = compareBlock(x);
    const p = $("#peers"); if (p && x?.peers?.length) p.innerHTML = `<div class="blk"><h3>${S.lang === "bn" ? "একই রকম company" : "Similar companies"}</h3><div class="peers">${x.peers.map(q => `<a class="state" href="#stock" data-open="${esc(q.symbol)}"><span class="trunc">${esc(clean(q.name))} <span class="muted num">${esc(q.symbol)}</span></span>${BY.has(q.symbol) ? chip(BY.get(q.symbol).v) : ""}</a>`).join("")}</div></div>`;
    const pv = $("#pxv"); if (pv && !pv.textContent && x?.metrics?.close) pv.textContent = px(x.metrics.close);
  });
}
let RO = [];
function watchSize(box, draw) { if (!("ResizeObserver" in window)) return; const ro = new ResizeObserver(() => { if (Math.abs(box.clientWidth - box.dataset.w) > 16) draw(); }); ro.observe(box); RO.push(ro); }

/* ---------- search ---------- */
function find(q) {
  q = q.toLowerCase(); const out = [];
  for (const s of D.search || []) {
    const sy = s.symbol.toLowerCase(), nm = (s.name || "").toLowerCase(); let sc = 0;
    if (sy === q) sc = 100; else if (sy.startsWith(q)) sc = 90; else if (nm.split(/\s+/).some(x => x.startsWith(q))) sc = 80; else if (nm.includes(q)) sc = 60; else if (sy.includes(q)) sc = 55;
    else { let i = 0; for (const ch of nm) if (ch === q[i]) i++; if (i === q.length && q.length > 2) sc = 30; }
    if (sc) out.push([sc + (BY.has(s.symbol) ? 6 : 0) + (HELD.has(s.symbol) ? 4 : 0) + (WL.has(s.symbol) ? 3 : 0), s.symbol]);
  }
  return out.sort((a, b) => b[0] - a[0]).slice(0, 8).map(x => x[1]);
}
let SR = [], SI = -1;
function searchShow() {
  const inp = $("#q"), list = $("#sr"), q = inp.value.trim();
  SR = q ? find(q) : (S.addMode ? [] : store.get("recent", []).filter(s => SMAP.has(s) || BY.has(s)));
  const li = (sym, i) => `<li role="option" id="sr${i}" data-pick="${esc(sym)}" data-i="${i}" aria-selected="${i === SI}"><span class="nm trunc">${esc(nameOf(sym))}</span><span class="tags">${S.addMode ? (WL.has(sym) ? `<span class="tag">${w("inWl")}</span>` : `<span class="tag"><span class="ms" style="font-size:16px">add</span>${w("watchlist")}</span>`) : (BY.has(sym) ? chip(BY.get(sym).v) : "") + (HELD.has(sym) ? `<span class="tag">${w("youHoldT")}</span>` : "") + starBtn(sym)}</span><span class="sy num">${esc(sym)}</span></li>`;
  SI = SR.length ? 0 : -1;
  list.innerHTML = SR.length ? (q ? "" : `<li class="hd eyebrow">${w("recent")}</li>`) + SR.map(li).join("") : (q ? `<li class="hd muted">${w("noMatch")}</li>` : "");
  list.hidden = !list.innerHTML; $(".search").classList.toggle("open", !list.hidden); inp.setAttribute("aria-expanded", String(!list.hidden));
}
function searchClose() { $("#sr").hidden = true; $(".search").classList.remove("open"); $("#q").setAttribute("aria-expanded", "false"); if (S.addMode) { S.addMode = false; $("#q").placeholder = w("search"); } }
function pick(sym) {
  const add = S.addMode; searchClose(); $("#q").value = ""; $("#q").blur();
  if (add) { if (!WL.has(sym)) addWatch(sym); return; }
  openStock(sym);
}

/* ---------- actions ---------- */
function addWatch(s) { WL.set(s, { symbol: s, name: nameOf(s), why: [], close: BY.get(s)?.entry }); render(); queue("watchlist_add", { symbol: s, exchange: SMAP.get(s)?.exchange || "NSE" }, w("added"), () => { WL.delete(s); render(); }); }
function removeWatch(s) { const old = WL.get(s); WL.delete(s); render(); queue("watchlist_remove", { symbol: s, exchange: SMAP.get(s)?.exchange || "NSE" }, w("removed"), () => { WL.set(s, old); render(); }); }
function openStock(sym) {
  const rec = [sym, ...store.get("recent", []).filter(s => s !== sym)].slice(0, 6); store.set("recent", rec);
  if (S.tab !== "stock") { S.back = S.tab; S.scroll[S.tab] = scrollY; }
  S.sym = sym; store.set("sym", sym); S.fromApp = true;
  if (location.hash === "#stock") { vt(() => { render(); scrollTo(0, 0); }); } else location.hash = "stock";
}

/* ---------- shell ---------- */
const NAV = [["today", "wb_sunny"], ["follow", "star"], ["watchlist", "visibility"], ["ideas", "query_stats", "desk"], ["portfolio", "account_balance_wallet"], ["market", "newspaper", "desk"], ["record", "fact_check", "desk"]];
const NAV2 = [["settings", "settings", "desk"], ["feedback", "rate_review", "desk"], ["health", "monitor_heart", "desk"]];
function renderRail() {
  const bad = D.meta && D.meta.status && D.meta.status.ok === false, cur = S.tab === "stock" ? S.back : S.tab; if (cur === "calls") cur = "today";
  const cnt = { follow: ITEMS.filter(i => !HELD.has(i.sym) && i.v === "watch").length, watchlist: WL.size, portfolio: HELD.size };
  const a = ([k, ic, cls]) => `<a class="nav ${cls || ""}" href="#${k}" ${cur === k ? 'aria-current="page"' : ""}><span class="ms">${ic}</span><span class="trunc lbl-l">${w(k)}</span><span class="trunc lbl-s">${w(k + "S") === k + "S" ? w(k) : w(k + "S")}</span>${cnt[k] ? `<span class="cnt num">${cnt[k]}</span>` : ""}${(k === "health" && bad) || (cur !== k && changed(k)) ? '<span class="dot" aria-label="changed"></span>' : ""}</a>`;
  const m = D.meta || {};
  $("#rail").innerHTML = `<div class="brand"><i>s</i><span>stockpilot</span></div>${NAV.map(a).join("")}
   <button class="nav phone" data-more-nav style="border:0;background:none;cursor:pointer"><span class="ms">more_horiz</span><span>${w("moreNav")}</span></button>
   <div class="rail-gap"></div><div class="rail-div"></div>${NAV2.map(a).join("")}
   <div class="rail-foot">${w("upd")} ${esc((m.built_at || "").slice(11, 16))}${m.holdings?.days_old != null ? `<br>${w("synced")} ${w("ago", m.holdings.days_old)}` : ""}</div>`;
}
function renderBar() {
  const dark = root.dataset.theme === "dark";
  $("#bar").innerHTML = `<div class="search"><label for="q"><span class="ms">search</span><input id="q" role="combobox" aria-controls="sr" aria-expanded="false" aria-autocomplete="list" placeholder="${esc(w(S.addMode ? "searchAdd" : "search"))}" autocomplete="off"></label><ul class="sr" id="sr" role="listbox" hidden></ul></div>
   <span class="fresh"></span>
   <button class="icb" id="lang" data-tip="${esc(w("langB"))}" aria-label="${esc(w("langB"))}"><span class="ms">translate</span></button>
   <button class="icb" id="theme" data-tip="${esc(w("theme"))}" aria-label="${esc(w("theme"))}"><span class="ms">${dark ? "light_mode" : "dark_mode"}</span></button>`;
}
const PAGES = { today: pageToday, calls: pageCalls, settings: pageSettings, follow: pageFollow, watchlist: pageWatchlist, ideas: pageIdeas, portfolio: pagePortfolio, market: pageMarket, record: pageRecord, feedback: pageFeedback, health: pageHealth, stock: pageStock };
function render() {
  CH.clear(); cid = 0; RO.forEach(r => r.disconnect()); RO = [];
  $("#view").innerHTML = (PAGES[S.tab] || pageToday)();
  hydrate(); hydrateSince(); renderRail();
  if (S.tab === "stock") fillStock();
  $$("[data-chart='NIFTYBEES'][data-days]").forEach(box => hist("NIFTYBEES").then(h => { if (!h) return; const draw = () => { box.dataset.w = box.clientWidth - 40; box.innerHTML = priceChart(null, h, box.clientWidth - 40, 250); }; draw(); watchSize(box, draw); }));
  $$("[data-bars]").forEach(box => { const mons = (D.own_record?.by_month || []).slice(-24).map(x => ({ label: x.month.slice(2).replace("-", "/"), v: x.gain, tip: `${x.month}: ${x.closed} trades closed, ${x.winners} made money; ${x.gain >= 0 ? "gain" : "loss"} ${inr(Math.abs(x.gain))}` })); box.innerHTML = bars(mons, box.clientWidth - 40); });
}
function renderAll() { root.lang = S.lang === "bn" ? "bn" : "en"; renderBar(); render(); }

/* ---------- events ---------- */
document.addEventListener("click", e => {
  hideTip(); const el = sel => e.target.closest(sel); let x;
  if ((x = el("[data-pick]"))) return pick(x.dataset.pick);
  if ((x = el("[data-watch]"))) return addWatch(x.dataset.watch);
  if ((x = el("[data-unwatch]"))) { e.preventDefault(); e.stopPropagation(); return removeWatch(x.dataset.unwatch); }
  if ((x = el("[data-snooze]"))) return queue("snooze", { symbol: x.dataset.snooze, scope: "stock" }, w("snoozed"));
  if ((x = el("[data-dismiss]"))) return queue("dismiss", { symbol: x.dataset.dismiss, scope: "stock" }, w("dismissed"));
  if ((x = el("[data-ask]"))) { x.disabled = true; return queue("ask_analyst", { symbol: x.dataset.ask }, w("asked"), () => { x.disabled = false; }); }   // TODO(backend): new queue kind, 5 a day
  if ((x = el("[data-fbsend]"))) { const t = $("#fbt").value.trim(); if (!t) { $("#fbt").focus(); return; } $("#fbt").value = ""; return queue("feedback", { text: t, kind: null }, w("sent")); }
  if ((x = el("[data-addmode]"))) { S.addMode = true; const q = $("#q"); q.placeholder = w("searchAdd"); scrollTo({ top: 0 }); q.focus(); return; }
  if ((x = el("[data-go]"))) { location.hash = x.dataset.go; return; }
  if ((x = el("[data-jump]"))) { e.preventDefault(); document.getElementById(x.dataset.jump)?.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" }); return; }
  if ((x = el("[data-lang]"))) { S.lang = x.dataset.lang; store.set("lang", S.lang); vt(renderAll); return; }
  if ((x = el("[data-themeset]"))) { const v = x.dataset.themeset, auto = v === "auto"; root.dataset.theme = auto ? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light") : v; store.set("theme", auto ? null : v); vt(() => { renderBar(); render(); }); return; }
  if ((x = el("[data-budget]"))) { const amt = Math.round(+String($("#bud").value).replace(/[^\d.]/g, "")); if (!amt) { $("#bud").focus(); return; } return queue("budget_set", { month: x.dataset.budget, amount: amt }, w("budgetSet")); }
  if ((x = el("[data-nnundo]"))) return queue("not_now_undo", { id: x.dataset.nnundo }, w("undone"));
  if ((x = el("[data-forget]"))) return queue("learned_forget", { pattern: x.dataset.forget }, w("undone"));
  if ((x = el("[data-refresh]"))) return queue("refresh_docs", {}, w("queued"));
  if ((x = el("[data-rerun]"))) return queue("rerun", { job: x.dataset.rerun }, w("queued"));
  if ((x = el("[data-open]"))) { e.preventDefault(); return openStock(x.dataset.open); }
  if ((x = el("[data-back]"))) { e.preventDefault(); S.fromApp ? history.back() : (location.hash = S.back); return; }
  if ((x = el("[data-toggle]"))) { const k = x.dataset.toggle; S.open.has(k) ? S.open.delete(k) : S.open.add(k); render(); return; }
  if ((x = el("[data-more]"))) { const k = x.dataset.more; S.more.has(k) ? S.more.delete(k) : S.more.add(k); render(); return; }
  if ((x = el("[data-chip]"))) { const [k, v] = x.dataset.chip.split(":"); S.chip[k] = v; render(); return; }
  if ((x = el("[data-sort]"))) { const [k, i0] = x.dataset.sort.split(":"), i = +i0, so = S.sort[k]; S.sort[k] = so?.i === i ? (so.d > 0 ? { i, d: -1 } : null) : { i, d: 1 }; render(); return; }
  if ((x = el("[data-more-nav]"))) { openMore(); return; }
  if (el("#scrim")) { closeMore(); return; }
  if (el("#more a")) { closeMore(); return; }
  if (el("#lang")) { S.lang = S.lang === "en" ? "bn" : "en"; store.set("lang", S.lang); vt(renderAll); return; }
  if (el("#theme")) { root.dataset.theme = root.dataset.theme === "dark" ? "light" : "dark"; store.set("theme", root.dataset.theme); vt(renderBar); return; }
});
function openMore() {
  document.body.insertAdjacentHTML("beforeend", `<div id="scrim"></div><nav id="more" aria-label="${esc(w("moreNav"))}"><div class="grab"></div>${[["ideas", "query_stats"], ["market", "newspaper"], ["record", "fact_check"], ["settings", "settings"], ["feedback", "rate_review"], ["health", "monitor_heart"]].map(([k, ic]) => `<a class="nav" href="#${k}"><span class="ms">${ic}</span><span>${w(k)}</span></a>`).join("")}</nav>`);
}
function closeMore() { $("#more")?.remove(); $("#scrim")?.remove(); }
document.addEventListener("mousedown", e => { if (e.target.closest("#sr")) e.preventDefault(); });
document.addEventListener("focusin", e => { if (e.target.id === "q") searchShow(); });
document.addEventListener("focusout", e => { if (e.target.id === "q") setTimeout(searchClose, 150); });
document.addEventListener("input", e => {
  if (e.target.id === "q") searchShow();
  if (e.target.id === "qf") { S.q = e.target.value; const pos = e.target.selectionStart; render(); const f = $("#qf"); if (f) { f.focus(); f.setSelectionRange(pos, pos); } }
});
document.addEventListener("keydown", e => {
  if (e.target.id === "q" && SR.length) {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); SI = (SI + (e.key === "ArrowDown" ? 1 : SR.length - 1)) % SR.length; $$("#sr li[role=option]").forEach(li => li.setAttribute("aria-selected", String(+li.dataset.i === SI))); $("#q").setAttribute("aria-activedescendant", "sr" + SI); return; }
    if (e.key === "Enter" && SI >= 0) { e.preventDefault(); pick(SR[SI]); return; }
  }
  if (e.key === "Escape") { if (!$("#sr").hidden) return searchClose(); if ($("#more")) return closeMore(); }
  if (e.key === "/" && !/INPUT|TEXTAREA/.test(document.activeElement?.tagName || "")) { e.preventDefault(); $("#q").focus(); }
  if (e.key === "Enter" && e.target.matches("tr[data-open],tr[data-toggle]")) e.target.click();
});
function route() {
  const [h, sb] = location.hash.slice(1).split("/"), t = TABS.includes(h) ? h : "today";
  const prev = S.tab; if (t !== "stock" && prev === "stock") S.back = t;
  S.tab = t; S.q = ""; S.sub[t] = sb || null; closeMore(); if (DOTS[t]) seen(t, true);
  vt(() => { render(); scrollTo(0, t !== "stock" && S.scroll[t] && prev === "stock" ? S.scroll[t] : 0); });
}
addEventListener("hashchange", route);

/* ================= round 10: app shell, one scroll, collapsible sections, workbenches ================= */
let pageHoldings, pageTrading, pageTax;
TABS.push("holdings", "tax", "tradrec");
Object.assign(W.en, {
  hold: "Keep", none: "No view", holdings: "Holdings", holdingsS: "Holdings", tax: "Tax", taxS: "Tax", tradrec: "Trading record", tradrecS: "Trades",
  record: "Our record", recordS: "Our record", follow: "Worth following", followS: "Follow", market: "Market & news", marketS: "Market",
  tblView: "Table", fFall: "Falling", fBusy: "Busy today", fView: "Has a view", splitView: "List", openFull: "Open full page", fStocks: "Stocks", fFunds: "Mutual funds", fRsu: "RSUs", fWon: "Made money", fLost: "Lost money",
  backTo: n => `Back to ${n}`, listFind: "Search this list", gClose: "Close to a buy", gTop: "Best 10 today", gNear: "Just missed", pickOne: "Pick a row from the list.", noneHere: "Nothing matches.",
  fundNote: "A mutual fund. Its weekly review is in Our record.", watchAdd: "Add a stock to watch...", watchStar: "Watch this stock", watchOn: "Watching. Click to stop.", wAdded: "Watch",
  glNifty: "Market trend", glLevel: "Market price level", glLeft: "Left to invest this month", glRoom: "Profit you can book tax-free", newCalls: n => `${n} new since last time`,
  sumView: "Summary", listTrades: "Every trade", listCalls: "Every call",
});
Object.assign(DOTS, { holdings: ["portfolio"], tax: ["portfolio"], tradrec: ["own_record"], record: ["record"] });
NAV.length = 0;
NAV.push(["today", "wb_sunny"], ["holdings", "account_balance_wallet"], ["follow", "star"], ["watchlist", "visibility"], ["ideas", "query_stats"]);
const NAVQ = [["market", "newspaper", "desk"], ["tax", "receipt_long", "desk"], ["tradrec", "history", "desk"], ["record", "fact_check", "desk"]];

renderRail = function () {
  const bad = D.meta && D.meta.status && D.meta.status.ok === false; let cur = S.tab === "stock" ? S.back : S.tab; if (cur === "calls" || cur === "portfolio") cur = cur === "calls" ? "today" : "holdings";
  const cnt = { holdings: HELD.size, follow: ITEMS.filter(i => !HELD.has(i.sym) && i.v === "watch").length, watchlist: WL.size };
  const a = ([k, ic, cls]) => `<a class="nav ${cls || ""}" href="#${k}" ${cur === k ? 'aria-current="page"' : ""}><span class="ms">${ic}</span><span class="trunc lbl-l">${w(k)}</span><span class="trunc lbl-s">${w(k + "S") === k + "S" ? w(k) : w(k + "S")}</span>${cnt[k] ? `<span class="cnt num">${cnt[k]}</span>` : ""}${(k === "health" && bad) || (cur !== k && changed(k)) ? '<span class="dot" aria-label="changed"></span>' : ""}</a>`;
  const m = D.meta || {};
  $("#rail").innerHTML = `<div class="brand"><i>s</i><span>stockpilot</span></div>${NAV.map(a).join("")}
   <button class="nav phone" data-more-nav style="border:0;background:none;cursor:pointer"><span class="ms">more_horiz</span><span>${w("moreNav")}</span></button>
   <div class="rail-div"></div>${NAVQ.map(a).join("")}
   <div class="rail-gap"></div><div class="rail-div"></div>${NAV2.map(a).join("")}
   <div class="rail-foot">${w("upd")} ${esc((m.built_at || "").slice(11, 16))}${m.holdings?.days_old != null ? `<br>${w("synced")} ${w("ago", m.holdings.days_old)}` : ""}</div>`;
};
openMore = function () {
  document.body.insertAdjacentHTML("beforeend", `<div id="scrim"></div><nav id="more" aria-label="${esc(w("moreNav"))}"><div class="grab"></div>${[["market", "newspaper"], ["tax", "receipt_long"], ["tradrec", "history"], ["record", "fact_check"], ["settings", "settings"], ["feedback", "rate_review"], ["health", "monitor_heart"]].map(([k, ic]) => `<a class="nav" href="#${k}"><span class="ms">${ic}</span><span>${w(k)}</span></a>`).join("")}</nav>`);
};

/* ---------- engine ---------- */
const MODE = {}, SEL = {}, LP = {}, LSCR = {}, FOLD = store.get("fold", {}), DRAW = {};
let CURKEY = null;
const isFund2 = s => /^INF/.test(s);
const reduce = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
function starBtn(sym) { const on = WL.has(sym); return `<button class="icb star" data-star="${esc(sym)}" aria-pressed="${on}" data-tip="${esc(w(on ? "watchOn" : "watchStar"))}" aria-label="${esc(w("watchStar"))}"><span class="ms">star</span></button>`; }
const rid = r => r.id ?? r.sym;
function lrow(key, r) {
  const id = rid(r);
  return `<div class="lrow r-${r.v || "none"}" role="option" data-sel="${key}:${esc(id)}" aria-selected="${SEL[key] === id}" tabindex="0">
  ${r.chip || (r.v ? chip(r.v) : `<span class="chip v-none">${w("none")}</span>`)}
  <span class="lm"><b class="trunc">${esc(r.name)}</b><span class="ls trunc">${esc(r.sub || r.sym)}</span></span>
  <span class="lspc">${r.nospark ? "" : lsp(r.sym, 64, 24)}</span><span class="lr">${r.right || ""}</span>${r.nostar ? "<span></span>" : starBtn(r.sym)}</div>`;
}
function visibleRows(key, o) {
  const all = o.rowsFn ? o.rowsFn() : o.rows, cur = S.chip[key] || "all";
  let rows = all.filter((o.chips.find(c => c[0] === cur) || o.chips[0])[1]);
  const q = S.q.trim().toLowerCase(); if (q) rows = rows.filter(r => (r.sym + " " + r.name).toLowerCase().includes(q));
  return { all, rows };
}
function listHTML(key, o, rows) {
  if (!rows.length) return `<p class="empty">${w("noneHere")}</p>`;
  if (!o.groups) return rows.map(r => lrow(key, r)).join("");
  return o.groups.map(g => {
    const it = rows.filter(r => r.g === g.k); if (!it.length) return "";
    const open = FOLD[key + g.k] ?? !g.closed;
    return `<section class="lg" data-open="${open}"><button class="lgh r-${g.k}" data-fold="${key + g.k}:${g.closed ? 1 : 0}" aria-expanded="${open}"><span class="ms car">expand_more</span><b>${esc(g.label)}</b><span class="n num">${it.length}</span></button><div class="lgr">${it.map(r => lrow(key, r)).join("")}</div></section>`;
  }).join("");
}
const chipset = (key, o, all) => { const cur = S.chip[key] || "all"; return o.chips.map(([k, f]) => [k, all.filter(f).length]).filter(([k, n]) => n || k === "all" || k === cur).map(([k, n]) => `<button class="fchip" data-chip="${key}:${k}" aria-pressed="${cur === k}">${w(k)} <span class="num">${n}</span></button>`).join(""); };
const seg2 = (key, items) => `<span class="seg2 vt">${items.map(([m, l]) => `<button class="sg" data-mode="${key}:${m}" aria-pressed="${(MODE[key] || items[0][0]) === m}">${w(l)}</button>`).join("")}</span>`;
function listPane(key, o) {
  LP[key] = o; CURKEY = key;
  const mode = MODE[key] || "split", toggle = seg2(key, [["split", "splitView"], ["table", "tblView"]]);
  if (mode === "table") return `<div class="pagewrap">${o.lead || ""}${table(key, o.rowsFn ? o.rowsFn() : o.rows, o.chips, o.cols, { tools: (o.extra || "") + toggle })}</div>`;
  const { all, rows } = visibleRows(key, o); if (!rows.find(r => rid(r) === SEL[key])) SEL[key] = rows[0] && rid(rows[0]);
  const pane = SEL[key] != null ? (o.pane ? o.pane.html(SEL[key], rows.find(r => rid(r) === SEL[key])) : paneHTML(SEL[key])) : `<p class="muted" style="padding:24px">${w("pickOne")}</p>`;
  return `${o.lead || ""}<div class="tools"><span class="chipset">${chipset(key, o, all)}</span><label class="qf"><span class="ms" style="font-size:18px">search</span><input id="qf" value="${esc(S.q)}" placeholder="${esc(w("listFind"))}" autocomplete="off"></label>${o.extra || ""}${toggle}</div>
   <div class="lp" data-key="${key}"><div class="lp-list" role="listbox" aria-label="${esc(o.label || "")}">${listHTML(key, o, rows)}</div><aside class="lp-pane" id="lpp" data-sym="${esc(SEL[key] ?? "")}">${pane}</aside></div>`;
}
function refreshList(key) {
  const o = LP[key], l = $(".lp-list"); if (!o || !l) return; const { all, rows } = visibleRows(key, o), before = SEL[key];
  if (!rows.find(r => rid(r) === SEL[key])) SEL[key] = rows[0] && rid(rows[0]);
  l.innerHTML = listHTML(key, o, rows); $(".chipset").innerHTML = chipset(key, o, all); hydrate();
  if (SEL[key] !== before) selectRow(key, SEL[key], true);
}
function paneHTML(sym) {
  const it = BY.get(sym), h = HELD.get(sym), fund = isFund2(sym), price = it?.entry ?? WL.get(sym)?.close ?? h?.price ?? LK?.[sym]?.metrics?.close;
  const ladder = it?.stop && it?.target && it?.entry ? (() => { const sp = Math.max(4, Math.min(96, (it.entry - it.stop) / (it.target - it.stop) * 100)); return `<div class="rb" style="--sp:${sp}%"><span class="now" style="left:${sp}%"></span><span class="c num" style="left:${sp}%">${w("now")} ${px(it.entry)}</span><span class="l num dn">${w("stop")} ${px(it.stop)}</span><span class="r num up">${w("target")} ${px(it.target)}</span></div>`; })() : "";
  const holdLine = h ? `<div class="pn-hold"><span class="tag">${w("youHoldT")}</span><span class="num">${n0(Math.round(h.quantity * 1000) / 1000)}</span><span class="num">${inr(h.value)}</span><b class="num ${h.gain_pct >= 0 ? "up" : "dn"}">${spct(h.gain_pct)}</b>${h.tax_note ? `<span class="muted trunc">${esc(h.tax_note)}</span>` : ""}</div>` : "";
  const view = it ? `<div class="pn-view"><p class="bigview">${esc(say(it))}</p><div class="pn-ch"><span class="bigp num">${pct(it.p)}</span><div style="flex:1;min-width:0">${bar12(it)}</div></div>${ladder}</div>`
    : fund ? `<p class="muted pn-note">${w("fundNote")}</p>` : `<div class="ask pn-ask"><div><h3>${w("noView")}</h3><p>${w("noViewL")}</p></div><button class="btn f" data-ask="${esc(sym)}"><span class="ms">query_stats</span>${w("ask")}</button></div>`;
  return `<div class="pn-top"><div style="min-width:0"><div class="sb-chips">${it ? chip(it.v) : `<span class="chip v-none">${w("none")}</span>`}</div>
     <h2 class="trunc">${esc(nameOf(sym))}</h2><div class="muted num">${esc(sym)}</div></div>
     <div class="pn-r"><div class="px num">${price != null ? px(price) : ""}</div><div class="pn-btns">${starBtn(sym)}${fund ? "" : `<a class="btn t" href="#stock" data-open="${esc(sym)}">${w("openFull")}<span class="ms">chevron_right</span></a>`}</div></div></div>
   ${holdLine}${view}${fund ? "" : `<div class="pn-chart" data-pchart="${esc(sym)}"></div><div class="pn-facts" id="pfacts"></div>`}
   ${it && it.risks.length ? `<div class="blk pn-risk"><h3>${w("whatWrong")}</h3><ul>${it.risks.slice(0, 2).map(r => `<li class="trunc">${esc(r)}</li>`).join("")}</ul></div>` : ""}`;
}
let LK = null; lookup().then(x => { LK = x; });
function fillPane(sym) {
  if (!sym || isFund2(sym) || !$(`[data-pchart]`)) return; const it = BY.get(sym);
  lookup().then(L => { if ($("#lpp")?.dataset.sym !== sym) return; const f = $("#pfacts"); if (!f) return; const x = L[sym]; if (!x) f.remove(); else f.innerHTML = facts(x); })
    .then(() => hist(sym)).then(h => {
      const box = $(`[data-pchart="${CSS.escape(sym)}"]`); if (!box || $("#lpp")?.dataset.sym !== sym) return;
      if (!h) { box.remove(); return; }
      box.innerHTML = priceChart(it, h, box.clientWidth - 2, 130, Math.max(130, box.clientHeight - 32));
    });
}
function selectRow(key, id, quiet) {
  SEL[key] = id; $$("[data-sel]").forEach(el => el.setAttribute("aria-selected", String(el.dataset.sel === key + ":" + id)));
  const p = $("#lpp"), o = LP[key]; if (!p) return; p.dataset.sym = id ?? "";
  if (id == null) { p.innerHTML = `<p class="muted" style="padding:24px">${w("pickOne")}</p>`; return; }
  const row = visibleRows(key, o).rows.find(r => rid(r) === id);
  p.innerHTML = o.pane ? o.pane.html(id, row) : paneHTML(id);
  if (!quiet && !reduce() && p.animate) p.animate([{ opacity: .55, transform: "translateY(4px)" }, { opacity: 1, transform: "none" }], { duration: 150, easing: "ease-out" });
  o.pane ? o.pane.fill?.(id, row) : fillPane(id);
}
const _render = render;
render = function () {
  const l0 = $(".lp-list")?.scrollTop; _render();
  const sh = !!$(".lp") && innerWidth > 900; $("#app").classList.toggle("shell", sh);
  const l = $(".lp-list"); if (l) { CURKEY = $(".lp").dataset.key; if (LSCR[CURKEY]) l.scrollTop = LSCR[CURKEY]; }
  const p = $("#lpp"); if (p && p.dataset.sym) { const o = LP[CURKEY]; o?.pane ? o.pane.fill?.(p.dataset.sym) : fillPane(p.dataset.sym); }
  drawBoxes();
};
function drawBoxes() { $$("[data-draw]").forEach(b => { const f = DRAW[b.dataset.draw]; if (f) b.innerHTML = f(b.clientWidth || 600, b.clientHeight || 240); }); }
let lastW = innerWidth; addEventListener("resize", () => { clearTimeout(drawBoxes.t); drawBoxes.t = setTimeout(() => { if ((lastW > 900) !== (innerWidth > 900)) render(); else { drawBoxes(); const p = $("#lpp"); if (p?.dataset.sym) { const o = LP[CURKEY]; o?.pane ? o.pane.fill?.(p.dataset.sym) : fillPane(p.dataset.sym); } } lastW = innerWidth; }, 200); });
document.addEventListener("scroll", e => { if (e.target.classList?.contains("lp-list") && CURKEY) LSCR[CURKEY] = e.target.scrollTop; }, true);

/* watch toggles patch the page in place; nothing re-renders */
function starSync(s) {
  $$(`[data-star="${CSS.escape(s)}"]`).forEach(b => { const on = WL.has(s); b.setAttribute("aria-pressed", String(on)); b.dataset.tip = w(on ? "watchOn" : "watchStar"); });
  renderRail(); if (S.tab === "watchlist" && $(".lp")) refreshList("wl"); if (S.tab === "stock") render();
}
addWatch = function (s) { WL.set(s, { symbol: s, name: nameOf(s), why: [], close: BY.get(s)?.entry ?? LK?.[s]?.metrics?.close }); starSync(s); queue("watchlist_add", { symbol: s, exchange: SMAP.get(s)?.exchange || "NSE" }, w("added"), () => { WL.delete(s); starSync(s); }); };
removeWatch = function (s) { const old = WL.get(s); WL.delete(s); starSync(s); queue("watchlist_remove", { symbol: s, exchange: SMAP.get(s)?.exchange || "NSE" }, w("removed"), () => { WL.set(s, old); starSync(s); }); };

/* events (capture phase: these stop the older handlers that re-rendered the whole page) */
document.addEventListener("click", e => {
  let x = e.target.closest("[data-star]");
  if (x) { e.stopPropagation(); e.preventDefault(); const s = x.dataset.star; WL.has(s) ? removeWatch(s) : addWatch(s); return; }
  x = e.target.closest("[data-fold]");
  if (x) { e.stopPropagation(); const k = x.dataset.fold.split(":")[0], sec = x.closest(".lg"), open = sec.dataset.open !== "true"; FOLD[k] = open; store.set("fold", FOLD); sec.dataset.open = open; x.setAttribute("aria-expanded", String(open)); return; }
  x = e.target.closest("[data-chip]");
  if (x && $(".lp")) { const [k, v] = x.dataset.chip.split(":"); if (LP[k]) { e.stopPropagation(); S.chip[k] = v; refreshList(k); return; } }
  x = e.target.closest("[data-sel]");
  if (x) { const i = x.dataset.sel.indexOf(":"), key = x.dataset.sel.slice(0, i), id = x.dataset.sel.slice(i + 1); e.stopPropagation(); if (innerWidth <= 900) { const o = LP[key]; const sym = o?.pane ? (o.rows.find(r => rid(r) === id)?.sym) : id; if (!o?.pane || sym) { SEL[key] = id; openStock(sym || id); } } else selectRow(key, id); return; }
  x = e.target.closest("[data-mode]"); if (x) { const [k, m] = x.dataset.mode.split(":"); MODE[k] = m; e.stopPropagation(); render(); return; }
  x = e.target.closest("[data-rng]"); if (x) { S.rng = x.dataset.rng; e.stopPropagation(); render(); return; }
  x = e.target.closest("[data-wladd]"); if (x) { e.stopPropagation(); const s = x.dataset.wladd; $("#wla").value = ""; $("#wlr").hidden = true; addWatch(s); }
}, true);
document.addEventListener("input", e => {
  if (e.target.id === "qf" && $(".lp") && LP[CURKEY]) { e.stopPropagation(); S.q = e.target.value; refreshList(CURKEY); return; }
  if (e.target.id === "wla") { e.stopPropagation(); const q = e.target.value.trim(), box = $("#wlr"), r = q ? find(q).filter(s => !WL.has(s)).slice(0, 6) : [];
    box.innerHTML = r.map(s => `<li role="option" data-wladd="${esc(s)}"><span class="trunc">${esc(nameOf(s))} <span class="muted num">${esc(s)}</span></span><span class="tag"><span class="ms" style="font-size:16px">add</span>${w("wAdded")}</span></li>`).join("") || (q ? `<li class="muted">${w("noMatch")}</li>` : ""); box.hidden = !box.innerHTML; }
}, true);
document.addEventListener("keydown", e => {
  if (e.key === "Escape" && S.tab === "stock" && !$("#sr").hidden === false && !/INPUT/.test(document.activeElement?.tagName || "")) { history.back(); return; }
  const l = $(".lp-list"); if (!l || /INPUT|TEXTAREA/.test(document.activeElement?.tagName || "")) return;
  const dn = e.key === "j" || (e.key === "ArrowDown" && l.contains(document.activeElement)), up = e.key === "k" || (e.key === "ArrowUp" && l.contains(document.activeElement));
  if (!dn && !up) return; e.preventDefault();
  const rows = $$(".lrow", l).filter(r => r.offsetParent), i = rows.findIndex(r => r.getAttribute("aria-selected") === "true"), n = rows[Math.max(0, Math.min(rows.length - 1, i + (dn ? 1 : -1)))];
  if (n) { const v = n.dataset.sel; selectRow(v.slice(0, v.indexOf(":")), v.slice(v.indexOf(":") + 1)); n.focus({ preventScroll: true }); n.scrollIntoView({ block: "nearest" }); }
});
document.addEventListener("focusout", e => { if (e.target.id === "wla") setTimeout(() => { const b = $("#wlr"); if (b) b.hidden = true; }, 150); });
document.addEventListener("mousedown", e => { if (e.target.closest("#wlr")) e.preventDefault(); });

/* ---------- full page: a fixed strip with a big Back ---------- */
const _pageStock = pageStock;
pageStock = function () {
  const sym = S.sym; if (!sym) return pageToday();
  const html = _pageStock().replace(/<a class="btn x back"[^>]*>.*?<\/a>/s, "");
  const it = BY.get(sym), price = it?.entry ?? WL.get(sym)?.close;
  return `<div class="fullbar"><a class="btn f back2" href="#${esc(S.back)}" data-back><span class="ms">arrow_back</span>${w("backTo", w(S.back === "calls" ? "today" : S.back))}</a><b class="trunc fb-n">${esc(nameOf(sym))}</b><span class="num fb-p">${price != null ? px(price) : ""}</span>${starBtn(sym)}</div>${html}`;
};

/* ---------- Today ---------- */
function glance() {
  const m = D.market || {}, v = m.valuation || {}, cheapP = v.percentile != null ? 100 - v.percentile : null, b = D.today?.budget, t = D.portfolio?.tax || {};
  return `<div class="glance">${kv(w("glNifty"), w(m.nifty_above_200dma ? "up" : "down"), "", m.nifty_above_200dma ? "up" : "dn")}
   ${cheapP != null ? kv(w("glLevel"), w(cheapP > 60 ? "cheapW" : cheapP < 30 ? "dearW" : "fairW"), "", cheapP > 60 ? "up" : cheapP < 30 ? "dn" : "") : ""}
   ${b ? kv(w("glLeft"), inr(b.left), "") : ""}${t.harvest_room != null ? kv(w("glRoom"), inr(t.harvest_room), "") : ""}</div>`;
}
const leadH = (h1, p, extra) => `<header class="lead"><div class="lead-t">${extra || ""}<h1>${h1}</h1>${p ? `<p class="clamp">${p}</p>` : ""}</div></header>`;
const callCols = () => [
  { l: "cStock", v: r => r.name, h: stockCell }, { l: "cView", v: r => VORD[r.it.v], h: viewCell },
  { l: "cChance", v: r => r.it.p, h: r => chanceCell(r.it), t: w("chance") },
  { l: "cWhyL", h: r => `<span class="msg">${esc(say(r.it))}</span>`, c: "h2" },
  { l: "money", h: r => `<div class="mc">${moneyCell(r.it)}</div>`, c: "h1" }, { l: "c6", h: r => lsp(r.sym), c: "h3" }];
const chanceMini = it => `<b class="num">${pct(it.p)}</b>${mini(it)}`;
function callRow(i) {
  const money = (i.v === "sell" || i.v === "weak") && i.qty ? `<small class="num">${inr(i.qty * i.entry)}</small>` : i.v === "buy" && i.target ? `<small class="num up">→ ${px(i.target)}</small>` : "";
  return { sym: i.sym, name: i.name, it: i, v: i.v, g: i.v, sub: say(i), right: `<span class="chance" data-tip="${esc(chanceTip(i))}"><b class="num">${pct(i.p)}</b>${mini(i)}</span>${money}` };
}
pageToday = function () {
  const worth = i => (i.qty || 0) * (i.entry || 0), rows = ITEMS.filter(i => ["sell", "weak", "buy", "hold", "watch"].includes(i.v));
  const ord = { sell: 0, weak: 1, buy: 2, hold: 3, watch: 4 };
  rows.sort((a, b) => ord[a.v] - ord[b.v] || (a.v === "sell" || a.v === "weak" ? worth(b) - worth(a) : b.p - a.p));
  const sells = rows.filter(i => i.v === "sell").length, weaks = rows.filter(i => i.v === "weak").length, buys = rows.filter(i => i.v === "buy").length;
  const lead = `<header class="lead"><div class="lead-t"><div class="eyebrow">${esc(dayLine())}</div><h1>${esc(w("head", sells, weaks, buys))}</h1>
     <p class="clamp">${esc(S.lang === "bn" && D.calls?.market_view_bn ? D.calls.market_view_bn : (D.today?.market_mood || ""))}</p></div>${glance()}</header>`;
  return listPane("today", { rows: rows.map(callRow), lead, label: w("today"),
    chips: [["all", () => true], ["sell", r => r.v === "sell"], ["weak", r => r.v === "weak"], ["buy", r => r.v === "buy"], ["hold", r => r.v === "hold"], ["watch", r => r.v === "watch"]],
    groups: [{ k: "sell", label: w("sell") }, { k: "weak", label: w("weak") }, { k: "buy", label: w("buy") }, { k: "hold", label: w("hold"), closed: 1 }, { k: "watch", label: w("gClose"), closed: 1 }], cols: callCols() });
};

/* ---------- Holdings (stocks, mutual funds, RSUs) ---------- */
const RSU_SAMPLE = { symbol: "NOW", name: "ServiceNow, Inc.", group: "RSUs", quantity: null, sample: true };
pageHoldings = function () {
  const p = D.portfolio; if (!p) return `<p class="empty">${w("noData")}</p>`;
  const cost = p.holdings.reduce((a, h) => a + (h.avg_cost || 0) * (h.quantity || 0), 0), gain = p.total_value - cost;
  const lead = leadH(w("holdings"), `<b class="num">${lakh(p.total_value)}</b> · <span class="num ${gain >= 0 ? "up" : "dn"}">${gain >= 0 ? "+" : "−"}${lakh(Math.abs(gain))} (${spct(gain / cost)})</span> · ${esc(p.headline || "")}`);
  const rows = p.holdings.map(h => { const it = BY.get(h.symbol), v = it?.v || (["sell", "weak", "hold", "buy", "watch"].includes(h.verdict) ? h.verdict : null);
    return { sym: h.symbol, name: clean(h.name), it, h, v, sub: isFund2(h.symbol) ? "Mutual fund" : `${n0(h.quantity)} shares`, value: h.value, nospark: isFund2(h.symbol),
      right: `<b class="num">${inr(h.value)}</b><small class="num ${h.gain_pct >= 0 ? "up" : "dn"}">${spct(h.gain_pct)}</small>` }; }).sort((a, b) => b.value - a.value);
  rows.push({ sym: RSU_SAMPLE.symbol, name: RSU_SAMPLE.name, it: null, h: RSU_SAMPLE, v: null, chip: `<span class="chip v-none">RSU</span>`, sub: "Sample row. Shares and value arrive when the Fidelity statements are read.", value: 0, nospark: true, nostar: true, right: `<small class="muted">sample</small>` });
  return listPane("hold", { rows, lead, label: w("holdings"),
    chips: [["all", () => true], ["fStocks", r => !isFund2(r.sym) && !r.h.sample], ["fFunds", r => isFund2(r.sym)], ["fRsu", r => !!r.h.sample], ["sell", r => r.v === "sell"], ["weak", r => r.v === "weak"]],
    cols: [{ l: "hHolding", v: r => r.name, h: r => `<div class="nm trunc">${esc(r.name)}</div><div class="sy num">${esc(r.sym)} · ${r.h.quantity != null ? n0(r.h.quantity) + " shares" : "RSU"}</div>` },
      { l: "cView", v: r => r.it ? VORD[r.it.v] : 9, h: r => r.v ? chip(r.v) : chip("none") },
      { l: "hValue", v: r => r.h.value ?? 0, h: r => `<span class="num">${r.h.value != null ? inr(r.h.value) : "–"}</span>`, r: 1 },
      { l: "hGain", v: r => r.h.gain_pct, h: r => r.h.gain_pct != null ? `<span class="num ${r.h.gain_pct >= 0 ? "up" : "dn"}">${spct(r.h.gain_pct)}</span>` : "–", r: 1, c: "h1" },
      { l: "hShare", v: r => r.h.share, h: r => r.h.share != null ? `<span class="num">${pct(r.h.share, 1)}</span>` : "–", r: 1, c: "h2" },
      { l: "hHeld", v: r => r.h.tax_note, h: r => `<span class="muted">${esc(r.h.tax_note || "")}</span>`, c: "h3" }] });
};

/* ---------- Worth following, Watchlist (star + inline add), Ideas ---------- */
pageFollow = function () {
  const rows = ITEMS.filter(i => !HELD.has(i.sym) && i.v === "watch").sort((a, b) => b.p - a.p).map(i => ({ sym: i.sym, name: i.name, it: i, v: i.v, sub: i.would ? `${w("wouldBuy")}: ${i.would}` : say(i), right: `<span class="chance" data-tip="${esc(chanceTip(i))}"><b class="num">${pct(i.p)}</b>${mini(i)}</span><small class="num">${px(i.entry)}</small>` }));
  return listPane("follow", { rows, lead: leadH(w("follow"), w("followP")), label: w("follow"), chips: [["all", () => true]], cols: [
    { l: "cStock", v: r => r.name, h: stockCell }, { l: "cChance", v: r => r.it.p, h: r => chanceCell(r.it) }, { l: "cPrice", v: r => r.it.entry, h: r => `<span class="num">${px(r.it.entry)}</span>`, r: 1 },
    { l: "wouldBuy", h: r => `<span class="msg">${esc(r.it.would || say(r.it))}</span>`, c: "h2" }, { l: "c6", h: r => lsp(r.sym), c: "h3" }] });
};
pageWatchlist = function () {
  const mk = r => { const it = BY.get(r.symbol); return { sym: r.symbol, name: clean(r.name), it, v: it?.v || null, held: HELD.has(r.symbol), w: r,
    sub: (r.why || []).filter(x => !/^Today's call/i.test(x))[0] || "", right: `<b class="num">${px(r.close)}</b>${r.dist_200dma == null ? "" : `<small class="num ${r.dist_200dma >= 0 ? "up" : "dn"}">${w("trendT", Math.round(r.dist_200dma * 100))}</small>`}` }; };
  const rowsFn = () => [...WL.values()].map(mk);
  const extra = `<label class="qf wla"><span class="ms" style="font-size:18px">add</span><input id="wla" placeholder="${esc(w("watchAdd"))}" autocomplete="off" role="combobox" aria-expanded="false"><ul class="wlr" id="wlr" role="listbox" hidden></ul></label>`;
  return listPane("wl", { rows: rowsFn(), rowsFn, extra, lead: leadH(w("watchlist"), w("wlP")), label: w("watchlist"),
    chips: [["all", () => true], ["fView", r => !!r.it], ["fHeld", r => r.held], ["fFall", r => (r.w.dist_200dma ?? 0) < -0.05], ["fBusy", r => (r.w.volume_spike || 0) >= 2]],
    cols: [{ l: "cStock", v: r => r.name, h: stockCell }, { l: "cView", v: r => r.it ? VORD[r.it.v] : 9, h: viewCell },
      { l: "cChance", v: r => r.it?.p ?? -1, h: r => r.it ? chanceCell(r.it) : `<span class="muted">–</span>` },
      { l: "cPrice", v: r => r.w.close, h: r => `<span class="num">${px(r.w.close)}</span>`, r: 1, c: "h1" },
      { l: "cTrend", v: r => r.w.dist_200dma, h: r => r.w.dist_200dma == null ? "–" : `<span class="num ${r.w.dist_200dma >= 0 ? "up" : "dn"}">${w("trendT", Math.round(r.w.dist_200dma * 100))}</span>`, r: 1, c: "h2" },
      { l: "c6", h: r => lsp(r.sym), c: "h2" }] });
};
pageIdeas = function () {
  const mk = (x, near) => ({ sym: x.symbol, name: clean(x.name), sector: x.industry, x, it: BY.get(x.symbol), v: BY.get(x.symbol)?.v || null, near, g: near ? "near" : "top",
    sub: (() => { const L = rankLines(x.scores); return x.trigger ? `${w("cIf")}: ${x.trigger}` : L[0].t; })(), right: `<b class="num">#${x.rank}</b><small class="num">${px(x.close)}</small>` });
  const rows = [...(D.ideas?.ranking || []).map(x => mk(x, false)), ...(D.ideas?.near_misses || []).map(x => mk(x, true))];
  return listPane("ideas", { rows, lead: leadH(w("ideas"), w("ideasP")), label: w("ideas"), chips: [["all", () => true], ["fTop", r => !r.near], ["fNear", r => r.near]],
    groups: [{ k: "top", label: w("gTop") }, { k: "near", label: w("gNear") }],
    cols: [{ l: "cRank", v: r => r.x.rank, h: r => `<b class="num">${r.x.rank}</b>` }, { l: "cStock", v: r => r.name, h: stockCell },
      { l: "cWhyR", h: r => `<span class="msg">${esc(r.sub)}</span>`, c: "h1" }, { l: "cPrice", v: r => r.x.close, h: r => `<span class="num">${px(r.x.close)}</span>`, r: 1, c: "h2" },
      { l: "c6", v: r => r.x.ret_6m, h: r => `<span class="num ${r.x.ret_6m >= 0 ? "up" : "dn"}">${spct(r.x.ret_6m, 0)}</span>`, r: 1, c: "h2" }, { l: "cView", v: r => r.it ? VORD[r.it.v] : 9, h: viewCell }] });
};

/* ---------- workbench pieces ---------- */
const extra2 = {}; ["trades_closed", "indices", "flows"].forEach(n => getJSON(n).then(v => { extra2[n] = v; if (["tradrec", "market", "record"].includes(S.tab)) render(); }).catch(() => { extra2[n] = null; }));
const wcard = (span, title, plain, body, cls = "") => `<section class="card wk s${span} ${cls}"><h3>${title}</h3>${plain ? `<p class="muted wk-p">${plain}</p>` : ""}${body}</section>`;
const chbox = (id, fn, h = 240) => { DRAW[id] = fn; return `<div class="chbox" data-draw="${id}" style="height:${h}px"></div>`; };
const mlabel = m => { const [y, mo] = m.split("-"); return MON[+mo - 1] + " " + y.slice(2); };
function curve(dates, vals, W0, H, lab, fmt, color) {
  const n = vals.length; if (n < 2) return ""; const lo = Math.min(0, ...vals), hi = Math.max(0, ...vals), pd = (hi - lo) * .08 || 1, L = 6, R = 10, T = 10, B = 24;
  const x = i => L + (W0 - L - R) * i / (n - 1), y = v => T + (H - T - B) * (1 - (v - (lo - pd)) / ((hi + pd) - (lo - pd))), id = "k" + (cid++);
  const p = vals.map((v, i) => (i ? "L" : "M") + x(i).toFixed(1) + " " + y(v).toFixed(1)).join("");
  CH.set(id, { type: "sp", h: { d: dates, c: vals }, x, y, n, W: W0, L, R, lab, fmt });
  const xs = [0, n >> 1, n - 1].map(i => `<text class="ax" x="${x(i)}" y="${H - 6}" text-anchor="${i === 0 ? "start" : i === n - 1 ? "end" : "middle"}">${esc(mlabel(dates[i].slice(0, 7)))}</text>`).join("");
  return `<svg class="pc sp2" data-id="${id}" viewBox="0 0 ${W0} ${H}" style="height:${H}px" role="img"><line class="grd" x1="${L}" x2="${W0 - R}" y1="${y(0)}" y2="${y(0)}"/><path class="la" d="${p}L${x(n - 1)} ${y(0)}L${x(0)} ${y(0)}Z"/><path class="lc" d="${p}" style="stroke:${color || "var(--pri)"}"/>${xs}<circle class="end" cx="${x(n - 1)}" cy="${y(vals[n - 1])}" r="4.5"/><line class="xh" y1="${T}" y2="${H - B}"/><circle class="hd" r="5"/></svg>`;
}
const barsTip = (rows, W0, H) => bars(rows, W0, H);
const tile = (k, v, s) => `<div class="tile"><span class="k">${k}</span><span class="v num">${v}</span>${s ? `<span class="s">${s}</span>` : ""}</div>`;

/* ---------- Tax ---------- */
pageTax = function () {
  const p = D.portfolio; if (!p) return `<p class="empty">${w("noData")}</p>`; const t = p.tax || {}, asof = D.meta?.calls_on || D.today?.as_of || "";
  const lots = []; p.holdings.forEach(h => (h.lots || []).forEach(l => lots.push({ h, l, gain: (h.price - l.cost) * l.quantity })));
  const lt = lots.filter(x => x.l.long_term), st = lots.filter(x => !x.l.long_term), sum = a => a.reduce((s, x) => s + x.gain, 0);
  const ltG = sum(lt), stG = sum(st), room = t.harvest_room || 0, used = t.realised_gain || 0;
  const byM = {}; st.filter(x => x.l.turns_long_term_on).forEach(x => { const m = x.l.turns_long_term_on.slice(0, 7); (byM[m] ||= { n: 0, g: 0 }); byM[m].n++; byM[m].g += x.gain; });
  const months = Object.keys(byM).sort().slice(0, 12);
  DRAW.taxm = (W0, H) => bars(months.map(m => ({ label: mlabel(m), v: byM[m].g, tip: `${mlabel(m)}: ${byM[m].n} purchase${byM[m].n > 1 ? "s" : ""} turn long-term; gain on them ${inr(byM[m].g)}` })), W0, H);
  const losers = p.holdings.filter(h => h.gain_pct < 0 && !isFund2(h.symbol)).map(h => ({ h, loss: (h.price - h.avg_cost) * h.quantity })).sort((a, b) => a.loss - b.loss).slice(0, 8);
  const tot = Math.abs(ltG) + Math.abs(stG) || 1;
  return `<div class="pagewrap">${leadH(w("tax"), "Your profit and loss for tax, in plain words: what you booked, what you are sitting on, and when it gets cheaper to sell.")}<div class="tiles wk-t">${tile("Profit booked this year", inr(used), t.fy ? `Financial year ${esc(t.fy)}`: "")}${tile("Profit you can still book tax-free", inr(room), "Long-term gains up to this amount pay no tax this year.")}${tile("Gain on shares held over a year", inr(ltG), "These already qualify for the lower long-term tax.")}${tile("Gain on shares held under a year", inr(stG), "Selling these early is taxed at the higher rate.")}</div>
   <div class="wgrid">
   ${wcard(6, "Where your gains sit", "Long-term gains are taxed less. The bar shows how much of your paper gain is long-term already.", `<div class="split"><i style="width:${Math.abs(ltG) / tot * 100}%;background:var(--gain)" data-tip="Held over a year: ${inr(ltG)}"></i><i style="width:${Math.abs(stG) / tot * 100}%;background:var(--warn)" data-tip="Held under a year: ${inr(stG)}"></i></div><div class="legend2"><span><i style="background:var(--gain)"></i>Over a year <b class="num">${inr(ltG)}</b></span><span><i style="background:var(--warn)"></i>Under a year <b class="num">${inr(stG)}</b></span></div>`)}
   ${wcard(6, "Tax-free room used", "Up to this much long-term profit can be booked each year with no tax.", `<div class="meter big"><i style="width:${Math.min(100, used / (used + room || 1) * 100)}%"></i></div><p class="num wk-big">${inr(used)} <span class="muted">of ${inr(used + room)}</span></p>`)}
   ${months.length ? wcard(12, "When short-term gains turn long-term", "Each bar is one month. Shares bought then pass one year, so selling after that date is taxed less.", chbox("taxm", DRAW.taxm, 240)) : ""}
   ${losers.length ? wcard(12, "If you want to book a loss", "Selling these would book a loss, which can reduce the tax on your profits.", `<table class="grid mini"><thead><tr><th><button tabindex="-1">Stock</button></th><th class="r"><button tabindex="-1">Shares</button></th><th class="r"><button tabindex="-1">Loss if sold</button></th><th class="h2"><button tabindex="-1">Held</button></th></tr></thead><tbody>${losers.map(x => `<tr class="r" data-open="${esc(x.h.symbol)}" tabindex="0"><td><div class="nm trunc">${esc(clean(x.h.name))}</div><div class="sy num">${esc(x.h.symbol)}</div></td><td class="r num">${n0(x.h.quantity)}</td><td class="r num dn">${inr(x.loss)}</td><td class="h2 muted">${esc(x.h.tax_note || "")}</td></tr>`).join("")}</tbody></table>`) : ""}
   ${wcard(12, "Notes", "", `<div class="lines">${(t.notes || []).map(n => `<p>${esc(n)}</p>`).join("")}</div>${t.itr_pack ? `<div style="margin-top:12px"><a class="btn t" href="${esc(t.itr_pack)}"><span class="ms">arrow_downward</span>${w("pPack")}</a></div>` : ""}`)}
   </div></div>`;
};

/* ---------- Trading record: summary charts, every trade as a list with a pane ---------- */
function paneTrade(id, r) {
  if (!r) return "";
  const t = r.t, pctG = t.cost ? t.gain / t.cost : 0, won = t.gain > 0;
  return `<div class="pn-top"><div style="min-width:0"><div class="sb-chips"><span class="chip ${won ? "v-buy" : "v-sell"}">${won ? w("fWon") : w("fLost")}</span></div><h2 class="trunc">${esc(nameOf(t.symbol))}</h2><div class="muted num">${esc(t.symbol)} · sold ${mdate(t.sold_on)}</div></div>
    <div class="pn-r"><div class="px num ${won ? "up" : "dn"}">${won ? "+" : "−"}${inr(Math.abs(t.gain))}</div><span class="muted num">${spct(pctG)}</span></div></div>
   <div class="tiles pn-tiles">${tile("Shares sold", n0(Math.round(t.quantity * 1000) / 1000))}${tile("Held for", Math.round(t.days) + " days", t.days >= 365 ? "Long-term" : "Short-term")}${tile("You paid", inr(t.cost))}${tile("You got", inr(t.proceeds))}</div>
   <div class="pn-pg"><div><span>You paid</span><i style="width:${Math.min(100, t.cost / Math.max(t.cost, t.proceeds) * 100)}%"></i><b class="num">${inr(t.cost)}</b></div><div><span>You got</span><i class="${won ? "w" : "l"}" style="width:${Math.min(100, t.proceeds / Math.max(t.cost, t.proceeds) * 100)}%"></i><b class="num">${inr(t.proceeds)}</b></div></div>
   <p class="bigview">${esc(`You sold ${n0(Math.round(t.quantity))} shares after ${Math.round(t.days)} days and ${won ? "made" : "lost"} ${inr(Math.abs(t.gain))} (${spct(Math.abs(pctG), 0).replace("+", "")}).`)}<span id="aftr"></span></p>
   <div class="pn-chart" data-pchart="${esc(t.symbol)}"></div>`;
}
function fillTrade(id, r) {
  if (!r) return; const t = r.t;
  hist(t.symbol).then(h => {
    const box = $(`[data-pchart="${CSS.escape(t.symbol)}"]`); if (!box || $("#lpp")?.dataset.sym !== id) return;
    if (!h) { box.remove(); return; }
    box.innerHTML = priceChart(null, h, box.clientWidth - 2, 130, Math.max(150, box.clientHeight - 30));
    const px0 = t.proceeds / t.quantity, last = h.close[h.close.length - 1]; if (last) { const a = $("#aftr"); if (a) a.textContent = ` It trades at ${px(last)} now, ${last >= px0 ? "above" : "below"} your sale price of ${px(px0)}.`; }
  });
}
pageTrading = function () {
  const o = D.own_record || {}, T = extra2.trades_closed, mode = MODE.trade || "sum";
  const seg = seg2("trade", [["sum", "sumView"], ["list", "listTrades"]]);
  if (mode === "list" && T) {
    const rows = T.map((t, i) => ({ id: String(i), sym: t.symbol, name: clean(nameOf(t.symbol)), t, v: null, chip: `<span class="chip ${t.gain > 0 ? "v-buy" : "v-sell"}">${t.gain > 0 ? "Won" : "Lost"}</span>`, g: t.sold_on.slice(0, 4), nospark: true, nostar: true,
      sub: `Sold ${mdate(t.sold_on)} · held ${Math.round(t.days)} days`, right: `<b class="num ${t.gain > 0 ? "up" : "dn"}">${t.gain > 0 ? "+" : "−"}${inr(Math.abs(t.gain))}</b><small class="num">${spct(t.cost ? t.gain / t.cost : 0, 0)}</small>` }));
    const years = [...new Set(rows.map(r => r.g))].sort().reverse();
    return listPane("trade", { rows, label: w("tradrec"), lead: `<header class="lead"><div class="lead-t"><h1>${w("tradrec")}</h1><p class="clamp">${esc(o.lines?.[0] || "")}</p></div>${seg}</header>`, extra: "",
      chips: [["all", () => true], ["fWon", r => r.t.gain > 0], ["fLost", r => r.t.gain <= 0]], groups: years.map((y, i) => ({ k: y, label: y, closed: i > 1 ? 1 : 0 })),
      pane: { html: (id, r) => paneTrade(id, r), fill: fillTrade },
      cols: [{ l: "cStock", v: r => r.name, h: r => `<div class="nm trunc">${esc(r.name)}</div><div class="sy num">${esc(r.sym)}</div>` }, { l: "", v: r => r.t.sold_on, h: r => `<span class="num">${mdate(r.t.sold_on)}</span>` }, { l: "", v: r => r.t.days, h: r => `<span class="num">${Math.round(r.t.days)} days</span>`, r: 1 }, { l: "", v: r => r.t.gain, h: r => `<b class="num ${r.t.gain > 0 ? "up" : "dn"}">${inr(r.t.gain)}</b>`, r: 1 }] });
  }
  const mons = (o.by_month || []).slice(-24); let cum = 0; const cv = mons.map(m => (cum += m.gain)), cd = mons.map(m => m.month + "-28");
  DRAW.tm = (W0, H) => bars(mons.map(x => ({ label: mlabel(x.month), v: x.gain, tip: `${mlabel(x.month)}: ${x.closed} trades closed, ${x.winners} made money; ${x.gain >= 0 ? "gain" : "loss"} ${inr(Math.abs(x.gain))}` })), W0, H);
  DRAW.tc = (W0, H) => curve(cd, cv, W0, H, "Total so far", v => inr(v));
  const buckets = [[0, 30, "Under 1 month"], [30, 90, "1 to 3 months"], [90, 180, "3 to 6 months"], [180, 365, "6 to 12 months"], [365, 1e9, "Over a year"]];
  const hb = T ? buckets.map(([a, b, l]) => ({ l, w: T.filter(t => t.days >= a && t.days < b && t.gain > 0).length, x: T.filter(t => t.days >= a && t.days < b && t.gain <= 0).length })) : [];
  const mx = Math.max(1, ...hb.map(b => b.w + b.x));
  return `<div class="pagewrap"><header class="lead"><div class="lead-t"><h1>${w("tradrec")}</h1><p class="clamp">${esc(o.lines?.[0] || "")}</p></div>${seg}</header>
   <div class="tiles wk-t">${tile(w("rClosed"), o.closed ?? "–")}${tile(w("rWin"), (o.win_rate ?? "–") + "%", `${o.winners} of ${o.closed} made money`)}${tile(w("rHeldW"), Math.round(o.avg_days_winners || 0) + " " + w("days"), `${w("rHeldL")}: ${Math.round(o.avg_days_losers || 0)} ${w("days")}`)}${tile(w("rEarly"), (o.sold_early?.share ?? "–") + "%", w("rEarlyS"))}${tile(w("rBeat"), (o.vs_nifty?.share ?? "–") + "%", `${o.vs_nifty?.beat} of ${o.vs_nifty?.checked} trades beat the Nifty`)}</div>
   <div class="wgrid">
   ${wcard(6, "Profit and loss each month", "Green months made money, red months lost it. Each bar is the sum of trades you closed that month.", chbox("tm", DRAW.tm))}
   ${wcard(6, "Total profit so far", "Every closed trade added up over time. Hover for the running total.", chbox("tc", DRAW.tc))}
   ${hb.length ? wcard(6, "How long you held", "Winners and losers by how long you kept them. Green is a trade that made money.", `<div class="hbars">${hb.map(b => `<div class="hb"><span>${b.l}</span><span class="hbt"><i class="w" style="width:${b.w / mx * 100}%" data-tip="${b.w} winners"></i><i class="l" style="width:${b.x / mx * 100}%" data-tip="${b.x} losers"></i></span><b class="num">${b.w + b.x}</b></div>`).join("")}</div>`) : ""}
   ${wcard(6, "What this says", "", `<div class="lines">${(o.lines || []).map(l => `<p>${esc(l)}</p>`).join("")}</div>`)}
   </div></div>`;
};

/* ---------- Our record: how sure we were, every call with its outcome ---------- */
function paneCall(id, r) {
  if (!r) return ""; const c = r.c, it = BY.get(c.symbol), sc = k => c["score_" + k] == null ? `<span class="muted">Not scored yet</span>` : spct(c["score_" + k]);
  return `<div class="pn-top"><div style="min-width:0"><div class="sb-chips">${r.chip}</div><h2 class="trunc">${esc(nameOf(c.symbol))}</h2><div class="muted num">${esc(c.symbol)} · called ${mdate(c.made_on)}</div></div><div class="pn-r"><div class="px num">${pct(c.probability)}</div><span class="muted">our chance</span></div></div>
   <div class="tiles pn-tiles">${tile("Our chance", pct(c.probability), "That it beats the market")}${tile("Usual for stocks like it", pct(c.base_rate), "What happened to similar stocks")}${tile("Money in the call", c.size_inr ? inr(c.size_inr) : "None", "")}</div>
   <div class="pn-score"><div><span class="k">After 1 month</span>${sc("1m")}</div><div><span class="k">After 3 months</span>${sc("3m")}</div><div><span class="k">After 6 months</span>${sc("6m")}</div></div>
   ${it ? `<p class="bigview">${esc(say(it))}</p>` : ""}<div class="pn-chart" data-pchart="${esc(c.symbol)}"></div>`;
}
pageRecord = function () {
  const r = D.record || {}, mode = MODE.rec || "sum", seg = seg2("rec", [["sum", "sumView"], ["list", "listCalls"]]), calls = r.calls || [];
  if (mode === "list") {
    const rows = calls.map((c, i) => ({ id: String(i), sym: c.symbol, name: clean(nameOf(c.symbol)), c, v: ACT[c.action] === "sell" ? "sell" : c.action === "hold" ? "hold" : c.action, nospark: true, nostar: true, sub: `Called ${mdate(c.made_on)} · not scored yet`, right: `<span class="chance"><b class="num">${pct(c.probability)}</b></span>` }));
    rows.forEach(x => { x.chip = chip(x.v); });
    const acts = [...new Set(rows.map(x => x.v))];
    return listPane("rec", { rows, label: w("record"), lead: `<header class="lead"><div class="lead-t"><h1>${w("record")}</h1><p class="clamp">${esc(r.headline || "")}</p></div>${seg}</header>`,
      chips: [["all", () => true], ...acts.map(a => [a, x => x.v === a])], pane: { html: paneCall, fill: (id, row) => row && hist(row.c.symbol).then(h => { const box = $(`[data-pchart="${CSS.escape(row.c.symbol)}"]`); if (!box || $("#lpp")?.dataset.sym !== id) return; if (!h) return box.remove(); box.innerHTML = priceChart(null, h, box.clientWidth - 2, 130, Math.max(150, box.clientHeight - 30)); }) },
      cols: [{ l: "cStock", v: r => r.name, h: r => `<div class="nm trunc">${esc(r.name)}</div><div class="sy num">${esc(r.sym)}</div>` }, { l: "cView", v: r => r.v, h: r => chip(r.v) }, { l: "cChance", v: r => r.c.probability, h: r => `<span class="num">${pct(r.c.probability)}</span>` }, { l: "", v: r => r.c.made_on, h: r => `<span class="num">${mdate(r.c.made_on)}</span>` }] });
  }
  const cnt = {}; calls.forEach(c => { cnt[c.action] = (cnt[c.action] || 0) + 1; });
  const bins = Array.from({ length: 12 }, (_, i) => ({ lo: .2 + i * .05, n: 0 })); calls.forEach(c => { const i = Math.max(0, Math.min(11, Math.floor((c.probability - .2) / .05))); bins[i].n++; });
  DRAW.rc = (W0, H) => bars(Object.entries(cnt).map(([k, n]) => ({ label: w(ACT[k] === "sell" ? "sell" : k), v: n, tip: `${n} ${w(ACT[k] === "sell" ? "sell" : k)} calls` })), W0, H);
  DRAW.rb = (W0, H) => bars(bins.map(b => ({ label: Math.round(b.lo * 100) + "", v: b.n, tip: `${b.n} calls with a chance of ${Math.round(b.lo * 100)} to ${Math.round(b.lo * 100) + 5}%` })), W0, H);
  DRAW.cal = (W0, H) => { const L = 36, B = 28, T = 10, R = 12, x = v => L + (W0 - L - R) * v, y = v => T + (H - T - B) * (1 - v); const g = [0, .25, .5, .75, 1].map(v => `<line class="grd" x1="${L}" x2="${W0 - R}" y1="${y(v)}" y2="${y(v)}"/><text class="ax" x="${L - 6}" y="${y(v) + 4}" text-anchor="end">${Math.round(v * 100)}%</text><text class="ax" x="${x(v)}" y="${H - 8}" text-anchor="middle">${Math.round(v * 100)}%</text>`).join(""); return `<svg class="bc" viewBox="0 0 ${W0} ${H}" style="height:${H}px">${g}<line x1="${x(0)}" y1="${y(0)}" x2="${x(1)}" y2="${y(1)}" stroke="var(--on2)" stroke-dasharray="5 5"/><text class="ax" x="${W0 / 2}" y="${H / 2}" text-anchor="middle" style="font-size:14px">Dots appear here once calls are old enough to score</text></svg>`; };
  return `<div class="pagewrap"><header class="lead"><div class="lead-t"><h1>${w("record")}</h1><p class="clamp">${esc(r.headline || "")}</p></div>${seg}</header>
   <div class="tiles wk-t">${tile("Calls made so far", calls.length, "From tonight's run")}${tile("Scored so far", r.scored_3m ?? 0, "A call is scored a month after it is made")}${tile("Days of history", (r.dates || []).length, "Runs recorded")}</div>
   <div class="wgrid">
   ${wcard(6, "How sure we were", "Each bar counts calls by our chance. Most calls sit close to even, which is honest.", chbox("rb", DRAW.rb))}
   ${wcard(6, "What we called", "How many calls of each kind tonight's run made.", chbox("rc", DRAW.rc))}
   ${wcard(8, "Did our chances come true?", "Dots on the dashed line mean we are right about our own odds. This fills in as calls get scored.", chbox("cal", DRAW.cal, 280))}
   ${wcard(4, "What we are learning", "", `<div class="lines">${(r.learning_lines || []).map(l => `<p>${esc(l)}</p>`).join("") || `<p class="muted">Too early to say.</p>`}</div>`)}
   </div></div>`;
};

/* ---------- Market & news ---------- */
const RNG = { "1M": 21, "3M": 63, "6M": 126, "1Y": 252 };
pageMarket = function () {
  const m = D.market || {}, v = m.valuation || {}, I = extra2.indices, F = extra2.flows, rng = S.rng || "6M", n = RNG[rng], pos = v.pe_now ? (v.pe_now - v.low) / (v.high - v.low) * 100 : 0, secs = [...(m.sectors || [])].sort((a, b) => b.ret_6m - a.ret_6m);
  const NM = { nifty: ["Nifty 50", "The 50 biggest companies"], bank: ["Bank Nifty", "The big banks"], mid: ["Midcap", "100 medium-sized companies"], small: ["Smallcap", "250 small companies"], vix: ["Fear gauge (India VIX)", "Higher means traders expect bigger swings"] };
  const idx = I ? Object.entries(NM).filter(([k]) => I[k]).map(([k, [nm, sub]]) => { const s = I[k], d = s.dates.slice(-n - 1), c = s.close.slice(-n - 1), chg = c[c.length - 1] / c[0] - 1, up = k === "vix" ? chg < 0 : chg >= 0;
    const id = "ix" + k; DRAW[id] = (W0, H) => { const id2 = "s" + (cid++), lo = Math.min(...c), hi = Math.max(...c), x = i => 2 + (W0 - 6) * i / (c.length - 1), y = vv => 3 + (H - 6) * (1 - (vv - lo) / ((hi - lo) || 1)), p = c.map((vv, i) => (i ? "L" : "M") + x(i).toFixed(1) + " " + y(vv).toFixed(1)).join(""); CH.set(id2, { type: "sp", h: { d, c }, x, y, n: c.length, W: W0, L: 2, R: 4, lab: nm, fmt: vv => Math.round(vv).toLocaleString("en-IN") }); return `<svg class="sp ${up ? "up" : "dn"}" data-id="${id2}" viewBox="0 0 ${W0} ${H}" preserveAspectRatio="none" style="height:${H}px"><path class="a" d="${p}L${x(c.length - 1)} ${H}L${x(0)} ${H}Z"/><path class="l" d="${p}" vector-effect="non-scaling-stroke"/><line class="xh" y1="0" y2="${H}" vector-effect="non-scaling-stroke"/></svg>`; };
    return `<div class="idx"><div class="idx-h"><b>${nm}</b><span class="muted">${sub}</span></div><div class="idx-v num">${Math.round(c[c.length - 1]).toLocaleString("en-IN")} <span class="${up ? "up" : "dn"}">${spct(chg)}</span></div><div class="chbox" data-draw="${id}" style="height:64px"></div></div>`; }).join("") : "";
  const f = F && F.length ? (() => { const day = F[F.length - 1].date, r = F.filter(x => x.date === day), mx = Math.max(...r.map(x => Math.abs(x.net)), 1); return `<div class="flows">${r.map(x => `<div class="fl"><span>${x.category === "FII" ? "Foreign funds" : "Indian funds"}</span><span class="flt"><i class="${x.net >= 0 ? "w" : "l"}" style="width:${Math.abs(x.net) / mx * 100}%" data-tip="${x.category}: bought ${inr(x.buy)} crore, sold ${inr(x.sell)} crore"></i></span><b class="num ${x.net >= 0 ? "up" : "dn"}">${x.net >= 0 ? "+" : "−"}${inr(Math.abs(x.net))} cr</b></div>`).join("")}<p class="muted">${mdate(day)}. ${r.map(x => `${x.category === "FII" ? "Foreign" : "Indian"} funds ${x.net >= 0 ? "bought" : "sold"} ₹${Math.round(Math.abs(x.net)).toLocaleString("en-IN")} crore ${x.net >= 0 ? "more than they sold" : "more than they bought"}`).join("; ")}. A longer history builds up each day.</p></div>`; })() : "";
  return `<div class="pagewrap">${leadH(w("market"), esc(m.headline || ""))}
   <div class="wgrid">
   ${wcard(12, "The market, by group", "Each line is one index: a basket of companies. Green means the group rose over the period.", `<div class="rngbar"><span class="seg2">${Object.keys(RNG).map(k => `<button class="sg" data-rng="${k}" aria-pressed="${rng === k}">${k}</button>`).join("")}</span></div><div class="idxs">${idx || '<p class="muted">Loading...</p>'}</div>`)}
   ${wcard(6, "Who is buying", "Foreign funds and Indian funds, net of what they sold, for the latest day.", f || "")}
   ${v.pe_now ? wcard(6, w("mVal"), esc(w("mValS", v.pe_now, v.low, v.high)) + " " + esc(v.verdict || ""), `<div class="rb" style="--sp:${pos}%;background:linear-gradient(90deg,var(--gain),var(--c3),var(--loss));margin-top:34px"><span class="now" style="left:${pos}%"></span><span class="c num" style="left:${pos}%">₹${v.pe_now}</span><span class="l num">₹${v.low}</span><span class="r num">₹${v.high}</span></div>`) : ""}
   ${wcard(12, w("mSect"), "Each box is one industry. Green rose over six months, red fell. The line says how many of its stocks are doing well.", `<div class="sectors">${secs.map(s => `<div style="background:color-mix(in oklab,${s.ret_6m >= 0 ? "var(--gain)" : "var(--loss)"} ${Math.round(Math.min(55, Math.abs(s.ret_6m) * 150))}%,var(--surf));border:1px solid var(--line2)" data-tip="${esc(`${s.industry}: ${spct(s.ret_6m)} ${w("in6")}. ${w("mSectS", pct(s.above_200dma))}. ${s.n} stocks.`)}"><span class="trunc" style="font-weight:600">${esc(s.industry)}</span><b class="num">${spct(s.ret_6m, 0)}</b><span class="muted">${w("mSectS", pct(s.above_200dma))}</span></div>`).join("")}</div>`)}
   ${(m.events || []).length ? wcard(12, w("mEvents"), "", (m.events || []).map(e => `<div class="ev"><b class="num">${mdate(e.date)}</b><span>${esc(e.text)}</span></div>`).join("")) : ""}
   </div></div>`;
};
Object.assign(PAGES, { today: pageToday, holdings: pageHoldings, follow: pageFollow, watchlist: pageWatchlist, ideas: pageIdeas, tax: pageTax, tradrec: pageTrading, record: pageRecord, market: pageMarket, portfolio: pageHoldings, stock: pageStock });

/* ---------- boot ---------- */
function boot() {
  const th = store.get("theme", null); root.dataset.theme = th || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  root.lang = S.lang === "bn" ? "bn" : "en";
  document.body.insertAdjacentHTML("beforeend", `<div id="app"><nav id="rail" aria-label="Main"></nav><main id="main"><div class="topbar" id="bar"></div><div id="view"><p class="muted" style="padding:40px 4px">${w("load")}</p></div></main></div><div id="tip" role="tooltip"></div><div id="toasts" role="status" aria-live="polite"></div>`);
  renderBar();
  const names = ["meta", "today", "calls", "market", "portfolio", "watchlist", "ideas", "search", "record", "own_record", "smallcase", "health", "feedback", "settings", "learned", "funds"];
  Promise.all(names.map(n => getJSON(n).catch(() => null))).then(v => {
    names.forEach((n, i) => D[n] = v[i]); model();
    const [h, sb] = location.hash.slice(1).split("/"); S.tab = TABS.includes(h) ? h : "today"; if (S.tab === "stock" && !S.sym) S.tab = "today"; S.sub[S.tab] = sb || null;
    Object.keys(DOTS).forEach(t => { if (seen(t) == null || t === S.tab) seen(t, true); });
    renderAll();
  });
}
document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", boot) : boot();
})();
