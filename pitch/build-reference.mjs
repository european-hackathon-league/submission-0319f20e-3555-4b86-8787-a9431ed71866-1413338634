import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const b64 = async file => (await fs.readFile(path.join(here, file))).toString('base64');
const source = await fs.readFile(path.join(here, 'output/pitch-bmw-motion.html'), 'utf8');
const texture = `data:image/png;base64,${await b64('assets/invertix-copper-texture.png')}`;
const serif = `data:font/ttf;base64,${await b64('assets/fonts/instrument-serif-regular.ttf')}`;
const sans = `data:font/ttf;base64,${await b64('assets/fonts/instrument-sans-400.ttf')}`;
const sansMedium = `data:font/ttf;base64,${await b64('assets/fonts/instrument-sans-500.ttf')}`;

const css = `
@font-face{font-family:'Instrument Serif';font-style:normal;font-weight:400;src:url(${serif}) format('truetype')}
@font-face{font-family:'Instrument Sans';font-style:normal;font-weight:400;src:url(${sans}) format('truetype')}
@font-face{font-family:'Instrument Sans';font-style:normal;font-weight:500;src:url(${sansMedium}) format('truetype')}
:root{--navy:#111110;--ink:#181918;--blue:#d17442;--paper:#fdfdfb;--tile:#f1f2ef;--muted:#60625f;--light:#f5e5da}
body{font-family:'Instrument Sans',sans-serif}
.deck{background:var(--paper)}
.slide.dark{background:#111110}
.slide.opening,.slide.close{background:linear-gradient(90deg,#180e0b7a,#54291322),url(${texture}) center center/cover no-repeat;color:#fff}
.reference-brand{position:absolute;z-index:2;left:83px;top:57px;font:500 16px/1 'Instrument Sans',sans-serif;letter-spacing:.07em;color:#444744}
.reference-brand span{font-weight:400;color:#7c817d}
.dark .reference-brand{color:#f8eee6}.dark .reference-brand span{color:#efcbb5}
.footer{font-family:'Instrument Sans',sans-serif;letter-spacing:.1em;color:#777b77}
.footer-dark{color:#f2d9c8}
h1,h2{font-family:'Instrument Serif',serif;font-weight:400;letter-spacing:-.025em}
h1{font-size:83px;line-height:1.03}h2{font-size:67px;line-height:1.06}
.opening h1{left:85px;top:211px;width:1100px}.opening .lead{left:87px;top:510px;width:970px;font:400 27px/1.25 'Instrument Sans',sans-serif;color:#fff2e9}
.opening .blue-rule,.close .blue-rule{display:none}
.light-head{top:111px}.light-head .sub{margin-top:10px}
.sub{font-size:23px;color:#686b67}
.evidence-grid .tile,.identity,.update-grid .tile{background:var(--tile)}
.tile h3{font:500 28px/1.1 'Instrument Sans',sans-serif}.tile p{font:400 20px/1.3 'Instrument Sans',sans-serif;color:#60645f}
.sample-note{font-family:'Instrument Sans',sans-serif;font-size:13px;letter-spacing:.08em}
.dark-head{top:115px}.logic{top:255px}.logic-row{border-color:#454545}
.logic-row strong{font:400 40px/1.1 'Instrument Serif',serif}.logic-row span{font:400 22px/1.3 'Instrument Sans',sans-serif;color:#c8c9c6}
.decision-head{top:109px}.identity .id{color:#a75a35;font:500 17px 'Instrument Sans',sans-serif;letter-spacing:.02em}
.identity h3{font:400 50px/1 'Instrument Serif',serif}.identity p{font-size:21px}
.step b{color:#a75a35;font:500 17px 'Instrument Sans',sans-serif}
.step strong{font:500 25px 'Instrument Sans',sans-serif}.step p{font-size:21px}
.update-head{top:111px}.sim-tag{color:#ad603a;font-family:'Instrument Sans',sans-serif;letter-spacing:.07em}
.update-grid em{color:#ad603a;font-family:'Instrument Sans',sans-serif}
.close h1{left:85px;top:230px;width:1000px;font-size:89px}.close .lead{left:87px;top:506px;width:1020px;font-size:27px;color:#fff2e9}
.close .car,.close .credit{display:none}
.progress{background:#d17442}
.toolbar{font-family:'Instrument Sans',sans-serif}
.editing [contenteditable=true]{outline-color:#d17442}.editing [contenteditable=true]:focus{outline-color:#d17442;background:#d1744225}
`;

const output = source
  .replace('<title>BMW Product Intelligence · Pitch</title>', '<title>Reference Template · Pitch</title>')
  .replace('aria-label="BMW Product Intelligence pitch deck"', 'aria-label="Reference style pitch template"')
  .replace(/<div class="brand">[\s\S]*?<\/div>/g, '<div class="reference-brand">PRODUCT INTELLIGENCE <span>/ G60 · US</span></div>')
  .replace(/<img class="car"[^>]*>/, '')
  .replace(/<span class="credit">[^<]*<\/span>/, '')
  .replace(/@font-face\{font-family:'(?:Barlow|IBM Plex Mono)'[^}]*\}/g, '')
  .replace('</style>', `${css}\n</style>`);
await fs.writeFile(path.join(here, 'output/pitch-reference-template.html'), output);
console.log(path.join(here, 'output/pitch-reference-template.html'));
