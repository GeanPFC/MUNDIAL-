const TEAM_ES = {
  Afghanistan: "Afganistán",
  Albania: "Albania",
  Algeria: "Argelia",
  Andorra: "Andorra",
  Angola: "Angola",
  Argentina: "Argentina",
  Armenia: "Armenia",
  Aruba: "Aruba",
  Australia: "Australia",
  Austria: "Austria",
  Azerbaijan: "Azerbaiyán",
  Bahamas: "Bahamas",
  Bahrain: "Baréin",
  Bangladesh: "Bangladés",
  Barbados: "Barbados",
  Belarus: "Bielorrusia",
  Belgium: "Bélgica",
  Belize: "Belice",
  Benin: "Benin",
  Bermuda: "Bermudas",
  Bolivia: "Bolivia",
  "Bosnia and Herzegovina": "Bosnia y Herzegovina",
  Botswana: "Botsuana",
  Brazil: "Brasil",
  Bulgaria: "Bulgaria",
  "Burkina Faso": "Burkina Faso",
  Burundi: "Burundi",
  Cambodia: "Camboya",
  Cameroon: "Camerún",
  Canada: "Canadá",
  "Cape Verde": "Cabo Verde",
  "Central African Republic": "República Centroafricana",
  Chad: "Chad",
  Chile: "Chile",
  China: "China",
  Colombia: "Colombia",
  Comoros: "Comoras",
  Congo: "Congo",
  "Cook Islands": "Islas Cook",
  "Costa Rica": "Costa Rica",
  Croatia: "Croacia",
  Cuba: "Cuba",
  Curacao: "Curazao",
  Cyprus: "Chipre",
  "Czech Republic": "Chequia",
  Denmark: "Dinamarca",
  Djibouti: "Yibuti",
  Dominica: "Dominica",
  "Dominican Republic": "República Dominicana",
  "DR Congo": "RD Congo",
  Ecuador: "Ecuador",
  Egypt: "Egipto",
  "El Salvador": "El Salvador",
  England: "Inglaterra",
  "Equatorial Guinea": "Guinea Ecuatorial",
  Eritrea: "Eritrea",
  Estonia: "Estonia",
  Eswatini: "Esuatini",
  Ethiopia: "Etiopía",
  "Faroe Islands": "Islas Feroe",
  Fiji: "Fiyi",
  Finland: "Finlandia",
  France: "Francia",
  Gabon: "Gabón",
  Gambia: "Gambia",
  Georgia: "Georgia",
  Germany: "Alemania",
  Ghana: "Ghana",
  Gibraltar: "Gibraltar",
  Greece: "Grecia",
  Grenada: "Granada",
  Guatemala: "Guatemala",
  Guinea: "Guinea",
  "Guinea-Bissau": "Guinea-Bisau",
  Guyana: "Guyana",
  Haiti: "Haití",
  Honduras: "Honduras",
  "Hong Kong": "Hong Kong",
  Hungary: "Hungría",
  Iceland: "Islandia",
  India: "India",
  Indonesia: "Indonesia",
  Iran: "Irán",
  Iraq: "Irak",
  Ireland: "Irlanda",
  Israel: "Israel",
  Italy: "Italia",
  "Ivory Coast": "Costa de Marfil",
  Jamaica: "Jamaica",
  Japan: "Japón",
  Jordan: "Jordania",
  Kazakhstan: "Kazajistán",
  Kenya: "Kenia",
  Kosovo: "Kosovo",
  Kuwait: "Kuwait",
  Kyrgyzstan: "Kirguistán",
  Laos: "Laos",
  Latvia: "Letonia",
  Lebanon: "Líbano",
  Lesotho: "Lesoto",
  Liberia: "Liberia",
  Libya: "Libia",
  Liechtenstein: "Liechtenstein",
  Lithuania: "Lituania",
  Luxembourg: "Luxemburgo",
  Macau: "Macao",
  Madagascar: "Madagascar",
  Malawi: "Malaui",
  Malaysia: "Malasia",
  Maldives: "Maldivas",
  Mali: "Mali",
  Malta: "Malta",
  Mauritania: "Mauritania",
  Mauritius: "Mauricio",
  Mexico: "México",
  Moldova: "Moldavia",
  Mongolia: "Mongolia",
  Montenegro: "Montenegro",
  Morocco: "Marruecos",
  Mozambique: "Mozambique",
  Myanmar: "Myanmar",
  Namibia: "Namibia",
  Nepal: "Nepal",
  Netherlands: "Países Bajos",
  "New Caledonia": "Nueva Caledonia",
  "New Zealand": "Nueva Zelanda",
  Nicaragua: "Nicaragua",
  Niger: "Níger",
  Nigeria: "Nigeria",
  "North Korea": "Corea del Norte",
  "North Macedonia": "Macedonia del Norte",
  "Northern Ireland": "Irlanda del Norte",
  Norway: "Noruega",
  Oman: "Omán",
  Pakistan: "Pakistán",
  Palestine: "Palestina",
  Panama: "Panamá",
  Paraguay: "Paraguay",
  Peru: "Perú",
  Philippines: "Filipinas",
  Poland: "Polonia",
  Portugal: "Portugal",
  Qatar: "Catar",
  Romania: "Rumanía",
  Russia: "Rusia",
  Rwanda: "Ruanda",
  Samoa: "Samoa",
  "San Marino": "San Marino",
  "Saudi Arabia": "Arabia Saudita",
  Scotland: "Escocia",
  Senegal: "Senegal",
  Serbia: "Serbia",
  Seychelles: "Seychelles",
  "Sierra Leone": "Sierra Leona",
  Singapore: "Singapur",
  Slovakia: "Eslovaquia",
  Slovenia: "Eslovenia",
  Somalia: "Somalia",
  "South Africa": "Sudáfrica",
  "South Korea": "Corea del Sur",
  Spain: "España",
  "Sri Lanka": "Sri Lanka",
  Sudan: "Sudán",
  Suriname: "Surinam",
  Sweden: "Suecia",
  Switzerland: "Suiza",
  Syria: "Siria",
  Tahiti: "Tahití",
  Taiwan: "Taiwán",
  Tajikistan: "Tayikistán",
  Tanzania: "Tanzania",
  Thailand: "Tailandia",
  Togo: "Togo",
  Tonga: "Tonga",
  "Trinidad and Tobago": "Trinidad y Tobago",
  Tunisia: "Túnez",
  Turkey: "Turquía",
  Turkmenistan: "Turkmenistán",
  Uganda: "Uganda",
  Ukraine: "Ucrania",
  "United Arab Emirates": "Emiratos Árabes Unidos",
  "United States": "Estados Unidos",
  Uruguay: "Uruguay",
  Uzbekistan: "Uzbekistán",
  Vanuatu: "Vanuatu",
  Venezuela: "Venezuela",
  Vietnam: "Vietnam",
  Wales: "Gales",
  Yemen: "Yemen",
  Zambia: "Zambia",
  Zimbabwe: "Zimbabue",
};

const EXTRA_ALIASES = {
  "usa": "United States",
  "eeuu": "United States",
  "ee uu": "United States",
  "estados unidos de america": "United States",
  "holanda": "Netherlands",
  "paises bajos": "Netherlands",
  "republica checa": "Czech Republic",
  "chequia": "Czech Republic",
  "costa rica": "Costa Rica",
  "costa de marfil": "Ivory Coast",
  "rd congo": "DR Congo",
  "republica democratica del congo": "DR Congo",
  "congo democratico": "DR Congo",
  "emiratos arabes": "United Arab Emirates",
  "emiratos arabes unidos": "United Arab Emirates",
  "arabia saudita": "Saudi Arabia",
  "corea sur": "South Korea",
  "corea del sur": "South Korea",
  "corea norte": "North Korea",
  "corea del norte": "North Korea",
  "irlanda norte": "Northern Ireland",
  "irlanda del norte": "Northern Ireland",
  "macedonia norte": "North Macedonia",
  "macedonia del norte": "North Macedonia",
  "bosnia": "Bosnia and Herzegovina",
  "bosnia herzegovina": "Bosnia and Herzegovina",
  "bosnia y herzegovina": "Bosnia and Herzegovina",
  "trinidad tobago": "Trinidad and Tobago",
  "trinidad y tobago": "Trinidad and Tobago",
  "nueva zelanda": "New Zealand",
  "nueva caledonia": "New Caledonia",
  "islas feroe": "Faroe Islands",
  "islas cook": "Cook Islands",
  "republica dominicana": "Dominican Republic",
  "republica centroafricana": "Central African Republic",
  "guinea ecuatorial": "Equatorial Guinea",
  "guinea bisau": "Guinea-Bissau",
  "guinea bissau": "Guinea-Bissau",
  "burkina faso": "Burkina Faso",
  "sierra leona": "Sierra Leone",
  "sudafrica": "South Africa",
  "sri lanka": "Sri Lanka",
  "hong kong": "Hong Kong",
  "san marino": "San Marino",
  "cabo verde": "Cape Verde",
};

function normalizeText(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/&/g, " y ")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function displayTeam(team) {
  return TEAM_ES[team] || team;
}

function buildTeamLookup(teams) {
  const lookup = new Map();
  for (const team of teams) {
    lookup.set(normalizeText(team), team);
    lookup.set(normalizeText(displayTeam(team)), team);
  }
  for (const [alias, team] of Object.entries(EXTRA_ALIASES)) {
    if (teams.includes(team)) {
      lookup.set(normalizeText(alias), team);
    }
  }
  return lookup;
}

function resolveTeam(input, teams) {
  const normalized = normalizeText(input);
  const lookup = buildTeamLookup(teams);
  return lookup.get(normalized) || null;
}

function teamSuggestions(input, teams, limit = 5) {
  const normalized = normalizeText(input);
  if (!normalized) return [];
  return teams
    .map((team) => ({
      team,
      label: displayTeam(team),
      score: Math.max(
        normalizeText(team).startsWith(normalized) ? normalized.length : 0,
        normalizeText(displayTeam(team)).startsWith(normalized) ? normalized.length : 0,
      ),
    }))
    .filter((row) => row.score > 0)
    .sort((a, b) => b.score - a.score || a.label.localeCompare(b.label))
    .slice(0, limit);
}

function publicTeams(teams) {
  return teams
    .map((team) => ({
      team,
      label: displayTeam(team),
      search: team === displayTeam(team) ? team : `${displayTeam(team)} (${team})`,
    }))
    .sort((a, b) => a.label.localeCompare(b.label, "es"));
}

export { displayTeam, publicTeams, resolveTeam, teamSuggestions };
