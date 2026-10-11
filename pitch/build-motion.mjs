import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import sharp from 'sharp';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.dirname(here);
const out = path.join(here, 'output/pitch-bmw-motion.html');
const fontRoot = '/Users/troy/Desktop/ehl-final/mcp_server/ui/node_modules/@fontsource';
const b64 = async file => (await fs.readFile(file)).toString('base64');
const font = async (family, weight, file) => `@font-face{font-family:'${family}';font-style:normal;font-weight:${weight};font-display:swap;src:url(data:font/woff2;base64,${await b64(file)}) format('woff2')}`;
const fonts = [
  await font('Barlow', 300, `${fontRoot}/barlow/files/barlow-latin-300-normal.woff2`),
  await font('Barlow', 400, `${fontRoot}/barlow/files/barlow-latin-400-normal.woff2`),
  await font('Barlow', 500, `${fontRoot}/barlow/files/barlow-latin-500-normal.woff2`),
  await font('Barlow', 600, `${fontRoot}/barlow/files/barlow-latin-600-normal.woff2`),
  await font('IBM Plex Mono', 400, `${fontRoot}/ibm-plex-mono/files/ibm-plex-mono-latin-400-normal.woff2`),
].join('\n');

const logoWhite = (await fs.readFile(path.join(root, 'web/public/brand/bmw-white.svg'), 'utf8')).replace(/^<\?xml[^>]+>\s*/, '');
const logoGrey = (await fs.readFile(path.join(root, 'web/public/brand/bmw-grey.svg'), 'utf8')).replace(/^<\?xml[^>]+>\s*/, '');
const iconSvgs = await Promise.all([1,2,3,4].map(i => fs.readFile(path.join(here, `assets/reference-icon-${i}.svg`), 'utf8')));
const car = await sharp(path.join(root, 'assets/vehicles/g60-us/poster.webp'))
  .extract({ left: 365, top: 225, width: 1035, height: 610 })
  .webp({ quality: 90 }).toBuffer();
const carUri = `data:image/webp;base64,${car.toString('base64')}`;

function mark(dark=false) {
  return `<div class="brand">${dark ? logoWhite : logoGrey}<span><strong>BMW</strong><small>PRODUCT INTELLIGENCE</small></span></div>`;
}
function footer(i, dark=false) {
  return `<div class="footer ${dark ? 'footer-dark' : ''}"><span>G60 / US</span><span>${String(i).padStart(2,'0')}</span></div>`;
}
const icon = i => iconSvgs[i].replaceAll('#171b21', '#171b21').replaceAll('currentColor', '#171b21');

const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BMW Product Intelligence · Pitch</title>
<style>
${fonts}
:root{--navy:#0b1422;--ink:#171b21;--blue:#1c69d4;--paper:#f4f5f7;--tile:#edeff3;--muted:#657080;--light:#c9d8eb}
*{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;overflow:hidden;background:#050b13}body{font-family:Barlow,Arial,sans-serif}
.deck{position:absolute;left:50%;top:50%;width:1280px;height:720px;transform:translate(-50%,-50%) scale(var(--scale,1));transform-origin:center;overflow:hidden;background:var(--navy);box-shadow:0 25px 100px #0008}
.slide{position:absolute;inset:0;display:none;overflow:hidden;padding:0;background:var(--paper);color:var(--ink)}.slide.active{display:block;animation:slideIn .55s cubic-bezier(.2,.75,.2,1) both}.slide.dark{background:var(--navy);color:white}
@keyframes slideIn{from{opacity:0;transform:scale(1.025)}to{opacity:1;transform:scale(1)}}
.brand{position:absolute;z-index:2;left:83px;top:42px;display:flex;gap:15px;align-items:center}.brand svg{width:47px;height:47px}.brand span{display:flex;flex-direction:column;gap:1px}.brand strong{font-size:24px;font-weight:600;line-height:1}.brand small{font:400 11px/1.2 'IBM Plex Mono',monospace;color:var(--muted)}.dark .brand small{color:#a9bbd2}
.footer{position:absolute;left:84px;right:84px;bottom:29px;display:flex;justify-content:space-between;font:400 12px 'IBM Plex Mono',monospace;color:var(--muted)}.footer-dark{color:#aabdd6}
.blue-rule{position:absolute;left:86px;top:182px;width:7px;height:316px;background:var(--blue);transform-origin:top;transform:scaleY(0)}.active .blue-rule{animation:ruleGrow .7s .15s cubic-bezier(.2,.8,.2,1) forwards}@keyframes ruleGrow{to{transform:scaleY(1)}}
[data-enter]{opacity:0;transform:translateY(22px)}.active [data-enter]{animation:rise .58s calc(.13s + var(--d,0s)) cubic-bezier(.2,.8,.2,1) both}@keyframes rise{to{opacity:1;transform:translateY(0)}}
h1,h2,h3,p{margin:0}h1,h2{font-weight:300;letter-spacing:-.022em}h1{font-size:72px;line-height:1.08}h2{font-size:62px;line-height:1.08}.lead{font-size:26px;line-height:1.25;color:var(--light)}.sub{font-size:24px;color:var(--muted)}
.opening h1{position:absolute;left:113px;top:225px;width:1030px}.opening .lead{position:absolute;left:113px;top:526px;width:900px}
.light-head{position:absolute;left:82px;top:145px}.light-head .sub{margin-top:3px}
.evidence-grid{position:absolute;left:82px;top:284px;display:grid;grid-template-columns:repeat(4,259px);gap:22px}.tile{height:319px;background:var(--tile);padding:30px 28px}.tile svg{width:42px;height:42px}.tile h3{font-size:28px;font-weight:600;margin-top:76px;line-height:1.1}.tile p{font-size:21px;color:var(--muted);line-height:1.3;margin-top:30px}
.sample-note{position:absolute;left:83px;top:628px;font:400 13px 'IBM Plex Mono',monospace;color:var(--muted)}.sim-tag{position:absolute;right:84px;top:63px;font:400 14px 'IBM Plex Mono',monospace;color:var(--blue)}
.dark-head{position:absolute;left:83px;top:153px}.logic{position:absolute;left:83px;top:277px;width:1114px}.logic-row{display:grid;grid-template-columns:415px 1fr;min-height:124px;padding-top:7px;border-bottom:1px solid #30445f}.logic-row:last-child{border-bottom:0}.logic-row strong{font-size:31px;font-weight:400}.logic-row span{font-size:23px;color:#b9c9dd;line-height:1.25}
.decision-head{position:absolute;left:82px;top:146px}.identity{position:absolute;left:83px;top:265px;width:405px;height:355px;padding:30px;background:var(--tile)}.identity svg{width:48px;height:48px}.identity .id{font:400 19px 'IBM Plex Mono',monospace;color:var(--blue);margin-top:62px}.identity h3{font-size:43px;font-weight:300;margin-top:29px}.identity p{font-size:21px;color:var(--muted);margin-top:29px}.steps{position:absolute;left:544px;top:280px;width:652px}.step{display:grid;grid-template-columns:60px 1fr;padding:0 0 21px;margin-bottom:16px;border-bottom:1px solid #dce1e8;min-height:99px}.step:last-child{border-bottom:0}.step b{font:400 17px 'IBM Plex Mono',monospace;color:var(--blue)}.step strong{font-size:27px;font-weight:600}.step p{font-size:21px;color:var(--muted);margin-top:11px}
.update-head{position:absolute;left:82px;top:149px}.update-grid{position:absolute;left:82px;top:305px;display:grid;grid-template-columns:repeat(3,354px);gap:26px}.update-grid .tile{height:285px}.update-grid em{font:400 22px 'IBM Plex Mono',monospace;color:var(--blue);font-style:normal}.update-grid h3{font-size:29px;margin-top:68px}.update-grid p{margin-top:24px}
.close .blue-rule{top:185px;height:345px;left:82px}.close h1{position:absolute;left:113px;top:241px;width:530px;font-size:63px}.close .lead{position:absolute;left:113px;top:495px;width:530px;font-size:24px}.car{position:absolute;left:673px;top:186px;width:582px;height:360px;object-fit:cover}.credit{position:absolute;right:47px;bottom:86px;color:#8fa5be;font-size:12px}
.progress{position:absolute;z-index:10;left:0;bottom:0;height:4px;background:var(--blue);transition:width .45s ease}.nav{position:absolute;z-index:11;right:26px;top:24px;display:flex;gap:7px;opacity:0;transition:opacity .2s}.deck:hover .nav,.nav:focus-within{opacity:1}.nav button{width:35px;height:35px;border:1px solid #7e9abb55;background:#0b1422cc;color:#fff;font:24px Barlow,Arial;cursor:pointer}.nav button:hover{background:var(--blue)}
@media(prefers-reduced-motion:reduce){.slide.active,.active [data-enter],.active .blue-rule{animation:none!important;opacity:1!important;transform:none!important}.progress{transition:none}}
</style></head><body><main class="deck" aria-label="BMW Product Intelligence pitch deck">
<section class="slide dark opening active" aria-label="Slide 1 of 6">${mark(true)}<div class="blue-rule"></div><h1 data-enter>Every requirement<br>begins with the customer</h1><p class="lead" data-enter style="--d:.15s">Agents read and draft. The product manager decides.</p>${footer(1,true)}</section>
<section class="slide" aria-label="Slide 2 of 6">${mark()}<div class="light-head"><h2 data-enter>The G60 / US evidence</h2><p class="sub" data-enter style="--d:.1s">The pilot can explain its sample before asking for a decision.</p></div><div class="evidence-grid">
<article class="tile" data-enter style="--d:.12s">${icon(0)}<h3><span data-count="4365">4,365</span> records</h3><p>Actual G60 / US feedback in the prototype</p></article>
<article class="tile" data-enter style="--d:.2s">${icon(1)}<h3><span data-count="72.7">72.7</span>%</h3><p>Of records come from one source</p></article>
<article class="tile" data-enter style="--d:.28s">${icon(2)}<h3>Priority</h3><p>A deterministic score with a visible breakdown</p></article>
<article class="tile" data-enter style="--d:.36s">${icon(3)}<h3>Evidence grade</h3><p>Source strength shown separately from priority</p></article></div><span class="sample-note">SAMPLE COUNTS, NOT MARKET SHARE</span>${footer(2)}</section>
<section class="slide dark" aria-label="Slide 3 of 6">${mark(true)}<div class="dark-head"><h2 data-enter>Priority and proof stay separate</h2></div><div class="logic"><div class="logic-row" data-enter style="--d:.12s"><strong>Priority score</strong><span>Code applies the declared rubric to the same inputs</span></div><div class="logic-row" data-enter style="--d:.24s"><strong>Evidence grade</strong><span>Source quality remains visible even when priority is high</span></div><div class="logic-row" data-enter style="--d:.36s"><strong>Customer words</strong><span>A requirement opens the workbook, sheet and source row</span></div></div>${footer(3,true)}</section>
<section class="slide" aria-label="Slide 4 of 6">${mark()}<div class="decision-head"><h2 data-enter>The PM owns the decision</h2></div><article class="identity" data-enter style="--d:.12s">${icon(0)}<div class="id">REQ-G60-US-001</div><h3>Charging</h3><p>G60 / i5 M60 / US</p></article><div class="steps"><div class="step" data-enter style="--d:.18s"><b>01</b><div><strong>AI draft</strong><p>A linked proposal the PM can inspect</p></div></div><div class="step" data-enter style="--d:.3s"><b>02</b><div><strong>PM assumption</strong><p>An unsupported target stays labelled</p></div></div><div class="step" data-enter style="--d:.42s"><b>03</b><div><strong>Approval record</strong><p>The PM edits, explains and approves a version</p></div></div></div>${footer(4)}</section>
<section class="slide" aria-label="Slide 5 of 6">${mark()}<span class="sim-tag">SIMULATED UPDATE</span><div class="update-head"><h2 data-enter>Only affected decisions return</h2><p class="sub" data-enter style="--d:.1s">New evidence arrives during the two-year development cycle.</p></div><div class="update-grid"><article class="tile" data-enter style="--d:.15s"><em>01</em><h3>New feedback</h3><p>A new batch enters the same evidence pipeline</p></article><article class="tile" data-enter style="--d:.28s"><em>02</em><h3>Charging returns</h3><p>The affected requirement reopens beside its approved version</p></article><article class="tile" data-enter style="--d:.41s"><em>03</em><h3>PM review</h3><p>The PM sees the delta and decides whether to update</p></article></div>${footer(5)}</section>
<section class="slide dark close" aria-label="Slide 6 of 6">${mark(true)}<div class="blue-rule"></div><h1 data-enter>Agents read.<br>The PM decides.</h1><p class="lead" data-enter style="--d:.15s">Every requirement is one click from the customer’s own words.</p><img class="car" data-enter style="--d:.25s" src="${carUri}" alt="BMW i5 M60 artist model"><span class="credit">2023 BMW i5 M60 by Nazh Design / Sketchfab · CC BY 4.0</span>${footer(6,true)}</section>
<div class="progress" id="progress"></div><nav class="nav" aria-label="Slide controls"><button id="prev" aria-label="Previous slide">‹</button><button id="next" aria-label="Next slide">›</button></nav>
</main><script>
const slides=[...document.querySelectorAll('.slide')];let current=0;let frame=0;
function fit(){document.querySelector('.deck').style.setProperty('--scale',Math.min(innerWidth/1280,innerHeight/720))}fit();addEventListener('resize',fit);
function countOn(slide){cancelAnimationFrame(frame);if(matchMedia('(prefers-reduced-motion:reduce)').matches)return;const nodes=[...slide.querySelectorAll('[data-count]')];const start=performance.now();function tick(now){const p=Math.min((now-start)/900,1);const eased=1-Math.pow(1-p,3);nodes.forEach(n=>{const goal=Number(n.dataset.count);const value=goal*eased;n.textContent=goal%1?value.toFixed(1):Math.round(value).toLocaleString('en-US')});if(p<1)frame=requestAnimationFrame(tick)}frame=requestAnimationFrame(tick)}
function show(i){if(i<0||i>=slides.length)return;slides[current].classList.remove('active');current=i;void slides[current].offsetWidth;slides[current].classList.add('active');document.getElementById('progress').style.width=((current+1)/slides.length*100)+'%';countOn(slides[current]);}
document.getElementById('next').onclick=()=>show(current+1);document.getElementById('prev').onclick=()=>show(current-1);
addEventListener('keydown',e=>{if(['ArrowRight',' ','PageDown','Enter'].includes(e.key)){e.preventDefault();show(current+1)}else if(['ArrowLeft','PageUp','Backspace'].includes(e.key)){e.preventDefault();show(current-1)}else if(e.key==='Home'){show(0)}else if(e.key==='End'){show(slides.length-1)}else if(e.key.toLowerCase()==='f'){document.fullscreenElement?document.exitFullscreen():document.documentElement.requestFullscreen()}else if(e.key.toLowerCase()==='r'){show(current)}});
show(0);
</script></body></html>`;
await fs.writeFile(out, html);
console.log(out);
