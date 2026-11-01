// Navigation model for the sidebar and the overview grid (pure data, no React).
// Every entry maps to an implemented backend phase; nothing here is a placeholder.
export const NAV_GROUPS = [
  { title: null, items: [
    { id: "overview", label: "Overview", icon: "home", blurb: "Latest saved results for the selected company.", needs: "" },
  ] },
  { title: "Your data", items: [
    { id: "files", label: "Files", icon: "file", blurb: "Upload an Excel, CSV or PDF file, or create the built-in sample.", needs: "" },
    { id: "process", label: "Process & report", icon: "process", blurb: "Clean and inspect a table, then download a formatted Excel report.", needs: "A CSV or Excel file" },
    { id: "pdf", label: "PDF extraction", icon: "pdf", blurb: "Pull text and tables out of a PDF (no OCR).", needs: "A PDF file" },
  ] },
  { title: "Analysis", items: [
    { id: "fundamentals", label: "Fundamentals", icon: "table", blurb: "Margins, returns, debt ratios and growth from your file.", needs: "A processed CSV or Excel file" },
    { id: "market", label: "Market data", icon: "candles", blurb: "Daily prices for a symbol, validated bar by bar.", needs: "ALPHA_VANTAGE_API_KEY on the server" },
    { id: "technical", label: "Technical", icon: "trend", blurb: "Moving averages, RSI, MACD, Bollinger Bands and ATR.", needs: "Stored prices (Market data)" },
    { id: "sentiment", label: "Sentiment", icon: "bubble", blurb: "Score headlines with a transparent word list.", needs: "Pasting needs no key; fetching news needs NEWS_API_KEY" },
    { id: "risk", label: "Risk", icon: "gauge", blurb: "Volatility, drawdown, VaR and beta from past prices.", needs: "Stored prices (Market data)" },
  ] },
  { title: "Insight", items: [
    { id: "score", label: "Score", icon: "target", blurb: "Combine what exists into one explainable 0–100 summary.", needs: "At least two of the four components" },
    { id: "explain", label: "Explain", icon: "book", blurb: "What, how and why for the latest score.", needs: "A completed score" },
  ] },
];

export const NAV_ITEMS = NAV_GROUPS.flatMap((g) => g.items);
export const navItem = (id) => NAV_ITEMS.find((n) => n.id === id) || NAV_ITEMS[0];
