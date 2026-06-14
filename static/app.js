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

let localTeams = [];
let teamMap = new Map();

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

async function loadTeams() {
  if (window.MODEL_SNAPSHOT) {
    localTeams = window.MODEL_SNAPSHOT.teams.map((row) => row.team).sort();
    teamMap = new Map(window.MODEL_SNAPSHOT.teams.map((row) => [row.team, row]));
    teamsList.innerHTML = localTeams.map((team) => `<option value="${team}"></option>`).join("");
    asOf.value = window.MODEL_SNAPSHOT.as_of;
    document.querySelector("#dataStatus").textContent =
      `${window.MODEL_SNAPSHOT.n_train_matches.toLocaleString("es-PE")} partidos al ${window.MODEL_SNAPSHOT.as_of}`;
    return;
  }

  const response = await fetch("/api/teams");
  const data = await response.json();
  teamsList.innerHTML = data.teams.map((team) => `<option value="${team}"></option>`).join("");
  asOf.value = data.default_cutoff;
  document.querySelector("#dataStatus").textContent =
    `${data.n_matches.toLocaleString("es-PE")} partidos al ${data.default_cutoff}`;
}

async function loadBacktest() {
  if (window.MODEL_SNAPSHOT) {
    renderBacktest(window.MODEL_SNAPSHOT.backtest || []);
    return;
  }

  const response = await fetch("/api/backtest");
  const data = await response.json();
  const target = document.querySelector("#backtestRows");
  if (!response.ok) {
    target.innerHTML = `<div><span>Estado</span><strong>${data.error}</strong></div>`;
    return;
  }
  renderBacktest(data.rows);
}

function renderBacktest(rows) {
  const target = document.querySelector("#backtestRows");
  if (!rows.length) {
    target.innerHTML = "<div><span>Estado</span><strong>Sin reporte</strong></div>";
    return;
  }
  target.innerHTML = rows
    .slice(0, 4)
    .map((row) => (
      `<div><span>${row.model}</span><strong>LL ${fmtNum.format(row.log_loss)}</strong></div>`
    ))
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
    dixon_coles_rho: "Dixon-Coles rho",
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

function renderPrediction(data) {
  const a = data.teams.team_a;
  const b = data.teams.team_b;
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
  renderVariables(data.influential_variables);
  showError(data.warning || "");
}

function clamp(value, lower, upper) {
  return Math.max(lower, Math.min(upper, value));
}

function poissonPmf(k, lambda) {
  let value = Math.exp(-lambda);
  for (let i = 1; i <= k; i += 1) {
    value *= lambda / i;
  }
  return value;
}

function poissonQuantile(probability, lambda) {
  let cdf = 0;
  for (let k = 0; k <= 20; k += 1) {
    cdf += poissonPmf(k, lambda);
    if (cdf >= probability) {
      return k;
    }
  }
  return 20;
}

function modalScore(lambdaA, lambdaB) {
  let best = { a: 0, b: 0, p: -1 };
  for (let a = 0; a <= 10; a += 1) {
    for (let b = 0; b <= 10; b += 1) {
      const p = poissonPmf(a, lambdaA) * poissonPmf(b, lambdaB);
      if (p > best.p) {
        best = { a, b, p };
      }
    }
  }
  return best;
}

function predictLocal() {
  const snapshot = window.MODEL_SNAPSHOT;
  const aName = teamA.value.trim();
  const bName = teamB.value.trim();
  const a = teamMap.get(aName);
  const b = teamMap.get(bName);
  if (!a || !b) {
    showError("Selecciona equipos validos del listado.");
    return null;
  }
  if (aName === bName) {
    showError("Los equipos deben ser distintos.");
    return null;
  }

  const homeAdvantage = neutral.checked ? 0 : snapshot.elo_home_advantage;
  const eloDiff = a.elo - b.elo + homeAdvantage;
  const expected = 1 / (1 + (10 ** (-eloDiff / 400)));
  const draw = clamp(snapshot.elo_draw_base_rate * Math.exp(-Math.abs(eloDiff) / snapshot.elo_draw_decay), 0.08, 0.34);
  let pA = expected - 0.5 * draw;
  let pB = 1 - expected - 0.5 * draw;
  const total = pA + draw + pB;
  pA /= total;
  pB /= total;
  const pD = draw / total;

  const baseA = neutral.checked
    ? (snapshot.global_home_rate + snapshot.global_away_rate) / 2
    : snapshot.global_home_rate;
  const baseB = neutral.checked
    ? (snapshot.global_home_rate + snapshot.global_away_rate) / 2
    : snapshot.global_away_rate;
  const lambdaA = clamp(baseA * a.attack * b.defense, 0.05, 5.5);
  const lambdaB = clamp(baseB * b.attack * a.defense, 0.05, 5.5);
  const score = modalScore(lambdaA, lambdaB);
  const minMatches = Math.min(a.matches, b.matches);

  return {
    teams: { team_a: aName, team_b: bName },
    as_of: snapshot.as_of,
    neutral: neutral.checked,
    n_train_matches: snapshot.n_train_matches,
    max_train_date: snapshot.max_train_date,
    probabilities: {
      team_a_win: pA,
      draw: pD,
      team_b_win: pB,
    },
    expected_goals: {
      team_a: lambdaA,
      team_b: lambdaB,
    },
    most_likely_score: {
      team_a: score.a,
      team_b: score.b,
    },
    goal_intervals: {
      team_a: [poissonQuantile(0.05, lambdaA), poissonQuantile(0.95, lambdaA)],
      team_b: [poissonQuantile(0.05, lambdaB), poissonQuantile(0.95, lambdaB)],
    },
    uncertainty: minMatches < 8 ? "alta" : minMatches < 25 ? "media" : "baja",
    influential_variables: {
      elo_team_a: a.elo,
      elo_team_b: b.elo,
      elo_diff_adjusted: eloDiff,
      home_attack: a.attack,
      away_attack: b.attack,
      home_defense_allowed_rate: a.defense,
      away_defense_allowed_rate: b.defense,
      dixon_coles_rho: 0,
      neutral_venue: neutral.checked ? 1 : 0,
    },
    warning: snapshot.snapshot_max_date > snapshot.as_of
      ? "El snapshot original contiene filas posteriores a la fecha de corte; esta vista usa solo el corte entrenado."
      : "",
  };
}

async function predict() {
  setLoading(true);
  showError("");
  if (window.MODEL_SNAPSHOT) {
    const data = predictLocal();
    if (data) {
      renderPrediction(data);
    }
    setLoading(false);
    return;
  }

  const params = new URLSearchParams({
    team_a: teamA.value.trim(),
    team_b: teamB.value.trim(),
    as_of: asOf.value,
    neutral: neutral.checked ? "true" : "false",
  });
  try {
    const response = await fetch(`/api/predict?${params.toString()}`);
    const data = await response.json();
    if (!response.ok) {
      showError(data.error || "No se pudo calcular la prediccion.");
      return;
    }
    renderPrediction(data);
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
