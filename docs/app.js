// WorldCupBench Dashboard - Static JS (reads from data/*.json)

const MODEL_COLORS = {
  'GPT-5.5': '#60B5FF',
  'Claude-Fable-5': '#FF9149',
  'Gemini-3.5-Flash': '#80D8C3',
  'Grok-4.3': '#FF6363',
  'DeepSeek-V4-Pro': '#A78BFA',
  'Qwen-3.7-Max': '#34D399',
  'Kimi-K2.6': '#F472B6',
  'GLM-5.1': '#FBBF24',
  'MiniMax-M3': '#38BDF8',
  'MiMo-V2.5-Pro': '#FB923C',
  'Nex-N2-Pro': '#C084FC',
};

// Country code to flag emoji.
const FLAGS = {};
const A = 0x1F1E6;
function codeToFlag(code) {
  if (!code || code.length < 2) return '\u{1F3F3}';
  // FIFA 3-letter to 2-letter mapping for common cases.
  const map3to2 = {
    'MEX':'MX','RSA':'ZA','KOR':'KR','CZE':'CZ','USA':'US','ENG':'GB','BRA':'BR','ARG':'AR',
    'FRA':'FR','GER':'DE','ESP':'ES','POR':'PT','NED':'NL','BEL':'BE','CRO':'HR','SUI':'CH',
    'URU':'UY','COL':'CO','CHI':'CL','PER':'PE','ECU':'EC','PAR':'PY','BOL':'BO','VEN':'VE',
    'JPN':'JP','AUS':'AU','IRN':'IR','KSA':'SA','QAT':'QA','CAN':'CA','CRC':'CR','HON':'HN',
    'JAM':'JM','PAN':'PA','TTO':'TT','SRB':'RS','POL':'PL','UKR':'UA','WAL':'GB','SCO':'GB',
    'IRL':'IE','DEN':'DK','SWE':'SE','NOR':'NO','FIN':'FI','AUT':'AT','ROU':'RO','GRE':'GR',
    'TUR':'TR','RUS':'RU','CIV':'CI','GHA':'GH','SEN':'SN','NGA':'NG','CMR':'CM','EGY':'EG',
    'MAR':'MA','TUN':'TN','ALG':'DZ','MLI':'ML','GUI':'GN','GAB':'GA','CGO':'CG','COD':'CD',
    'ZAM':'ZM','ZIM':'ZW','MOZ':'MZ','ANG':'AO','NAM':'NA','BOT':'BW','MAS':'MY',
    'THA':'TH','VIE':'VN','IDN':'ID','PHI':'PH','SGP':'SG','CHN':'CN','IND':'IN',
    'PAK':'PK','BAN':'BD','SRI':'LK','NZL':'NZ','SLV':'SV','GUA':'GT','NCA':'NI',
    'CUB':'CU','HAI':'HT','DOM':'DO','BRB':'BB','BER':'BM','ISR':'IL','IRQ':'IQ',
    'UZB':'UZ','KGZ':'KG','TJK':'TJ','AFG':'AF','MYA':'MM','LAO':'LA','CAM':'KH',
    'PRK':'KP','HKG':'HK','MAC':'MO','TPE':'TW','BHR':'BH','OMA':'OM','YEM':'YE',
    'JOR':'JO','LBN':'LB','SYR':'SY','KUW':'KW','UAE':'AE','PLW':'PW',
    'TOG':'TG','BEN':'BJ','BFA':'BF','NIG':'NE','CHA':'TD','CAF':'CF','STP':'ST',
    'GEQ':'GQ','COM':'KM','MDG':'MG','MRI':'MU','SEY':'SC','CPV':'CV','GNB':'GW',
    'SLE':'SL','LBR':'LR','GAM':'GM','MTN':'MR','DJI':'DJ','ERI':'ER','SOM':'SO',
    'SSD':'SS','ETH':'ET','KEN':'KE','UGA':'UG','RWA':'RW','BDI':'BI','TAN':'TZ',
    'MWI':'MW','LES':'LS','SWZ':'SZ','FIJ':'FJ','SAM':'WS','TON':'TO','VAN':'VU',
    'SOL':'SB','PNG':'PG','NCL':'NC','TAH':'PF','GUM':'GU','ASA':'AS','COK':'CK',
    'TGA':'TO','NIR':'GB','SKN':'KN','ANT':'AG','VIN':'VC','GRN':'GD','LCA':'LC',
    'DMA':'DM','MSR':'MS','AIA':'AI','VIR':'VI','CAY':'KY','TCA':'TC','BIH':'BA',
    'SVN':'SI','SVK':'SK','MKD':'MK','KOS':'XK','MNE':'ME','ALB':'AL','MDA':'MD',
    'BLR':'BY','LTU':'LT','LVA':'LV','EST':'EE','GEO':'GE','ARM':'AM','AZE':'AZ',
    'CYP':'CY','MLT':'MT','LUX':'LU','LIE':'LI','AND':'AD','FRO':'FO','ISL':'IS',
    'SMR':'SM','GIB':'GI',
  };
  let c2 = map3to2[code] || code.substring(0, 2).toUpperCase();
  try {
    return String.fromCodePoint(c2.charCodeAt(0) - 65 + A, c2.charCodeAt(1) - 65 + A);
  } catch {
    return '\u{1F3F3}';
  }
}

let leaderboard = null;
let tournament = null;
let predictionsSummary = null;

function accuracy(m) {
  if (!m) return null;
  if (m.accuracy === null || m.accuracy === undefined) return null;
  return Number(m.accuracy).toFixed(1);
}

async function loadData() {
  try {
    const [lb, tn, ps] = await Promise.all([
      fetch('data/leaderboard.json').then(r => r.ok ? r.json() : null).catch(() => null),
      fetch('data/tournament.json').then(r => r.ok ? r.json() : null).catch(() => null),
      fetch('data/predictions_summary.json').then(r => r.ok ? r.json() : null).catch(() => null),
    ]);
    leaderboard = lb;
    tournament = tn;
    predictionsSummary = ps;
  } catch (e) {
    console.error('Data load error:', e);
  }
  render();
}

function render() {
  renderStats();
  renderLeaderboard();
  renderConsensus();
  renderMatches();
  renderBracket();

  if (leaderboard?.last_updated) {
    const d = new Date(leaderboard.last_updated);
    document.getElementById('last-updated').textContent = `Updated: ${d.toLocaleDateString()} ${d.toLocaleTimeString()}`;
  }
}

// === STATS ===
function renderStats() {
  const el = document.getElementById('stats-row');
  const models = leaderboard?.total_models || 0;
  const results = leaderboard?.total_results || 0;
  const totalMatches = tournament?.matches?.length || 104;
  const accuracies = leaderboard?.models?.length
    ? leaderboard.models.map(m => accuracy(m)).filter(a => a !== null).map(Number)
    : [];
  const avgAcc = accuracies.length
    ? (accuracies.reduce((s, v) => s + v, 0) / accuracies.length).toFixed(1)
    : null;

  el.innerHTML = [
    { label: 'AI Models', value: models, icon: '\ud83e\udd16', color: 'blue' },
    { label: 'Results In', value: `${results}/${totalMatches}`, icon: '\u26bd', color: 'green' },
    { label: 'Avg Accuracy', value: results > 0 && avgAcc !== null ? `${avgAcc}%` : '\u2014', icon: '\ud83c\udfaf', color: 'gold' },
    { label: 'Tournament', value: results === 0 ? 'Pre-Kickoff' : 'Live', icon: '\ud83d\udcc5', color: 'purple' },
  ].map(s => `
    <div class="glass rounded-xl p-4 hover:border-${s.color === 'gold' ? 'gold' : `accent-${s.color}`}/30 transition">
      <div class="text-2xl mb-2">${s.icon}</div>
      <div class="text-2xl font-bold text-white">${s.value}</div>
      <div class="text-xs text-gray-400 mt-1">${s.label}</div>
    </div>
  `).join('');
}

// === LEADERBOARD ===
function renderLeaderboard() {
  const models = leaderboard?.models || [];
  const tbody = document.getElementById('leaderboard-table');
  const podium = document.getElementById('podium');

  if (!models.length) {
    tbody.innerHTML = '<tr><td colspan="9" class="px-4 py-12 text-center text-gray-500">No scoring data yet. Leaderboard will populate as match results come in.</td></tr>';
    podium.innerHTML = renderPreKickoffHero();
    return;
  }

  // Podium (top 3)
  if (models.length >= 3) {
    const [first, second, third] = models;
    podium.innerHTML = `
      <div class="grid grid-cols-3 gap-4 mb-8">
        ${renderPodiumCard(second, 2)}
        ${renderPodiumCard(first, 1)}
        ${renderPodiumCard(third, 3)}
      </div>
    `;
  }

  // Table
  tbody.innerHTML = models.map((m, i) => {
    const color = MODEL_COLORS[m.model_name] || '#9CA3AF';
    const medal = i === 0 ? '\ud83e\udd47' : i === 1 ? '\ud83e\udd48' : i === 2 ? '\ud83e\udd49' : `${i + 1}`;
    return `
      <tr class="border-t border-gray-800 hover:bg-bg-hover transition">
        <td class="px-4 py-3 font-bold">${medal}</td>
        <td class="px-4 py-3">
          <div class="flex items-center gap-2">
            <div class="w-3 h-3 rounded-full" style="background:${color}"></div>
            <span class="font-medium text-white">${m.model_name}</span>
          </div>
        </td>
        <td class="px-4 py-3 text-center text-gray-300">${m.total_evaluated}</td>
        <td class="px-4 py-3 text-center text-green-400">${m.correct_outcomes}</td>
        <td class="px-4 py-3 text-center text-gold">${m.exact_scores}</td>
        <td class="px-4 py-3 text-center">
          <span class="font-bold" style="color:${color}">${accuracy(m) !== null ? accuracy(m) + '%' : '—'}</span>
        </td>
        <td class="px-4 py-3 text-center text-gray-300">${m.brier_avg ?? '—'}</td>
        <td class="px-4 py-3 text-center font-bold text-gold">${m.bracket_points}</td>
        <td class="px-4 py-3">
          <span class="text-lg">${codeToFlag(m.champion)}</span>
          <span class="text-xs text-gray-400 ml-1">${m.champion || '—'}</span>
        </td>
      </tr>
    `;
  }).join('');
}

function renderPodiumCard(model, position) {
  const color = MODEL_COLORS[model.model_name] || '#9CA3AF';
  const medals = { 1: ['\ud83e\udd47', 'medal-1'], 2: ['\ud83e\udd48', 'medal-2'], 3: ['\ud83e\udd49', 'medal-3'] };
  const [emoji, cls] = medals[position];
  const tall = position === 1 ? 'pt-0' : 'pt-8';
  return `
    <div class="${tall}">
      <div class="glass rounded-xl p-5 text-center ${position === 1 ? 'glow pulse-gold' : ''}">
        <div class="text-4xl mb-2">${emoji}</div>
        <div class="w-4 h-4 rounded-full mx-auto mb-2" style="background:${color}"></div>
        <h3 class="font-bold text-white text-lg">${model.model_name}</h3>
        <div class="mt-3 text-3xl font-black" style="color:${color}">${accuracy(model) !== null ? accuracy(model) + '%' : '—'}</div>
        <div class="text-xs text-gray-400 mt-1">accuracy</div>
        <div class="mt-3 flex justify-center gap-4 text-xs">
          <div><span class="text-green-400 font-bold">${model.correct_outcomes}</span> correct</div>
          <div><span class="text-gold font-bold">${model.bracket_points}</span> pts</div>
        </div>
        <div class="mt-3 text-2xl">${codeToFlag(model.champion)}</div>
      </div>
    </div>
  `;
}

function renderPreKickoffHero() {
  const models = predictionsSummary || [];
  const champCounts = {};
  models.forEach(m => {
    const c = m.champion || '?';
    champCounts[c] = (champCounts[c] || 0) + 1;
  });
  const sorted = Object.entries(champCounts).sort((a, b) => b[1] - a[1]);

  return `
    <div class="glass rounded-xl p-8 text-center mb-8 glow">
      <div class="text-5xl mb-4">\ud83c\udfc6</div>
      <h2 class="text-2xl font-bold text-white mb-2">Predictions Frozen</h2>
      <p class="text-gray-400 mb-6">${models.length} frontier AI models have locked in their predictions.<br>Scoring begins when the first match is played.</p>
      ${sorted.length ? `
        <div class="mb-4">
          <h3 class="text-sm font-semibold text-gray-300 mb-3">\ud83d\udd2e Champion Predictions</h3>
          <div class="flex flex-wrap justify-center gap-3">
            ${sorted.map(([code, count]) => `
              <div class="glass rounded-lg px-4 py-2 flex items-center gap-2">
                <span class="text-2xl">${codeToFlag(code)}</span>
                <span class="text-white font-bold">${code}</span>
                <span class="text-xs text-gray-400">${count}/${models.length}</span>
              </div>
            `).join('')}
          </div>
        </div>
      ` : ''}
      ${models.length ? `
        <div class="mt-6 overflow-x-auto">
          <table class="mx-auto text-sm">
            <thead><tr class="text-gray-400"><th class="px-3 py-1">Model</th><th class="px-3 py-1">\ud83e\udd47</th><th class="px-3 py-1">\ud83e\udd48</th><th class="px-3 py-1">\ud83e\udd49</th></tr></thead>
            <tbody>
              ${models.map(m => {
                const color = MODEL_COLORS[m.model_name] || '#9CA3AF';
                return `
                  <tr class="border-t border-gray-800">
                    <td class="px-3 py-2 flex items-center gap-2">
                      <div class="w-2 h-2 rounded-full" style="background:${color}"></div>
                      <span class="text-white">${m.model_name}</span>
                    </td>
                    <td class="px-3 py-2 text-center">${codeToFlag(m.champion)} ${m.champion || '—'}</td>
                    <td class="px-3 py-2 text-center">${codeToFlag(m.runner_up)} ${m.runner_up || '—'}</td>
                    <td class="px-3 py-2 text-center">${codeToFlag(m.third_place)} ${m.third_place || '—'}</td>
                  </tr>
                `;
              }).join('')}
            </tbody>
          </table>
        </div>
      ` : ''}
    </div>
  `;
}

// === CONSENSUS ===
function renderConsensus() {
  const el = document.getElementById('consensus-content');
  const models = predictionsSummary || [];

  if (!models.length) {
    el.innerHTML = '<p class="text-gray-500 text-center py-12">No predictions loaded.</p>';
    return;
  }

  // Champion consensus
  const champCounts = {};
  const runnerCounts = {};
  const thirdCounts = {};
  models.forEach(m => {
    champCounts[m.champion] = (champCounts[m.champion] || 0) + 1;
    runnerCounts[m.runner_up] = (runnerCounts[m.runner_up] || 0) + 1;
    thirdCounts[m.third_place] = (thirdCounts[m.third_place] || 0) + 1;
  });

  const n = models.length;
  const renderBar = (counts, label, emoji) => {
    const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]);
    return `
      <div class="glass rounded-xl p-6 mb-6">
        <h3 class="text-lg font-bold mb-4">${emoji} ${label}</h3>
        <div class="space-y-3">
          ${sorted.map(([code, count]) => {
            const pct = (count / n * 100).toFixed(0);
            return `
              <div class="flex items-center gap-3">
                <span class="text-2xl w-10">${codeToFlag(code)}</span>
                <span class="text-white font-medium w-12">${code}</span>
                <div class="flex-1 bg-gray-800 rounded-full h-6 overflow-hidden">
                  <div class="h-full rounded-full bg-gold/70 flex items-center pl-2 text-xs font-bold text-black" style="width:${pct}%">
                    ${count}/${n}
                  </div>
                </div>
                <span class="text-sm text-gray-400 w-12 text-right">${pct}%</span>
              </div>
            `;
          }).join('')}
        </div>
      </div>
    `;
  };

  el.innerHTML = renderBar(champCounts, 'Champion Predictions', '\ud83c\udfc6') +
                 renderBar(runnerCounts, 'Runner-Up Predictions', '\ud83e\udd48') +
                 renderBar(thirdCounts, 'Third Place Predictions', '\ud83e\udd49');
}

// === MATCHES ===
function renderMatches() {
  if (!tournament?.matches) return;

  const filtersEl = document.getElementById('group-filters');
  const gridEl = document.getElementById('matches-grid');

  const groups = [...new Set(tournament.matches.map(m => m.group))].sort();
  filtersEl.innerHTML = `
    <button onclick="filterMatches('all')" class="px-3 py-1 rounded-full text-xs font-medium bg-gold text-black" id="filter-all">All</button>
    ${groups.map(g => `
      <button onclick="filterMatches('${g}')" class="px-3 py-1 rounded-full text-xs font-medium bg-gray-800 text-gray-300 hover:bg-gray-700" id="filter-${g}">Group ${g}</button>
    `).join('')}
  `;

  window.filterMatches = (group) => {
    // Update button styles
    document.querySelectorAll('#group-filters button').forEach(b => {
      b.className = b.id === `filter-${group}` || (group === 'all' && b.id === 'filter-all')
        ? 'px-3 py-1 rounded-full text-xs font-medium bg-gold text-black'
        : 'px-3 py-1 rounded-full text-xs font-medium bg-gray-800 text-gray-300 hover:bg-gray-700';
    });

    const matches = group === 'all' ? tournament.matches : tournament.matches.filter(m => m.group === group);
    gridEl.innerHTML = matches.map(m => {
      const date = new Date(m.date + 'T00:00:00');
      const dateStr = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
      return `
        <div class="glass rounded-xl p-4 hover:border-gold/30 transition">
          <div class="flex items-center justify-between mb-3">
            <span class="text-xs px-2 py-0.5 rounded bg-gray-800 text-gray-400">Group ${m.group}</span>
            <span class="text-xs text-gray-500">${dateStr}</span>
          </div>
          <div class="flex items-center justify-between">
            <div class="text-center flex-1">
              <div class="text-2xl mb-1">${codeToFlag(m.home_team)}</div>
              <div class="text-xs font-medium text-white">${m.home_team}</div>
            </div>
            <div class="text-gray-500 text-sm font-bold px-4">vs</div>
            <div class="text-center flex-1">
              <div class="text-2xl mb-1">${codeToFlag(m.away_team)}</div>
              <div class="text-xs font-medium text-white">${m.away_team}</div>
            </div>
          </div>
          <div class="mt-3 text-xs text-gray-500 text-center">${m.venue?.stadium || ''}</div>
        </div>
      `;
    }).join('');
  };

  filterMatches('all');
}

// === BRACKET ===
function renderBracket() {
  const el = document.getElementById('bracket-content');
  if (!predictionsSummary?.length) {
    el.innerHTML = '<p class="text-gray-500 text-center py-12">Bracket data not available yet.</p>';
    return;
  }

  el.innerHTML = `
    <div class="glass rounded-xl p-6">
      <h2 class="text-lg font-bold mb-4">\ud83c\udfc5 Predicted Final Standings by Model</h2>
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-gray-400 border-b border-gray-800">
              <th class="px-4 py-3 text-left">Model</th>
              <th class="px-4 py-3 text-center">\ud83e\udd47 Champion</th>
              <th class="px-4 py-3 text-center">\ud83e\udd48 Runner-Up</th>
              <th class="px-4 py-3 text-center">\ud83e\udd49 Third</th>
              <th class="px-4 py-3 text-center">4th</th>
            </tr>
          </thead>
          <tbody>
            ${predictionsSummary.map(m => {
              const color = MODEL_COLORS[m.model_name] || '#9CA3AF';
              return `
                <tr class="border-t border-gray-800 hover:bg-bg-hover">
                  <td class="px-4 py-3">
                    <div class="flex items-center gap-2">
                      <div class="w-3 h-3 rounded-full" style="background:${color}"></div>
                      <span class="text-white font-medium">${m.model_name}</span>
                    </div>
                  </td>
                  <td class="px-4 py-3 text-center">${codeToFlag(m.champion)} ${m.champion || '—'}</td>
                  <td class="px-4 py-3 text-center">${codeToFlag(m.runner_up)} ${m.runner_up || '—'}</td>
                  <td class="px-4 py-3 text-center">${codeToFlag(m.third_place)} ${m.third_place || '—'}</td>
                  <td class="px-4 py-3 text-center">${codeToFlag(m.fourth_place)} ${m.fourth_place || '—'}</td>
                </tr>
              `;
            }).join('')}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

// === TAB SWITCHING ===
function showTab(name) {
  ['leaderboard', 'consensus', 'matches', 'bracket'].forEach(t => {
    document.getElementById(`section-${t}`).classList.toggle('hidden', t !== name);
    document.getElementById(`tab-${t}`).className = t === name ? 'tab-active pb-3 text-sm font-medium whitespace-nowrap transition' : 'tab-inactive pb-3 text-sm font-medium whitespace-nowrap transition';
  });
}

// === INIT ===
loadData();
// Auto-refresh every 60 seconds.
setInterval(loadData, 60000);
