import { BACKTEST_SUMMARY, sendJson } from "./_model.js";

export default function handler(_req, res) {
  sendJson(
    res,
    {
      rows: BACKTEST_SUMMARY,
      note: "Resumen del backtesting local contra Mundiales 2014, 2018 y 2022.",
    },
    200,
    24 * 60 * 60,
  );
}
