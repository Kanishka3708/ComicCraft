const get = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (character) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[character]));
let currentComic = null;
let characterCount = 0;
let activeStep = 1;

function characterTemplate(index) {
  return `<article class="character-card" data-character="${index}"><div class="character-card-head"><b>Character ${index}</b><button type="button" class="remove-character">Remove</button></div><div class="character-grid"><label>Name<input class="character-name" required placeholder="Character name"></label><label>Age<input class="character-age" placeholder="Age"></label><label>Gender<input class="character-gender" placeholder="Gender"></label><label>Hair<input class="character-hair" placeholder="Hair style and color"></label><label class="wide">Appearance<textarea class="character-appearance" rows="2" placeholder="Face, build, distinguishing features"></textarea></label><label>Clothing<input class="character-clothing" placeholder="What they wear"></label><label>Personality<input class="character-personality" placeholder="Traits and mannerisms"></label><label>Character role<input class="character-role" placeholder="Hero, rival, guide..."></label></div></article>`;
}

function addCharacter() {
  characterCount += 1;
  get('characters').insertAdjacentHTML('beforeend', characterTemplate(characterCount));
  get('characters').lastElementChild.querySelector('.remove-character').onclick = (event) => event.currentTarget.closest('.character-card').remove();
}

function renderManualPanels() {
  const panelCount = Number(get('panelCount').value);
  get('manualPanels').innerHTML = Array.from({length: panelCount}, (_, index) => `<article class="manual-panel"><h3>Panel ${index + 1}</h3><div class="manual-grid"><label class="wide">Scene description<textarea class="panel-scene" rows="2" placeholder="What does this panel show?"></textarea></label><label>Characters present<input class="panel-characters" placeholder="Names"></label><label>Character actions<input class="panel-actions" placeholder="What are they doing?"></label><label>Background<input class="panel-background" placeholder="Place and environment"></label><label>Camera angle<input class="panel-camera" placeholder="Wide shot, close-up..."></label><label>Emotion<input class="panel-emotion" placeholder="Mood and expression"></label><label>Dialogue<input class="panel-dialogue" placeholder="Spoken line"></label><label>Narration<input class="panel-narration" placeholder="Narration text"></label></div></article>`).join('');
}

function setStep(step) {
  activeStep = step;
  document.querySelectorAll('.form-step').forEach((section) => section.classList.toggle('active', Number(section.dataset.step) === step));
  document.querySelectorAll('.step').forEach((button) => button.classList.toggle('active', Number(button.dataset.step) === step));
  window.scrollTo({top: 0, behavior: 'smooth'});
}

function collectCharacters() {
  return [...document.querySelectorAll('.character-card')].map((card) => ({
    name: card.querySelector('.character-name').value.trim(),
    age: card.querySelector('.character-age').value.trim(),
    gender: card.querySelector('.character-gender').value.trim(),
    appearance: card.querySelector('.character-appearance').value.trim(),
    hair_style: card.querySelector('.character-hair').value.trim(),
    clothing: card.querySelector('.character-clothing').value.trim(),
    personality: card.querySelector('.character-personality').value.trim(),
    accessories: '',
    reference_image: null,
  }));
}

function collectManualPanels() {
  return [...document.querySelectorAll('.manual-panel')].map((panel, index) => ({
    title: `Panel ${index + 1}`,
    scene: panel.querySelector('.panel-scene').value.trim(),
    characters: panel.querySelector('.panel-characters').value.trim(),
    actions: panel.querySelector('.panel-actions').value.trim(),
    background: panel.querySelector('.panel-background').value.trim(),
    camera_angle: panel.querySelector('.panel-camera').value.trim(),
    emotion: panel.querySelector('.panel-emotion').value.trim(),
    dialogue: panel.querySelector('.panel-dialogue').value.trim(),
    narration: panel.querySelector('.panel-narration').value.trim(),
  }));
}

function renderComic(data) {
  currentComic = data;
  get('resultTitle').textContent = data.title;
  get('resultMeta').textContent = `${data.panels.length} panels | ${data.art_style} | ${data.colour_style}`;
  get('resultPanels').innerHTML = data.panels.map((panel, index) => `<article class="result-panel">${data.assets?.[index] ? `<img src="${escapeHtml(data.assets[index])}" alt="${escapeHtml(panel.title)}">` : '<div class="loading">Image generation failed for this panel.</div>'}<div class="result-panel-body"><h3>Panel ${index + 1}: ${escapeHtml(panel.title)}</h3><p>${escapeHtml(panel.narration)}</p><p><b>${escapeHtml(data.character)}:</b> ${escapeHtml(panel.dialogue)}</p></div></article>`).join('');
  get('result').hidden = false;
  get('result').scrollIntoView({behavior: 'smooth'});
}

function setProgress(message) {
  let status = get('progressStatus');
  if (!status) {
    status = document.createElement('p');
    status.id = 'progressStatus';
    status.className = 'generation-progress';
    status.setAttribute('aria-live', 'polite');
    get('formError').before(status);
  }
  status.textContent = message;
  status.hidden = false;
}

async function requestComicStream(payload) {
  const response = await fetch('/api/generate-stream', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.error || 'Comic generation failed.');
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let result = null;
  while (true) {
    const chunk = await reader.read();
    buffer += decoder.decode(chunk.value || new Uint8Array(), {stream: !chunk.done});
    const messages = buffer.split('\n\n');
    buffer = messages.pop();
    for (const message of messages) {
      const line = message.split('\n').find((entry) => entry.startsWith('data: '));
      if (!line) continue;
      const event = JSON.parse(line.slice(6));
      if (event.type === 'panel_started') setProgress(`Generating Panel ${event.panel} / ${event.total}`);
      if (event.type === 'rate_limited') setProgress(`Panel ${event.panel} image generation is temporarily rate-limited. Retrying in ${Math.ceil(event.delay)} seconds...`);
      if (event.type === 'complete') { setProgress('Building comic layout...'); result = event.data; }
      if (event.type === 'error') throw new Error(event.error || 'Comic generation failed.');
    }
    if (chunk.done) break;
  }
  if (!result) throw new Error('Comic generation stopped before all panels were completed.');
  return result;
}

async function generateComic(event) {
  event.preventDefault();
  const formError = get('formError');
  formError.hidden = true;
  const characters = collectCharacters();
  const panelMode = document.querySelector('input[name="panelMode"]:checked').value;
  const manualPanels = panelMode === 'manual' ? collectManualPanels() : [];
  if (!get('storyTitle').value.trim() || !get('storyDescription').value.trim() || !characters.length || !characters[0].name) {
    formError.textContent = 'Comic title, story / plot, and at least one character name are required.';
    formError.hidden = false;
    return;
  }
  if (panelMode === 'manual' && manualPanels.some((panel) => !panel.scene)) {
    formError.textContent = 'Add a scene description for every manual panel.';
    formError.hidden = false;
    return;
  }
  const button = document.querySelector('.generate-btn');
  button.disabled = true;
  button.textContent = 'Generating your comic...';
  get('result').hidden = true;
  const payload = {story_title: get('storyTitle').value.trim(), story_description: get('storyDescription').value.trim(), genre: get('genre').value, target_audience: get('audience').value, panel_count: Number(get('panelCount').value), language: get('language').value, character: characters[0].name, setting: 'Story world', custom_setting: 'Story world', tone: get('lightingMood').value || 'Cinematic', theme: get('lightingMood').value, art_style: get('artStyle').value, custom_art_style: get('customStyle').value.trim(), colour_style: get('colourStyle').value, premise: get('storyDescription').value.trim(), characters, orientation: get('orientation').value, character_visual_style: get('characterVisual').value.trim(), background_style: get('backgroundStyle').value.trim(), lighting_mood: get('lightingMood').value.trim(), panel_mode: panelMode, panel_details: manualPanels};
  try {
    const data = await requestComicStream(payload);
    if (!Array.isArray(data.assets) || data.assets.length !== data.panels.length || data.assets.some((asset) => typeof asset !== 'string' || !asset)) {
      throw new Error('Every panel needs a valid generated image. Please try again.');
    }
    renderComic(data);
    setProgress('Comic generated successfully.');
  } catch (error) {
    formError.textContent = error.message;
    formError.hidden = false;
  } finally {
    button.disabled = false;
    button.innerHTML = 'Generate My Comic <span>-></span>';
  }
}

async function downloadComic(endpoint, body, filename) {
  const response = await fetch(endpoint, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  if (!response.ok) { alert('Export failed.'); return; }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a'); link.href = url; link.download = filename; link.click(); URL.revokeObjectURL(url);
}

document.querySelectorAll('.next-step').forEach((button) => button.onclick = () => setStep(Math.min(4, activeStep + 1)));
document.querySelectorAll('.back-step').forEach((button) => button.onclick = () => setStep(Math.max(1, activeStep - 1)));
document.querySelectorAll('.step').forEach((button) => button.onclick = () => setStep(Number(button.dataset.step)));
get('addCharacter').onclick = addCharacter;
get('panelCount').onchange = renderManualPanels;
document.querySelectorAll('input[name="panelMode"]').forEach((input) => input.onchange = () => { get('manualPanels').hidden = input.value !== 'manual' || !input.checked; if (input.checked && input.value === 'manual') renderManualPanels(); });
get('comicForm').onsubmit = generateComic;
get('exportPdf').onclick = () => downloadComic('/api/export-pdf', currentComic, 'comiccraft-comic.pdf');
get('exportPng').onclick = () => downloadComic('/api/export-image', {assets: currentComic.assets, format: 'png'}, 'comiccraft-comic.png');
get('exportJson').onclick = () => downloadComic('/api/download-json', currentComic, 'comiccraft-story.json');
get('startOver').onclick = () => { get('result').hidden = true; setStep(1); window.scrollTo({top: 0, behavior: 'smooth'}); };
addCharacter();
