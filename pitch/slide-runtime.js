const slides = [...document.querySelectorAll('.slide')];
const deck = document.querySelector('.deck');
const editable = [...document.querySelectorAll('.slide h1, .slide h2, .slide h3, .slide p, .slide .logic-row strong, .slide .logic-row span, .slide .id, .slide .step b, .slide .step strong, .slide .update-grid em, .slide .sample-note, .slide .sim-tag, .slide .credit, .slide [data-edit]')];
const stageCount = slides.filter(slide => !slide.hasAttribute('data-backup')).length;
let current = 0;
let editing = false;
let timerStart = null;
let timerHandle = null;

function fit() {
  deck.style.setProperty('--scale', Math.min(innerWidth / 1280, innerHeight / 720));
}
fit();
addEventListener('resize', fit);

function label(index) {
  return slides[index].dataset.label || `${index + 1} / ${slides.length}`;
}

function film(slide) {
  return slide.querySelector('video.film');
}

function show(index) {
  if (index < 0 || index >= slides.length) return;
  const leaving = film(slides[current]);
  if (leaving && index !== current) leaving.pause();
  slides[current].classList.remove('active');
  current = index;
  void slides[current].offsetWidth;
  slides[current].classList.add('active');
  const position = slides[current].hasAttribute('data-backup') ? 1 : Math.min(current + 1, stageCount) / stageCount;
  document.getElementById('progress').style.width = `${position * 100}%`;
  document.getElementById('page-count').textContent = label(current);
  history.replaceState(null, '', `#${current + 1}`);
}

// On a film slide, the first "next" starts the film; the deck advances when it ends.
function next() {
  const video = film(slides[current]);
  if (video && video.readyState > 0 && video.paused && !video.ended) {
    video.play();
    return;
  }
  show(current + 1);
}

function toggleTimer(force) {
  const element = document.getElementById('timer');
  if (!element) return;
  const on = force ?? !timerHandle;
  clearInterval(timerHandle);
  timerHandle = null;
  document.body.classList.toggle('timing', on);
  if (!on) { element.hidden = true; timerStart = null; return; }
  timerStart = timerStart || Date.now();
  element.hidden = false;
  const tick = () => {
    const seconds = Math.floor((Date.now() - timerStart) / 1000);
    element.textContent = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
  };
  tick();
  timerHandle = setInterval(tick, 500);
}

function setEditing(value) {
  editing = value;
  document.body.classList.toggle('editing', editing);
  editable.forEach(element => { element.contentEditable = editing ? 'true' : 'false'; });
  document.getElementById('edit').textContent = editing ? 'Done editing' : 'Edit text';
  if (editing) {
    document.querySelectorAll('[data-count]').forEach(element => element.removeAttribute('data-count'));
  } else {
    document.activeElement?.blur();
  }
}

function saveHtml() {
  const copy = document.documentElement.cloneNode(true);
  copy.querySelector('body').classList.remove('editing');
  copy.querySelectorAll('[contenteditable]').forEach(element => element.removeAttribute('contenteditable'));
  copy.querySelectorAll('.slide').forEach((slide, index) => slide.classList.toggle('active', index === 0));
  copy.querySelector('#page-count').textContent = label(0);
  const timer = copy.querySelector('#timer');
  if (timer) timer.hidden = true;
  const blob = new Blob([`<!doctype html>\n${copy.outerHTML}`], {type: 'text/html;charset=utf-8'});
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = document.title.includes('Reference') ? 'pitch-reference-edited.html'
    : document.title.includes('Final') ? 'pitch-final-edited.html' : 'pitch-bmw-edited.html';
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

slides.forEach((slide, index) => {
  const video = film(slide);
  if (!video) return;
  video.addEventListener('loadeddata', () => slide.classList.add('has-film'));
  video.addEventListener('ended', () => { if (current === index) show(index + 1); });
});

document.getElementById('next').onclick = next;
document.getElementById('prev').onclick = () => show(current - 1);
document.getElementById('edit').onclick = () => setEditing(!editing);
document.getElementById('save').onclick = saveHtml;
document.getElementById('print').onclick = () => window.print();
addEventListener('keydown', event => {
  const inText = document.activeElement?.isContentEditable;
  if (event.key === 'Escape' && editing) { setEditing(false); return; }
  if (inText || event.metaKey || event.ctrlKey || event.altKey) return;
  const key = event.key.toLowerCase();
  if (key === 'e') { setEditing(!editing); return; }
  if (key === 'f') { document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen(); return; }
  if (key === 'r') { show(current); return; }
  if (key === 't') { toggleTimer(); return; }
  if (key === 'b') { const first = slides.findIndex(slide => slide.hasAttribute('data-backup')); if (first >= 0) show(first); return; }
  if (key === 'c') { const close = slides.findIndex(slide => slide.hasAttribute('data-close')); if (close >= 0) show(close); return; }
  if (['ArrowRight', ' ', 'PageDown', 'Enter'].includes(event.key)) { event.preventDefault(); next(); }
  else if (['ArrowLeft', 'PageUp', 'Backspace'].includes(event.key)) { event.preventDefault(); show(current - 1); }
  else if (event.key === 'Home') show(0);
  else if (event.key === 'End') show(slides.length - 1);
});
show(Math.max(0, Math.min(slides.length - 1, (parseInt(location.hash.slice(1), 10) || 1) - 1)));
