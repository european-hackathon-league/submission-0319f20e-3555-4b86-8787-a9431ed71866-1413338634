import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// Final stage deck: film slot, hook, close, then backup slides for demo fallback and Q&A.
// Slides carry only headlines, large figures and short card text; the presenter speaks the
// detail and caveats (notes/pitch-final-run-of-show.md). Figures follow the claim ledger.
const here = path.dirname(fileURLToPath(import.meta.url));
const out = path.join(here, 'output/pitch-final.html');
const fontRoot = path.join(here, 'assets/fonts');
const b64 = async file => (await fs.readFile(file)).toString('base64');
const font = async (family, weight, file) => `@font-face{font-family:'${family}';font-style:normal;font-weight:${weight};font-display:swap;src:url(data:font/woff2;base64,${await b64(file)}) format('woff2')}`;
const fonts = [
  await font('Barlow', 300, `${fontRoot}/barlow-latin-300-normal.woff2`),
  await font('Barlow', 400, `${fontRoot}/barlow-latin-400-normal.woff2`),
  await font('Barlow', 500, `${fontRoot}/barlow-latin-500-normal.woff2`),
].join('\n');
const editCss = await fs.readFile(path.join(here, 'slide-edit.css'), 'utf8');
const runtime = await fs.readFile(path.join(here, 'slide-runtime.js'), 'utf8');
const logoWhite = (await fs.readFile(path.join(here, 'assets/bmw-white.svg'), 'utf8')).replace(/^<\?xml[^>]+>\s*/, '');
const logoGrey = (await fs.readFile(path.join(here, 'assets/bmw-grey.svg'), 'utf8')).replace(/^<\?xml[^>]+>\s*/, '');
// g60-car-faded.png is g60-car.webp with its studio backdrop faded to transparent, so the car
// sits on any dark panel without a visible box (CSS masks leave seams in printed PDFs).
// Car model: "2023 BMW i5 M60" by Nazh Design / Sketchfab, CC BY 4.0 (credited in pitch/README.md).
const carUri = `data:image/png;base64,${await b64(path.join(here, 'assets/g60-car-faded.png'))}`;

const mark = dark => `<div class="mark">${dark ? logoWhite : logoGrey}</div>`;
const card = (value, text, d, extra = '') => `<article class="card ${extra}" data-enter style="--d:${d}s"><strong data-edit>${value}</strong><p>${text}</p></article>`;
const backup = (n, title, cards) => `
<section class="slide backup" data-backup data-label="B${n}" aria-label="Backup ${n}: ${title}">${mark(false)}
<h2 data-enter>${title}</h2>
<div class="cards">${cards}</div></section>`;

const slides = [
  // Film slot. Put pitch-film.mp4 next to this HTML; without it, the title card shows instead.
  `<section class="slide dark film-slide active" data-label="Film" aria-label="Opening film">
<div class="film-fallback"><div class="film-car car-art" aria-hidden="true"></div><h1 class="film-title">Agents prepare.<br>Product managers decide.</h1></div>
<video class="film" src="pitch-film.mp4" preload="auto" playsinline></video></section>`,

  `<section class="slide hook" data-label="Hook" aria-label="Three questions">${mark(false)}
<h2 data-enter>Every requirement has to survive three questions.</h2>
<ol class="questions">
<li data-enter style="--d:.16s"><b>1</b><strong data-edit>Where did it come from?</strong></li>
<li data-enter style="--d:.28s"><b>2</b><strong data-edit>How sure are we?</strong></li>
<li data-enter style="--d:.40s"><b>3</b><strong data-edit>What changed since we decided?</strong></li>
</ol>
<div class="hook-panel"></div><div class="hook-car car-art" data-enter style="--d:.2s" role="img" aria-label="BMW i5 M60"></div></section>`,

  `<section class="slide dark close" data-close data-label="Close" aria-label="Close">${mark(true)}
<div class="blue-rule"></div>
<h1 data-enter>Agents prepare.<br>Product managers<br>decide.</h1>
<div class="lanes">
<div class="lane" data-enter style="--d:.14s"><strong data-edit>Automated</strong><p>Import, link to source, score</p></div>
<div class="lane" data-enter style="--d:.26s"><strong data-edit>Surfaced</strong><p>Weak evidence and assumptions</p></div>
<div class="lane human" data-enter style="--d:.38s"><strong data-edit>PM only</strong><p>Every decision, fully audited</p></div>
</div></section>`,

  backup(1, 'Samples, not market share', [
    card('4,365', 'Feedback rows', .12),
    card('73%', 'From one source', .2),
    card('11', 'Proposals', .28),
  ].join('')),
  backup(2, 'One click to the source', [
    card('264', 'Linked source rows', .12),
    card('12', 'Checked by hand', .2),
    card('1 click', "To the customer's words", .28),
  ].join('')),
  backup(3, 'Priority and proof stay separate', [
    card('71.26', 'Priority score', .12),
    card('C', 'Evidence grade', .2),
    card('80%', 'Target: PM assumption', .28, 'assume'),
  ].join('')),
  backup(4, 'Only a PM can decide', [
    card('Refused', 'AI approvals', .12),
    card('Versioned', 'Every PM decision', .2),
    card('Audited', 'Every step', .28),
  ].join('')),
  backup(5, 'Only affected decisions come back', [
    card('+1', 'Simulated record', .12),
    card('1 of 11', 'Reopened', .2),
    card('+0.07', 'Priority change', .28),
  ].join('')),
  backup(6, 'Built today, pilot next', `
<article class="list" data-enter style="--d:.12s"><strong>Built today</strong><ul><li>Source-linked proposals</li><li>Deterministic scoring</li><li>Human-only decisions</li><li>Delta-only review</li></ul></article>
<article class="list pilot" data-enter style="--d:.22s"><strong>Pilot next</strong><ul><li>BMW SSO</li><li>Codebeamer export</li><li>Live LLM agents</li><li>More markets</li></ul></article>`),
  backup(7, 'Ready for agents', [
    card('Registry', 'Scoped roles', .1),
    card('Tasks', 'One market each', .18),
    card('Schedule', 'Recurring checks', .26),
    card('Runs', 'Every one logged', .34),
  ].join('')),
];

const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Final Pitch · BMW Product Intelligence</title>
<style>
${fonts}
:root{--navy:#0b1422;--ink:#171b21;--blue:#1c69d4;--paper:#f4f5f7;--tile:#e9ecf1;--muted:#5d6878;--amber:#b86e00}
*{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;overflow:hidden;background:#050b13}body{font-family:Barlow,Arial,sans-serif}
.deck{position:absolute;left:50%;top:50%;width:1280px;height:720px;transform:translate(-50%,-50%) scale(var(--scale,1));transform-origin:center;overflow:hidden;background:var(--navy);box-shadow:0 25px 100px #0008}
.slide{position:absolute;inset:0;display:none;overflow:hidden;background:var(--paper);color:var(--ink)}.slide.active{display:block;animation:slideIn .5s cubic-bezier(.2,.75,.2,1) both}.slide.dark{background:var(--navy);color:#fff}
@keyframes slideIn{from{opacity:0}to{opacity:1}}
[data-enter]{opacity:0;transform:translateY(18px)}.active [data-enter]{animation:rise .55s calc(.1s + var(--d,0s)) cubic-bezier(.2,.8,.2,1) both}@keyframes rise{to{opacity:1;transform:none}}
h1,h2,p,ol,ul{margin:0}h1,h2{font-weight:300;letter-spacing:-.022em}
.mark{position:absolute;z-index:2;left:80px;top:48px}.mark svg{width:48px;height:48px;display:block}
.car-art{background:url(${carUri}) center/contain no-repeat;aspect-ratio:1035/610}
/* Film */
.film-slide{background:#000}.film{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;background:#000;opacity:0}.has-film .film{opacity:1}
.film-fallback{position:absolute;inset:0;background:radial-gradient(circle at 70% 55%,#173a6b 0,#0b1422 55%)}.film-car{position:absolute;right:20px;top:170px;width:700px}
.film-title{position:absolute;left:80px;top:250px;width:620px;font-size:68px;line-height:1.06}.has-film .film-fallback{display:none}
/* Hook */
.hook h2{position:absolute;left:80px;top:170px;width:640px;font-size:58px;line-height:1.08}
.questions{position:absolute;left:80px;top:380px;width:640px;padding:0;list-style:none}.questions li{display:grid;grid-template-columns:56px 1fr;align-items:baseline;padding:20px 0;border-top:1px solid #d4dae3}.questions li:last-child{border-bottom:1px solid #d4dae3}
.questions b{font-size:30px;font-weight:300;color:var(--blue)}.questions strong{font-size:32px;font-weight:500;letter-spacing:-.01em}
.hook-panel{position:absolute;left:792px;top:0;right:0;bottom:0;background:radial-gradient(circle at 50% 52%,#1d3352 0,#0b1422 70%)}.hook-car{position:absolute;left:806px;top:262px;width:460px}
/* Close */
.close .blue-rule{position:absolute;left:80px;top:196px;width:7px;height:300px;background:var(--blue);transform-origin:top;transform:scaleY(0)}.active .blue-rule{animation:ruleGrow .7s .1s cubic-bezier(.2,.8,.2,1) forwards}@keyframes ruleGrow{to{transform:scaleY(1)}}
.close h1{position:absolute;left:112px;top:206px;width:540px;font-size:68px;line-height:1.06}
.lanes{position:absolute;left:700px;top:196px;width:500px}.lane{padding:22px 0 24px;border-top:1px solid #2c4060}.lane:last-child{border-bottom:1px solid #2c4060}.lane strong{display:block;font-size:30px;font-weight:500}.lane p{font-size:24px;color:#b9c9dd;margin-top:4px}
.lane.human{background:linear-gradient(90deg,#1c69d433,transparent);padding-left:20px;margin-left:-20px;border-left:3px solid var(--blue)}.lane.human p{color:#fff}
/* Backup */
.backup h2{position:absolute;left:80px;top:150px;width:1120px;font-size:56px;line-height:1.08}
.cards{position:absolute;left:80px;top:300px;width:1120px;display:grid;grid-auto-flow:column;grid-auto-columns:1fr;gap:20px}
.card{background:var(--tile);padding:34px 32px;min-height:250px;display:flex;flex-direction:column;justify-content:space-between}.card strong{font-size:72px;font-weight:300;letter-spacing:-.02em;line-height:1}.card p{font-size:26px;color:var(--muted)}
.cards:has(.card:nth-child(4)) .card strong{font-size:52px}
.card.assume{box-shadow:inset 0 4px 0 var(--amber)}
.list{background:var(--tile);padding:34px 36px}.list strong{font-size:32px;font-weight:500;color:var(--blue)}.list.pilot strong{color:var(--amber)}.list ul{list-style:none;padding:0;margin-top:20px}.list li{font-size:26px;padding:9px 0;border-top:1px solid #d4dae3}
/* Controls */
.progress{position:absolute;z-index:10;left:0;bottom:0;height:4px;background:var(--blue);transition:width .45s ease}
.toolbar .timer{font-size:13px;padding:0 6px;color:#8fb4e8}
@media(prefers-reduced-motion:reduce){.slide.active,.active [data-enter],.active .blue-rule{animation:none!important;opacity:1!important;transform:none!important}.progress{transition:none}}
${editCss}
@media print{.film{display:none!important}.film-fallback{display:block!important}}
</style></head><body><main class="deck" aria-label="Final pitch deck">
${slides.join('\n')}
<div class="progress" id="progress"></div><div class="toolbar" aria-label="Slide controls"><span class="timer" id="timer" hidden>0:00</span><button id="prev" aria-label="Previous slide">‹</button><span class="page-count" id="page-count">Film</span><button id="next" aria-label="Next slide">›</button><button id="edit">Edit text</button><button id="save">Save HTML</button><button id="print">Print PDF</button></div>
</main><script>${runtime}</script></body></html>`;
await fs.writeFile(out, html);
console.log(out);
