const FLAG_CDN_BASE = "https://flagcdn.com";

const COUNTRY_TO_ISO2 = {
  "south africa": "za", "canada": "ca", "netherlands": "nl", "morocco": "ma",
  "germany": "de", "paraguay": "py", "france": "fr", "sweden": "se",
  "belgium": "be", "senegal": "sn", "united states": "us", "usa": "us",
  "bosnia and herzegovina": "ba", "bosnia": "ba", "spain": "es", "austria": "at",
  "portugal": "pt", "croatia": "hr", "brazil": "br", "japan": "jp",
  "ivory coast": "ci", "cote d'ivoire": "ci", "cote divoire": "ci", "norway": "no",
  "mexico": "mx", "ecuador": "ec", "england": "gb-eng", "dr congo": "cd",
  "democratic republic of the congo": "cd", "switzerland": "ch", "algeria": "dz",
  "colombia": "co", "ghana": "gh", "argentina": "ar", "cabo verde": "cv",
  "cape verde": "cv", "australia": "au", "egypt": "eg", "eqypt": "eg"
};

const COUNTRY_TO_FIFA3 = {
  "south africa": "RSA", "canada": "CAN", "netherlands": "NED", "morocco": "MAR",
  "germany": "GER", "paraguay": "PAR", "france": "FRA", "sweden": "SWE",
  "belgium": "BEL", "senegal": "SEN", "united states": "USA", "usa": "USA",
  "bosnia and herzegovina": "BIH", "bosnia": "BIH", "spain": "ESP", "austria": "AUT",
  "portugal": "POR", "croatia": "CRO", "brazil": "BRA", "japan": "JPN",
  "ivory coast": "CIV", "cote d'ivoire": "CIV", "cote divoire": "CIV", "norway": "NOR",
  "mexico": "MEX", "ecuador": "ECU", "england": "ENG", "dr congo": "COD",
  "democratic republic of the congo": "COD", "switzerland": "SUI", "algeria": "ALG",
  "colombia": "COL", "ghana": "GHA", "argentina": "ARG", "cabo verde": "CPV",
  "cape verde": "CPV", "australia": "AUS", "egypt": "EGY", "eqypt": "EGY"
};

function normalizeCountryName(name) {
  return (name || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9' ]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function getFlagCode(teamName) {
  const normalized = normalizeCountryName(teamName);
  return COUNTRY_TO_ISO2[normalized] || null;
}

function getFlagUrl(teamName) {
  const code = getFlagCode(teamName);
  return code ? `${FLAG_CDN_BASE}/${code}.svg` : null;
}

function getFifaCode(teamName) {
  const normalized = normalizeCountryName(teamName);
  return COUNTRY_TO_FIFA3[normalized] || teamName;
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) {
    return parts.pop().split(";").shift();
  }
  return "";
}

function renderRoundSliceInteractive(state, teamsForRound, containerId, roundIndex, startMatch, matchCount, setWinner) {
  const container = document.getElementById(containerId);
  if (!container) return;

  const isMobileContainer = containerId.startsWith("mobile-");
  const teams = teamsForRound(roundIndex);
  container.innerHTML = "";

  for (let matchIndex = startMatch; matchIndex < startMatch + matchCount; matchIndex += 1) {
    const i = matchIndex * 2;
    const selected = state.rounds[roundIndex][matchIndex];

    const match = document.createElement("div");
    match.className = "match";

    [teams[i], teams[i + 1]].forEach((team) => {
      const btn = document.createElement("button");
      btn.className = "team";
      const flagUrl = getFlagUrl(team);
      const fifaCode = getFifaCode(team);
      const labelText = team && team !== "TBD" ? (isMobileContainer ? team : fifaCode) : "TBD";
      const isLockedMatch = state.officialRounds[roundIndex][matchIndex] !== null;

      if (flagUrl) {
        const flag = document.createElement("img");
        flag.className = "flag";
        flag.src = flagUrl;
        flag.alt = `${team} flag`;
        flag.loading = "lazy";
        flag.referrerPolicy = "no-referrer";
        flag.addEventListener("error", () => flag.remove());
        btn.appendChild(flag);
      }

      const label = document.createElement("span");
      label.className = "team-label";
      label.textContent = labelText;
      btn.appendChild(label);

      if (!team || team === "TBD") {
        btn.classList.add("disabled");
        btn.disabled = true;
      } else {
        btn.title = team;
        btn.setAttribute("aria-label", `${team} (${fifaCode})`);
        if (isLockedMatch) {
          btn.classList.add("disabled");
          btn.disabled = true;
        } else {
          btn.addEventListener("click", () => setWinner(roundIndex, matchIndex, team));
        }
      }

      if (selected === team) btn.classList.add("selected");
      match.appendChild(btn);
    });

    container.appendChild(match);
  }
}

function renderRoundSliceReadonly(rounds, teamsForRound, containerId, roundIndex, startMatch, count) {
  const container = document.getElementById(containerId);
  if (!container) return;

  const isMobileContainer = containerId.startsWith("mobile-");
  const teams = teamsForRound(roundIndex);
  container.innerHTML = "";

  for (let matchIndex = startMatch; matchIndex < startMatch + count; matchIndex += 1) {
    const i = matchIndex * 2;
    const selected = (rounds[roundIndex] || [])[matchIndex] || null;

    const match = document.createElement("div");
    match.className = "match";

    [teams[i], teams[i + 1]].forEach((team) => {
      const row = document.createElement("div");
      row.className = "team";

      const flagUrl = getFlagUrl(team);
      if (flagUrl) {
        const flag = document.createElement("img");
        flag.className = "flag";
        flag.src = flagUrl;
        flag.alt = `${team} flag`;
        flag.loading = "lazy";
        flag.referrerPolicy = "no-referrer";
        flag.addEventListener("error", () => flag.remove());
        row.appendChild(flag);
      }

      const label = document.createElement("span");
      label.textContent = team && team !== "TBD" ? (isMobileContainer ? team : getFifaCode(team)) : "TBD";
      row.appendChild(label);

      if (selected === team) row.classList.add("selected");
      match.appendChild(row);
    });

    container.appendChild(match);
  }
}

function renderLeaderboardRows(body, rows, rankStart = 0) {
  if (!rows.length) {
    body.innerHTML = "<tr><td colspan='4'>No submissions yet.</td></tr>";
    return;
  }

  body.innerHTML = rows
    .map(
      (row, idx) => `<tr><td>${rankStart + idx + 1}</td><td>${escapeHtml(row.name)}</td><td>${row.score}/${row.possible}</td><td><a class=\"view-btn\" href=\"/entry/${row.id}/\">View</a></td></tr>`
    )
    .join("");
}

async function fetchLeaderboardRows() {
  const res = await fetch("/api/leaderboard/");
  const data = await res.json();
  return data.rows || [];
}

function initRoundWizard() {
  const layout = document.getElementById("mobileLayout");
  const wizard = document.getElementById("roundWizard");
  const stageEl = document.getElementById("wizardStage");
  const prevBtn = document.getElementById("wizardPrev");
  const nextBtn = document.getElementById("wizardNext");

  if (!layout || !wizard || !stageEl || !prevBtn || !nextBtn) return;

  const stages = ["r32", "r16", "qf", "sf", "final"];
  const labels = {
    r32: "Round of 32",
    r16: "Round of 16",
    qf: "Quarterfinal",
    sf: "Semifinal",
    final: "Final",
  };

  let currentIndex = 0;

  function applyStep() {
    const step = stages[currentIndex];
    layout.dataset.roundStep = step;
    stageEl.textContent = labels[step];
    const isFirst = currentIndex === 0;
    const isLast = currentIndex === stages.length - 1;

    prevBtn.style.visibility = isFirst ? "hidden" : "visible";
    nextBtn.style.visibility = isLast ? "hidden" : "visible";
    prevBtn.disabled = isFirst;
    nextBtn.disabled = isLast;
  }

  prevBtn.addEventListener("click", () => {
    if (currentIndex > 0) {
      currentIndex -= 1;
      applyStep();
    }
  });

  nextBtn.addEventListener("click", () => {
    if (currentIndex < stages.length - 1) {
      currentIndex += 1;
      applyStep();
    }
  });

  applyStep();
}

function setChampionLabels(champion) {
  const display = champion && champion !== "TBD" ? getFifaCode(champion) : "TBD";
  const flagUrl = champion && champion !== "TBD" ? getFlagUrl(champion) : null;

  const winner = document.getElementById("winner");
  const mobileWinner = document.getElementById("mobile-winner");
  const winnerFlag = document.getElementById("winner-flag");
  const mobileWinnerFlag = document.getElementById("mobile-winner-flag");

  if (winner) winner.textContent = display;
  if (mobileWinner) mobileWinner.textContent = display;

  [winnerFlag, mobileWinnerFlag].forEach((img) => {
    if (!img) return;

    if (flagUrl) {
      img.src = flagUrl;
      img.alt = `${champion} flag`;
      img.hidden = false;
    } else {
      img.src = "";
      img.alt = "";
      img.hidden = true;
    }
  });
}

async function refreshLeaderboardBody(body) {
  if (!body) return;

  try {
    const rows = await fetchLeaderboardRows();
    renderLeaderboardRows(body, rows);
    return rows;
  } catch (_err) {
    body.innerHTML = "<tr><td colspan='4'>Unable to load leaderboard.</td></tr>";
    return [];
  }
}

function initIndexPage() {
  const teamsNode = document.getElementById("teams-data");
  if (!teamsNode) return;

  const TEAMS = JSON.parse(teamsNode.textContent);
  const STORAGE_KEY = "wc2026_quick_bracket";
  const API_SUBMIT_ENTRY = "/api/submit-entry/";
  const API_RESULTS = "/api/results/";

  const state = {
    officialRounds: [
      Array(16).fill(null),
      Array(8).fill(null),
      Array(4).fill(null),
      Array(2).fill(null),
      Array(1).fill(null),
    ],
    rounds: [
      Array(16).fill(null),
      Array(8).fill(null),
      Array(4).fill(null),
      Array(2).fill(null),
      Array(1).fill(null),
    ]
  };

  function getTeamsForRound(roundIndex) {
    if (roundIndex === 0) return TEAMS;
    const prevWinners = state.rounds[roundIndex - 1];
    const teams = [];
    for (let i = 0; i < prevWinners.length; i += 1) {
      teams.push(prevWinners[i] || "TBD");
    }
    return teams;
  }

  function saveState() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state.rounds));
  }

  function loadState() {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
      if (
        Array.isArray(saved) &&
        saved.length === 5 &&
        saved[0].length === 16 &&
        saved[1].length === 8 &&
        saved[2].length === 4 &&
        saved[3].length === 2 &&
        saved[4].length === 1
      ) {
        state.rounds = saved;
      }
    } catch (_err) {
      // Ignore malformed localStorage data.
    }

    applyOfficialResultsToState();
  }

  function setWinner(roundIndex, matchIndex, team) {
    state.rounds[roundIndex][matchIndex] = team;
    for (let r = roundIndex + 1; r < state.rounds.length; r += 1) {
      const dependentMatch = Math.floor(matchIndex / Math.pow(2, r - roundIndex));
      state.rounds[r][dependentMatch] = null;
    }
    saveState();
    renderAll();
  }

  function renderAll() {
    renderRoundSliceInteractive(state, getTeamsForRound, "left-r32", 0, 0, 8, setWinner);
    renderRoundSliceInteractive(state, getTeamsForRound, "left-r16", 1, 0, 4, setWinner);
    renderRoundSliceInteractive(state, getTeamsForRound, "left-qf", 2, 0, 2, setWinner);
    renderRoundSliceInteractive(state, getTeamsForRound, "left-sf", 3, 0, 1, setWinner);
    renderRoundSliceInteractive(state, getTeamsForRound, "right-r32", 0, 8, 8, setWinner);
    renderRoundSliceInteractive(state, getTeamsForRound, "right-r16", 1, 4, 4, setWinner);
    renderRoundSliceInteractive(state, getTeamsForRound, "right-qf", 2, 2, 2, setWinner);
    renderRoundSliceInteractive(state, getTeamsForRound, "right-sf", 3, 1, 1, setWinner);
    renderRoundSliceInteractive(state, getTeamsForRound, "final", 4, 0, 1, setWinner);

    renderRoundSliceInteractive(state, getTeamsForRound, "mobile-r32", 0, 0, 16, setWinner);
    renderRoundSliceInteractive(state, getTeamsForRound, "mobile-r16", 1, 0, 8, setWinner);
    renderRoundSliceInteractive(state, getTeamsForRound, "mobile-qf", 2, 0, 4, setWinner);
    renderRoundSliceInteractive(state, getTeamsForRound, "mobile-sf", 3, 0, 2, setWinner);
    renderRoundSliceInteractive(state, getTeamsForRound, "mobile-final", 4, 0, 1, setWinner);

    const champion = state.rounds[4][0] || "TBD";
    setChampionLabels(champion);
  }

  function applyOfficialResultsToState() {
    for (let roundIndex = 0; roundIndex < state.officialRounds.length; roundIndex += 1) {
      for (let matchIndex = 0; matchIndex < state.officialRounds[roundIndex].length; matchIndex += 1) {
        const winner = state.officialRounds[roundIndex][matchIndex];
        if (winner) {
          state.rounds[roundIndex][matchIndex] = winner;
        }
      }
    }
  }

  async function loadOfficialResults() {
    try {
      const res = await fetch(API_RESULTS);
      const data = await res.json();
      if (!res.ok || !data.ok || !Array.isArray(data.rounds)) {
        return;
      }

      state.officialRounds = data.rounds;
      applyOfficialResultsToState();
      saveState();
      renderAll();
    } catch (_err) {
      // Keep page usable even if official result sync fails.
    }
  }

  function resetBracket() {
    state.rounds = [
      Array(16).fill(null),
      Array(8).fill(null),
      Array(4).fill(null),
      Array(2).fill(null),
      Array(1).fill(null),
    ];
    applyOfficialResultsToState();
    saveState();
    renderAll();
  }

  function randomizeBracket() {
    resetBracket();
    for (let r = 0; r < 5; r += 1) {
      const teams = getTeamsForRound(r);
      for (let i = 0; i < teams.length; i += 2) {
        if (state.officialRounds[r][i / 2]) {
          continue;
        }
        const pick = Math.random() > 0.5 ? teams[i] : teams[i + 1];
        if (pick && pick !== "TBD") {
          state.rounds[r][i / 2] = pick;
        }
      }
    }
    applyOfficialResultsToState();
    saveState();
    renderAll();
  }

  function hasCompleteBracket() {
    return state.rounds.every((round) => round.every((pick) => !!pick));
  }

  function refreshLeaderboard() {
    const body = document.getElementById("leaderboardBody");
    if (!body) return Promise.resolve([]);

    return fetchLeaderboardRows()
      .then((rows) => {
        renderLeaderboardRows(body, rows.slice(0, 5), 0);
        return rows;
      })
      .catch(() => {
        body.innerHTML = "<tr><td colspan='4'>Unable to load leaderboard.</td></tr>";
        return [];
      });
  }

  async function submitEntry() {
    const nameInput = document.getElementById("entryName");
    const status = document.getElementById("submitStatus");
    if (!nameInput || !status) return;

    const name = nameInput.value.trim();

    if (!hasCompleteBracket()) {
      status.textContent = "Complete every pick before submitting.";
      return;
    }
    if (!name) {
      status.textContent = "Enter your name first.";
      return;
    }

    try {
      const res = await fetch(API_SUBMIT_ENTRY, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCookie("csrftoken"),
        },
        body: JSON.stringify({ name, rounds: state.rounds }),
      });

      const contentType = res.headers.get("content-type") || "";
      let data = null;
      if (contentType.includes("application/json")) {
        data = await res.json();
      }

      if (!res.ok || !data || !data.ok) {
        if (data && data.error) {
          status.textContent = data.error;
        } else {
          status.textContent = `Submission failed (HTTP ${res.status}).`;
        }
        return;
      }

      window.location.href = "/leaderboard/";
    } catch (_err) {
      status.textContent = "Submission failed.";
    }
  }

  const resetBtn = document.getElementById("reset");
  const randomizeBtn = document.getElementById("randomize");
  const submitBtn = document.getElementById("submitEntry");
  const refreshBtn = document.getElementById("refreshLeaderboard");

  if (resetBtn) resetBtn.addEventListener("click", resetBracket);
  if (randomizeBtn) randomizeBtn.addEventListener("click", randomizeBracket);
  if (submitBtn) submitBtn.addEventListener("click", submitEntry);
  if (refreshBtn) refreshBtn.addEventListener("click", refreshLeaderboard);

  loadState();
  renderAll();
  initRoundWizard();
  refreshLeaderboard();
  loadOfficialResults();
}

function initLeaderboardPage() {
  const body = document.getElementById("leaderboardBody");
  const refreshBtn = document.getElementById("refreshLeaderboard");
  const pageSizeSelect = document.getElementById("leaderboardPageSize");
  const prevBtn = document.getElementById("leaderboardPrev");
  const nextBtn = document.getElementById("leaderboardNext");

  const state = {
    rows: [],
    page: 1,
    pageSize: pageSizeSelect ? Number(pageSizeSelect.value) : 10,
  };

  function renderPage() {
    if (!body) return;

    const totalRows = state.rows.length;
    const totalPages = Math.max(1, Math.ceil(totalRows / state.pageSize));
    if (state.page > totalPages) state.page = totalPages;

    const start = (state.page - 1) * state.pageSize;
    const end = start + state.pageSize;
    const pageRows = state.rows.slice(start, end);
    renderLeaderboardRows(body, pageRows, start);

    if (prevBtn) prevBtn.hidden = state.page <= 1;
    if (nextBtn) nextBtn.hidden = state.page >= totalPages;
  }

  async function refreshAllRows() {
    if (!body) return;

    try {
      state.rows = await fetchLeaderboardRows();
      renderPage();
    } catch (_err) {
      body.innerHTML = "<tr><td colspan='4'>Unable to load leaderboard.</td></tr>";
    }
  }

  if (refreshBtn) {
    refreshBtn.addEventListener("click", refreshAllRows);
  }

  if (pageSizeSelect) {
    pageSizeSelect.addEventListener("change", () => {
      state.pageSize = Number(pageSizeSelect.value) || 10;
      state.page = 1;
      renderPage();
    });
  }

  if (prevBtn) {
    prevBtn.addEventListener("click", () => {
      if (state.page > 1) {
        state.page -= 1;
        renderPage();
      }
    });
  }

  if (nextBtn) {
    nextBtn.addEventListener("click", () => {
      const totalPages = Math.max(1, Math.ceil(state.rows.length / state.pageSize));
      if (state.page < totalPages) {
        state.page += 1;
        renderPage();
      }
    });
  }

  refreshAllRows();
}

function initReadonlyPage() {
  const roundsNode = document.getElementById("entry-rounds");
  const teamsNode = document.getElementById("initial-teams");
  if (!roundsNode || !teamsNode) return;

  const rounds = JSON.parse(roundsNode.textContent);
  const initialTeams = JSON.parse(teamsNode.textContent);

  function teamsForRound(roundIndex) {
    if (roundIndex === 0) return initialTeams;
    const prior = rounds[roundIndex - 1] || [];
    return prior.map((team) => team || "TBD");
  }

  renderRoundSliceReadonly(rounds, teamsForRound, "left-r32", 0, 0, 8);
  renderRoundSliceReadonly(rounds, teamsForRound, "left-r16", 1, 0, 4);
  renderRoundSliceReadonly(rounds, teamsForRound, "left-qf", 2, 0, 2);
  renderRoundSliceReadonly(rounds, teamsForRound, "left-sf", 3, 0, 1);
  renderRoundSliceReadonly(rounds, teamsForRound, "right-r32", 0, 8, 8);
  renderRoundSliceReadonly(rounds, teamsForRound, "right-r16", 1, 4, 4);
  renderRoundSliceReadonly(rounds, teamsForRound, "right-qf", 2, 2, 2);
  renderRoundSliceReadonly(rounds, teamsForRound, "right-sf", 3, 1, 1);
  renderRoundSliceReadonly(rounds, teamsForRound, "final", 4, 0, 1);

  renderRoundSliceReadonly(rounds, teamsForRound, "mobile-r32", 0, 0, 16);
  renderRoundSliceReadonly(rounds, teamsForRound, "mobile-r16", 1, 0, 8);
  renderRoundSliceReadonly(rounds, teamsForRound, "mobile-qf", 2, 0, 4);
  renderRoundSliceReadonly(rounds, teamsForRound, "mobile-sf", 3, 0, 2);
  renderRoundSliceReadonly(rounds, teamsForRound, "mobile-final", 4, 0, 1);

  const champion = (rounds[4] || [])[0] || "TBD";
  setChampionLabels(champion);

  initRoundWizard();
}

document.addEventListener("DOMContentLoaded", () => {
  const page = document.body.dataset.page;
  if (page === "index") {
    initIndexPage();
  }
  if (page === "readonly") {
    initReadonlyPage();
  }
  if (page === "leaderboard") {
    initLeaderboardPage();
  }
});
