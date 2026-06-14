const form = document.querySelector("#predictForm");
const teamA = document.querySelector("#teamA");
const teamB = document.querySelector("#teamB");
const asOf = document.querySelector("#asOf");
const neutral = document.querySelector("#neutral");
const teamsList = document.querySelector("#teamsList");
const message = document.querySelector("#message");
const primary = document.querySelector(".primary");

const fmtPct = new Intl.NumberFormat("es-PE", {
  style: "percent",
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

const fmtNum = new Intl.NumberFormat("es-PE", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

function setText(id, value) {
  document.querySelector(`#${id}`).textContent = value;
}

function setBar(id, value) {
  document.querySelector(`#${id}`).style.width = `${Math.max(0, Math.min(100, value * 100))}%`;
}

function setLoading(isLoading) {
  primary.disabled = isLoading;
  primary.textContent = isLoading ? "Calculando..." : "Predecir";
}

function showError(text) {
  message.textContent = text || "";
}

async function fetchJson(url) {
  const response = await fetch(url);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Error de API");
  return data;
}

async function loadTeams() {
  const data = await fetchJson("/api/teams");
  const teams = data.teams_display || data.teams.map((team) => ({ label: team, search: team }));
  teamsList.innerHTML = teams.map((row) => `<option value="${row.label}"></option>`).join("");
  asOf.value = data.default_cutoff;
  const sourceLabel = data.source_status === "remote" ? "remoto" : "snapshot local";
  document.querySelector("#dataStatus").textContent =
    `${data.n_train_matches.toLocaleString("es-PE")} partidos al ${data.as_of} · ${sourceLabel}`;
}

async function loadBacktest() {
  const data = await fetchJson("/api/backtest");
  const target = document.querySelector("#backtestRows");
  target.innerHTML = data.rows
    .slice(0, 4)
    .map((row) => `<div><span>${row.model}</span><strong>LL ${fmtNum.format(row.log_loss)}</strong></div>`)
    .join("");
}

function renderVariables(vars) {
  const labels = {
    elo_team_a: "Elo Equipo A",
    elo_team_b: "Elo Equipo B",
    elo_diff_adjusted: "Diferencia Elo",
    home_attack: "Ataque A",
    away_attack: "Ataque B",
    home_defense_allowed_rate: "Defensa A",
    away_defense_allowed_rate: "Defensa B",
    neutral_venue: "Sede neutral",
  };
  document.querySelector("#variables").innerHTML = Object.entries(vars)
    .map(([key, value]) => {
      const label = labels[key] || key;
      const numeric = Number(value);
      const shown = Number.isFinite(numeric) ? fmtNum.format(numeric) : value;
      return `<div class="var"><span>${label}</span><strong>${shown}</strong></div>`;
    })
    .join("");
}

function renderPlainSummary(data) {
  const a = data.teams_display?.team_a || data.teams.team_a;
  const b = data.teams_display?.team_b || data.teams.team_b;
  const pA = data.probabilities.team_a_win;
  const pD = data.probabilities.draw;
  const pB = data.probabilities.team_b_win;
  const favName = pA >= pB ? a : b;
  const favProb = Math.max(pA, pB);
  const otherName = pA >= pB ? b : a;
  const margin = Math.abs(pA - pB);
  const totalGoals = data.expected_goals.team_a + data.expected_goals.team_b;
  const modal = `${data.most_likely_score.team_a}-${data.most_likely_score.team_b}`;
  const upset = data.upset_probability;

  let headline;
  if (margin < 0.08) {
    headline = `Partido muy parejo: ${a} y ${b} llegan casi igualados según el modelo.`;
  } else {
    const level =
      favProb >= 0.6 ? "el favorito claro" : favProb >= 0.48 ? "el favorito" : "ligero favorito";
    headline = `${favName} es ${level} (${fmtPct.format(favProb)} de ganar), pero no está decidido.`;
  }

  const goalsWord =
    totalGoals < 2.2 ? "pocos goles" : totalGoals <= 2.9 ? "una cantidad normal de goles" : "bastantes goles";
  const dataWord =
    data.uncertainty === "alta"
      ? "Hay pocos datos recientes de estos equipos, así que conviene tomarlo con cautela."
      : data.uncertainty === "media"
        ? "Hay una cantidad razonable de datos recientes de estos equipos."
        : "Hay bastantes datos recientes, así que la estimación es más sólida.";

  const items = [
    `Probabilidad de ganar — ${a}: ${fmtPct.format(pA)} · Empate: ${fmtPct.format(pD)} · ${b}: ${fmtPct.format(pB)}.`,
    `Se espera ${goalsWord} (≈${fmtNum.format(totalGoals)} en total). El marcador más probable es ${modal}.`,
    `Qué tan seguro: confianza ${data.confidence || "media"}. Aun así, hay ${fmtPct.format(upset)} de probabilidad de que ${favName} NO gane — el fútbol da sorpresas.`,
    dataWord,
  ];

  setText("summaryHeadline", headline);
  document.querySelector("#summaryList").innerHTML = items.map((t) => `<li>${t}</li>`).join("");
  setText(
    "summaryCaveat",
    "Esto son probabilidades calibradas, no certezas: una guía para hacerte una idea, no una predicción garantizada.",
  );
}

function renderMatchReading(reading) {
  if (!reading) return;
  setText("readingDisclaimer", reading.disclaimer);

  setText("favoriteLabel", reading.favorite.team);
  setText("favoriteMeta", `${fmtPct.format(reading.favorite.probability)} · ${reading.favorite.balance}`);
  setText("favoriteReason", reading.favorite.reason);

  setText("balanceLabel", reading.match_balance.label);
  setText("balanceMeta", `margen ${fmtPct.format(reading.match_balance.margin)} · ${reading.match_balance.draw_tendency}`);
  setText("balanceReason", reading.match_balance.reason);

  setText("goalsLabel", reading.goals_reading.label);
  setText("goalsMeta", `total esperado ${fmtNum.format(reading.goals_reading.expected_total_goals)} goles`);
  setText("goalsReason", reading.goals_reading.reason);
}

function renderPrediction(data) {
  const a = data.teams_display?.team_a || data.teams.team_a;
  const b = data.teams_display?.team_b || data.teams.team_b;
  const probs = data.probabilities;
  setText("fixtureLabel", `${a} vs ${b}`);
  setText("labelA", a);
  setText("labelB", b);
  setText("probA", fmtPct.format(probs.team_a_win));
  setText("probD", fmtPct.format(probs.draw));
  setText("probB", fmtPct.format(probs.team_b_win));
  setBar("barA", probs.team_a_win);
  setBar("barD", probs.draw);
  setBar("barB", probs.team_b_win);

  setText("modalScore", `${data.most_likely_score.team_a}-${data.most_likely_score.team_b}`);
  setText("xgA", fmtNum.format(data.expected_goals.team_a));
  setText("xgB", fmtNum.format(data.expected_goals.team_b));
  setText("intervalAName", a);
  setText("intervalBName", b);
  setText("intervalA", `${data.goal_intervals.team_a[0]} a ${data.goal_intervals.team_a[1]}`);
  setText("intervalB", `${data.goal_intervals.team_b[0]} a ${data.goal_intervals.team_b[1]}`);
  setText("uncertainty", data.uncertainty);
  setText("confidence", data.confidence || "--");
  setText("upset", data.upset_probability == null ? "--" : fmtPct.format(data.upset_probability));
  document.querySelector("#topScores").innerHTML = (data.top_scores || [])
    .slice(0, 5)
    .map((row) => (
      `<div><span>${row.team_a}-${row.team_b}</span><strong>${fmtPct.format(row.probability)}</strong></div>`
    ))
    .join("");
  renderPlainSummary(data);
  renderVariables(data.influential_variables);
  renderMatchReading(data.match_reading);
  const sourceWarning =
    data.data_source_status === "bundled_fallback"
      ? "No se pudo leer GitHub en esta ejecución; se usó el snapshot local empaquetado."
      : "";
  showError([data.warning, sourceWarning].filter(Boolean).join(" "));
}

async function predict() {
  setLoading(true);
  showError("");
  const params = new URLSearchParams({
    team_a: teamA.value.trim(),
    team_b: teamB.value.trim(),
    as_of: asOf.value,
    neutral: neutral.checked ? "true" : "false",
  });
  try {
    renderPrediction(await fetchJson(`/api/predict?${params.toString()}`));
  } catch (error) {
    showError(error.message);
  } finally {
    setLoading(false);
  }
}

document.querySelector("#swapTeams").addEventListener("click", () => {
  const a = teamA.value;
  teamA.value = teamB.value;
  teamB.value = a;
  predict();
});

form.addEventListener("submit", (event) => {
  event.preventDefault();
  predict();
});

Promise.all([loadTeams(), loadBacktest()])
  .then(predict)
  .catch((error) => showError(error.message));
