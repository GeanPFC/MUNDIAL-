import { readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { displayTeam, publicTeams, resolveTeam, teamSuggestions } from "./_teams_es.js";

const RESULTS_URL =
  "https://raw.githubusercontent.com/martj42/international_results/master/results.csv";
const LOCAL_RESULTS_PATH = join(dirname(fileURLToPath(import.meta.url)), "..", "data", "raw", "results.csv");

const OUTCOME_ORDER = ["H", "D", "A"];
const DATA_CACHE_MS = 6 * 60 * 60 * 1000;
const MODEL_CACHE_MS = 6 * 60 * 60 * 1000;
// Modelo activo v3: Elo "live" (recalculado con todos los resultados hasta el corte,
// incluidos los del Mundial ya jugados) para 1X2; Poisson para goles.
// DECISION basada en evidencia: la calibracion por temperatura NO se adopta porque no
// generaliza fuera de muestra (T=0.83 aprendida en 2014/2018 empeora 2022 en log loss,
// Brier, RPS y ECE). Ver reports/calibration_experiment.csv y CHANGELOG. Por eso los
// factores quedan en identidad (sin temperatura, sin blend); el Elo live ya esta
// razonablemente calibrado (ECE 2022 ~0.07).
const CALIBRATION = {
  version: "elo_live_v3",
  temperature: 1.0,
  drawMultiplier: 1.0,
  poissonBlend: 0.0,
  validation: {
    scope: "Validacion pre-torneo FIFA World Cup 2014/2018/2022 (modelo elo_live)",
    eloLiveLogLoss: 0.99346,
    eloLiveBrier: 0.589783,
    eloLiveRps: 0.210983,
    accuracy: 0.546875,
    note: "Calibracion por temperatura evaluada y descartada por no generalizar fuera de muestra.",
  },
};

let dataCache = null;
const modelCache = new Map();

function parseCsv(text) {
  const rows = [];
  let row = [];
  let value = "";
  let quoted = false;

  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    const next = text[i + 1];
    if (quoted) {
      if (char === '"' && next === '"') {
        value += '"';
        i += 1;
      } else if (char === '"') {
        quoted = false;
      } else {
        value += char;
      }
    } else if (char === '"') {
      quoted = true;
    } else if (char === ",") {
      row.push(value);
      value = "";
    } else if (char === "\n") {
      row.push(value);
      rows.push(row);
      row = [];
      value = "";
    } else if (char !== "\r") {
      value += char;
    }
  }
  if (value.length || row.length) {
    row.push(value);
    rows.push(row);
  }
  const header = rows.shift();
  return rows
    .filter((cells) => cells.length === header.length)
    .map((cells) => Object.fromEntries(header.map((name, idx) => [name, cells[idx]])));
}

function parseBool(value) {
  return ["true", "1", "yes", "y"].includes(String(value).trim().toLowerCase());
}

function normalizeMatch(row) {
  const homeScore = Number(row.home_score);
  const awayScore = Number(row.away_score);
  if (!row.date || !row.home_team || !row.away_team) return null;
  if (!Number.isFinite(homeScore) || !Number.isFinite(awayScore)) return null;
  const goalDiff = homeScore - awayScore;
  return {
    date: row.date.slice(0, 10),
    time: Date.parse(`${row.date.slice(0, 10)}T00:00:00Z`),
    home_team: row.home_team,
    away_team: row.away_team,
    home_score: homeScore,
    away_score: awayScore,
    tournament: row.tournament || "",
    city: row.city || "",
    country: row.country || "",
    neutral: parseBool(row.neutral),
    outcome: goalDiff > 0 ? "H" : goalDiff < 0 ? "A" : "D",
  };
}

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function compareByDate(a, b) {
  if (a.time !== b.time) return a.time - b.time;
  if (a.home_team !== b.home_team) return a.home_team.localeCompare(b.home_team);
  return a.away_team.localeCompare(b.away_team);
}

async function fetchResults() {
  const now = Date.now();
  if (dataCache && now - dataCache.fetchedAt < DATA_CACHE_MS) {
    return dataCache;
  }
  let csv;
  let sourceStatus = "remote";
  let sourceError = null;
  try {
    const response = await fetch(RESULTS_URL, {
      headers: { "User-Agent": "worldcup-2026-predictor/1.0" },
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    csv = await response.text();
  } catch (error) {
    sourceStatus = "bundled_fallback";
    sourceError = error.message;
    csv = await readFile(LOCAL_RESULTS_PATH, "utf-8");
  }
  const matches = parseCsv(csv).map(normalizeMatch).filter(Boolean).sort(compareByDate);
  dataCache = {
    fetchedAt: now,
    sourceUrl: RESULTS_URL,
    sourceStatus,
    sourceError,
    matches,
    snapshotMinDate: matches[0]?.date || null,
    snapshotMaxDate: matches.at(-1)?.date || null,
  };
  return dataCache;
}

function tournamentImportance(tournament) {
  const fixed = {
    "FIFA World Cup": 4.0,
    "FIFA World Cup qualification": 2.2,
    "UEFA Euro": 2.8,
    "Copa America": 2.6,
    "African Cup of Nations": 2.4,
    "AFC Asian Cup": 2.2,
    "CONCACAF Gold Cup": 2.0,
    Friendly: 0.7,
  };
  if (fixed[tournament]) return fixed[tournament];
  const lowered = tournament.toLowerCase();
  if (lowered.includes("qualification") || lowered.includes("qualifier")) return 1.8;
  if (lowered.includes("cup") || lowered.includes("championship")) return 1.6;
  return 1.0;
}

function expectedScore(ratingA, ratingB, homeAdvantage) {
  return 1 / (1 + 10 ** (-(ratingA - ratingB + homeAdvantage) / 400));
}

function fitElo(matches) {
  const ratings = new Map();
  const initial = 1500;
  const kFactor = 20;
  const homeAdvantage = 60;
  for (const match of matches) {
    const home = ratings.get(match.home_team) ?? initial;
    const away = ratings.get(match.away_team) ?? initial;
    const actual =
      match.home_score > match.away_score ? 1 : match.home_score < match.away_score ? 0 : 0.5;
    const expected = expectedScore(home, away, match.neutral ? 0 : homeAdvantage);
    const goalDiff = Math.abs(match.home_score - match.away_score);
    const margin = goalDiff <= 1 ? 1 : Math.min(Math.log(goalDiff + 1), 2.5);
    const importance = 1 + 0.25 * Math.max(tournamentImportance(match.tournament) - 1, 0);
    const change = kFactor * importance * margin * (actual - expected);
    ratings.set(match.home_team, home + change);
    ratings.set(match.away_team, away - change);
  }
  return {
    initial,
    homeAdvantage,
    drawBaseRate: 0.27,
    drawDecay: 500,
    ratings,
  };
}

function weightedStats(matches, asOfTime) {
  const halfLifeDays = 1095;
  let totalWeight = 0;
  let homeGoals = 0;
  let awayGoals = 0;
  const teams = new Map();

  for (const match of matches) {
    const ageDays = Math.max(0, (asOfTime - match.time) / 86400000);
    const recency = 0.5 ** (ageDays / halfLifeDays);
    const weight = recency * tournamentImportance(match.tournament);
    totalWeight += weight;
    homeGoals += match.home_score * weight;
    awayGoals += match.away_score * weight;

    for (const team of [match.home_team, match.away_team]) {
      if (!teams.has(team)) teams.set(team, { gf: 0, ga: 0, exposure: 0 });
    }
    const home = teams.get(match.home_team);
    const away = teams.get(match.away_team);
    home.gf += match.home_score * weight;
    home.ga += match.away_score * weight;
    home.exposure += weight;
    away.gf += match.away_score * weight;
    away.ga += match.home_score * weight;
    away.exposure += weight;
  }

  const globalHomeRate = homeGoals / Math.max(totalWeight, 1e-9);
  const globalAwayRate = awayGoals / Math.max(totalWeight, 1e-9);
  const globalGoalRate = Math.max((globalHomeRate + globalAwayRate) / 2, 0.2);
  const strengths = new Map();
  const priorMatches = 8;
  for (const [team, row] of teams.entries()) {
    const gfRate = (row.gf + priorMatches * globalGoalRate) / (row.exposure + priorMatches);
    const gaRate = (row.ga + priorMatches * globalGoalRate) / (row.exposure + priorMatches);
    strengths.set(team, {
      attack: clamp(gfRate / globalGoalRate, 0.35, 2.75),
      defense: clamp(gaRate / globalGoalRate, 0.35, 2.75),
      matches: row.exposure,
    });
  }
  return { globalHomeRate, globalAwayRate, globalGoalRate, strengths };
}

function clamp(value, lower, upper) {
  return Math.max(lower, Math.min(upper, value));
}

function poissonPmf(k, lambda) {
  let value = Math.exp(-lambda);
  for (let i = 1; i <= k; i += 1) value *= lambda / i;
  return value;
}

function poissonQuantile(probability, lambda) {
  let cdf = 0;
  for (let k = 0; k <= 20; k += 1) {
    cdf += poissonPmf(k, lambda);
    if (cdf >= probability) return k;
  }
  return 20;
}

function poissonOutcomeProbabilities(lambdaA, lambdaB, maxGoals = 10) {
  let pA = 0;
  let pD = 0;
  let pB = 0;
  for (let a = 0; a <= maxGoals; a += 1) {
    for (let b = 0; b <= maxGoals; b += 1) {
      const p = poissonPmf(a, lambdaA) * poissonPmf(b, lambdaB);
      if (a > b) pA += p;
      else if (a === b) pD += p;
      else pB += p;
    }
  }
  const total = pA + pD + pB;
  return [pA / total, pD / total, pB / total];
}

function modalScore(lambdaA, lambdaB) {
  let best = { team_a: 0, team_b: 0, probability: -1 };
  for (let a = 0; a <= 10; a += 1) {
    for (let b = 0; b <= 10; b += 1) {
      const probability = poissonPmf(a, lambdaA) * poissonPmf(b, lambdaB);
      if (probability > best.probability) best = { team_a: a, team_b: b, probability };
    }
  }
  return best;
}

function topScores(lambdaA, lambdaB, maxGoals = 6, limit = 5) {
  const rows = [];
  for (let a = 0; a <= maxGoals; a += 1) {
    for (let b = 0; b <= maxGoals; b += 1) {
      rows.push({
        team_a: a,
        team_b: b,
        probability: poissonPmf(a, lambdaA) * poissonPmf(b, lambdaB),
      });
    }
  }
  const total = rows.reduce((sum, row) => sum + row.probability, 0);
  return rows
    .sort((a, b) => b.probability - a.probability)
    .slice(0, limit)
    .map((row) => ({ ...row, probability: row.probability / total }));
}

function normalizeProbabilities(probs) {
  const clipped = probs.map((p) => Math.max(p, 1e-12));
  const total = clipped.reduce((sum, p) => sum + p, 0);
  return clipped.map((p) => p / total);
}

function calibrateEloProbabilities(probs) {
  const adjusted = [...probs];
  adjusted[1] *= CALIBRATION.drawMultiplier;
  const normalized = normalizeProbabilities(adjusted);
  return normalizeProbabilities(normalized.map((p) => p ** (1 / CALIBRATION.temperature)));
}

function blendProbabilities(primary, secondary, secondaryWeight) {
  return normalizeProbabilities(
    primary.map((p, idx) => (1 - secondaryWeight) * p + secondaryWeight * secondary[idx]),
  );
}

// Lectura analitica del partido (sin lenguaje de apuestas): describe favorito, margen,
// equilibrio e incertidumbre. Sustituye a la antigua guia de apuestas (auditoria C1).
function buildMatchReading({ displayA, displayB, probabilities, lambdaA, lambdaB, confidence }) {
  const [pA, pD, pB] = probabilities;
  const favoriteSide = pA >= pB ? "A" : "B";
  const favoriteName = favoriteSide === "A" ? displayA : displayB;
  const favoriteProbability = favoriteSide === "A" ? pA : pB;
  const margin = Math.abs(pA - pB);
  const totalGoals = lambdaA + lambdaB;

  let balance;
  if (favoriteProbability >= 0.6) balance = "favorito claro";
  else if (favoriteProbability >= 0.45) balance = "favorito leve";
  else balance = "partido parejo";

  const drawTendency = pD >= 0.28 ? "empate probable" : pD >= 0.22 ? "empate posible" : "empate poco probable";
  const goalsTendency =
    totalGoals >= 2.8 ? "partido de bastantes goles" : totalGoals >= 1.8 ? "goles moderados" : "partido de pocos goles";

  return {
    disclaimer:
      "Lectura analitica del modelo, no una prediccion garantizada. El futbol tiene alta varianza.",
    favorite: {
      team: favoriteName,
      probability: favoriteProbability,
      balance,
      reason: `${favoriteName} es ${balance} por diferencia de Elo y fuerza de ataque/defensa.`,
    },
    match_balance: {
      label: balance,
      margin,
      draw_tendency: drawTendency,
      reason:
        margin < 0.1
          ? "Las probabilidades de ambos equipos estan muy cerca; resultado abierto."
          : "Hay una diferencia perceptible entre ambos equipos segun el modelo.",
    },
    goals_reading: {
      label: goalsTendency,
      expected_total_goals: totalGoals,
      reason: "Lectura derivada del total de goles esperados (Poisson).",
    },
    note: "Sin recomendaciones de apuestas. Uso analitico y deportivo unicamente.",
  };
}

async function buildModel(asOf = todayIso()) {
  const cutoff = asOf.slice(0, 10);
  const cacheKey = cutoff;
  const now = Date.now();
  const cached = modelCache.get(cacheKey);
  if (cached && now - cached.createdAt < MODEL_CACHE_MS) return cached.model;

  const data = await fetchResults();
  const cutoffTime = Date.parse(`${cutoff}T23:59:59Z`);
  const train = data.matches.filter((match) => match.time <= cutoffTime);
  if (!train.length) throw new Error(`No hay partidos antes de la fecha de corte ${cutoff}`);

  const elo = fitElo(train);
  const poisson = weightedStats(train, cutoffTime);
  const teams = [...new Set(train.flatMap((m) => [m.home_team, m.away_team]))].sort();
  const model = {
    asOf: cutoff,
    sourceUrl: data.sourceUrl,
    sourceStatus: data.sourceStatus,
    sourceError: data.sourceError,
    snapshotMinDate: data.snapshotMinDate,
    snapshotMaxDate: data.snapshotMaxDate,
    fetchedAt: new Date(data.fetchedAt).toISOString(),
    nTrainMatches: train.length,
    maxTrainDate: train.at(-1)?.date || null,
    teams,
    elo,
    poisson,
  };
  modelCache.set(cacheKey, { createdAt: now, model });
  return model;
}

function resolveInputTeamOrThrow(input, teams) {
  const team = resolveTeam(input, teams);
  if (team) return team;
  const suggestions = teamSuggestions(input, teams);
  const suffix = suggestions.length
    ? ` Sugerencias: ${suggestions.map((row) => row.label).join(", ")}.`
    : "";
  throw new Error(`No encontre la seleccion "${input}". Escribela en espanol o ingles.${suffix}`);
}

function predictFromModel(model, teamAInput, teamBInput, neutral = true) {
  const teamA = resolveInputTeamOrThrow(teamAInput, model.teams);
  const teamB = resolveInputTeamOrThrow(teamBInput, model.teams);
  if (!model.teams.includes(teamA) || !model.teams.includes(teamB)) {
    throw new Error("Uno o ambos equipos no existen en el dataset.");
  }
  if (teamA === teamB) throw new Error("Los equipos deben ser distintos.");

  const ratingA = model.elo.ratings.get(teamA) ?? model.elo.initial;
  const ratingB = model.elo.ratings.get(teamB) ?? model.elo.initial;
  const homeAdvantage = neutral ? 0 : model.elo.homeAdvantage;
  const eloDiff = ratingA - ratingB + homeAdvantage;
  const expected = expectedScore(ratingA, ratingB, homeAdvantage);
  const draw = clamp(
    model.elo.drawBaseRate * Math.exp(-Math.abs(eloDiff) / model.elo.drawDecay),
    0.08,
    0.34,
  );
  let pA = expected - 0.5 * draw;
  let pB = 1 - expected - 0.5 * draw;
  const total = pA + draw + pB;
  pA /= total;
  pB /= total;
  const pD = draw / total;

  const strengthA = model.poisson.strengths.get(teamA) || { attack: 1, defense: 1, matches: 0 };
  const strengthB = model.poisson.strengths.get(teamB) || { attack: 1, defense: 1, matches: 0 };
  const neutralBase = (model.poisson.globalHomeRate + model.poisson.globalAwayRate) / 2;
  const baseA = neutral ? neutralBase : model.poisson.globalHomeRate;
  const baseB = neutral ? neutralBase : model.poisson.globalAwayRate;
  const lambdaA = clamp(baseA * strengthA.attack * strengthB.defense, 0.05, 5.5);
  const lambdaB = clamp(baseB * strengthB.attack * strengthA.defense, 0.05, 5.5);
  const score = modalScore(lambdaA, lambdaB);
  const topScoreRows = topScores(lambdaA, lambdaB);
  const minMatches = Math.min(strengthA.matches, strengthB.matches);
  const rawEloProbabilities = [pA, pD, pB];
  const calibratedEloProbabilities = calibrateEloProbabilities(rawEloProbabilities);
  const poissonProbabilities = poissonOutcomeProbabilities(lambdaA, lambdaB);
  const finalProbabilities = blendProbabilities(
    calibratedEloProbabilities,
    poissonProbabilities,
    CALIBRATION.poissonBlend,
  );
  const maxProbability = Math.max(...finalProbabilities);
  const displayA = displayTeam(teamA);
  const displayB = displayTeam(teamB);
  const confidence =
    maxProbability >= 0.7 ? "alta" : maxProbability >= 0.55 ? "media" : "baja";

  return {
    teams: { team_a: teamA, team_b: teamB },
    teams_display: { team_a: displayA, team_b: displayB },
    teams_input: { team_a: teamAInput, team_b: teamBInput },
    as_of: model.asOf,
    neutral,
    n_train_matches: model.nTrainMatches,
    max_train_date: model.maxTrainDate,
    data_source: model.sourceUrl,
    data_source_status: model.sourceStatus,
    data_source_error: model.sourceError,
    data_fetched_at: model.fetchedAt,
    snapshot_max_date: model.snapshotMaxDate,
    probabilities: {
      team_a_win: finalProbabilities[0],
      draw: finalProbabilities[1],
      team_b_win: finalProbabilities[2],
    },
    probability_components: {
      raw_elo: {
        team_a_win: rawEloProbabilities[0],
        draw: rawEloProbabilities[1],
        team_b_win: rawEloProbabilities[2],
      },
      calibrated_elo: {
        team_a_win: calibratedEloProbabilities[0],
        draw: calibratedEloProbabilities[1],
        team_b_win: calibratedEloProbabilities[2],
      },
      poisson_goals: {
        team_a_win: poissonProbabilities[0],
        draw: poissonProbabilities[1],
        team_b_win: poissonProbabilities[2],
      },
    },
    expected_goals: {
      team_a: lambdaA,
      team_b: lambdaB,
    },
    most_likely_score: {
      team_a: score.team_a,
      team_b: score.team_b,
    },
    top_scores: topScoreRows,
    goal_intervals: {
      team_a: [poissonQuantile(0.05, lambdaA), poissonQuantile(0.95, lambdaA)],
      team_b: [poissonQuantile(0.05, lambdaB), poissonQuantile(0.95, lambdaB)],
    },
    uncertainty: minMatches < 8 ? "alta" : minMatches < 25 ? "media" : "baja",
    confidence,
    upset_probability: 1 - maxProbability,
    match_reading: buildMatchReading({
      displayA,
      displayB,
      probabilities: finalProbabilities,
      lambdaA,
      lambdaB,
      confidence,
    }),
    influential_variables: {
      elo_team_a: ratingA,
      elo_team_b: ratingB,
      elo_diff_adjusted: eloDiff,
      home_attack: strengthA.attack,
      away_attack: strengthB.attack,
      home_defense_allowed_rate: strengthA.defense,
      away_defense_allowed_rate: strengthB.defense,
      neutral_venue: neutral ? 1 : 0,
    },
    model_decision:
      "Modelo v3: Elo live para 1X2 (sin calibracion ad-hoc, descartada por no generalizar); Poisson para goles esperados, marcador modal e intervalos.",
    calibration: CALIBRATION,
    warning:
      model.snapshotMaxDate > model.asOf
        ? "El snapshot remoto contiene filas posteriores a la fecha de corte; el entrenamiento se filtro por fecha."
        : "",
  };
}

function publicModelSummary(model) {
  return {
    as_of: model.asOf,
    default_cutoff: todayIso(),
    source_url: model.sourceUrl,
    source_status: model.sourceStatus,
    source_error: model.sourceError,
    data_fetched_at: model.fetchedAt,
    snapshot_min_date: model.snapshotMinDate,
    snapshot_max_date: model.snapshotMaxDate,
    n_train_matches: model.nTrainMatches,
    max_train_date: model.maxTrainDate,
    teams: model.teams,
    teams_display: publicTeams(model.teams),
  };
}

function setJsonHeaders(res, cacheSeconds = 0) {
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  if (cacheSeconds > 0) {
    res.setHeader("Cache-Control", `s-maxage=${cacheSeconds}, stale-while-revalidate=86400`);
  } else {
    res.setHeader("Cache-Control", "no-store");
  }
}

function sendJson(res, payload, status = 200, cacheSeconds = 0) {
  setJsonHeaders(res, cacheSeconds);
  res.status(status).send(JSON.stringify(payload));
}

function readParam(req, key, fallback = "") {
  const value = req.query?.[key];
  if (Array.isArray(value)) return String(value[0] ?? fallback).trim();
  return String(value ?? fallback).trim();
}

function readBool(value, fallback = false) {
  if (value === "") return fallback;
  return ["1", "true", "yes", "y", "on"].includes(String(value).toLowerCase());
}

const BACKTEST_SUMMARY = [
  {
    model: "elo_live_v3 (activo)",
    log_loss: 0.99346,
    brier: 0.589783,
    rps: 0.210983,
    accuracy: 0.546875,
    ece: 0.092537,
  },
  {
    model: "elo_static_pre_tournament",
    log_loss: 1.000796,
    brier: 0.595727,
    rps: 0.213749,
    accuracy: 0.552083,
    ece: 0.110922,
  },
  { model: "ml_hist_gradient_boosting", log_loss: 1.004441, brier: 0.59838, rps: 0.21413, accuracy: 0.546875, ece: 0.10501 },
  { model: "bayesian_gamma_poisson", log_loss: 1.055385, brier: 0.636945, rps: 0.232362, accuracy: 0.489583, ece: 0.111728 },
  { model: "poisson_simple", log_loss: 1.056308, brier: 0.637518, rps: 0.232569, accuracy: 0.489583, ece: 0.112353 },
  { model: "baseline_rates", log_loss: 1.073582, brier: 0.651555, rps: 0.241605, accuracy: 0.427083, ece: 0.054124 },
];

export {
  BACKTEST_SUMMARY,
  buildModel,
  predictFromModel,
  publicModelSummary,
  readBool,
  readParam,
  sendJson,
  todayIso,
};
