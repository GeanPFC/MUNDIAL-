import { buildModel, publicModelSummary, readParam, sendJson, todayIso } from "./_model.js";

export default async function handler(req, res) {
  try {
    const asOf = readParam(req, "as_of", todayIso());
    const model = await buildModel(asOf);
    sendJson(res, publicModelSummary(model), 200, 6 * 60 * 60);
  } catch (error) {
    sendJson(res, { error: error.message }, 500);
  }
}
