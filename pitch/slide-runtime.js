const slides = [...document.querySelectorAll('.slide')];
const deck = document.querySelector('.deck');
const editable = [...document.querySelectorAll('.slide h1, .slide h2, .slide h3, .slide p, .slide .logic-row strong, .slide .logic-row span, .slide .id, .slide .step b, .slide .step strong, .slide .update-grid em, .slide .sample-note, .slide .sim-tag, .slide .credit')];
let current = 0;
let editing = false;

function fit() {
  deck.style.setProperty('--scale', Math.min(innerWidth / 1280, innerHeight / 720));
}
fit();
addEventListener('resize', fit);

function show(index) {
  if (index < 0 || index >= slides.length) return;
  slides[current].classList.remove('active');
  current = index;
  void slides[current].offsetWidth;
  slides[current].classList.add('active');
  document.getElementById('progress').style.width = `${(current + 1) / slides.length * 100}%`;
  document.getElementById('page-count').textContent = `${current + 1} / ${slides.length}`;
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
  copy.querySelector('#page-count').textContent = `1 / ${slides.length}`;
  const blob = new Blob([`<!doctype html>\n${copy.outerHTML}`], {type: 'text/html;charset=utf-8'});
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = document.title.includes('Reference') ? 'pitch-reference-edited.html' : 'pitch-bmw-edited.html';
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

document.getElementById('next').onclick = () => show(current + 1);
document.getElementById('prev').onclick = () => show(current - 1);
document.getElementById('edit').onclick = () => setEditing(!editing);
document.getElementById('save').onclick = saveHtml;
document.getElementById('print').onclick = () => window.print();
addEventListener('keydown', event => {
  const inText = document.activeElement?.isContentEditable;
  if (event.key === 'Escape' && editing) { setEditing(false); return; }
  if (inText) return;
  if (event.key.toLowerCase() === 'e') { setEditing(!editing); return; }
  if (event.key.toLowerCase() === 'f') { document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen(); return; }
  if (event.key.toLowerCase() === 'r') { show(current); return; }
  if (['ArrowRight', ' ', 'PageDown', 'Enter'].includes(event.key)) { event.preventDefault(); show(current + 1); }
  else if (['ArrowLeft', 'PageUp', 'Backspace'].includes(event.key)) { event.preventDefault(); show(current - 1); }
  else if (event.key === 'Home') show(0);
  else if (event.key === 'End') show(slides.length - 1);
});
show(0);
