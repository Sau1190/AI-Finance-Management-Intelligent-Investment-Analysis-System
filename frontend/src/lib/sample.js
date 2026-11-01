// Built-in demo data so the whole workflow can be shown without hunting for files.
// All numbers are made up for demonstration and are not real company data.

export const SAMPLE_CSV_NAME = "sample_financials_AAA.csv";
export const SAMPLE_SYMBOL = "AAA";

export const SAMPLE_CSV = [
  "Date,Ticker,Revenue,Net Income,Total Assets,Total Liabilities,Shareholders Equity,Total Debt",
  "2022-12-31,AAA,1000,120,5000,2750,2250,900",
  "2023-12-31,AAA,1150,150,5400,2900,2500,950",
  "2024-12-31,AAA,1300,170,5900,3100,2800,1000",
  "",
].join("\n");

export const SAMPLE_HEADLINES = [
  "AAA beats earnings estimates and raises full-year guidance",
  "AAA reports record revenue growth in the latest quarter",
  "Analysts upgrade AAA after strong profit increase",
  "AAA faces lawsuit and shares fall on weak outlook",
  "AAA misses revenue estimates as costs rise",
  "AAA announces dividend increase after solid results",
].join("\n");

export function makeSampleFile() {
  return new File([SAMPLE_CSV], SAMPLE_CSV_NAME, { type: "text/csv" });
}

export const DISCLAIMER =
  "This is a learning project: it is not investment advice, not a recommendation to buy, sell or hold anything, and no returns are promised. Scores and explanations summarise past or supplied data with unvalidated reference ranges.";
