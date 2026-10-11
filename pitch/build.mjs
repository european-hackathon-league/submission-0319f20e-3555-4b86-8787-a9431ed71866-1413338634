import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import sharp from 'sharp';
import JSZip from 'jszip';
import { Presentation, PresentationFile } from '@oai/artifact-tool';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.dirname(here);
const buildDir = path.join(here, '.build');
const outDir = path.join(here, 'output');
const skillDir = '/Users/troy/.codex/plugins/cache/openai-primary-runtime/presentations/26.1007.11041/skills/presentations';
const pythonExecutable = '/Users/troy/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3';
const { finalizePresentation } = await import(pathToFileURL(path.join(skillDir, 'container_tools/artifact_tool_utils.mjs')).href);

await fs.mkdir(buildDir, { recursive: true });
await fs.mkdir(outDir, { recursive: true });

const carCrop = path.join(buildDir, 'g60-car.webp');
await sharp(path.join(root, 'assets/vehicles/g60-us/poster.webp'))
  .extract({ left: 365, top: 225, width: 1035, height: 610 })
  .webp({ quality: 92 })
  .toFile(carCrop);

const referenceIcons = await Promise.all([1, 2, 3, 4].map(i => fs.readFile(path.join(here, `assets/reference-icon-${i}.svg`), 'utf8')));
const logoWhite = await fs.readFile(path.join(root, 'web/public/brand/bmw-white.svg'), 'utf8');
const logoGrey = await fs.readFile(path.join(root, 'web/public/brand/bmw-grey.svg'), 'utf8');
const referenceUrl = 'https://www.invertix.ai/security';
const planPath = 'notes/pitch-plan.md';
const licenseUrl = 'https://creativecommons.org/licenses/by/4.0/';
const carCredit = '2023 BMW i5 M60 by Nazh Design / Sketchfab · CC BY 4.0';

const themes = {
  reference: {
    name: 'reference',
    titleFont: 'Baskerville', bodyFont: 'Helvetica Neue', monoFont: 'Helvetica Neue',
    paper: '#FFFFFF', tile: '#F5F5F5', ink: '#202020', muted: '#626262',
    dark: '#0B0B0B', accent: '#E97632', line: '#353535',
    output: 'pitch-reference-template.pptx',
  },
  bmw: {
    name: 'bmw',
    titleFont: 'Barlow', bodyFont: 'Barlow', monoFont: 'IBM Plex Mono',
    paper: '#F4F5F7', tile: '#EDEFF3', ink: '#171B21', muted: '#657080',
    dark: '#0B1422', accent: '#1C69D4', line: '#30445F',
    output: 'pitch-bmw-dashboard-animated.pptx',
  },
};

function shape(slide, x, y, w, h, fill, name, line = 'none') {
  return slide.shapes.add({
    geometry: 'rect', name,
    position: { left: x, top: y, width: w, height: h },
    fill,
    line: { style: 'solid', fill: line, width: line === 'none' ? 0 : 1 },
  });
}
function text(slide, value, x, y, w, h, opts = {}) {
  const box = slide.shapes.add({
    geometry: 'textbox', name: opts.name || value.slice(0, 28),
    position: { left: x, top: y, width: w, height: h },
    fill: 'none', line: { style: 'solid', fill: 'none', width: 0 },
  });
  box.text = value;
  box.text.style = {
    typeface: opts.font || 'Helvetica Neue',
    fontSize: opts.size || 22,
    bold: opts.bold || false,
    color: opts.color || '#202020',
    alignment: opts.align || 'left',
    verticalAlignment: opts.valign || 'top',
    wrap: 'square',
    autoFit: 'none',
    insets: 0,
    lineSpacing: opts.leading || 1.1,
  };
  return box;
}
function icon(slide, svg, x, y, size, color) {
  const colored = svg.replaceAll('#171b21', color).replaceAll('currentColor', color);
  return slide.images.add({ svg: colored, alt: 'Thin line icon', position: { left: x, top: y, width: size, height: size } });
}
function logo(slide, theme, onDark, x = 83, y = 42) {
  if (theme.name !== 'bmw') return;
  slide.images.add({ svg: onDark ? logoWhite : logoGrey, alt: 'BMW dashboard logo', position: { left: x, top: y, width: 47, height: 47 } });
  text(slide, 'BMW', x + 62, y + 3, 180, 27, { font: theme.bodyFont, size: 24, bold: true, color: onDark ? '#F5F8FC' : theme.ink });
  text(slide, 'PRODUCT INTELLIGENCE', x + 63, y + 29, 220, 18, { font: theme.monoFont, size: 11, color: onDark ? '#A9BBD2' : theme.muted });
}
function kicker(slide, theme, value, onDark = false, y = 66) {
  if (theme.name === 'bmw') return;
  text(slide, value, 82, y, 660, 27, { font: theme.bodyFont, size: 15, bold: true, color: onDark ? '#F5E7DF' : theme.muted });
}
function footer(slide, theme, page, dark = false) {
  if (theme.name === 'bmw') {
    text(slide, `G60 / US`, 84, 668, 200, 22, { font: theme.monoFont, size: 12, color: dark ? '#AABDD6' : theme.muted });
    text(slide, String(page).padStart(2, '0'), 1155, 668, 40, 22, { font: theme.monoFont, size: 12, color: dark ? '#AABDD6' : theme.muted, align: 'right' });
  }
}
function notes(slide, body, extra = '') {
  slide.speakerNotes.text = `${body}\n\nSources: ${planPath} (draft, 11 October 2026); ${referenceUrl} (visual reference).${extra ? ` ${extra}` : ''}`;
}

async function addImage(slide, file, x, y, w, h, alt, fit = 'cover') {
  const bytes = await fs.readFile(file);
  const contentType = file.endsWith('.webp') ? 'image/webp' : 'image/png';
  slide.images.add({ blob: bytes, contentType, alt, fit, position: { left: x, top: y, width: w, height: h } });
}

async function build(theme) {
  const pres = Presentation.create({ slideSize: { width: 1280, height: 720 } });
  const isBmw = theme.name === 'bmw';

  // 01: opening. Keep the central promise large enough to read from the room.
  {
    const slide = pres.slides.add();
    slide.background.fill = theme.dark;
    if (isBmw) {
      shape(slide, 86, 182, 7, 316, theme.accent, 'blue accent rule');
      logo(slide, theme, true);
    } else {
      await addImage(slide, path.join(here, 'assets/invertix-copper-texture.png'), 0, 0, 1280, 720, 'Copper grain inspired by Invertix security page');
      shape(slide, 0, 0, 1280, 84, '#21110D', 'top dark band');
      kicker(slide, theme, 'PRODUCT INTELLIGENCE / G60 · US', true, 43);
    }
    const title = isBmw ? 'Every requirement\nbegins with the customer' : 'Every requirement begins\nwith the customer';
    text(slide, title, isBmw ? 113 : 84, isBmw ? 210 : 213, isBmw ? 1080 : 1030, 245,
      { font: theme.titleFont, size: isBmw ? 71 : 70, color: '#FFFFFF', leading: 1.08 });
    text(slide, 'Agents read and draft. The product manager decides.', isBmw ? 113 : 86, 518, isBmw ? 540 : 820, 70,
      { font: theme.bodyFont, size: 26, color: isBmw ? '#C9D8EB' : '#F7E6DC', leading: 1.18 });
    footer(slide, theme, 1, true);
    notes(slide, 'Opening after the 30-second trailer. State the product promise once, then move into the live G60 / US story.', isBmw ? ` Vehicle image: ${carCredit}. ${licenseUrl}` : ' Copper texture cropped from the visual reference page.');
  }

  // 02: truthful data scope in the reference page's four-square card language.
  {
    const slide = pres.slides.add();
    slide.background.fill = theme.paper;
    logo(slide, theme, false);
    kicker(slide, theme, 'THE G60 / US PILOT');
    text(slide, 'The G60 / US evidence', 82, isBmw ? 127 : 92, 1110, 86,
      { font: theme.titleFont, size: isBmw ? 62 : 59, color: theme.ink });
    text(slide, 'The pilot can explain its sample before asking for a decision.', 84, isBmw ? 202 : 174, 1090, 46,
      { font: theme.bodyFont, size: 24, color: theme.muted });
    const cards = [
      ['4,365 records', 'Actual G60 / US feedback in the prototype'],
      ['72.7%', 'Of records come from one source'],
      ['Priority', 'A deterministic score with a visible breakdown'],
      ['Evidence grade', 'Source strength shown separately from priority'],
    ];
    const xs = [82, 363, 644, 925];
    for (let i = 0; i < 4; i++) {
      const x = xs[i];
      shape(slide, x, 284, 259, 319, theme.tile, `evidence tile ${i + 1}`);
      icon(slide, referenceIcons[i], x + 30, 314, 42, theme.ink);
      text(slide, cards[i][0], x + 28, 410, 205, 44,
        { font: theme.bodyFont, size: i < 2 ? 28 : 26, color: theme.ink, bold: isBmw });
      text(slide, cards[i][1], x + 28, 468, 205, 100,
        { font: theme.bodyFont, size: 20, color: theme.muted, leading: 1.25 });
    }
    text(slide, 'SAMPLE COUNTS, NOT MARKET SHARE', 83, 628, 550, 22,
      { font: theme.monoFont, size: 13, color: theme.muted });
    footer(slide, theme, 2);
    notes(slide, 'The record count and source concentration are sample facts, not market prevalence. State that clearly before discussing the charging requirement. The priority score and evidence grade answer different questions.');
  }

  // 03: dark, rule-led section like the reference page's protection section.
  {
    const slide = pres.slides.add();
    slide.background.fill = theme.dark;
    logo(slide, theme, true);
    kicker(slide, theme, 'DECISION LOGIC', true);
    text(slide, 'Priority and proof stay separate', 83, isBmw ? 141 : 86, 1100, 92,
      { font: theme.titleFont, size: isBmw ? 61 : 58, color: '#FFFFFF' });
    const rows = [
      ['Priority score', 'Code applies the declared rubric to the same inputs'],
      ['Evidence grade', 'Source quality remains visible even when priority is high'],
      ['Customer words', 'A requirement opens the workbook, sheet and source row'],
    ];
    const start = isBmw ? 276 : 238;
    rows.forEach((r, i) => {
      const y = start + i * 124;
      if (i) shape(slide, 83, y - 24, 1114, 1, theme.line, `divider ${i}`);
      text(slide, r[0], 84, y, 380, 45, { font: theme.titleFont, size: 31, color: '#F7F9FC' });
      text(slide, r[1], 501, y + 4, 675, 74, { font: theme.bodyFont, size: 23, color: isBmw ? '#B9C9DD' : '#AEB0B1', leading: 1.15 });
    });
    footer(slide, theme, 3, true);
    notes(slide, 'Open REQ-G60-US-001, the charging requirement. Show its evidence grade and score as separate signals. Click into the source trace and briefly show disagreeing evidence. Do not imply sample counts represent market share.');
  }

  // 04: the actual approval boundary, with the source-to-decision chain.
  {
    const slide = pres.slides.add();
    slide.background.fill = theme.paper;
    logo(slide, theme, false);
    kicker(slide, theme, 'ONE CHARGING REQUIREMENT');
    text(slide, 'The PM owns the decision', 82, isBmw ? 138 : 98, 1110, 86,
      { font: theme.titleFont, size: isBmw ? 62 : 59, color: theme.ink });
    shape(slide, 83, 265, 405, 355, theme.tile, 'requirement identity square');
    icon(slide, referenceIcons[0], 112, 295, 48, theme.ink);
    text(slide, 'REQ-G60-US-001', 112, 403, 320, 30,
      { font: theme.monoFont, size: 19, color: isBmw ? theme.accent : theme.muted });
    text(slide, 'Charging', 112, 450, 330, 64,
      { font: theme.titleFont, size: 43, color: theme.ink });
    text(slide, 'G60 / i5 M60 / US', 113, 547, 300, 38,
      { font: theme.bodyFont, size: 21, color: theme.muted });
    const items = [
      ['01', 'AI draft', 'A linked proposal the PM can inspect'],
      ['02', 'PM assumption', 'An unsupported target stays labelled'],
      ['03', 'Approval record', 'The PM edits, explains and approves a version'],
    ];
    items.forEach((r, i) => {
      const y = 280 + i * 116;
      if (i) shape(slide, 544, y - 20, 652, 1, isBmw ? '#DCE1E8' : '#DEDEDE', `decision divider ${i}`);
      text(slide, r[0], 548, y + 2, 42, 28, { font: theme.monoFont, size: 17, color: isBmw ? theme.accent : theme.muted });
      text(slide, r[1], 608, y, 555, 37, { font: theme.bodyFont, size: 27, color: theme.ink, bold: isBmw });
      text(slide, r[2], 608, y + 44, 555, 47, { font: theme.bodyFont, size: 21, color: theme.muted });
    });
    footer(slide, theme, 4);
    notes(slide, 'The AI proposes a target labelled PM assumption because the feedback does not justify the number. Only the PM can approve. An edit and reason create a new immutable requirement version linked to its score and audit event.');
  }

  // 05: the rolling review loop, explicitly marked as a simulated update.
  {
    const slide = pres.slides.add();
    slide.background.fill = theme.paper;
    logo(slide, theme, false);
    kicker(slide, theme, 'SIMULATED UPDATE');
    if (isBmw) text(slide, 'SIMULATED UPDATE', 880, 63, 314, 22,
      { font: theme.monoFont, size: 14, color: theme.accent, align: 'right' });
    text(slide, 'Only affected decisions return', 82, isBmw ? 140 : 96, 1110, 87,
      { font: theme.titleFont, size: isBmw ? 61 : 57, color: theme.ink });
    text(slide, 'New evidence arrives during the two-year development cycle.', 84, isBmw ? 219 : 176, 1070, 40,
      { font: theme.bodyFont, size: 24, color: theme.muted });
    const updateCards = [
      ['New feedback', 'A new batch enters the same evidence pipeline'],
      ['Charging returns', 'The affected requirement reopens beside its approved version'],
      ['PM review', 'The PM sees the delta and decides whether to update'],
    ];
    const xs = [82, 462, 842];
    updateCards.forEach((r, i) => {
      const x = xs[i];
      shape(slide, x, 305, 354, 285, theme.tile, `update tile ${i + 1}`);
      text(slide, `0${i + 1}`, x + 29, 335, 70, 35, { font: theme.monoFont, size: 22, color: isBmw ? theme.accent : theme.muted });
      text(slide, r[0], x + 28, 417, 295, 44, { font: theme.bodyFont, size: 29, bold: isBmw, color: theme.ink });
      text(slide, r[1], x + 28, 474, 297, 89, { font: theme.bodyFont, size: 21, color: theme.muted, leading: 1.2 });
    });
    footer(slide, theme, 5);
    notes(slide, 'The update batch is simulated because the supplied feedback has no dates. Demonstrate the approved baseline next to the proposed change only if that path has passed the demo preflight. The intended review scope is the affected charging decision, not a full re-review.');
  }

  // 06: close. A single decisive line, plus enterprise fit in speaker notes.
  {
    const slide = pres.slides.add();
    slide.background.fill = theme.dark;
    if (isBmw) {
      await addImage(slide, carCrop, 673, 186, 582, 360, 'BMW i5 M60 artist model');
      logo(slide, theme, true);
      shape(slide, 82, 185, 7, 345, theme.accent, 'blue closing rule');
    } else {
      await addImage(slide, path.join(here, 'assets/invertix-copper-texture.png'), 0, 0, 1280, 720, 'Copper grain inspired by Invertix security page');
      shape(slide, 0, 0, 1280, 86, '#21110D', 'closing top dark band');
      kicker(slide, theme, 'THE PRODUCT MANAGER DECIDES', true, 45);
    }
    text(slide, isBmw ? 'Agents read.\nThe PM decides.' : 'Agents do the reading.\nThe PM makes the decision.', isBmw ? 113 : 83, isBmw ? 236 : 220, isBmw ? 530 : 1080, 220,
      { font: theme.titleFont, size: isBmw ? 63 : 66, color: '#FFFFFF', leading: 1.09 });
    text(slide, 'Every requirement is one click from the customer’s own words.', isBmw ? 113 : 86, isBmw ? 492 : 518, isBmw ? 530 : 960, 62,
      { font: theme.bodyFont, size: isBmw ? 24 : 26, color: isBmw ? '#C8D7E9' : '#F7E7DE', leading: 1.16 });
    if (isBmw) text(slide, carCredit, 753, 615, 480, 20, { font: theme.bodyFont, size: 12, color: '#8FA5BE', align: 'right' });
    footer(slide, theme, 6, true);
    notes(slide, 'Close with the one sentence. The pipeline is scoped by vehicle and market. Governed operations are exposed through MCP. Decided requirements are intended to move upstream of Codebeamer, without claiming a live Codebeamer integration. The live demo remains the proof.', isBmw ? ` Vehicle image: ${carCredit}. ${licenseUrl}` : ' Copper texture cropped from the visual reference page.');
  }

  const tag = theme.name;
  for (let i = 0; i < pres.slides.items.length; i++) {
    const png = await pres.export({ slide: pres.slides.items[i], format: 'png', scale: 1 });
    await fs.writeFile(path.join(buildDir, `${tag}-${String(i+1).padStart(2,'0')}.png`), new Uint8Array(await png.arrayBuffer()));
  }
  const candidatePath = path.join(buildDir, `${tag}-candidate.pptx`);
  await (await PresentationFile.exportPptx(pres)).save(candidatePath);
  if (isBmw) {
    // PowerPoint gets click-driven fade transitions; the HTML version carries staged object motion.
    const zip = await JSZip.loadAsync(await fs.readFile(candidatePath));
    for (let i = 1; i <= pres.slides.items.length; i++) {
      const entry = `ppt/slides/slide${i}.xml`;
      const xml = await zip.file(entry).async('string');
      zip.file(entry, xml.replace('</p:sld>', '<p:transition spd="fast" advClick="1"><p:fade /></p:transition></p:sld>'));
    }
    await fs.writeFile(candidatePath, await zip.generateAsync({ type: 'nodebuffer', compression: 'DEFLATE' }));
  }
  const finalPath = path.join(outDir, theme.output);
  const result = await finalizePresentation({
    explicitTotalSlideCount: 6,
    requiredNativeTableOwnerSlides: [],
    requiredNativeChartOwnerSlides: [],
    workspaceDir: root,
    candidatePath,
    finalPath,
    pythonExecutable,
    integrityValidatorPath: path.join(skillDir, 'container_tools/inspect_presentation_package_integrity.py'),
    layoutValidatorPath: path.join(skillDir, 'container_tools/inspect_presentation_layout_geometry.py'),
    layoutArgs: [ '--expected-slide-size-emu', '12192000,6858000', '--validate-heading-fit' ],
    fontPolicy: { basis: 'design', families: isBmw ? ['Barlow', 'IBM Plex Mono'] : [theme.titleFont, theme.bodyFont] },
    verifyArtifactToolImport: true,
    receiptPath: path.join(buildDir, `${tag}-${process.env.PITCH_BUILD_ID || 'final'}.validation.json`),
  });
  console.log(`${tag}: ${finalPath}`);
  console.log(JSON.stringify(result));
}

for (const theme of Object.values(themes)) {
  if (!process.env.PITCH_VARIANT || process.env.PITCH_VARIANT === theme.name) await build(theme);
}
