import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// Final stage deck: film slot, 10-second hook, 15-second close, then backup slides for
// demo fallback and Q&A. Every number comes from notes/bmw-demo-claim-ledger.md.
const here = path.dirname(fileURLToPath(import.meta.url));
const out = path.join(here, 'output/pitch-final.html');
const fontRoot = path.join(here, 'assets/fonts');
const b64 = async file => (await fs.readFile(file)).toString('base64');
const font = async (family, weight, file) => `@font-face{font-family:'${family}';font-style:normal;font-weight:${weight};font-display:swap;src:url(data:font/woff2;base64,${await b64(file)}) format('woff2')}`;
const fonts = [
  await font('Barlow', 300, `${fontRoot}/barlow-latin-300-normal.woff2`),
  await font('Barlow', 400, `${fontRoot}/barlow-latin-400-normal.woff2`),
  await font('Barlow', 500, `${fontRoot}/barlow-latin-500-normal.woff2`),
  await font('Barlow', 600, `${fontRoot}/barlow-latin-600-normal.woff2`),
  await font('IBM Plex Mono', 400, `${fontRoot}/ibm-plex-mono-latin-400-normal.woff2`),
].join('\n');
const editCss = await fs.readFile(path.join(here, 'slide-edit.css'), 'utf8');
const runtime = await fs.readFile(path.join(here, 'slide-runtime.js'), 'utf8');
const logoWhite = (await fs.readFile(path.join(here, 'assets/bmw-white.svg'), 'utf8')).replace(/^<\?xml[^>]+>\s*/, '');
const logoGrey = (await fs.readFile(path.join(here, 'assets/bmw-grey.svg'), 'utf8')).replace(/^<\?xml[^>]+>\s*/, '');
// g60-car-faded.png is g60-car.webp with its studio backdrop faded to transparent, so the car
// sits on any dark panel without a visible box (CSS masks leave seams in printed PDFs).
const carUri = `data:image/png;base64,${await b64(path.join(here, 'assets/g60-car-faded.png'))}`;

const mark = dark => `<div class="brand">${dark ? logoWhite : logoGrey}<span><strong>BMW</strong><small>PRODUCT INTELLIGENCE</small></span></div>`;
const footer = (text, dark) => `<div class="footer ${dark ? 'footer-dark' : ''}"><span>G60 / i5 M60 / US</span><span>${text}</span></div>`;
const credit = '2023 BMW i5 M60 by Nazh Design / Sketchfab · CC BY 4.0 · independent artist model';
const backup = (n, title, sub, body, tag = '') => `
<section class="slide backup" data-backup data-label="B${n}" aria-label="Backup ${n}: ${title}">${mark(false)}
<span class="tag">BACKUP B${n}${tag ? ` · ${tag}` : ''}</span>
<div class="head"><h2 data-enter>${title}</h2><p class="sub" data-enter style="--d:.08s">${sub}</p></div>
${body}${footer(`B${n}`, false)}</section>`;
const cell = (label, value, text, d, extra = '') => `<article class="cell ${extra}" data-enter style="--d:${d}s"><span class="cell-label" data-edit>${label}</span><strong data-edit>${value}</strong><p>${text}</p></article>`;

const slides = [
  // Film slot. Put pitch-film.mp4 next to this HTML; without it, the title card shows instead.
  `<section class="slide dark film-slide active" data-label="Film" aria-label="Opening film">
<div class="film-fallback"><div class="film-car car-art" aria-hidden="true"></div><div class="film-copy"><p class="kicker" data-edit>BMW PRODUCT INTELLIGENCE</p><h1>Agents prepare.<br>Product managers decide.</h1></div><span class="credit">${credit}</span></div>
<video class="film" src="pitch-film.mp4" preload="auto" playsinline></video>
<span class="operator-note">Film slot: place pitch-film.mp4 beside this file. Press → to play; the deck advances when it ends.</span></section>`,

  // Hook: about 10 seconds, then switch to the live product.
  `<section class="slide hook" data-label="Hook" aria-label="Three questions">${mark(false)}
<p class="kicker" data-enter>LIVE · G60 / i5 M60 · US MARKET · 4,365 FEEDBACK ROWS</p>
<h2 data-enter style="--d:.06s">Every requirement has to survive three questions.</h2>
<ol class="questions">
<li data-enter style="--d:.16s"><b>01</b><div><strong data-edit>Where did it come from?</strong><p>One click to the customer's own words</p></div></li>
<li data-enter style="--d:.28s"><b>02</b><div><strong data-edit>How sure are we?</strong><p>Priority and proof, scored separately</p></div></li>
<li data-enter style="--d:.40s"><b>03</b><div><strong data-edit>What changed since we decided?</strong><p>Only affected decisions come back</p></div></li>
</ol>
<div class="hook-panel"></div><div class="hook-car car-art" data-enter style="--d:.2s" role="img" aria-label="BMW i5 M60 artist model"></div>
<span class="credit">${credit}</span>${footer('LIVE DEMO NEXT', false)}</section>`,

  // Close: about 15 seconds after the live demo.
  `<section class="slide dark close" data-close data-label="Close" aria-label="Close">${mark(true)}
<div class="blue-rule"></div>
<h1 data-enter>Agents prepare.<br>Product managers<br>decide.</h1>
<div class="lanes">
<div class="lane" data-enter style="--d:.14s"><span data-edit>AUTOMATED</span><p>Import feedback, link every proposal to its source rows, score it with a versioned rubric</p></div>
<div class="lane" data-enter style="--d:.26s"><span data-edit>SURFACED TO THE PM</span><p>Weak evidence, a dominant source, targets that are only assumptions</p></div>
<div class="lane human" data-enter style="--d:.38s"><span data-edit>PM ONLY</span><p>Approve, edit or reject the exact version. AI approvals are refused. Every step is audited.</p></div>
</div>
<p class="next" data-enter style="--d:.5s"><b>NEXT</b> Any <i>Baureihe</i>, any market · the same operations as scoped agent tasks over MCP · built to feed Codebeamer</p>
${footer('THANK YOU', true)}</section>`,

  backup(1, 'What the sample can and cannot say', 'Shown before any proposal, so counts are never read as market share.', `
<div class="cells three">
${cell('IMPORTED', '4,365', 'G60 / US feedback rows from the selected BMW files', .12)}
${cell('ONE SOURCE', '72.74%', 'of unique feedback IDs come from Source B (2,626 of 3,610); 60.2% of rows', .2)}
${cell('PROPOSALS', '11', 'source-linked requirement proposals in the opening demo state', .28)}
</div>
<p class="caveat" data-enter style="--d:.36s">Rows and feedback IDs are sample evidence, not customers or market prevalence.</p>`, 'OVERVIEW'),

  backup(2, 'Where the charging proposal came from', 'REQ-G60-US-001 · every link resolves to workbook, sheet and row.', `
<div class="trace">
<div class="trace-big" data-enter style="--d:.1s"><strong>264</strong><p>linked evidence records with exact locators</p><strong>12</strong><p>checked by hand against the archived workbook</p></div>
<table class="rows" data-enter style="--d:.2s"><caption>G60_feedback_hackathon.xlsx · Feedback_Explorer</caption>
<tr><th>Search and routing</th><td>rows 2141 · 4245 · 1932 · 2382</td></tr>
<tr><th>Charger availability</th><td>rows 432 · 1945 · 4764</td></tr>
<tr><th>Compatibility</th><td>rows 3383 · 193</td></tr>
<tr><th>Positive experience</th><td>rows 1692 · 4802</td></tr>
<tr class="warn"><th>False positive</th><td>row 4357 is phone charging. The PM sees it and can reject it.</td></tr>
</table></div>
<p class="caveat" data-enter style="--d:.32s">The rows support separate signals. The combined in-car route journey is a PM hypothesis that needs validation.</p>`, 'TRACE'),

  backup(3, 'Priority and proof stay separate', 'A high score with weak evidence must look different from a proven one.', `
<div class="cells three">
${cell('PRIORITY', '71.26', 'Deterministic rubric <code>customer-priority-v1</code>. Same inputs, same score. Some factors are heuristic or PM-assumed.', .12)}
${cell('EVIDENCE GRADE', 'C', 'Selected, undated and concentrated feedback with conflicts. Never mixed into the priority.', .2)}
${cell('TARGET', '80%', 'Task success in a moderated US trip-planning test. Labelled PM assumption: no study establishes it.', .28, 'assume')}
</div>`, 'SCORE'),

  backup(4, 'Only a PM can decide', 'The decision binds one exact requirement version and its score.', `
<div class="cells three">
${cell('AI APPROVAL', '403', 'An approval from the AI actor ai:reference:v1 is refused by the API.', .12)}
${cell('PM DECISION', 'v2', 'Approve, edit or reject the exact version and score, with a written rationale.', .2)}
${cell('AUDIT CHAIN', '130 → 143', 'Recorded events before and after the update. The chain verifies in both states.', .28)}
</div>
<p class="caveat" data-enter style="--d:.36s">In the prototype the actor name is self-declared. BMW SSO and permission mapping come in the pilot.</p>`, 'DECISION'),

  backup(5, 'Only affected decisions come back', 'A two-year process: new feedback reopens what it touches, nothing else.', `
<div class="cells three">
${cell('NEW INPUT', '+1', 'Synthetic, undated charging record, labelled simulated. Not BMW feedback.', .12)}
${cell('REOPENED', '1 of 11', 'Only the charging proposal returns for review. Ten stay untouched.', .2)}
${cell('THE DELTA', '+0.07', 'Priority 71.26 → 71.33. Wording and target unchanged. Approved v2 stays frozen beside v3.', .28)}
</div>`, 'SIMULATED UPDATE'),

  backup(6, 'Built today, pilot next', 'What we verified for this demo, and what BMW would validate with us.', `
<div class="split">
<div class="col" data-enter style="--d:.12s"><span>VERIFIED IN THIS BUILD</span><ul>
<li>Source-linked proposals for G60 / US</li><li>Versioned deterministic scoring with a separate evidence grade</li><li>Human-only decision gate and verifiable audit chain</li><li>Delta-only re-review after new input</li><li>The same operations over API and MCP</li></ul></div>
<div class="col pilot" data-enter style="--d:.22s"><span>PILOT WITH BMW</span><ul>
<li>BMW identity, SSO and permissions</li><li>Codebeamer export interface</li><li>Live LLM analysis on BMW's governed model endpoint</li><li>Second market and <i>Baureihe</i> comparison</li><li>Measure grounding rate, review effort and time-to-trace</li></ul></div>
</div>`, 'Q&A'),

  backup(7, 'The agent-ready runtime', 'Integrated platform build. Separate from the frozen G60 / US demo.', `
<div class="cells four">
${cell('REGISTRY', 'Roles', 'Specialist agents, each limited to the capabilities granted to it', .1)}
${cell('TASK QUEUE', 'Scoped', 'Every task is bound to one vehicle and market; stale writes are rejected', .18)}
${cell('SCHEDULER', 'Recurring', 'Recurring checks create one task per due slot', .26)}
${cell('RUN HISTORY', 'Logged', 'Inputs, input hash, outputs and errors for every run', .34)}
</div>
<p class="caveat" data-enter style="--d:.42s">Accepting a task never approves a requirement. Bounded LLM orchestration of these agents is the next phase.</p>`, 'Q&A'),
];

const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Final Pitch · BMW Product Intelligence</title>
<style>
${fonts}
:root{--navy:#0b1422;--ink:#171b21;--blue:#1c69d4;--paper:#f4f5f7;--tile:#e9ecf1;--muted:#5d6878;--light:#c9d8eb;--amber:#b86e00}
*{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;overflow:hidden;background:#050b13}body{font-family:Barlow,Arial,sans-serif}
.deck{position:absolute;left:50%;top:50%;width:1280px;height:720px;transform:translate(-50%,-50%) scale(var(--scale,1));transform-origin:center;overflow:hidden;background:var(--navy);box-shadow:0 25px 100px #0008}
.slide{position:absolute;inset:0;display:none;overflow:hidden;background:var(--paper);color:var(--ink)}.slide.active{display:block;animation:slideIn .5s cubic-bezier(.2,.75,.2,1) both}.slide.dark{background:var(--navy);color:#fff}
@keyframes slideIn{from{opacity:0}to{opacity:1}}
[data-enter]{opacity:0;transform:translateY(18px)}.active [data-enter]{animation:rise .55s calc(.1s + var(--d,0s)) cubic-bezier(.2,.8,.2,1) both}@keyframes rise{to{opacity:1;transform:none}}
h1,h2,h3,p,ol,ul{margin:0}h1,h2{font-weight:300;letter-spacing:-.022em}
.brand{position:absolute;z-index:2;left:80px;top:40px;display:flex;gap:14px;align-items:center}.brand svg{width:44px;height:44px}.brand span{display:flex;flex-direction:column;gap:2px}.brand strong{font-size:22px;font-weight:600;line-height:1}.brand small{font:400 11px/1.2 'IBM Plex Mono',monospace;color:var(--muted)}.dark .brand small{color:#a9bbd2}
.footer{position:absolute;left:80px;right:80px;bottom:28px;display:flex;justify-content:space-between;font:400 12px 'IBM Plex Mono',monospace;color:var(--muted);letter-spacing:.04em}.footer-dark{color:#8fa5be}
.kicker{font:400 15px 'IBM Plex Mono',monospace;letter-spacing:.06em;color:var(--blue)}
.credit{position:absolute;right:80px;bottom:52px;font-size:11px;color:#8b95a3}
/* Film */
.film-slide{background:#000}.film{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;background:#000;opacity:0}.has-film .film{opacity:1}
.film-fallback{position:absolute;inset:0;background:radial-gradient(circle at 70% 55%,#173a6b 0,#0b1422 55%)}.car-art{background:url(${carUri}) center/contain no-repeat;aspect-ratio:1035/610}.film-car{position:absolute;right:20px;top:170px;width:700px}
.film-copy{position:absolute;left:80px;top:220px;width:620px}.film-copy h1{font-size:68px;line-height:1.06;margin-top:22px}
.film-slide .credit{color:#6f86a3}.operator-note{position:absolute;left:80px;bottom:24px;font:400 11px 'IBM Plex Mono',monospace;color:#5d7391}.has-film .operator-note,.has-film .film-fallback{display:none}
/* Hook */
.hook .kicker{position:absolute;left:80px;top:140px}.hook h2{position:absolute;left:80px;top:174px;width:680px;font-size:56px;line-height:1.08}
.questions{position:absolute;left:80px;top:338px;width:640px;padding:0;list-style:none}.questions li{display:grid;grid-template-columns:66px 1fr;padding:16px 0 18px;border-top:1px solid #d4dae3}.questions li:last-child{border-bottom:1px solid #d4dae3}
.questions b{font:400 20px 'IBM Plex Mono',monospace;color:var(--blue);padding-top:5px}.questions strong{display:block;font-size:32px;font-weight:500;letter-spacing:-.01em;line-height:1.1}.questions p{font-size:20px;color:var(--muted);margin-top:5px}
.hook-panel{position:absolute;left:792px;top:0;right:0;bottom:0;background:radial-gradient(circle at 50% 52%,#1d3352 0,#0b1422 70%)}.hook-car{position:absolute;left:770px;top:240px;width:500px}.hook .credit{right:28px;width:440px;text-align:right;color:#6f86a3}.hook .footer span:last-child{color:#8fb4e8}.hook .questions,.hook h2{width:660px}
/* Close */
.close .blue-rule{position:absolute;left:80px;top:168px;width:7px;height:300px;background:var(--blue);transform-origin:top;transform:scaleY(0)}.active .blue-rule{animation:ruleGrow .7s .1s cubic-bezier(.2,.8,.2,1) forwards}@keyframes ruleGrow{to{transform:scaleY(1)}}
.close h1{position:absolute;left:112px;top:178px;width:540px;font-size:66px;line-height:1.06}
.lanes{position:absolute;left:676px;top:160px;width:524px}.lane{padding:18px 0 20px;border-top:1px solid #2c4060}.lane:last-child{border-bottom:1px solid #2c4060}.lane span{font:400 13px 'IBM Plex Mono',monospace;letter-spacing:.08em;color:#8fb4e8}.lane p{font-size:22px;line-height:1.28;color:#d8e3f1;margin-top:7px}
.lane.human{background:linear-gradient(90deg,#1c69d433,transparent);padding-left:18px;margin-left:-18px;border-left:3px solid var(--blue)}.lane.human span{color:#fff}.lane.human p{color:#fff}
.next{position:absolute;left:80px;right:80px;top:584px;padding-top:18px;border-top:1px solid #2c4060;font-size:19px;color:#b9c9dd}.next b{font:400 13px 'IBM Plex Mono',monospace;letter-spacing:.08em;color:#8fb4e8;margin-right:14px}
/* Backup */
.backup .tag{position:absolute;right:80px;top:56px;font:400 13px 'IBM Plex Mono',monospace;letter-spacing:.06em;color:var(--blue)}
.backup .head{position:absolute;left:80px;top:128px;width:1100px}.backup h2{font-size:52px;line-height:1.08}.sub{font-size:22px;color:var(--muted);margin-top:8px}
.cells{position:absolute;left:80px;top:300px;width:1120px;display:grid;gap:20px}.cells.three{grid-template-columns:repeat(3,1fr)}.cells.four{grid-template-columns:repeat(4,1fr)}
.cell{background:var(--tile);padding:26px 26px 28px;min-height:230px}.cell-label{font:400 13px 'IBM Plex Mono',monospace;letter-spacing:.07em;color:var(--blue)}.cell strong{display:block;font-size:58px;font-weight:300;letter-spacing:-.02em;margin-top:22px;line-height:1}.cells.four strong{font-size:40px}.cell code{font:400 15px 'IBM Plex Mono',monospace;white-space:nowrap}.cell p{font-size:19px;line-height:1.3;color:var(--muted);margin-top:18px}
.cell.assume .cell-label{color:var(--amber)}.cell.assume{box-shadow:inset 0 3px 0 var(--amber)}
.caveat{position:absolute;left:80px;width:1120px;top:590px;font-size:18px;color:var(--muted);padding-left:16px;border-left:3px solid #c3ccd8}
.trace{position:absolute;left:80px;top:270px;width:1120px;display:grid;grid-template-columns:300px 1fr;gap:40px}.trace-big strong{display:block;font-size:64px;font-weight:300;line-height:1}.trace-big p{font-size:18px;color:var(--muted);margin:6px 0 22px}
.rows{border-collapse:collapse;width:100%;font-size:19px}.rows caption{text-align:left;font:400 13px 'IBM Plex Mono',monospace;color:var(--blue);padding-bottom:10px;letter-spacing:.04em}.rows th{text-align:left;font-weight:500;padding:11px 0;width:240px;border-top:1px solid #d4dae3}.rows td{font:400 16px 'IBM Plex Mono',monospace;color:var(--ink);border-top:1px solid #d4dae3}.rows .warn th,.rows .warn td{color:var(--amber);font-family:Barlow,Arial,sans-serif;font-size:18px}
.split{position:absolute;left:80px;top:280px;width:1120px;display:grid;grid-template-columns:1fr 1fr;gap:20px}.col{background:var(--tile);padding:26px 30px}.col span{font:400 13px 'IBM Plex Mono',monospace;letter-spacing:.07em;color:var(--blue)}.col.pilot span{color:var(--amber)}.col ul{padding-left:20px;margin-top:14px}.col li{font-size:20px;line-height:1.3;padding:5px 0}
/* Controls */
.progress{position:absolute;z-index:10;left:0;bottom:0;height:4px;background:var(--blue);transition:width .45s ease}
.toolbar .timer{font:400 13px 'IBM Plex Mono',monospace;padding:0 6px;color:#8fb4e8}
@media(prefers-reduced-motion:reduce){.slide.active,.active [data-enter],.active .blue-rule{animation:none!important;opacity:1!important;transform:none!important}.progress{transition:none}}
${editCss}
@media print{.film,.operator-note{display:none!important}.film-fallback{display:block!important}}
</style></head><body><main class="deck" aria-label="Final pitch deck">
${slides.join('\n')}
<div class="progress" id="progress"></div><div class="toolbar" aria-label="Slide controls"><span class="timer" id="timer" hidden>0:00</span><button id="prev" aria-label="Previous slide">‹</button><span class="page-count" id="page-count">Film</span><button id="next" aria-label="Next slide">›</button><button id="edit">Edit text</button><button id="save">Save HTML</button><button id="print">Print PDF</button></div>
</main><script>${runtime}</script></body></html>`;
await fs.writeFile(out, html);
console.log(out);
