import teamsHandler from "../api/teams.js";
import predictHandler from "../api/predict.js";
import backtestHandler from "../api/backtest.js";

function mockReq(query = {}, headers = {}) {
  return { query, headers };
}

function mockRes(label) {
  return {
    statusCode: 200,
    headers: {},
    setHeader(key, value) {
      this.headers[key] = value;
    },
    status(code) {
      this.statusCode = code;
      return this;
    },
    send(body) {
      const text = String(body);
      console.log(`\n[${label}] HTTP ${this.statusCode}`);
      console.log(text.slice(0, 700));
      this.body = text;
      return this;
    },
  };
}

await teamsHandler(mockReq({ as_of: "2026-06-13" }), mockRes("teams"));
await predictHandler(
  mockReq({
    team_a: "Argentina",
    team_b: "France",
    as_of: "2026-06-13",
    neutral: "true",
  }),
  mockRes("predict"),
);
await backtestHandler(mockReq(), mockRes("backtest"));
