import { buildModel, publicModelSummary, sendJson, todayIso } from "./_model.js";

export default async function handler(req, res) {
  try {
    const model = await buildModel(todayIso());
    sendJson(
      res,
      {
        ok: true,
        triggered_by: req.headers["user-agent"] || "unknown",
        refreshed: publicModelSummary(model),
      },
      200,
    );
  } catch (error) {
    sendJson(res, { ok: false, error: error.message }, 500);
  }
}
