let dashboardData = null;
let selectedSlates = new Set();
let showCompleted = false;
let yahooShowBench = false;

async function loadDashboard() {
    try {
        const response = await fetch('/api/dashboard', {cache: 'no-store'});
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Dashboard error');
        dashboardData = data;
        initializeSelectedSlates();
        renderDashboard();
    } catch (error) {
        document.getElementById('content').innerHTML = `<div class="error">${escapeHtml(error.message)}</div>`;
    }
}

function initializeSelectedSlates() {
    if (selectedSlates.size === 0 && dashboardData.next_slate_id !== null) {
        selectedSlates.add(dashboardData.next_slate_id);
    }
}

function toggleSlate(id) {
    if (selectedSlates.has(id)) selectedSlates.delete(id);
    else selectedSlates.add(id);
    renderDashboard();
}

function toggleCompleted() {
    showCompleted = !showCompleted;
    renderDashboard();
}

function toggleYahooBench() {
    yahooShowBench = !yahooShowBench;
    renderDashboard();
}

function renderDashboard() {
    document.getElementById('content').innerHTML = `
        ${renderSlateSelector()}
        <div class="refresh-row">
            <div class="updated">Live dashboard</div>
            <button class="refresh" onclick="refreshDashboard()">↻ Refresh</button>
        </div>
        ${renderSleeper()}
        ${renderYahoo()}
        ${renderESPN()}
    `;
}

function renderSlateSelector() {
    if (!dashboardData.slates?.length) return '';
    const options = dashboardData.slates.map(slate => `
        <div class="slate-option">
            <input type="checkbox" id="slate-${slate.id}" ${selectedSlates.has(slate.id) ? 'checked' : ''} onchange="toggleSlate(${slate.id})">
            <label for="slate-${slate.id}">${escapeHtml(slate.label)}</label>
        </div>
    `).join('');
    return `
        <div class="slate-card">
            <div class="slate-label">NFL SLATES</div>
            <div class="slate-options">
                ${options}
                <div class="slate-option completed-option">
                    <input type="checkbox" id="games-completed" ${showCompleted ? 'checked' : ''} onchange="toggleCompleted()">
                    <label for="games-completed">Games Completed</label>
                </div>
            </div>
        </div>
    `;
}

function playerGameHasFinished(player) {
    const status = String(player.game_status || '').toUpperCase();
    const detail = String(player.status_detail || '').toUpperCase();
    return status.includes('FINAL') || status.includes('COMPLETED') || detail.includes('FINAL') || detail.includes('END');
}

function playerGameIsLive(player) {
    const status = String(player.game_status || '').toUpperCase();
    const detail = String(player.status_detail || '').toUpperCase();
    if (playerGameHasFinished(player)) return false;
    return status.includes('IN_PROGRESS') || status.includes('IN PROGRESS') || status === 'LIVE' || status.includes('LIVE') ||
        ['Q1', 'Q2', 'Q3', 'Q4', 'OT', 'HALFTIME'].some(x => detail.includes(x));
}

function playerBelongsToSelectedSlate(player) {
    if (showCompleted && playerGameHasFinished(player)) return true;
    if (!player.pro_team_id || selectedSlates.size === 0) return false;
    const teamId = String(player.pro_team_id).toUpperCase();
    for (const slateId of selectedSlates) {
        const slate = dashboardData.slates.find(item => item.id === slateId);
        if (!slate) continue;
        for (const game of slate.games) {
            if ([game.home_id, game.away_id, game.home, game.away].some(value => String(value).toUpperCase() === teamId)) return true;
        }
    }
    return false;
}

function renderSleeper() {
    return dashboardData.sleeper ? renderLeagueSection(dashboardData.sleeper, 'Sleeper') : `<div class="league-section"><div class="error">${escapeHtml(dashboardData.sleeper_error || 'Sleeper data unavailable.')}</div></div>`;
}
function renderYahoo() {
    return dashboardData.yahoo ? renderLeagueSection(dashboardData.yahoo, 'Yahoo') : `<div class="league-section"><div class="error">${escapeHtml(dashboardData.yahoo_error || 'Yahoo data unavailable.')}</div></div>`;
}
function renderESPN() {
    return dashboardData.espn ? renderLeagueSection(dashboardData.espn, 'ESPN') : `<div class="league-section"><div class="error">${escapeHtml(dashboardData.espn_error || 'ESPN data unavailable.')}</div></div>`;
}

function renderLeagueSection(league, platform) {
    const my = league.my_team;
    const opponent = league.opponent;
    return `
        <div class="league-section">
            <div class="league-subtitle">${escapeHtml(league.league_name || `Week ${league.week}`)}</div>
            <div class="score-card ${platform.toLowerCase()}">
                <div class="matchup">
                    <div>
                        <div class="team-abbrev">${escapeHtml(my.abbrev)}</div>
                        <div class="score">${formatNumber(my.actual_total ?? my.total ?? 0)}</div>
                        <div class="score-secondary">Actual</div>
                        <div class="score-secondary">Projected: ${formatNumber(my.projected_total ?? my.total ?? 0)}</div>
                    </div>
                    <div class="vs">VS</div>
                    <div>
                        <div class="team-abbrev">${escapeHtml(opponent.abbrev)}</div>
                        <div class="score">${formatNumber(opponent.actual_total ?? opponent.total ?? 0)}</div>
                        <div class="score-secondary">Actual</div>
                        <div class="score-secondary">Projected: ${formatNumber(opponent.projected_total ?? opponent.total ?? 0)}</div>
                    </div>
                </div>
            </div>
            <div class="rosters">
                ${renderTeam(my, platform)}
                ${renderTeam(opponent, platform)}
            </div>
            ${platform === 'Yahoo' ? `
                <div class="yahoo-bench-control">
                    <button class="refresh" onclick="toggleYahooBench()">${yahooShowBench ? 'Hide Bench' : 'Show Bench'}</button>
                </div>
            ` : ''}
        </div>
    `;
}

function renderTeam(team, platform) {
    const eligiblePlayers = (team.players || []).filter(playerBelongsToSelectedSlate);
    const starters = eligiblePlayers.filter(player => player.starter !== false);
    const bench = eligiblePlayers.filter(player => player.bench === true);
    let playerHtml = starters.length ? starters.map(renderPlayer).join('') : '<div class="no-players">No starters in selected slate</div>';
    if (platform === 'Yahoo' && yahooShowBench) playerHtml += renderBenchSection(bench);
    return `
        <div class="team-card">
            <div class="team-header">
                <div class="team-name">${escapeHtml(team.abbrev)}</div>
                <div>
                    <div class="team-total">${formatNumber(team.actual_total ?? team.total ?? 0)}</div>
                    <div class="team-total-secondary">Actual · Proj ${formatNumber(team.projected_total ?? team.total ?? 0)}</div>
                </div>
            </div>
            ${playerHtml}
        </div>
    `;
}

function renderBenchSection(bench) {
    if (!bench.length) return `<div class="bench-section"><div class="bench-title">BENCH</div><div class="no-players">No bench players in selected slate</div></div>`;
    return `<div class="bench-section"><div class="bench-title">BENCH</div>${bench.map(renderPlayer).join('')}</div>`;
}

function renderPlayer(player) {
    const projected = player.projected != null ? Number(player.projected).toFixed(2) : '--';
    const actual = player.actual != null ? Number(player.actual).toFixed(2) : '--';
    const finished = playerGameHasFinished(player);
    const live = playerGameIsLive(player);
    let points;
    if (finished) {
        points = `<div class="points"><span class="actual-points">${actual}</span><div class="points-label">ACTUAL</div></div>`;
    } else if (live) {
        points = `<div class="points"><span class="live-actual">${actual}</span><div class="points-secondary projected-points">${projected} PROJ</div></div>`;
    } else {
        points = `<div class="points"><span class="projected-points">${projected}</span><div class="points-label">PROJ</div></div>`;
    }
    let injury = '';
    if (player.injury && String(player.injury).toUpperCase() !== 'ACTIVE') {
        const injuryClass = ['OUT', 'DOUBTFUL'].includes(String(player.injury).toUpperCase()) ? 'injury-alert' : '';
        injury = `<span class="injury ${injuryClass}">${escapeHtml(player.injury)}</span>`;
    }
    let game = '';
    if (player.nfl_team && player.opponent && player.game_time) {
        game = `<span class="game-info">${escapeHtml(player.nfl_team)} vs ${escapeHtml(player.opponent)} · ${escapeHtml(player.game_time)}</span>`;
    } else if (player.nfl_team) {
        game = `<span class="game-info">${escapeHtml(player.nfl_team)}</span>`;
    }
    const projectionSource = player.projection_source && player.projected != null ? `<span class="game-info">${escapeHtml(player.projection_source)}</span>` : '';
    const playerClass = finished ? 'locked' : live ? 'live' : 'projected';
    const statusText = finished ? '✓ FINAL' : live ? '● LIVE' : 'PROJECTED';
    return `
        <div class="player">
            <div class="position">${escapeHtml(player.predicted_slot || player.slot)}</div>
            <div>
                <div class="player-name">${escapeHtml(player.name)}</div>
                <div class="player-meta"><span class="status ${playerClass}">${statusText}</span>${injury}${game}${projectionSource}</div>
            </div>
            ${points}
        </div>
    `;
}

function refreshDashboard() { loadDashboard(); }
function formatNumber(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number.toFixed(2) : '0.00';
}
function escapeHtml(value) {
    if (value == null) return '';
    return String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}

loadDashboard();
setInterval(loadDashboard, 60000);
