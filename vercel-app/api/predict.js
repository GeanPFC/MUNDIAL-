import { buildModel, predictFromModel, readBool, readParam, sendJson, todayIso } from "./_model.js";

export default async function handler(req, res) {
  try {
    const teamA = readParam(req, "team_a");
    const teamB = readParam(req, "team_b");
    const asOf = readParam(req, "as_of", todayIso());
    const neutral = readBool(readParam(req, "neutral", "true"), true);
    if (!teamA || !teamB) {
      sendJson(res, { error: "Selecciona ambos equipos." }, 400);
      return;
    }
    const model = await buildModel(asOf);
    sendJson(res, predictFromModel(model, teamA, teamB, neutral), 200, 60 * 60);
  } catch (error) {
    sendJson(res, { error: error.message }, 400);
  }
}
