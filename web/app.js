const $ = (selector, root = document) => root.querySelector(selector);
const main = $('#main');
const modal = $('#modal');
const docDialog = $('#document-dialog');
const sidebar = $('#sidebar');
const sidebarBackdrop = $('#sidebar-backdrop');
const menuToggle = $('.mobile-menu');
const mobileNavigation = window.matchMedia('(max-width: 700px)');
let sidebarOpen = false;
let sidebarScrollPosition = null;
const state = { snapshot: null, view: 'overview', collection: '', asOf: '', filter: 'open', search: '', answer: null, plans: [], plan: null, simulation: null, baseline: null, edits: {}, appliedEdits: {}, runToken: 0, doc: null, docTab: 'source', highlight: null, editing: null };
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const icons = {
  home: '<path d="m3 10 9-7 9 7v10H3z"/><path d="M9 20v-7h6v7"/>',
  file: '<path d="M14 3H5v18h14V8z"/><path d="M14 3v5h5M8 12h8M8 16h6"/>',
  calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4M17 3v4M3 10h18M7 14h3M14 14h3"/>',
  layers: '<path d="m12 3 10 5-10 5L2 8zM2 12l10 5 10-5M2 16l10 5 10-5"/>',
  alert: '<path d="M12 3 2 21h20zM12 9v5M12 17v1"/>',
  chart: '<path d="M4 3v17h17M7 15l4-5 4 3 5-7"/>',
  history: '<path d="M3 11a9 9 0 1 1 2 7M3 4v7h7M12 7v5l3 2"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  arrow: '<path d="M5 12h14m-6-6 6 6-6 6"/>',
  up: '<path d="M6 18 18 6M6 6h12v12"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  upload: '<path d="M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6"/>',
  download: '<path d="M12 3v13m-5-5 5 5 5-5M4 17v4h16v-4"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  shield: '<path d="m12 3 8 3v7c0 5-8 9-8 9s-8-4-8-9V6zM8 12l3 3 5-6"/>',
  spark: '<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z"/>',
  branch: '<circle cx="6" cy="4" r="2"/><circle cx="6" cy="20" r="2"/><circle cx="18" cy="5" r="2"/><path d="M6 6v12M6 15c8 0 12-2 12-8"/>',
  trash: '<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7"/>',
  edit: '<path d="m15 3 6 6L9 21H3v-6zM12 6l6 6"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
};
const icon = name => `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${icons[name] || icons.file}</svg>`;
const fmtDate = (value, options = {}) => new Intl.DateTimeFormat('en', { day: 'numeric', month: 'short', ...options }).format(new Date(value + (value.length === 10 ? 'T12:00:00' : '')));
const amount = (minor, currency = 'USD', compact = false) => { try { return new Intl.NumberFormat('en', { style: 'currency', currency, maximumFractionDigits: compact ? 0 : 2 }).format(minor / 100); } catch { return `${currency} ${(minor / 100).toFixed(2)}`; } };
const uid = () => crypto.randomUUID().replaceAll('-', '').slice(0, 12);
const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };
const addDays = (value, days) => { const d = new Date(value + 'T12:00:00'); d.setDate(d.getDate() + days); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };
const scoped = items => items.filter(item => !state.collection || item.matter === state.collection);
const pill = (label, color = 'gray') => `<span class="label-pill ${color}">${esc(label)}</span>`;
const button = (label, action, glyph, extra = '', variant = '') => `<button class="button ${variant}" data-action="${action}" ${extra}>${glyph ? icon(glyph) : ''}${label}</button>`;

async function api(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { 'Content-Type': 'application/json', 'X-Lipso-Client': 'workspace', ...options.headers }, body: options.body === undefined ? undefined : JSON.stringify(options.body) });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'The request could not be completed.');
  return data;
}
function toast(message) {
  $('#toast').textContent = message;
  $('#toast').classList.add('visible');
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => $('#toast').classList.remove('visible'), 4500);
}
async function refresh() {
  const [snapshot, plans] = await Promise.all([api('/api/state' + (state.asOf ? '?as_of=' + state.asOf : '')), api('/api/plans')]);
  state.snapshot = snapshot;
  state.plans = plans.plans;
  render();
}
function setSidebarOpen(open, { restoreFocus = true } = {}) {
  const wasOpen = sidebarOpen;
  sidebarOpen = Boolean(open && mobileNavigation.matches);
  if (sidebarOpen && !wasOpen) sidebarScrollPosition = { x: window.scrollX, y: window.scrollY };
  document.body.classList.toggle('nav-open', sidebarOpen);
  document.documentElement.classList.toggle('nav-open', sidebarOpen);
  $('.app-shell').inert = sidebarOpen;
  sidebarBackdrop.hidden = !sidebarOpen;
  menuToggle.setAttribute('aria-expanded', String(sidebarOpen));
  // Hidden mobile navigation must not remain in the keyboard tab order.
  const hidden = mobileNavigation.matches && !sidebarOpen;
  sidebar.inert = hidden;
  if (hidden) sidebar.setAttribute('aria-hidden', 'true');
  else sidebar.removeAttribute('aria-hidden');
  if (sidebarOpen) {
    sidebar.setAttribute('role', 'dialog');
    sidebar.setAttribute('aria-modal', 'true');
    if (!wasOpen) $('.sidebar-close').focus({ preventScroll: true });
  } else {
    sidebar.removeAttribute('role');
    sidebar.removeAttribute('aria-modal');
    if (wasOpen) {
      if (sidebarScrollPosition) window.scrollTo({ left: sidebarScrollPosition.x, top: sidebarScrollPosition.y, behavior: 'instant' });
      sidebarScrollPosition = null;
      if (restoreFocus) (mobileNavigation.matches ? menuToggle : main).focus({ preventScroll: true });
    }
  }
}
setSidebarOpen(false, { restoreFocus: false });
sidebarBackdrop.addEventListener('click', () => setSidebarOpen(false));
mobileNavigation.addEventListener('change', () => setSidebarOpen(false));
function navigate(view, collection = '') {
  state.view = view; state.collection = collection; state.answer = null;
  if (view !== 'commitments') state.filter = 'open';
  history.replaceState(null, '', '#' + view);
  setSidebarOpen(false, { restoreFocus: false });
  render();
  window.scrollTo({ top: 0 });
  main.focus({ preventScroll: true });
  if (view === 'plans' && state.plans.length && !state.plan) loadPlan(state.plans[0].id).catch(error => toast(error.message));
}
function renderNavigation() {
  const stats = state.snapshot.stats;
  const nav = [['overview', 'Overview', 'home', ''], ['documents', 'Documents', 'file', stats.documents], ['commitments', 'Commitments', 'calendar', stats.upcoming], ['review', 'Review queue', 'layers', stats.review], ['plans', 'Planning lab', 'chart', ''], ['activity', 'Activity & integrity', 'history', '']];
  $('#navigation').innerHTML = nav.map(([id, title, glyph, count]) => `<button class="nav-item ${state.view === id && !state.collection ? 'active' : ''}" data-view="${id}" ${state.view === id && !state.collection ? 'aria-current="page"' : ''}>${icon(glyph)}<span>${title}</span>${count !== '' ? `<span class="count ${id === 'review' && count ? 'alert' : ''}">${count}</span>` : ''}</button>`).join('');
  $('#collections').innerHTML = state.snapshot.collections.map(name => `<button class="collection-item ${state.collection === name ? 'active' : ''}" data-collection="${esc(name)}" title="${esc(name)}"><span class="collection-dot"></span><span class="collection-name">${esc(name)}</span></button>`).join('') || '<p class="inline-note">&nbsp; Your collections will appear here.</p>';
  $('#page-name').textContent = state.collection || nav.find(([id]) => id === state.view)?.[1] || 'Overview';
}
function intro(title, subtitle, actions = '', eyebrow = 'YOUR WORKSPACE, IN FOCUS') {
  return `<div class="page-intro"><div><p class="eyebrow">${eyebrow}</p><h1>${title}</h1><p class="subtext">${subtitle}</p></div><div class="intro-actions">${actions}</div></div>`;
}
function askBox() {
  return `<section class="ask-card" aria-label="Ask your workspace"><div class="ask-caption">${icon('spark')} A question is a good place to start.</div><form id="ask-form" class="ask-form">${icon('search')}<input name="question" id="ask-input" maxlength="500" required autocomplete="off" aria-label="Ask your workspace" placeholder="Ask about a deadline, an amount, or what changed…" value="${esc(state.search)}"><button class="button primary" type="submit">Find evidence ${icon('arrow')}</button></form><div class="ask-suggestions"><span>TRY ASKING</span>${["What's due next?", 'What changed?', 'Any conflicting terms?'].map(q => `<button class="suggestion" data-ask="${esc(q)}">${esc(q)}</button>`).join('')}</div></section>`;
}
function emptyState(title, description, actions = '') { return `<div class="empty-state">${icon('layers')}<h2>${title}</h2><p>${description}</p>${actions}</div>`; }
function statCard(label, value, note, glyph, view, warning = false) {
  return `<button class="stat-card ${warning ? 'warn' : ''}" data-view="${view}"><span class="stat-heading">${label}${icon(glyph)}</span><div class="stat-value">${value}</div><span class="stat-note">${note}</span></button>`;
}
function cite(fact, compact = false) {
  return `<button class="citation" data-doc="${esc(fact.document_id)}" data-chunk="${fact.chunk_id}"><blockquote>${esc(fact.quote)}</blockquote><small>${icon('file')} ${esc(fact.document_title)} · ${fact.page > 1 ? 'page ' + fact.page + ', ' : ''}line ${fact.line}${!compact && fact.status ? ' · ' + esc(fact.status) : ''} ↗</small></button>`;
}
function documentTable(documents, limit = 1000) {
  if (!documents.length) return emptyState('No documents here yet.', 'Import a source to start building a clearer picture.', button('Import document', 'import', 'plus', '', 'primary'));
  return `<div class="table-wrap"><table class="documents-table"><thead><tr><th>Document</th><th class="mobile-hide">Collection</th><th class="optional-column">Findings</th><th>Status</th><th></th></tr></thead><tbody>${documents.slice(0, limit).map(doc => `<tr><td><button class="document-title" data-doc="${doc.id}"><span class="file-icon">${icon('file')}</span><span><strong>${esc(doc.title)}</strong><small>${esc(doc.filename.split('.').pop().toUpperCase())} · ${fmtDate(doc.imported_at)}${doc.demo ? '<span class="sample-tag">SAMPLE</span>' : ''}</small></span></button></td><td class="mobile-hide"><span class="collection-tag">${esc(doc.matter)}</span></td><td class="optional-column muted">${doc.fact_count} findings</td><td>${pill(doc.state === 'current' ? 'Current' : doc.state === 'upcoming' ? 'Upcoming' : 'Replaced', doc.state === 'current' ? 'green' : 'gray')}</td><td><button class="text-button" data-doc="${doc.id}" aria-label="Open ${esc(doc.title)}">↗</button></td></tr>`).join('')}</tbody></table></div>`;
}
function upcomingRows(obligations, limit = 4) {
  const active = obligations.filter(o => o.action_state === 'open').slice(0, limit);
  if (!active.length) return emptyState('A little breathing room.', 'No open commitments in this collection.');
  return active.map(item => `<div class="upcoming-item"><div class="date-tile"><small>${fmtDate(item.value, { day: undefined, month: 'short' })}</small><strong>${Number(item.value.slice(-2))}</strong></div><button class="upcoming-info" data-doc="${item.document_id}" data-chunk="${item.chunk_id}"><strong>${esc(item.label)}</strong><small>${esc(item.matter)}</small></button><span class="due-label ${item.days <= 7 ? 'urgent' : ''}">${item.days < 0 ? `${-item.days}d overdue` : item.days === 0 ? 'Today' : `In ${item.days} days`}</span></div>`).join('');
}
function renderOverview() {
  const snapshot = state.snapshot, stats = snapshot.stats;
  let html = intro('A clearer picture.', 'Your documents, commitments, and plans. Finally on the same page.', button('Import document', 'import', 'plus', '', 'primary'));
  if (snapshot.documents.some(d => d.demo)) html += '<div class="sample-banner"><span class="status-dot"></span>You’re exploring fictional sample records.</div>';
  html += askBox();
  if (state.answer) html += renderAnswer();
  if (!snapshot.documents.length) return html + `<section class="panel">${emptyState('Make room for what matters.', 'Start with a contract, an invoice, or a plain text note. Lipso connects the details to the decisions ahead.', button('Import a document', 'import', 'upload', '', 'primary') + button('Explore a sample workspace', 'demo', 'spark'))}</section>`;
  html += `<section class="stats-grid" aria-label="Workspace summary">${statCard('Documents', stats.documents, `Across ${stats.collections} collections`, 'file', 'documents')}${statCard('Coming up', stats.upcoming, 'Commitments in the next 30 days', 'calendar', 'commitments')}${statCard('Possible conflicts', stats.conflicts, 'Different terms. Worth a closer look.', 'alert', 'review', true)}${statCard('Ready to review', stats.review, 'Extracted findings awaiting your eye', 'layers', 'review')}</section>`;
  const conflict = snapshot.conflicts[0];
  const attention = conflict ? `<div class="attention-body"><div class="attention-eyebrow">${icon('alert')} ${esc(conflict.matter.toUpperCase())}</div><h3>Two versions of ${esc(conflict.label.toLowerCase())}.</h3><p>Current documents show different values. A little context could make all the difference.</p><div class="comparison-values">${conflict.facts.slice(0, 2).map(fact => `<button class="compare-value" data-doc="${fact.document_id}" data-chunk="${fact.chunk_id}"><strong>${esc(fact.display)}</strong><span>${esc(fact.document_title)} ↗</span></button>`).join('')}</div><div class="attention-footer"><span>Every value links to its source</span><button class="text-button" data-view="review">Review the evidence ↗</button></div></div>` : `<div class="attention-body"><div class="attention-eyebrow">${icon('check')} A LITTLE MORE CLARITY</div><h3>No competing terms detected.</h3><p>Review extracted findings to check their meaning and context. Unrecognized language still needs a human eye.</p>${button('Review findings', 'review-view', 'arrow')}</div>`;
  html += `<div class="content-grid"><section class="panel"><div class="panel-heading"><div class="heading-group"><h2>Worth your attention</h2>${pill(conflict ? 'Needs a look' : 'Looking clear', conflict ? '' : 'green')}</div>${icon('spark')}</div>${attention}</section><section class="panel"><div class="panel-heading"><h2>On the horizon</h2><span class="muted calendar-icon">${icon('calendar')}<small>Next 30 days</small></span></div>${upcomingRows(snapshot.obligations.filter(o => o.days <= 30))}<div class="panel-bottom"><button class="text-button" data-view="commitments">See all commitments ${icon('arrow')}</button></div></section></div>`;
  html += `<div class="recent-layout"><section class="panel"><div class="panel-heading"><h2>Recently added</h2><button class="text-button" data-view="documents">View all ↗</button></div>${documentTable(snapshot.documents, 4)}</section><aside class="insight-card"><div class="insight-illustration" aria-hidden="true"><span class="illustrated-sheet"></span><span class="illustrated-sheet second"></span><span class="illustration-check">✓</span></div><div><h3>What if the plan<br>doesn’t go to plan?</h3><p>Connect your working hours and cash flow. Explore a different outcome before it becomes reality.</p><button class="text-button" data-view="plans">Enter the planning lab ↗</button></div></aside></div>`;
  return html;
}
function renderAnswer() {
  const result = state.answer;
  return `<section class="result-answer" aria-label="Evidence results"><div class="result-eyebrow">EVIDENCE FROM YOUR DOCUMENTS · ${esc(result.as_of)}</div><h2>${esc(result.title)}</h2><p>${esc(result.summary)}</p>${result.conflicts?.length ? `<div class="notice">${result.conflicts.length} possible conflict${result.conflicts.length === 1 ? '' : 's'}: different values are shown separately.</div>` : ''}${result.changes ? result.changes.map(change => `<div class="finding-meta">${esc(change.matter)} · ${esc(change.label)}: ${esc(change.before.map(f => f.display).join(', ') || 'Not stated')} → ${esc(change.after.map(f => f.display).join(', ') || 'Not stated')}</div>`).join('') : ''}${result.citations.map(fact => `${fact.display ? `<div class="section-heading"><h3>${esc(fact.label)}: ${esc(fact.display)}</h3>${pill(fact.status, fact.status === 'confirmed' ? 'green' : 'gray')}</div>` : ''}${cite(fact)}`).join('')}${!result.citations.length ? '<p>No matching source passages are available.</p>' : ''}</section>`;
}
function collectionSelect() { return `<select class="field-input" id="collection-filter" aria-label="Filter collection"><option value="">All collections</option>${state.snapshot.collections.map(c => `<option ${state.collection === c ? 'selected' : ''}>${esc(c)}</option>`).join('')}</select>`; }
function timelineControl() { return `<label class="as-of-label">As of <input class="field-input" type="date" id="as-of" aria-label="View terms as of date" value="${state.asOf || state.snapshot.today}"></label>`; }
function renderDocuments() {
  return intro(esc(state.collection || 'The source of truth.'), 'Original files, exact passages, and a history of what changed.', button('Import document', 'import', 'plus', '', 'primary'), 'THE DOCUMENT LIBRARY') + askBox() + (state.answer ? renderAnswer() : '') + `<div class="toolbar">${collectionSelect()}<span class="spacer"></span>${timelineControl()}</div><section class="panel">${documentTable(scoped(state.snapshot.documents))}</section>`;
}
function renderCommitments() {
  const items = scoped(state.snapshot.obligations).filter(o => state.filter === 'all' || o.action_state === state.filter);
  return intro('A little ahead of things.', 'Explicit dates from your documents, with the context to act.', '<a class="button" href="/api/calendar">' + icon('download') + 'Export calendar</a>', 'YOUR COMMITMENTS') + `<div class="toolbar">${collectionSelect()}<select class="field-input" id="action-filter" aria-label="Filter commitments"><option value="open" ${state.filter === 'open' ? 'selected' : ''}>Open commitments</option><option value="completed" ${state.filter === 'completed' ? 'selected' : ''}>Completed</option><option value="all" ${state.filter === 'all' ? 'selected' : ''}>All commitments</option></select><span class="spacer"></span>${timelineControl()}</div><section class="panel">${items.length ? items.map(o => `<div class="timeline-item ${o.action_state === 'completed' ? 'completed' : ''}"><button class="check-button ${o.action_state === 'completed' ? 'checked' : ''}" data-action="complete" data-id="${o.id}" data-state="${o.action_state === 'completed' ? 'open' : 'completed'}" aria-label="${o.action_state === 'completed' ? 'Reopen' : 'Complete'} ${esc(o.label)}">✓</button><div class="item-body"><h3>${esc(o.label)} · ${esc(o.matter)}</h3><p>${fmtDate(o.value, { year: 'numeric' })} · ${o.days < 0 ? -o.days + ' days overdue' : o.days === 0 ? 'Today' : 'In ' + o.days + ' days'} · ${esc(o.status)}</p><button class="text-button" data-doc="${o.document_id}" data-chunk="${o.chunk_id}">${esc(o.document_title)} ↗</button></div><div class="item-actions">${button('Plan this', 'plan-fact', 'plus', `data-id="${o.id}"`, 'small')}</div></div>`).join('') : emptyState('Nothing waiting here.', 'Commitments appear when a current document states a due date, renewal, delivery, or cancellation deadline.')}</section><p class="inline-note">Dates are candidates until reviewed. Recurrence and relative wording are not inferred. Calendar exports include open commitments from current sources.</p>`;
}
function renderReview() {
  const conflicts = scoped(state.snapshot.conflicts);
  const facts = scoped(state.snapshot.facts).filter(f => f.current && f.status === 'suggested');
  return intro('A second look matters.', 'Check the evidence. Keep what’s right. Dismiss what doesn’t apply.', '', 'THE REVIEW QUEUE') + `<div class="toolbar">${collectionSelect()}<span class="spacer"></span>${timelineControl()}</div>${conflicts.length ? `<div class="section-heading"><h2>${conflicts.length} possible conflicts</h2><span class="muted">Matching labels, different values</span></div><div class="stack">${conflicts.map(conflict => `<section class="finding-card"><div class="finding-top"><div><div class="finding-meta">${esc(conflict.matter)}</div><h3>${esc(conflict.label)}</h3></div>${pill('Context needed')}</div>${conflict.facts.map(f => `<div class="finding-value">${esc(f.display)}</div>${cite(f)}`).join('')}<p class="inline-note">These values may have different scope. Confirming an extraction does not choose which document applies; import an explicit replacement or dismiss an inapplicable finding.</p></section>`).join('')}</div>` : ''}<div class="section-heading"><h2>${facts.length} findings to review</h2></div><div class="stack">${facts.length ? facts.slice(0, 100).map(f => findingCard(f)).join('') : `<section class="panel">${emptyState('You’re up to date.', 'Every current finding has been reviewed. Newly imported documents will appear here.')}</section>`}</div>`;
}
function findingCard(fact) {
  return `<article class="finding-card"><div class="finding-top"><div><div class="finding-meta">${esc(fact.matter)} · ${esc(fact.label)}</div><div class="finding-value">${esc(fact.display)}</div></div>${pill(fact.status, fact.status === 'confirmed' ? 'green' : 'gray')}</div>${cite(fact)}<div class="finding-actions">${fact.status !== 'suggested' ? button('Reset review', 'review-fact', null, `data-id="${fact.id}" data-status="suggested"`, 'small') : ''}${fact.status !== 'dismissed' ? button('Dismiss', 'review-fact', null, `data-id="${fact.id}" data-status="dismissed"`, 'small subtle') : ''}${fact.status !== 'confirmed' ? button('Confirm extraction', 'review-fact', 'check', `data-id="${fact.id}" data-status="confirmed"`, 'small primary') : ''}${fact.kind === 'date' && fact.key !== 'effective_date' ? button('Plan this', 'plan-fact', 'plus', `data-id="${fact.id}"`, 'small') : ''}</div></article>`;
}
function render() {
  if (!state.snapshot) return;
  renderNavigation();
  const views = { overview: renderOverview, documents: renderDocuments, commitments: renderCommitments, review: renderReview, plans: renderPlans, activity: renderActivity };
  main.innerHTML = (views[state.view] || renderOverview)();
  document.title = `Lipso · ${$('#page-name').textContent}`;
}

async function openDocument(id, chunk = null, preserveTab = false) {
  state.doc = await api('/api/documents/' + id);
  if (!preserveTab) state.docTab = 'source';
  state.highlight = chunk;
  renderDocument();
  if (!docDialog.open) docDialog.showModal();
  if (chunk) requestAnimationFrame(() => $(`[data-source-chunk="${Number(chunk)}"]`)?.scrollIntoView({ block: 'center', behavior: 'instant' }));
}
function renderDocument() {
  const doc = state.doc;
  let body;
  if (state.docTab === 'source') body = `${doc.warnings.map(w => `<div class="notice">${esc(w)}</div>`).join('')}<div class="source-sheet">${doc.chunks.map(chunk => `<p class="source-line ${Number(state.highlight) === chunk.id ? 'target' : ''}" data-source-chunk="${chunk.id}"><small>${doc.filename.toLowerCase().endsWith('.pdf') ? `P${chunk.page} · ` : ''}L${chunk.line}</small>${esc(chunk.text)}</p>`).join('')}</div>`;
  else if (state.docTab === 'findings') body = `<div class="stack">${doc.facts.length ? doc.facts.map(findingCard).join('') : emptyState('No structured terms found.', 'The full text is still searchable. Extraction recognizes explicit dates, selected labeled amounts, and notice periods.')}</div>`;
  else body = `<div class="detail-row"><span>Collection</span><span>${esc(doc.matter)}</span></div><div class="detail-row"><span>Effective date</span><span>${esc(doc.effective_date || 'Not specified · applies immediately')}</span></div><div class="detail-row"><span>Imported</span><span>${esc(doc.imported_at)}</span></div><div class="detail-row"><span>Original SHA-256</span><code>${doc.sha}</code></div><div class="detail-row"><span>Text SHA-256</span><code>${doc.text_sha}</code></div><p class="inline-note">Checksums identify stored content. They do not establish who authored a document or whether its claims are true.</p><div class="section-heading"><a class="button" href="/api/documents/${doc.id}/original">${icon('download')}Download original</a>${button('Delete document', 'delete-doc', 'trash', `data-id="${doc.id}"`, 'danger')}</div>`;
  $('#document-content').innerHTML = `<header class="document-header"><div class="document-header-top"><span class="eyebrow">THE ORIGINAL CONTEXT</span><button class="icon-button" data-action="close-doc" aria-label="Close document">×</button></div><h2>${esc(doc.title)}</h2><div class="document-meta"><span class="collection-tag">${esc(doc.matter)}</span><span>${esc(doc.filename)}</span>${doc.demo ? '<span class="sample-tag">FICTIONAL SAMPLE</span>' : ''}</div><div class="tab-bar">${[['source', 'Source text'], ['findings', `Findings (${doc.facts.length})`], ['details', 'File details']].map(([key, label]) => `<button class="tab-button ${state.docTab === key ? 'active' : ''}" data-doc-tab="${key}">${label}</button>`).join('')}</div></header><div class="document-body">${body}</div>`;
}
function showModal(title, subtitle, body, footer = '', formId = '') {
  $('#modal-content').innerHTML = `${formId ? `<form id="${formId}">` : ''}<div class="modal-heading"><div><h2>${title}</h2><p>${subtitle}</p></div><button class="icon-button" type="button" data-action="close-modal" aria-label="Close dialog">×</button></div><div class="modal-body">${body}<p class="form-error" id="form-error" role="alert"></p></div>${footer ? `<div class="modal-footer">${footer}</div>` : ''}${formId ? '</form>' : ''}`;
  if (!modal.open) modal.showModal();
}
const field = (label, name, value = '', type = 'text', attrs = '', note = '', full = false) => `<div class="form-field ${full ? 'full' : ''}"><label for="field-${name}">${label}</label><input class="field-input" id="field-${name}" name="${name}" type="${type}" value="${esc(value)}" ${attrs}>${note ? `<small>${note}</small>` : ''}</div>`;
function openImport() {
  showModal('Bring a little context.', 'Import a document. Keep the original. Connect the details.', `<label class="dropzone" id="dropzone">${icon('upload')}<strong>Choose a file or drop it here</strong><small>PDF, DOCX, TXT, Markdown, CSV · up to 12 MB</small><input type="file" id="import-file" accept=".pdf,.docx,.txt,.md,.csv" required aria-label="Document file"></label><div class="form-grid">${field('Collection', 'matter', state.collection, 'text', 'required maxlength="100" list="collection-options"', 'Group documents about the same contract, account, or project.', true)}<datalist id="collection-options">${state.snapshot.collections.map(c => `<option value="${esc(c)}">`).join('')}</datalist>${field('Document title', 'title', '', 'text', 'maxlength="160"', 'Optional. Uses the filename when blank.', true)}${field('Effective from', 'effective_date', '', 'date', '', 'Leave blank if it applies immediately.')}<div class="form-field"><label for="field-replaces">Replaces a document</label><select class="field-input" id="field-replaces" name="replaces_id"><option value="">A separate source</option></select><small>Only choose a predecessor if this is an actual replacement.</small></div></div>`, '<button type="button" class="button" data-action="close-modal">Cancel</button><button type="submit" class="button primary">Import document ' + icon('arrow') + '</button>', 'import-form');
  updateReplacements();
}
function updateReplacements() {
  const collection = $('#field-matter')?.value.trim();
  const select = $('#field-replaces');
  if (select) select.innerHTML = '<option value="">A separate source</option>' + state.snapshot.documents.filter(d => d.matter === collection && !state.snapshot.documents.some(other => other.replaces_id === d.id)).map(d => `<option value="${d.id}">${esc(d.title)}</option>`).join('');
}
async function importDocument(form) {
  const file = $('#import-file').files[0];
  if (!file) throw new Error('Choose a file first.');
  if (file.size > 12 * 1024 * 1024) throw new Error('Choose a file smaller than 12 MB.');
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = '';
  for (let i = 0; i < bytes.length; i += 8192) binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
  const data = Object.fromEntries(new FormData(form));
  const result = await api('/api/documents', { method: 'POST', body: { ...data, filename: file.name, content_base64: btoa(binary) } });
  modal.close();
  await refresh();
  toast(result.duplicate ? 'This document is already in that collection.' : `Document imported. ${result.facts} findings ready to review.`);
  await openDocument(result.id);
}

function renderPlans() {
  let html = intro('Try tomorrow on for size.', 'Time, money, and evidence. Connected in a plan you can question.', button('New plan', 'new-plan', 'plus', '', 'primary'), 'THE PLANNING LAB');
  if (!state.plans.length) return html + `<section class="panel">${emptyState('A plan with room to change.', 'Model income, expenses, and the work that makes them possible. Then test an alternate future without changing the original.', button('Create your first plan', 'new-plan', 'plus', '', 'primary'))}</section>`;
  html += `<div class="toolbar"><div class="plan-controls"><select id="plan-picker" class="field-input plan-picker" aria-label="Choose plan">${state.plans.map(plan => `<option value="${plan.id}" ${state.plan?.id === plan.id ? 'selected' : ''}>${esc(plan.name)}${plan.parent_id ? ' ↳' : ''}</option>`).join('')}</select>${button('Settings', 'plan-settings', 'edit')}${button('Export JSON', 'export-plan', 'download')}${button('', 'delete-plan', 'trash', 'aria-label="Delete selected plan"')}</div></div>`;
  if (!state.plan || !state.simulation) return html + '<div class="loading-state loading-pulse">Connecting the numbers and the work…</div>';
  const sim = state.simulation, plan = state.plan.data;
  const s = sim.summary;
  html += `<div class="plan-metrics"><div class="stat-card"><span class="stat-heading">Cash below zero</span><div class="stat-value">${Math.round(s.negative_probability * 100)}<small>%</small></div><span class="stat-note">Of ${sim.runs} paths, given your assumptions</span></div><div class="stat-card"><span class="stat-heading">Ending cash · median</span><div class="stat-value">${amount(s.ending_p50, plan.currency, true)}</div><span class="stat-note">${plan.horizon} days from ${fmtDate(plan.start)}</span></div><div class="stat-card"><span class="stat-heading">Work needing attention</span><div class="stat-value">${s.late_tasks}<small> / ${plan.tasks.length}</small></div><span class="stat-note">Late or beyond the forecast horizon</span></div></div>`;
  html += `<div class="forecast-grid"><section class="panel"><div class="panel-heading"><h2>A range of tomorrows</h2>${Object.values(state.appliedEdits).some(Boolean) ? '<span class="scenario-badge">WHAT IF</span>' : pill('Baseline', 'green')}</div><div class="chart-wrap">${forecastChart(sim)}</div><div class="chart-legend"><span><i class="legend-dot"></i>Median cash</span><span><i class="legend-dot band"></i>10th–90th percentile</span></div><p class="inline-note chart-wrap">Based on entered amounts, probabilities, and delays. These are simulated paths, not predictions.</p></section><section class="panel"><div class="panel-heading"><h2>Change one thing. Or three.</h2>${icon('branch')}</div><div class="scenario-controls">${scenarioSlider('Income arrives later', 'income_delay', 0, 30, state.edits.income_delay || 0, 'days')}${scenarioSlider('Expenses change', 'expense_increase', -30, 50, Math.round((state.edits.expense_increase || 0) * 100), '%')}${scenarioSlider('Available time changes', 'capacity_change', -75, 100, Math.round((state.edits.capacity_change || 0) * 100), '%')}<div class="scenario-delta">${state.baseline && Object.values(state.appliedEdits).some(Boolean) ? `Median ending cash changes by <strong>${amount(s.ending_p50 - state.baseline.summary.ending_p50, plan.currency)}</strong>. ${s.late_tasks - state.baseline.summary.late_tasks > 0 ? `${s.late_tasks - state.baseline.summary.late_tasks} more task(s) need attention.` : 'The original plan is unchanged.'}` : 'Move a slider, then test the assumptions. Save an alternate plan to keep both versions.'}</div>${button('Test this scenario', 'simulate', 'chart', '', 'primary')}${button('Save as a branch', 'branch-plan', 'branch')}${button('Reset to baseline', 'reset-scenario', null, '', 'small subtle')}</div></section></div>`;
  if (sim.warnings.length) html += `<section class="panel"><div class="panel-heading"><h2>What this plan is telling you</h2>${pill(sim.warnings.length + ' signals')}</div><div class="warning-list">${sim.warnings.map(w => `<div class="warning-row">${icon(w.type === 'evidence_drift' ? 'file' : 'alert')}<span>${esc(w.message)}${w.fact_id ? ` <button class="text-button" data-action="open-fact" data-id="${w.fact_id}">Inspect source ↗</button>` : ''}</span></div>`).join('')}</div></section>`;
  html += `<div class="section-heading"><div><h2>The work behind the numbers</h2><p>${sim.schedule.hours} estimated hours · ${sim.schedule.capacity_hours} available hours in this forecast</p></div>${button('Add task', 'add-task', 'plus')}</div><section class="panel"><div class="chart-wrap">${scheduleChart(sim.schedule)}</div><div class="schedule-legend">Daily scheduled hours / available capacity · dependencies are completed before downstream work begins</div>${taskTable(plan.tasks, sim.schedule.tasks)}</section>`;
  html += `<div class="section-heading"><h2>Money in motion</h2>${button('Add cash flow', 'add-flow', 'plus')}</div><section class="panel">${flowTable(plan.flows, plan.currency, sim.events)}</section><div class="section-heading"><h2>The evidence behind this plan</h2></div>${sim.evidence.citations.length ? `<section class="panel"><div class="modal-body">${sim.evidence.citations.map(f => cite(f, true)).join('')}</div></section>` : '<p class="inline-note">This plan currently uses manually entered assumptions. Use “Plan this” on a commitment to retain a link to its source.</p>'}<p class="inline-note">Scheduling uses a deadline-first heuristic. Same-day cash flows are netted together. Task effort is fixed; cash uncertainty is sampled independently. ${button('Read the model assumptions', 'model-help', null, '', 'small subtle')}</p>`;
  return html;
}
function scenarioSlider(label, name, min, max, value, unit) { return `<div class="scenario-field"><label for="scenario-${name}">${label}<output id="output-${name}">${value > 0 && unit === '%' ? '+' : ''}${value}${unit === '%' ? '%' : ' days'}</output></label><input id="scenario-${name}" data-scenario="${name}" type="range" min="${min}" max="${max}" value="${value}" step="1"></div>`; }
function forecastChart(sim) {
  const width = 680, height = 235, left = 65, right = 13, top = 13, bottom = 35;
  const all = sim.days.flatMap(d => [d.p10, d.p90]);
  const low = Math.min(0, ...all) - 5000, high = Math.max(10000, sim.summary.reserve, ...all) + 5000;
  const x = i => left + i / Math.max(1, sim.days.length - 1) * (width - left - right);
  const y = v => top + (high - v) / (high - low) * (height - top - bottom);
  const path = (key, reverse = false) => (reverse ? [...sim.days].reverse() : sim.days).map((d, i) => `${x(reverse ? sim.days.length - 1 - i : i).toFixed(1)},${y(d[key]).toFixed(1)}`).join(' ');
  const grid = Array.from({ length: 4 }, (_, i) => { const value = low + (high - low) * i / 3; return `<line class="chart-grid" x1="${left}" x2="${width - right}" y1="${y(value)}" y2="${y(value)}"/><text class="chart-label" x="${left - 9}" y="${y(value) + 3}" text-anchor="end">${esc(amount(value, sim.currency, true))}</text>`; }).join('');
  return `<svg class="forecast-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Cash forecast showing median and a range from the tenth to ninetieth percentile">${grid}<polygon class="chart-band" points="${path('p90')} ${path('p10', true)}"/><line class="chart-zero" x1="${left}" x2="${width - right}" y1="${y(0)}" y2="${y(0)}"/><line class="chart-reserve" x1="${left}" x2="${width - right}" y1="${y(sim.summary.reserve)}" y2="${y(sim.summary.reserve)}"/><polyline class="chart-line" points="${path('p50')}"/>${[0, Math.floor((sim.days.length - 1) / 2), sim.days.length - 1].map(i => `<text class="chart-label" x="${x(i)}" y="${height - 10}" text-anchor="${i === 0 ? 'start' : i === sim.days.length - 1 ? 'end' : 'middle'}">${fmtDate(sim.days[i].date)}</text>`).join('')}</svg>`;
}
function scheduleChart(schedule) {
  const width = 900, height = 106, max = Math.max(60, ...schedule.days.map(d => d.capacity_minutes));
  const size = (width - 20) / schedule.days.length;
  return `<svg class="schedule-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Daily work allocation and available capacity">${schedule.days.map((d, i) => `<rect x="${10 + i * size}" y="${85 - d.capacity_minutes / max * 70}" width="${Math.max(2, size - 3)}" height="${d.capacity_minutes / max * 70}" rx="2" fill="#ecf1e3"/><rect x="${10 + i * size}" y="${85 - d.minutes / max * 70}" width="${Math.max(2, size - 3)}" height="${d.minutes / max * 70}" rx="2" fill="#91ab76"><title>${d.date}: ${(d.minutes / 60).toFixed(1)} / ${(d.capacity_minutes / 60).toFixed(1)} hours</title></rect>${i % 7 === 0 ? `<text x="${10 + i * size}" y="102" class="chart-label">${fmtDate(d.date)}</text>` : ''}`).join('')}</svg>`;
}
function taskTable(tasks, outcomes) {
  if (!tasks.length) return emptyState('Make the work visible.', 'Add a task, its effort, and the work it depends on.', button('Add task', 'add-task', 'plus'));
  return `<div class="table-wrap"><table class="documents-table"><thead><tr><th>Task</th><th>Effort</th><th>Deadline</th><th>Forecast</th><th></th></tr></thead><tbody>${tasks.map(task => { const result = outcomes.find(o => o.id === task.id); return `<tr><td><strong>${esc(task.title)}</strong><div class="inline-note">${task.dependencies.length ? 'After: ' + task.dependencies.map(dep => esc(tasks.find(t => t.id === dep)?.title || dep)).join(', ') : 'No dependencies'}</div></td><td>${task.hours}h</td><td>${fmtDate(task.due)}</td><td>${pill(result?.status === 'on_time' ? 'On time' : result?.status === 'late' ? `${result.late_days}d late` : 'Unscheduled', result?.status === 'on_time' ? 'green' : '')}${result?.finish ? `<div class="inline-note">${fmtDate(result.finish)}</div>` : ''}</td><td><div class="item-row-actions">${button('', 'edit-task', 'edit', `data-id="${task.id}" aria-label="Edit ${esc(task.title)}"`, 'small')}${button('', 'delete-task', 'trash', `data-id="${task.id}" aria-label="Delete ${esc(task.title)}"`, 'small')}</div></td></tr>`; }).join('')}</tbody></table></div>`;
}
function flowTable(flows, currency, events = []) {
  if (!flows.length) return emptyState('Follow the flow.', 'Add expected income and expenses, including their uncertainty.', button('Add cash flow', 'add-flow', 'plus'));
  return `<div class="table-wrap"><table class="documents-table"><thead><tr><th>Cash flow</th><th>Modeled amount</th><th>First modeled date</th><th class="mobile-hide">Assumptions</th><th></th></tr></thead><tbody>${flows.map(flow => `<tr><td><strong>${esc(flow.title)}</strong><div class="inline-note">${esc(flow.recurrence)}${flow.depends_on_task ? ' · linked to work' : ''}</div></td><td class="${flow.direction === 'in' ? 'money-in' : 'money-out'}">${flow.direction === 'in' ? '+' : '−'}${amount(Math.abs(events.find(e => e.flow_id === flow.id)?.amount ?? Number(flow.amount) * 100), currency)}${Math.abs(events.find(e => e.flow_id === flow.id)?.amount ?? Number(flow.amount) * 100) !== Number(flow.amount) * 100 ? `<div class="inline-note">Input: ${amount(Number(flow.amount) * 100, currency)}</div>` : ''}</td><td>${events.find(e => e.flow_id === flow.id) ? fmtDate(events.find(e => e.flow_id === flow.id).date) : 'Outside forecast'}${events.find(e => e.flow_id === flow.id)?.date !== flow.date ? `<div class="inline-note">Input: ${fmtDate(flow.date)}</div>` : ''}</td><td class="mobile-hide muted">${Math.round(flow.probability * 100)}% occurrence<br>0–${flow.delay_days}d delay</td><td><div class="item-row-actions">${button('', 'edit-flow', 'edit', `data-id="${flow.id}" aria-label="Edit ${esc(flow.title)}"`, 'small')}${button('', 'delete-flow', 'trash', `data-id="${flow.id}" aria-label="Delete ${esc(flow.title)}"`, 'small')}</div></td></tr>`).join('')}</tbody></table></div>`;
}
async function loadPlan(id) {
  const token = ++state.runToken;
  const plan = await api('/api/plans/' + id);
  if (token !== state.runToken) return;
  state.plan = plan; state.edits = {}; state.appliedEdits = {}; state.simulation = null; state.baseline = null;
  render();
  const simulation = await api('/api/simulate', { method: 'POST', body: { data: plan.data } });
  if (token !== state.runToken) return;
  state.simulation = simulation;
  state.baseline = state.simulation;
  render();
}
function openPlanSettings(isNew = false) {
  const plan = isNew ? { name: '', currency: 'USD', start: today(), horizon: 60, opening_balance: '0', reserve: '0', capacity: [4, 4, 4, 4, 4, 0, 0], tasks: [], flows: [] } : state.plan.data;
  state.editing = { type: 'settings', isNew };
  showModal(isNew ? 'A plan worth questioning.' : 'The shape of your plan.', 'One currency. Explicit assumptions. Room for an alternate outcome.', `<div class="form-grid">${field('Plan name', 'name', plan.name, 'text', 'required maxlength="120"', '', true)}${field('Currency code', 'currency', plan.currency, 'text', 'required pattern="[A-Z]{3}" maxlength="3"', 'For example USD, NGN, EUR. No conversion.')} ${field('Starts on', 'start', plan.start, 'date', 'required')}${field('Opening cash', 'opening_balance', plan.opening_balance, 'number', 'required step="0.01"')}${field('Cash reserve', 'reserve', plan.reserve, 'number', 'required min="0" step="0.01"')}${field('Forecast days', 'horizon', plan.horizon, 'number', 'required min="7" max="180"')}${field('Weekday working hours', 'weekday_hours', plan.capacity[0], 'number', 'required min="0" max="24" step="0.25"', 'Applies Monday to Friday when edited.')}${field('Weekend working hours', 'weekend_hours', plan.capacity[5], 'number', 'required min="0" max="24" step="0.25"', 'Applies Saturday and Sunday when edited.')}</div>`, '<button type="button" class="button" data-action="close-modal">Cancel</button><button class="button primary" type="submit">Save plan</button>', 'plan-settings-form');
}
function selectField(label, name, options, value, full = false, note = '') { return `<div class="form-field ${full ? 'full' : ''}"><label for="field-${name}">${label}</label><select class="field-input" id="field-${name}" name="${name}">${options.map(([key, text]) => `<option value="${esc(key)}" ${String(value ?? '') === String(key) ? 'selected' : ''}>${esc(text)}</option>`).join('')}</select>${note ? `<small>${note}</small>` : ''}</div>`; }
function openTask(id = null, fact = null) {
  const task = id ? state.plan.data.tasks.find(t => t.id === id) : { title: fact ? `${fact.label} · ${fact.matter}` : '', hours: 2, due: fact?.value || addDays(state.plan.data.start, 7), earliest: state.plan.data.start, priority: 3, dependencies: [], source_fact_id: fact?.id };
  state.editing = { type: 'task', id, original: task };
  showModal(id ? 'Adjust the work.' : 'Give the work a shape.', 'Effort and dependencies determine when a task can finish.', `<div class="form-grid">${field('Task title', 'title', task.title, 'text', 'required maxlength="160"', '', true)}${field('Effort in hours', 'hours', task.hours, 'number', 'required min="0.25" max="1000" step="0.25"')}${field('Deadline', 'due', task.due, 'date', 'required')}${field('Can start on', 'earliest', task.earliest, 'date', 'required')}${selectField('Priority', 'priority', [[1, 'Low'], [3, 'Normal'], [5, 'High']], task.priority)}<div class="form-field full"><label>Starts after these tasks</label><div class="checklist">${state.plan.data.tasks.filter(t => t.id !== id).map(t => `<label><input type="checkbox" name="dependencies" value="${t.id}" ${task.dependencies.includes(t.id) ? 'checked' : ''}>${esc(t.title)}</label>`).join('') || '<span class="muted">No other tasks yet.</span>'}</div></div>${task.source_fact_id ? `<p class="inline-note">Linked to finding #${task.source_fact_id}. Its source will be checked whenever this plan runs.</p>` : ''}</div>`, '<button type="button" class="button" data-action="close-modal">Cancel</button><button class="button primary" type="submit">Save task</button>', 'task-form');
}
function openFlow(id = null) {
  const flow = id ? state.plan.data.flows.find(f => f.id === id) : { title: '', direction: 'out', amount: '', date: state.plan.data.start, recurrence: 'once', probability: 1, delay_days: 0, variance: 0, lag_days: 0 };
  state.editing = { type: 'flow', id, original: flow };
  const moneyFacts = state.snapshot.facts.filter(f => f.kind === 'money' && f.status !== 'dismissed');
  const dateFacts = state.snapshot.facts.filter(f => f.kind === 'date' && f.status !== 'dismissed');
  showModal(id ? 'Adjust the cash flow.' : 'Put a number on it.', 'Record an assumption, then choose the evidence that supports it.', `<div class="form-grid">${field('Description', 'title', flow.title, 'text', 'required maxlength="160"', '', true)}${selectField('Direction', 'direction', [['in', 'Money in'], ['out', 'Money out']], flow.direction)}${field(`Amount (${esc(state.plan.data.currency)})`, 'amount', flow.amount, 'number', 'required min="0.01" step="0.01"')}${field('Expected date', 'date', flow.date, 'date', 'required')}${selectField('Repeats', 'recurrence', [['once', 'Once'], ['weekly', 'Weekly'], ['monthly', 'Monthly']], flow.recurrence)}${field('Chance it occurs (%)', 'probability', Math.round(flow.probability * 100), 'number', 'required min="0" max="100"', 'Your assumption, not a calculated confidence score.')}${field('Possible delay (days)', 'delay_days', flow.delay_days, 'number', 'required min="0" max="60"')}${field('Amount variation (±%)', 'variance', Math.round(flow.variance * 100), 'number', 'required min="0" max="100"')}${field('Days after task completion', 'lag_days', flow.lag_days || 0, 'number', 'required min="0" max="60"')}${selectField('Cannot arrive before this work finishes', 'depends_on_task', [['', 'No prerequisite'], ...state.plan.data.tasks.map(t => [t.id, t.title])], flow.depends_on_task, true)}${selectField('Amount evidence (optional)', 'source_fact_id', [['', 'Manually entered assumption'], ...moneyFacts.map(f => [f.id, `${f.matter} · ${f.label}: ${f.display}`])], flow.source_fact_id, true, 'Link a source to check for conflicts and changes. The amount stays as entered.')}${selectField('Date evidence (optional)', 'source_date_id', [['', 'Manually entered assumption'], ...dateFacts.map(f => [f.id, `${f.matter} · ${f.label}: ${f.display}`])], flow.source_date_id, true)}</div>`, '<button type="button" class="button" data-action="close-modal">Cancel</button><button class="button primary" type="submit">Save cash flow</button>', 'flow-form');
}
async function persistPlan(data) {
  await api('/api/plans/' + state.plan.id, { method: 'PATCH', body: { data } });
  modal.close(); await refresh(); await loadPlan(state.plan.id); toast('Plan saved and recalculated.');
}
function renderActivity() {
  const labels = { 'document.imported': 'Document imported and indexed', 'document.deleted': 'Document deleted', 'finding.reviewed': 'Finding reviewed', 'commitment.updated': 'Commitment updated', 'plan.saved': 'Plan saved', 'plan.deleted': 'Plan deleted' };
  return intro('A record you can follow.', 'Local changes, preserved sources, and checks you can run yourself.', button('Check integrity', 'integrity', 'shield', '', 'primary'), 'ACTIVITY & INTEGRITY') + `<section class="panel"><div class="panel-heading"><h2>Workspace activity</h2>${pill('Stored locally', 'green')}</div>${state.snapshot.audit.map(event => `<div class="audit-row"><span class="audit-symbol">${icon(event.event.startsWith('plan') ? 'branch' : 'file')}</span><div><strong>${labels[event.event] || esc(event.event)}</strong><small>#${event.sequence} · ${esc(new Date(event.at).toLocaleString())}</small><div class="hash">${event.hash.slice(0, 24)}…</div></div></div>`).join('') || emptyState('The story starts here.', 'Imports, reviews, and plan changes create an audit record.')}</section><p class="inline-note">The audit log uses chained hashes to detect inconsistencies. It is not digitally signed and does not prevent someone with database access from rewriting the whole chain. Originals remain downloadable.</p>`;
}

async function runAction(action, element) {
  const id = element?.dataset.id;
  if (action === 'reload') { location.reload(); return; }
  if (action === 'menu') return setSidebarOpen(!sidebarOpen);
  if (action === 'close-menu') return setSidebarOpen(false);
  if (action === 'overview') return navigate('overview');
  if (action === 'import') { setSidebarOpen(false); return openImport(); }
  if (action === 'close-modal') return modal.close();
  if (action === 'close-doc') return docDialog.close();
  if (action === 'export') { setSidebarOpen(false); window.location.href = '/api/export'; return; }
  if (action === 'review-view') return navigate('review');
  if (action === 'focus-search') { if (!['overview', 'documents'].includes(state.view)) navigate('overview'); $('#ask-input')?.focus(); return; }
  if (action === 'demo') {
    element.disabled = true; element.textContent = 'Building the sample workspace…';
    await api('/api/demo', { method: 'POST', body: {} }); await refresh(); toast('Fictional sample workspace loaded.'); return;
  }
  if (action === 'review-fact') {
    await api('/api/facts/' + id, { method: 'PATCH', body: { status: element.dataset.status } });
    await refresh(); if (docDialog.open) await openDocument(state.doc.id, state.highlight, true); toast('Review saved.'); return;
  }
  if (action === 'complete') {
    await api('/api/actions/' + id, { method: 'PATCH', body: { state: element.dataset.state } }); await refresh(); toast('Commitment updated.'); return;
  }
  if (action === 'delete-doc') {
    showModal('Remove this source?', 'The original file, text, and findings will be removed from this workspace.', '<p class="inline-note">Plans that reference this source will flag the missing evidence. Documents that replaced it will retain their own contents. A deletion event remains in the audit log.</p>', '<button class="button" data-action="close-modal">Keep document</button>' + button('Delete document', 'confirm-delete-doc', 'trash', `data-id="${id}"`, 'danger')); return;
  }
  if (action === 'confirm-delete-doc') {
    await api('/api/documents/' + id, { method: 'DELETE' }); modal.close(); docDialog.close(); await refresh(); toast('Document removed.'); return;
  }
  if (action === 'new-plan') return openPlanSettings(true);
  if (action === 'delete-plan') {
    showModal('Remove this plan?', 'Saved branches remain as independent plans. Your documents are unaffected.', `<p class="inline-note">${esc(state.plan.name)}</p>`, '<button class="button" data-action="close-modal">Keep plan</button>' + button('Delete plan', 'confirm-delete-plan', 'trash', '', 'danger')); return;
  }
  if (action === 'confirm-delete-plan') {
    state.runToken++;
    await api('/api/plans/' + state.plan.id, { method: 'DELETE' });
    state.plan = null; state.simulation = null; state.baseline = null; state.edits = {}; state.appliedEdits = {};
    modal.close(); await refresh();
    if (state.plans.length) await loadPlan(state.plans[0].id);
    toast('Plan deleted. Saved branches remain available.'); return;
  }
  if (action === 'plan-settings') return openPlanSettings();
  if (action === 'add-task' || action === 'edit-task') return openTask(id);
  if (action === 'add-flow' || action === 'edit-flow') return openFlow(id);
  if (action === 'plan-fact') {
    if (!state.plans.length) { docDialog.close(); navigate('plans'); toast('Create a plan first, then use “Plan this” on the commitment.'); return openPlanSettings(true); }
    const fact = state.snapshot.facts.find(f => f.id === Number(id));
    if (!fact) throw new Error('This finding no longer exists.');
    docDialog.close();
    if (!state.plan) await loadPlan(state.plans[0].id);
    state.view = 'plans'; render(); openTask(null, fact); return;
  }
  if (action === 'open-fact') {
    const fact = state.snapshot.facts.find(f => f.id === Number(id));
    if (!fact) throw new Error('The source finding has been deleted.');
    return openDocument(fact.document_id, fact.chunk_id);
  }
  if (action === 'simulate') {
    element.disabled = true; element.textContent = 'Simulating 400 paths…';
    const token = ++state.runToken, edits = structuredClone(state.edits);
    const simulation = await api('/api/simulate', { method: 'POST', body: { data: state.plan.data, scenario: edits } });
    if (token !== state.runToken) return;
    state.simulation = simulation; state.appliedEdits = edits; render(); return;
  }
  if (action === 'reset-scenario') { state.runToken++; state.edits = {}; state.appliedEdits = {}; state.simulation = state.baseline; render(); return; }
  if (action === 'branch-plan') {
    showModal('Keep another possibility.', 'A branch is a separate saved plan. The original stays unchanged.', `<div class="form-grid">${field('Branch name', 'name', state.plan.name + ' · alternate', 'text', 'required maxlength="120"', '', true)}</div><p class="inline-note">Income delay: ${state.edits.income_delay || 0} days. Expense change: ${Math.round((state.edits.expense_increase || 0) * 100)}%. Available time: ${Math.round((state.edits.capacity_change || 0) * 100)}%.</p>`, '<button type="button" class="button" data-action="close-modal">Cancel</button><button type="submit" class="button primary">Save branch</button>', 'branch-form'); return;
  }
  if (action === 'delete-task' || action === 'delete-flow') {
    const kind = action === 'delete-task' ? 'tasks' : 'flows';
    if (kind === 'tasks' && (state.plan.data.tasks.some(t => t.dependencies.includes(id)) || state.plan.data.flows.some(f => f.depends_on_task === id))) throw new Error('Remove this task from downstream dependencies and cash flows before deleting it.');
    const data = structuredClone(state.plan.data); data[kind] = data[kind].filter(item => item.id !== id); return persistPlan(data);
  }
  if (action === 'export-plan') {
    if (window.LipsoAndroid?.savePlan) {
      window.LipsoAndroid.savePlan(JSON.stringify(state.plan.data, null, 2)); return;
    }
    const blob = new Blob([JSON.stringify(state.plan.data, null, 2)], { type: 'application/json' });
    downloadBlob(blob, 'lipso-plan.json'); return;
  }
  if (action === 'integrity') {
    element.disabled = true;
    const report = await api('/api/integrity'); element.disabled = false;
    showModal(report.ok ? 'The records line up.' : 'Something needs checking.', 'Checksums, source spans, and the audit chain were checked.', `<div class="notice ${report.ok ? 'success' : ''}">${report.ok ? `${report.documents} original files and ${report.events} audit events passed.` : `${report.issues.length} integrity issues found. Export your workspace and inspect the affected records.`}</div><p class="hash">Audit head: ${report.head}</p>${report.issues.map(issue => `<p class="inline-note">${esc(issue.type)} · ${esc(issue.id)}</p>`).join('')}<p class="inline-note">This verifies internal consistency. It does not prove authorship, legal authority, or the truth of a claim.</p>`, '<button class="button primary" data-action="close-modal">Done</button>'); return;
  }
  if (action === 'model-help') return showModal('Inside the model.', 'Assumptions are part of the result.', `<div class="help-copy"><ul>${state.simulation.assumptions.map(a => `<li>${esc(a)}</li>`).join('')}</ul><p>All monetary calculations use integer minor units. Monthly recurrence keeps the original day of month, clipping only in shorter months. Payments linked to work cannot arrive before that work finishes plus its entered lag.</p></div>`, '<button class="button primary" data-action="close-modal">Understood</button>');
  if (action === 'about') return showModal('A little more Lipso.', 'A private workspace for evidence, commitments, and decisions.', `<div class="help-copy"><h3>One connected picture</h3><p>Import sources, review extracted terms, and connect deadlines to work and cash-flow plans. Test alternate assumptions without changing the original.</p><h3>What the evidence engine can read</h3><p>Selectable-text PDFs, DOCX, UTF-8 text, Markdown, and CSV. It recognizes explicit ISO or written-month dates, selected labeled amounts, and notice periods. It does not perform OCR, interpret legal authority, or infer relative deadlines.</p><h3>Questions with receipts</h3><p>Ask about due dates, changes, conflicts, rent, premiums, and other extracted terms. Other questions return ranked source passages. No language model or external service receives your documents.</p><h3>Local by design</h3><p>Your workspace is stored locally. It is not encrypted by this app. Use your device’s access controls and disk encryption for sensitive records. Export originals and structured data at any time.</p><h3>Keyboard shortcuts</h3><p>⌘/Ctrl K to search. Escape to close a dialog.</p></div>`, '<button class="button primary" data-action="close-modal">Back to the workspace</button>');
}
function downloadBlob(blob, filename) { const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = filename; link.click(); setTimeout(() => URL.revokeObjectURL(url), 5000); }

document.addEventListener('click', async event => {
  const element = event.target.closest('button, a[data-action]');
  if (!element || element.disabled) return;
  try {
    if (element.dataset.view) return navigate(element.dataset.view);
    if (element.dataset.collection !== undefined) return navigate('documents', element.dataset.collection);
    if (element.dataset.doc) return await openDocument(element.dataset.doc, element.dataset.chunk);
    if (element.dataset.docTab) { state.docTab = element.dataset.docTab; renderDocument(); return; }
    if (element.dataset.ask) { state.search = element.dataset.ask; return await askQuestion(element.dataset.ask); }
    if (element.dataset.action) { event.preventDefault(); await runAction(element.dataset.action, element); }
  } catch (error) { toast(error.message); if (element.isConnected) element.disabled = false; }
});
async function askQuestion(question) {
  const submit = $('#ask-form button');
  if (submit) { submit.disabled = true; submit.textContent = 'Finding evidence…'; }
  state.search = question;
  state.answer = await api('/api/ask', { method: 'POST', body: { question, matter: state.collection || null, as_of: state.asOf || null } });
  render(); $('.result-answer')?.scrollIntoView({ behavior: 'instant', block: 'nearest' });
}
document.addEventListener('submit', async event => {
  const form = event.target;
  event.preventDefault();
  const submit = form.querySelector('button[type="submit"]');
  const originalLabel = submit?.innerHTML;
  if (submit) submit.disabled = true;
  if ($('#form-error')) $('#form-error').textContent = '';
  try {
    const values = new FormData(form), data = Object.fromEntries(values);
    if (form.id === 'ask-form') return await askQuestion(data.question);
    if (form.id === 'import-form') return await importDocument(form);
    if (form.id === 'plan-settings-form') {
      const weekday = Number(data.weekday_hours), weekend = Number(data.weekend_hours);
      const old = state.editing.isNew ? { tasks: [], flows: [] } : structuredClone(state.plan.data);
      const capacity = state.editing.isNew ? [weekday, weekday, weekday, weekday, weekday, weekend, weekend] : old.capacity.map((h, i) => i < 5 ? (weekday !== old.capacity[0] ? weekday : h) : (weekend !== old.capacity[5] ? weekend : h));
      const value = { ...old, name: data.name, currency: data.currency, start: data.start, horizon: Number(data.horizon), opening_balance: data.opening_balance, reserve: data.reserve, capacity };
      const result = await api(state.editing.isNew ? '/api/plans' : '/api/plans/' + state.plan.id, { method: state.editing.isNew ? 'POST' : 'PATCH', body: { data: value } });
      modal.close(); state.view = 'plans'; await refresh(); await loadPlan(result.id); toast('Plan saved.'); return;
    }
    if (form.id === 'task-form' || form.id === 'flow-form') {
      const plan = structuredClone(state.plan.data), editing = state.editing;
      let item, collection;
      if (form.id === 'task-form') {
        collection = 'tasks'; item = { ...editing.original, ...data, id: editing.id || uid(), hours: Number(data.hours), priority: Number(data.priority), dependencies: values.getAll('dependencies') };
      } else {
        collection = 'flows'; item = { ...editing.original, ...data, id: editing.id || uid(), probability: Number(data.probability) / 100, variance: Number(data.variance) / 100, delay_days: Number(data.delay_days), lag_days: Number(data.lag_days), source_fact_id: data.source_fact_id ? Number(data.source_fact_id) : null, source_date_id: data.source_date_id ? Number(data.source_date_id) : null };
      }
      if (editing.id) plan[collection] = plan[collection].map(old => old.id === editing.id ? item : old); else plan[collection].push(item);
      return await persistPlan(plan);
    }
    if (form.id === 'branch-form') {
      const result = await api('/api/plans/' + state.plan.id + '/branch', { method: 'POST', body: { edits: state.edits, name: data.name } });
      modal.close(); await refresh(); await loadPlan(result.id); toast('Branch saved. The original plan is unchanged.'); return;
    }
  } catch (error) {
    const target = $('#form-error');
    if (modal.open && target) target.textContent = error.message; else toast(error.message);
  } finally { if (submit?.isConnected) { submit.disabled = false; submit.innerHTML = originalLabel; } }
});
document.addEventListener('input', event => {
  const element = event.target;
  if (element.id === 'field-matter') updateReplacements();
  if (element.dataset.scenario) {
    const key = element.dataset.scenario, value = Number(element.value);
    state.edits[key] = key === 'income_delay' ? value : value / 100;
    $('#output-' + key).textContent = `${value > 0 && key !== 'income_delay' ? '+' : ''}${value}${key === 'income_delay' ? ' days' : '%'}`;
  }
});
document.addEventListener('change', async event => {
  try {
    if (event.target.id === 'collection-filter') { state.collection = event.target.value; render(); }
    if (event.target.id === 'action-filter') { state.filter = event.target.value; render(); }
    if (event.target.id === 'as-of') { state.asOf = event.target.value; await refresh(); }
    if (event.target.id === 'plan-picker') await loadPlan(event.target.value);
  } catch (error) { toast(error.message); }
});
document.addEventListener('keydown', event => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault(); setSidebarOpen(false, { restoreFocus: false }); if (modal.open) modal.close(); if (docDialog.open) docDialog.close(); runAction('focus-search');
  }
  if (event.key === 'Escape' && sidebarOpen) { event.preventDefault(); setSidebarOpen(false); }
  if (event.key === 'Tab' && sidebarOpen) {
    const controls = [...sidebar.querySelectorAll('a[href], button:not([disabled]), [tabindex="0"]')].filter(el => el.getClientRects().length);
    const first = controls[0], last = controls.at(-1);
    if (event.shiftKey && (document.activeElement === first || document.activeElement === sidebar)) {
      event.preventDefault(); last?.focus({ preventScroll: true });
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault(); first?.focus({ preventScroll: true });
    }
  }
});
document.addEventListener('dragover', event => {
  if (event.target.closest('#dropzone')) { event.preventDefault(); $('#dropzone').classList.add('dragging'); }
});
document.addEventListener('dragleave', event => { if (event.target.closest('#dropzone')) $('#dropzone')?.classList.remove('dragging'); });
document.addEventListener('drop', event => {
  if (event.target.closest('#dropzone')) { event.preventDefault(); $('#dropzone').classList.remove('dragging'); if (event.dataTransfer.files.length) $('#import-file').files = event.dataTransfer.files; }
});
for (const dialog of [modal, docDialog]) dialog.addEventListener('click', event => { if (event.target === dialog) { const box = dialog.getBoundingClientRect(); if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) dialog.close(); } });
state.view = ['overview', 'documents', 'commitments', 'review', 'plans', 'activity'].includes(location.hash.slice(1)) ? location.hash.slice(1) : 'overview';
refresh().then(() => { if (state.view === 'plans' && state.plans.length) return loadPlan(state.plans[0].id); }).catch(error => { main.innerHTML = emptyState('The workspace couldn’t open.', esc(error.message), '<button class="button" data-action="reload">Try reloading this page</button>'); });
