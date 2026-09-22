let dashboardData = null;
let selectedSlates = new Set();
let showCompleted = false;

let showBench = {
    Sleeper: false,
    Yahoo: false,
    ESPN: false,
};

let hideOpponents = false;

let hidePlatform = {
    Sleeper: false,
    Yahoo: false,
    ESPN: false,
};

let expandedPlayerKey = null;


async function loadDashboard() {
    try {
        const response = await fetch(
            '/api/dashboard',
            {cache: 'no-store'}
        );

        const data = await response.json();

        if (!response.ok) {
            throw new Error(
                data.error || 'Dashboard error'
            );
        }

        dashboardData = data;

        initializeSelectedSlates();

        renderDashboard();

    } catch (error) {
        document.getElementById('content').innerHTML =
            `<div class="error">${escapeHtml(error.message)}</div>`;
    }
}


function initializeSelectedSlates() {
    if (
        selectedSlates.size === 0 &&
        dashboardData.next_slate_id !== null
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


function toggleBench(platform) {
    showBench[platform] = !showBench[platform];
    renderDashboard();
}


function toggleHideOpponents() {
    hideOpponents = !hideOpponents;
    renderDashboard();
}


function toggleHidePlatform(platform) {
    hidePlatform[platform] =
        !hidePlatform[platform];

    if (
        hidePlatform[platform] &&
        expandedPlayerKey &&
        expandedPlayerKey.startsWith(`${platform}|`)
    ) {
        expandedPlayerKey = null;
    }

    renderDashboard();
}


function togglePlayer(playerKey) {
    expandedPlayerKey =
        expandedPlayerKey === playerKey
            ? null
            : playerKey;

    renderDashboard();
}


function renderDashboard() {
    document.getElementById('content').innerHTML = `
        ${renderSlateSelector()}

        <div class="refresh-row">
            <div class="updated">Live dashboard</div>

            <button
                class="refresh"
                onclick="refreshDashboard()"
            >
                ↻ Refresh
            </button>
        </div>

        ${
            !hidePlatform.Sleeper
                ? renderSleeper()
                : ''
        }

        ${
            !hidePlatform.Yahoo
                ? renderYahoo()
                : ''
        }

        ${
            !hidePlatform.ESPN
                ? renderESPN()
                : ''
        }
    `;
}


function renderSlateSelector() {
    if (!dashboardData.slates?.length) {
        return '';
    }

    const options =
        dashboardData.slates.map(slate => `
            <div class="slate-option">
                <input
                    type="checkbox"
                    id="slate-${slate.id}"
                    ${
                        selectedSlates.has(slate.id)
                            ? 'checked'
                            : ''
                    }
                    onchange="toggleSlate(${slate.id})"
                >

                <label for="slate-${slate.id}">
                    ${escapeHtml(slate.label)}
                </label>
            </div>
        `).join('');

    return `
        <div class="slate-card">

            <div class="slate-label">
                NFL SLATES
            </div>

            <div class="slate-options">

                ${options}

                <div class="slate-option completed-option">
                    <input
                        type="checkbox"
                        id="games-completed"
                        ${
                            showCompleted
                                ? 'checked'
                                : ''
                        }
                        onchange="toggleCompleted()"
                    >

                    <label for="games-completed">
                        Games Completed
                    </label>
                </div>

            </div>

            <div
                class="slate-label"
                style="margin-top: 12px;"
            >
                DISPLAY
            </div>

            <div class="slate-options">

                <div class="slate-option">
                    <input
                        type="checkbox"
                        id="hide-opponents"
                        ${
                            hideOpponents
                                ? 'checked'
                                : ''
                        }
                        onchange="toggleHideOpponents()"
                    >

                    <label for="hide-opponents">
                        Hide Opponents
                    </label>
                </div>

                <div class="slate-option">
                    <input
                        type="checkbox"
                        id="hide-espn"
                        ${
                            hidePlatform.ESPN
                                ? 'checked'
                                : ''
                        }
                        onchange="toggleHidePlatform('ESPN')"
                    >

                    <label for="hide-espn">
                        Hide ESPN
                    </label>
                </div>

                <div class="slate-option">
                    <input
                        type="checkbox"
                        id="hide-sleeper"
                        ${
                            hidePlatform.Sleeper
                                ? 'checked'
                                : ''
                        }
                        onchange="toggleHidePlatform('Sleeper')"
                    >

                    <label for="hide-sleeper">
                        Hide Sleeper
                    </label>
                </div>

                <div class="slate-option">
                    <input
                        type="checkbox"
                        id="hide-yahoo"
                        ${
                            hidePlatform.Yahoo
                                ? 'checked'
                                : ''
                        }
                        onchange="toggleHidePlatform('Yahoo')"
                    >

                    <label for="hide-yahoo">
                        Hide Yahoo
                    </label>
                </div>

            </div>

        </div>
    `;
}


function playerGameHasFinished(player) {
    const status =
        String(
            player.game_status || ''
        ).toUpperCase();

    const detail =
        String(
            player.status_detail || ''
        ).toUpperCase();

    return (
        status.includes('FINAL') ||
        status.includes('COMPLETED') ||
        detail.includes('FINAL') ||
        detail.includes('END')
    );
}


function playerGameIsLive(player) {
    const status =
        String(
            player.game_status || ''
        ).toUpperCase();

    const detail =
        String(
            player.status_detail || ''
        ).toUpperCase();

    if (playerGameHasFinished(player)) {
        return false;
    }

    return (
        status.includes('IN_PROGRESS') ||
        status.includes('IN PROGRESS') ||
        status === 'LIVE' ||
        status.includes('LIVE') ||
        ['Q1', 'Q2', 'Q3', 'Q4', 'OT', 'HALFTIME']
            .some(
                x => detail.includes(x)
            )
    );
}


function playerBelongsToSelectedSlate(player) {
    if (
        showCompleted &&
        playerGameHasFinished(player)
    ) {
        return true;
    }

    if (
        !player.pro_team_id ||
        selectedSlates.size === 0
    ) {
        return false;
    }

    const teamId =
        String(
            player.pro_team_id
        ).toUpperCase();

    for (const slateId of selectedSlates) {
        const slate =
            dashboardData.slates.find(
                item => item.id === slateId
            );

        if (!slate) {
            continue;
        }

        for (const game of slate.games) {
            if (
                [
                    game.home_id,
                    game.away_id,
                    game.home,
                    game.away,
                ].some(
                    value =>
                        String(value)
                            .toUpperCase() === teamId
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
                        dashboardData.sleeper_error ||
                        'Sleeper data unavailable.'
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
                        dashboardData.yahoo_error ||
                        'Yahoo data unavailable.'
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
                        dashboardData.espn_error ||
                        'ESPN data unavailable.'
                    )}
                </div>
            </div>
        `;
}


function renderLeagueSection(
    league,
    platform
) {
    const my = league.my_team;
    const opponent = league.opponent;

    const opponentScore =
        hideOpponents
            ? ''
            : `
                <div class="vs">
                    VS
                </div>

                <div>
                    <div class="team-abbrev">
                        ${escapeHtml(
                            opponent.abbrev
                        )}
                    </div>

                    <div class="score">
                        ${formatNumber(
                            opponent.actual_total ??
                            opponent.total ??
                            0
                        )}
                    </div>

                    <div class="score-secondary">
                        Actual
                    </div>

                    <div class="score-secondary">
                        Projected:
                        ${formatNumber(
                            opponent.projected_total ??
                            opponent.total ??
                            0
                        )}
                    </div>
                </div>
            `;

    return `
        <div class="league-section">

            <div class="league-subtitle">
                ${escapeHtml(
                    league.league_name ||
                    `Week ${league.week}`
                )}
            </div>

            <div
                class="score-card ${platform.toLowerCase()}"
            >

                <div class="matchup">

                    <div>
                        <div class="team-abbrev">
                            ${escapeHtml(my.abbrev)}
                        </div>

                        <div class="score">
                            ${formatNumber(
                                my.actual_total ??
                                my.total ??
                                0
                            )}
                        </div>

                        <div class="score-secondary">
                            Actual
                        </div>

                        <div class="score-secondary">
                            Projected:
                            ${formatNumber(
                                my.projected_total ??
                                my.total ??
                                0
                            )}
                        </div>
                    </div>

                    ${opponentScore}

                </div>

            </div>

            <div class="rosters">

                ${renderTeam(my, platform)}

                ${
                    !hideOpponents
                        ? renderTeam(
                            opponent,
                            platform
                        )
                        : ''
                }

            </div>

            <div class="bench-control">

                <button
                    class="refresh"
                    onclick="toggleBench('${platform}')"
                >
                    ${
                        showBench[platform]
                            ? 'Hide Bench'
                            : 'Show Bench'
                    }
                </button>

            </div>

        </div>
    `;
}


function renderTeam(
    team,
    platform
) {
    const eligiblePlayers =
        (team.players || [])
            .filter(
                playerBelongsToSelectedSlate
            );

    const starters =
        eligiblePlayers.filter(
            player =>
                player.starter !== false
        );

    const bench =
        eligiblePlayers.filter(
            player =>
                player.bench === true
        );

    let playerHtml =
        starters.length
            ? starters
                .map(
                    player =>
                        renderPlayer(
                            player,
                            platform,
                            false
                        )
                )
                .join('')
            : `
                <div class="no-players">
                    No starters in selected slate
                </div>
            `;

    if (showBench[platform]) {
        playerHtml +=
            renderBenchSection(
                bench,
                platform
            );
    }

    return `
        <div class="team-card">

            <div class="team-header">

                <div class="team-name">
                    ${escapeHtml(team.abbrev)}
                </div>

                <div>

                    <div class="team-total">
                        ${formatNumber(
                            team.actual_total ??
                            team.total ??
                            0
                        )}
                    </div>

                    <div class="team-total-secondary">
                        Actual · Proj
                        ${formatNumber(
                            team.projected_total ??
                            team.total ??
                            0
                        )}
                    </div>

                </div>

            </div>

            ${playerHtml}

        </div>
    `;
}


function renderBenchSection(
    bench,
    platform
) {
    if (!bench.length) {
        return `
            <div class="bench-section">

                <div class="bench-title">
                    BENCH
                </div>

                <div class="no-players">
                    No bench players in selected slate
                </div>

            </div>
        `;
    }

    return `
        <div class="bench-section">

            <div class="bench-title">
                BENCH
            </div>

            ${
                bench
                    .map(
                        player =>
                            renderPlayer(
                                player,
                                platform,
                                true
                            )
                    )
                    .join('')
            }

        </div>
    `;
}


function renderPlayer(
    player,
    platform,
    isBench
) {
    const projected =
        player.projected != null
            ? Number(
                player.projected
            ).toFixed(2)
            : '--';

    const actual =
        player.actual != null
            ? Number(
                player.actual
            ).toFixed(2)
            : '--';

    const finished =
        playerGameHasFinished(player);

    const live =
        playerGameIsLive(player);

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

                <div
                    class="
                        points-secondary
                        projected-points
                    "
                >
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
        player.injury &&
        String(
            player.injury
        ).toUpperCase() !== 'ACTIVE'
    ) {
        const injuryClass =
            [
                'OUT',
                'DOUBTFUL',
            ].includes(
                String(
                    player.injury
                ).toUpperCase()
            )
                ? 'injury-alert'
                : '';

        injury = `
            <span
                class="injury ${injuryClass}"
            >
                ${escapeHtml(
                    player.injury
                )}
            </span>
        `;
    }

    let game = '';

    if (
        player.nfl_team &&
        player.opponent &&
        player.game_time
    ) {
        game = `
            <span class="game-info">
                ${escapeHtml(
                    player.nfl_team
                )}
                vs
                ${escapeHtml(
                    player.opponent
                )}
                ·
                ${escapeHtml(
                    player.game_time
                )}
            </span>
        `;
    } else if (player.nfl_team) {
        game = `
            <span class="game-info">
                ${escapeHtml(
                    player.nfl_team
                )}
            </span>
        `;
    }

    const projectionSource =
        player.projection_source &&
        player.projected != null
            ? `
                <span class="game-info">
                    ${escapeHtml(
                        player.projection_source
                    )}
                </span>
            `
            : '';

    const playerClass =
        finished
            ? 'locked'
            : live
                ? 'live'
                : 'projected';

    const statusText =
        finished
            ? '✓ FINAL'
            : live
                ? '● LIVE'
                : 'PROJECTED';

    const playerKey = [
        platform,
        player.name,
        player.nfl_team || '',
        player.position || '',
        isBench
            ? 'bench'
            : 'starter',
    ].join('|');

    const expanded =
        expandedPlayerKey === playerKey;

    return `
        <div class="player-wrap">

            <button
                class="
                    player
                    ${expanded ? 'expanded' : ''}
                "
                onclick='togglePlayer(
                    ${escapeHtml(
                        JSON.stringify(
                            playerKey
                        )
                    )}
                )'
                type="button"
            >

                <div class="position">
                    ${escapeHtml(
                        player.predicted_slot ||
                        player.slot
                    )}
                </div>

                <div class="player-main">

                    <div class="player-name">
                        ${escapeHtml(
                            player.name
                        )}
                    </div>

                    <div class="player-meta">

                        <span
                            class="
                                status
                                ${playerClass}
                            "
                        >
                            ${statusText}
                        </span>

                        ${injury}

                        ${game}

                        ${projectionSource}

                    </div>

                </div>

                ${points}

                <div class="player-chevron">
                    ${
                        expanded
                            ? '▴'
                            : '▾'
                    }
                </div>

            </button>

            ${
                expanded
                    ? renderUsageTray(player)
                    : ''
            }

        </div>
    `;
}


function renderUsageTray(player) {
    const usage = player.usage;

    if (
        !usage ||
        !usage.available
    ) {
        return `
            <div class="usage-tray">
                <div class="usage-unavailable">
                    Usage data is not available yet for this player.
                </div>
            </div>
        `;
    }

    /*
     * Yahoo supplies position directly, while Sleeper/ESPN can sometimes
     * omit it. The usage lookup knows the NFL position, so use that as the
     * fallback.
     */
    const position = String(
        player.position ||
        usage.position ||
        ''
    ).toUpperCase();

    if (
        !['RB', 'WR', 'TE'].includes(position)
    ) {
        return `
            <div class="usage-tray">
                <div class="usage-unavailable">
                    Usage data is not available yet for this player.
                </div>
            </div>
        `;
    }

    const isRb =
        position === 'RB';

    const kingLabel =
        isRb
            ? 'RUSH SHARE'
            : 'TARGET SHARE';

    const kingValue =
        isRb
            ? usage.rush_share
            : usage.target_share;

    const secondaryLabel =
        isRb
            ? 'OPPORTUNITY RATE'
            : 'TARGET COMPETITION';

    /*
     * Target competition means the percentage of the team's RB/WR/TE
     * targets that are going to somebody else.
     */
    const secondaryValue =
        isRb
            ? usage.opportunity_rate
            : (
                Number.isFinite(
                    Number(
                        usage.target_share
                    )
                )
                    ? Math.max(
                        0,
                        100 -
                        Number(
                            usage.target_share
                        )
                    )
                    : null
            );

    const offense =
        usage.offense || {};

    const runPct =
        offense.run_pct;

    const passPct =
        offense.pass_pct;

    const competition =
        usage.competition || [];

    const weeks =
        usage.weeks || [];

    return `
        <div class="usage-tray">

            <div class="usage-top">

                <div class="usage-stat king">

                    <div class="usage-label">
                        ${kingLabel}
                    </div>

                    <div class="usage-value">
                        ${formatPercent(
                            kingValue
                        )}
                    </div>

                </div>

                <div class="usage-stat">

                    <div class="usage-label">
                        ${secondaryLabel}
                    </div>

                    <div class="usage-value">
                        ${formatPercent(
                            secondaryValue
                        )}
                    </div>

                </div>

                <div class="usage-stat offense-stat">

                    <div class="usage-label">
                        OFFENSE
                    </div>

                    <div
                        class="
                            usage-value
                            offense-value
                        "
                    >
                        ${formatPercent(
                            runPct
                        )}
                        Run

                        <span>·</span>

                        ${formatPercent(
                            passPct
                        )}
                        Pass
                    </div>

                </div>

            </div>

            ${
                competition.length
                    ? `
                        <div class="usage-section">

                            <div
                                class="
                                    usage-section-title
                                "
                            >
                                ${
                                    isRb
                                        ? 'BACKFIELD COMPETITION'
                                        : 'TARGET COMPETITION'
                                }
                            </div>

                            ${renderCompetition(
                                competition,
                                player.name
                            )}

                        </div>
                    `
                    : ''
            }

            ${
                weeks.length
                    ? `
                        <div class="usage-section">

                            <div
                                class="
                                    usage-section-title
                                "
                            >
                                PREVIOUS WEEKS
                            </div>

                            ${renderWeekHistory(
                                weeks,
                                isRb
                            )}

                        </div>
                    `
                    : ''
            }

        </div>
    `;
}


function renderCompetition(
    competition,
    playerName
) {
    return `
        <div class="competition-list">

            ${
                competition.map(
                    item => {

                        const samePlayer =
                            String(
                                item.name || ''
                            ).toLowerCase() ===
                            String(
                                playerName || ''
                            ).toLowerCase();

                        return `
                            <div
                                class="
                                    competition-row
                                    ${
                                        samePlayer
                                            ? 'current'
                                            : ''
                                    }
                                "
                            >

                                <div
                                    class="
                                        competition-name
                                    "
                                >
                                    ${escapeHtml(
                                        item.name
                                    )}

                                    ${
                                        item.position
                                            ? `
                                                <span>
                                                    ${escapeHtml(
                                                        item.position
                                                    )}
                                                </span>
                                            `
                                            : ''
                                    }

                                </div>

                                <div
                                    class="
                                        competition-share
                                    "
                                >
                                    ${formatPercent(
                                        item.share
                                    )}
                                </div>

                            </div>
                        `;
                    }
                ).join('')
            }

        </div>
    `;
}


function renderWeekHistory(
    weeks,
    isRb
) {
    /*
     * Only show the five most recent weeks.
     *
     * The array is chronological so each week can be compared against
     * the immediately previous week. It is then reversed for display,
     * putting the most recent week first.
     */
    const rows = [...weeks]
        .sort(
            (a, b) =>
                Number(a.week) -
                Number(b.week)
        )
        .slice(-5);

    if (!rows.length) {
        return '';
    }

    const values = rows.map(
        row =>
            Number(
                isRb
                    ? row.rush_share
                    : row.target_share
            )
    );

    return `
        <div class="week-history">

            <div class="week-history-header">
                <span>WK</span>
                <span>
                    ${
                        isRb
                            ? 'RUSH SHARE'
                            : 'TARGET SHARE'
                    }
                </span>
            </div>

            ${
                rows
                    .map(
                        (row, index) => {

                            const value =
                                isRb
                                    ? row.rush_share
                                    : row.target_share;

                            const current =
                                Number(value);

                            const previous =
                                index > 0
                                    ? values[
                                        index - 1
                                    ]
                                    : null;

                            let trendClass =
                                '';

                            if (
                                Number.isFinite(
                                    current
                                ) &&
                                Number.isFinite(
                                    previous
                                )
                            ) {
                                if (
                                    current >
                                    previous
                                ) {
                                    trendClass =
                                        'usage-up';
                                } else if (
                                    current <
                                    previous
                                ) {
                                    trendClass =
                                        'usage-down';
                                }
                            }

                            return `
                                <div
                                    class="
                                        week-history-row
                                    "
                                >

                                    <span>
                                        W${escapeHtml(
                                            row.week
                                        )}
                                    </span>

                                    <span
                                        class="${trendClass}"
                                        style="
                                            ${
                                                trendClass ===
                                                'usage-up'
                                                    ? 'color:#22c55e;font-weight:700;'
                                                    : trendClass ===
                                                      'usage-down'
                                                        ? 'color:#ef4444;font-weight:700;'
                                                        : ''
                                            }
                                        "
                                    >
                                        ${formatPercent(
                                            value
                                        )}
                                    </span>

                                </div>
                            `;
                        }
                    )
                    .reverse()
                    .join('')
            }

        </div>
    `;
}


function refreshDashboard() {
    loadDashboard();
}


function formatNumber(value) {
    const number =
        Number(value);

    return Number.isFinite(number)
        ? number.toFixed(2)
        : '0.00';
}


function formatPercent(value) {
    const number =
        Number(value);

    return Number.isFinite(number)
        ? `${number.toFixed(1)}%`
        : '—';
}


function escapeHtml(value) {
    if (value == null) {
        return '';
    }

    return String(value)
        .replace(
            /&/g,
            '&amp;'
        )
        .replace(
            /</g,
            '&lt;'
        )
        .replace(
            />/g,
            '&gt;'
        )
        .replace(
            /"/g,
            '&quot;'
        )
        .replace(
            /'/g,
            '&#039;'
        );
}


loadDashboard();

setInterval(
    loadDashboard,
    60000
);