let dashboardData = null;
let selectedSlates = new Set();
let showCompleted = false;


async function loadDashboard() {
    try {
        const r = await fetch(
            '/api/dashboard',
            {cache: 'no-store'}
        );

        const d = await r.json();

        if (!r.ok) {
            throw new Error(
                d.error || 'Dashboard error'
            );
        }

        dashboardData = d;
        initializeSelectedSlates();
        renderDashboard();

    } catch (e) {
        document.getElementById('content').innerHTML =
            `<div class="error">${escapeHtml(e.message)}</div>`;
    }
}


function initializeSelectedSlates() {
    if (
        selectedSlates.size === 0
        && dashboardData.next_slate_id !== null
    ) {
        selectedSlates.add(
            dashboardData.next_slate_id
        );
    }
}


function toggleSlate(id) {
    if (selectedSlates.has(id)) {
        selectedSlates.delete(id);
    } else {
        selectedSlates.add(id);
    }

    renderDashboard();
}


function toggleCompleted() {
    showCompleted = !showCompleted;
    renderDashboard();
}


function renderDashboard() {
    document.getElementById('content').innerHTML =
        `${renderSlateSelector()}
        <div class="refresh-row">
            <div class="updated">Live dashboard</div>
            <button class="refresh" onclick="refreshDashboard()">
                ↻ Refresh
            </button>
        </div>
        ${renderSleeper()}
        ${renderYahoo()}
        ${renderESPN()}`;
}


function renderSlateSelector() {
    if (!dashboardData.slates?.length) {
        return '';
    }

    const options = dashboardData.slates
        .map(
            s =>
                `<div class="slate-option">
                    <input
                        type="checkbox"
                        id="slate-${s.id}"
                        ${selectedSlates.has(s.id) ? 'checked' : ''}
                        onchange="toggleSlate(${s.id})"
                    >
                    <label for="slate-${s.id}">
                        ${escapeHtml(s.label)}
                    </label>
                </div>`
        )
        .join('');

    return `
        <div class="slate-card">
            <div class="slate-label">NFL SLATES</div>

            <div class="slate-options">
                ${options}

                <div class="slate-option completed-option">
                    <input
                        type="checkbox"
                        id="games-completed"
                        ${showCompleted ? 'checked' : ''}
                        onchange="toggleCompleted()"
                    >
                    <label for="games-completed">
                        Games Completed
                    </label>
                </div>
            </div>
        </div>
    `;
}


function playerGameHasFinished(p) {
    const status = String(
        p.game_status || ''
    ).toUpperCase();

    const detail = String(
        p.status_detail || ''
    ).toUpperCase();

    return (
        status.includes('FINAL')
        || status.includes('COMPLETED')
        || detail.includes('FINAL')
        || detail.includes('END')
    );
}


function playerGameIsLive(p) {
    const status = String(
        p.game_status || ''
    ).toUpperCase();

    const detail = String(
        p.status_detail || ''
    ).toUpperCase();

    if (playerGameHasFinished(p)) {
        return false;
    }

    return (
        status.includes('IN_PROGRESS')
        || status.includes('LIVE')
        || status.includes('INPROGRESS')
        || detail.includes('LIVE')
        || detail.includes('Q1')
        || detail.includes('Q2')
        || detail.includes('Q3')
        || detail.includes('Q4')
        || detail.includes('HALFTIME')
        || detail.includes('OT')
    );
}


function playerBelongsToSelectedSlate(p) {
    if (
        showCompleted
        && playerGameHasFinished(p)
    ) {
        return true;
    }

    if (
        !p.pro_team_id
        || selectedSlates.size === 0
    ) {
        return false;
    }

    const teamId = String(
        p.pro_team_id
    ).toUpperCase();

    for (const id of selectedSlates) {
        const slate = dashboardData.slates.find(
            x => x.id === id
        );

        if (!slate) {
            continue;
        }

        for (const g of slate.games) {
            if (
                [
                    g.home_id,
                    g.away_id,
                    g.home,
                    g.away
                ].some(
                    value =>
                        String(value).toUpperCase()
                        === teamId
                )
            ) {
                return true;
            }
        }
    }

    return false;
}


function renderSleeper() {
    return dashboardData.sleeper
        ? renderLeagueSection(
            dashboardData.sleeper,
            'Sleeper'
        )
        : `
            <div class="league-section">
                <div class="error">
                    ${escapeHtml(
                        dashboardData.sleeper_error
                        || 'Sleeper data unavailable.'
                    )}
                </div>
            </div>
        `;
}


function renderYahoo() {
    return dashboardData.yahoo
        ? renderLeagueSection(
            dashboardData.yahoo,
            'Yahoo'
        )
        : `
            <div class="league-section">
                <div class="error">
                    ${escapeHtml(
                        dashboardData.yahoo_error
                        || 'Yahoo data unavailable.'
                    )}
                </div>
            </div>
        `;
}


function renderESPN() {
    return dashboardData.espn
        ? renderLeagueSection(
            dashboardData.espn,
            'ESPN'
        )
        : `
            <div class="league-section">
                <div class="error">
                    ${escapeHtml(
                        dashboardData.espn_error
                        || 'ESPN data unavailable.'
                    )}
                </div>
            </div>
        `;
}


function renderLeagueSection(league, platform) {
    const my = league.my_team;
    const opp = league.opponent;

    return `
        <div class="league-section">
            <div class="league-subtitle">
                ${escapeHtml(
                    league.league_name
                    || `Week ${league.week}`
                )}
            </div>

            <div class="score-card ${platform.toLowerCase()}">
                <div class="matchup">
                    <div>
                        <div class="team-abbrev">
                            ${escapeHtml(my.abbrev)}
                        </div>

                        <div class="score">
                            ${formatNumber(
                                my.actual_total
                                ?? my.total
                                ?? 0
                            )}
                        </div>

                        <div class="score-secondary">
                            Actual
                        </div>

                        <div class="score-secondary">
                            Projected:
                            ${formatNumber(
                                my.projected_total
                                ?? my.total
                                ?? 0
                            )}
                        </div>
                    </div>

                    <div class="vs">VS</div>

                    <div>
                        <div class="team-abbrev">
                            ${escapeHtml(opp.abbrev)}
                        </div>

                        <div class="score">
                            ${formatNumber(
                                opp.actual_total
                                ?? opp.total
                                ?? 0
                            )}
                        </div>

                        <div class="score-secondary">
                            Actual
                        </div>

                        <div class="score-secondary">
                            Projected:
                            ${formatNumber(
                                opp.projected_total
                                ?? opp.total
                                ?? 0
                            )}
                        </div>
                    </div>
                </div>
            </div>

            <div class="rosters">
                ${renderTeam(my)}
                ${renderTeam(opp)}
            </div>
        </div>
    `;
}


function renderTeam(team) {
    const players = (team.players || [])
        .filter(playerBelongsToSelectedSlate);

    return `
        <div class="team-card">
            <div class="team-header">
                <div class="team-name">
                    ${escapeHtml(team.abbrev)}
                </div>

                <div>
                    <div class="team-total">
                        ${formatNumber(
                            team.actual_total
                            ?? team.total
                            ?? 0
                        )}
                    </div>

                    <div class="team-total-secondary">
                        Actual · Proj
                        ${formatNumber(
                            team.projected_total
                            ?? team.total
                            ?? 0
                        )}
                    </div>
                </div>
            </div>

            ${
                players.length
                    ? players.map(renderPlayer).join('')
                    : `<div class="no-players">
                        No starters in selected slate
                    </div>`
            }
        </div>
    `;
}


function renderPlayer(p) {
    const projected =
        p.projected != null
            ? Number(p.projected).toFixed(2)
            : '--';

    const actual =
        p.actual != null
            ? Number(p.actual).toFixed(2)
            : '--';

    const finished = playerGameHasFinished(p);
    const live = playerGameIsLive(p);

    let points;

    if (finished) {
        points = `
            <div class="points">
                <span class="actual-points">
                    ${actual}
                </span>

                <div class="points-label">
                    ACTUAL
                </div>
            </div>
        `;
    } else if (live) {
        points = `
            <div class="points">
                <span class="live-actual">
                    ${actual}
                </span>

                <div class="points-secondary projected-points">
                    ${projected} PROJ
                </div>
            </div>
        `;
    } else {
        points = `
            <div class="points">
                <span class="projected-points">
                    ${projected}
                </span>

                <div class="points-label">
                    PROJ
                </div>
            </div>
        `;
    }

    let injury = '';

    if (
        p.injury
        && p.injury.toUpperCase() !== 'ACTIVE'
    ) {
        const injuryClass =
            ['OUT', 'DOUBTFUL'].includes(
                p.injury.toUpperCase()
            )
                ? 'injury-alert'
                : '';

        injury = `
            <span class="injury ${injuryClass}">
                ${escapeHtml(p.injury)}
            </span>
        `;
    }

    let game = '';

    if (
        p.nfl_team
        && p.opponent
        && p.game_time
    ) {
        game = `
            <span class="game-info">
                ${escapeHtml(p.nfl_team)}
                vs
                ${escapeHtml(p.opponent)}
                ·
                ${escapeHtml(p.game_time)}
            </span>
        `;
    } else if (p.nfl_team) {
        game = `
            <span class="game-info">
                ${escapeHtml(p.nfl_team)}
            </span>
        `;
    }

    const cls =
        finished
            ? 'locked'
            : live
                ? 'live'
                : 'projected';

    const status =
        finished
            ? '✓ FINAL'
            : live
                ? '● LIVE'
                : 'PROJECTED';

    return `
        <div class="player">
            <div class="position">
                ${escapeHtml(p.slot)}
            </div>

            <div>
                <div class="player-name">
                    ${escapeHtml(p.name)}
                </div>

                <div class="player-meta">
                    <span class="status ${cls}">
                        ${status}
                    </span>

                    ${injury}
                    ${game}
                </div>
            </div>

            ${points}
        </div>
    `;
}


function refreshDashboard() {
    loadDashboard();
}


function formatNumber(v) {
    const n = Number(v);

    return Number.isFinite(n)
        ? n.toFixed(2)
        : '0.00';
}


function escapeHtml(v) {
    if (v == null) {
        return '';
    }

    return String(v)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}


loadDashboard();

setInterval(
    loadDashboard,
    60000
);