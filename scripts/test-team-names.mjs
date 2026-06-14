// Test de conversion de nombres de selecciones (ES <-> EN) y alias.
// Ejecutar:  node scripts/test-team-names.mjs
import { displayTeam, resolveTeam } from "../api/_teams_es.js";

// Subconjunto de equipos del dataset relevante para el Mundial 2026.
const TEAMS = [
  "Qatar", "United States", "Czech Republic", "DR Congo", "Switzerland",
  "Mexico", "South Korea", "Ivory Coast", "Cape Verde", "Saudi Arabia",
  "Netherlands", "Haiti", "Curaçao",
];

const resolveCases = [
  ["Catar", "Qatar"],
  ["catar", "Qatar"],
  ["EEUU", "United States"],
  ["Estados Unidos", "United States"],
  ["usa", "United States"],
  ["Chequia", "Czech Republic"],
  ["RD Congo", "DR Congo"],
  ["Suiza", "Switzerland"],
  ["Corea del Sur", "South Korea"],
  ["Costa de Marfil", "Ivory Coast"],
  ["Países Bajos", "Netherlands"],
  ["holanda", "Netherlands"],
];

const displayCases = [
  ["Qatar", "Catar"],
  ["United States", "Estados Unidos"],
  ["Czech Republic", "Chequia"],
  ["DR Congo", "RD Congo"],
  ["Haiti", "Haití"],
];

let failures = 0;
for (const [input, expected] of resolveCases) {
  const got = resolveTeam(input, TEAMS);
  const ok = got === expected;
  if (!ok) failures += 1;
  console.log(`${ok ? "OK " : "FAIL"} resolveTeam(${JSON.stringify(input)}) -> ${got} (esperado ${expected})`);
}
for (const [input, expected] of displayCases) {
  const got = displayTeam(input);
  const ok = got === expected;
  if (!ok) failures += 1;
  console.log(`${ok ? "OK " : "FAIL"} displayTeam(${JSON.stringify(input)}) -> ${got} (esperado ${expected})`);
}

if (failures > 0) {
  console.error(`\n${failures} casos fallaron.`);
  process.exit(1);
}
console.log("\nTodos los casos de nombres pasaron.");
