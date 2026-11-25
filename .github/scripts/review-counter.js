// Numără review-urile făcute de fiecare membru pe PR-urile repo-ului și
// actualizează un singur comentariu în issue-ul de urmărire (implicit #7).
//
// Se numără doar review-urile cu decizie (Approve / Request changes), făcute
// de altcineva decât autorul PR-ului; boții sunt ignorați.

const MARKER = '<!-- review-counter -->';
const COUNTED_STATES = new Set(['APPROVED', 'CHANGES_REQUESTED']);

async function collectStats(github, owner, repo) {
  const pulls = await github.paginate(github.rest.pulls.list, {
    owner, repo, state: 'all', per_page: 100,
  });

  const stats = new Map(); // login -> { reviews, prs: Set }
  for (const pr of pulls) {
    const reviews = await github.paginate(github.rest.pulls.listReviews, {
      owner, repo, pull_number: pr.number, per_page: 100,
    });
    for (const r of reviews) {
      if (!r.user || r.user.type === 'Bot') continue;
      if (pr.user && r.user.login === pr.user.login) continue;
      if (!COUNTED_STATES.has(r.state)) continue;
      const s = stats.get(r.user.login) || { reviews: 0, prs: new Set() };
      s.reviews += 1;
      s.prs.add(pr.number);
      stats.set(r.user.login, s);
    }
  }
  return stats;
}

function renderBody(stats, { lead, target, now }) {
  const rows = [...stats.entries()].sort((a, b) => b[1].reviews - a[1].reviews || a[0].localeCompare(b[0]));
  const leadStats = stats.get(lead) || { reviews: 0, prs: new Set() };
  const done = leadStats.reviews >= target;

  const lines = [
    MARKER,
    `### Contor review-uri (actualizat automat)`,
    '',
    `**TL (${lead}): ${leadStats.reviews} / ${target}** ${done ? '✅ ținta atinsă' : `— mai sunt ${target - leadStats.reviews}`}`,
    '',
    '| Membru | Review-uri | PR-uri revizuite |',
    '|---|---|---|',
    ...rows.map(([login, s]) =>
      `| ${login} | ${s.reviews} | ${[...s.prs].sort((a, b) => a - b).map((n) => `#${n}`).join(', ')} |`),
    '',
    `<sub>Se numără doar review-urile Approve / Request changes pe PR-urile altora. Ultima actualizare: ${now}.</sub>`,
  ];
  return lines.join('\n');
}

module.exports = async ({ github, context, core }) => {
  const { owner, repo } = context.repo;
  const issueNumber = Number(process.env.TRACKING_ISSUE || 7);
  const target = Number(process.env.REVIEW_TARGET || 15);
  const lead = process.env.REVIEW_LEAD || 'mororazvan04';

  const stats = await collectStats(github, owner, repo);
  const body = renderBody(stats, { lead, target, now: new Date().toISOString().slice(0, 16).replace('T', ' ') + ' UTC' });

  const comments = await github.paginate(github.rest.issues.listComments, {
    owner, repo, issue_number: issueNumber, per_page: 100,
  });
  const existing = comments.find((c) => c.body && c.body.startsWith(MARKER));

  if (existing) {
    await github.rest.issues.updateComment({ owner, repo, comment_id: existing.id, body });
  } else {
    await github.rest.issues.createComment({ owner, repo, issue_number: issueNumber, body });
  }
  if (core) core.info(`TL ${lead}: ${(stats.get(lead) || { reviews: 0 }).reviews}/${target}`);
  return body;
};

module.exports.collectStats = collectStats;
module.exports.renderBody = renderBody;
