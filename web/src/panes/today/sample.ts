// Made-up rows for the Today prototype. Nothing here is real; it only lets the layout be judged.
export type Group = "sell" | "weak" | "keep" | "buy" | "unusual";
export type Row = {
  id: string;
  name: string;
  sector: string;
  why: string;
  group: Group;
  price: number;
  day: number;
};

export const CALL_LINE = {
  action: "Sell two stocks. Buy one if it dips.",
  detail:
    "Alpha Steel and Bravo Motors have broken their floors. Echo Bank is near a good buy price.",
};
export const MONEY_LEFT = { left: 184000, month: "November", note: "free to put in this month" };
export const MARKET = {
  breadth: { up: 31, of: 50, say: "More stocks rose than fell." },
  trend: { say: "The Nifty is above its 200-day line. The trend is up.", up: true },
  value: { say: "Prices are a little dear against their history.", band: "Fair to dear", at: 68 },
};
export const PORTFOLIO = { worth: 2846000, day: 0.6, total: 18.4, holdings: 14 };

export const ROWS: Row[] = [
  {
    id: "a",
    name: "Alpha Steel",
    sector: "Metals",
    why: "Broke its floor and the news is poor.",
    group: "sell",
    price: 350.9,
    day: 0.9,
  },
  {
    id: "b",
    name: "Bravo Motors",
    sector: "Auto",
    why: "Margins are shrinking.",
    group: "sell",
    price: 761.2,
    day: -1.1,
  },
  {
    id: "c",
    name: "Cedar Pharma",
    sector: "Health",
    why: "Do not add. Wait for the next result.",
    group: "weak",
    price: 698.5,
    day: -0.4,
  },
  {
    id: "d",
    name: "Delta Power",
    sector: "Energy",
    why: "Hold what we have, no new money.",
    group: "weak",
    price: 267.2,
    day: 0.3,
  },
  {
    id: "h",
    name: "Harbor Ports",
    sector: "Transport",
    why: "Nothing to do.",
    group: "keep",
    price: 1142,
    day: 0.1,
  },
  {
    id: "i",
    name: "Indigo Cement",
    sector: "Materials",
    why: "Fairly priced, no change.",
    group: "keep",
    price: 5144,
    day: -0.2,
  },
  {
    id: "j",
    name: "Juno Finance",
    sector: "Finance",
    why: "Wait for the next result.",
    group: "keep",
    price: 718.3,
    day: 0.6,
  },
  {
    id: "e",
    name: "Echo Bank",
    sector: "Banks",
    why: "Near a buy price. Earnings beat.",
    group: "buy",
    price: 5363,
    day: 1.8,
  },
  {
    id: "g",
    name: "Gamma Tech",
    sector: "IT",
    why: "Orders are up and the chart is clean.",
    group: "buy",
    price: 2090,
    day: 2.2,
  },
  {
    id: "k",
    name: "Kilo Retail",
    sector: "Retail",
    why: "Volume four times the usual.",
    group: "unusual",
    price: 456.7,
    day: 5.1,
  },
];
