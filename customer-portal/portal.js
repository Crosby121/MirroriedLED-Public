(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const endpoint = new URL('backend/api.php', window.location.href);
  const state = { configured: false, authenticated: false, csrf: null, user: null, plans: [], capabilities: {}, authMode: 'signup', file: null, item: null, localUrl: null, library: [], deleting: null };
  const player = $('mediaPlayer');
  const canvas = $('ledCanvas');
  const context = canvas.getContext('2d', { alpha: false });
  const sampleCanvas = document.createElement('canvas');
  sampleCanvas.width = 32;
  sampleCanvas.height = 18;
  const sampleContext = sampleCanvas.getContext('2d', { willReadFrequently: true });
  let audioContext, analyser, mediaSource, frequencies, demo, animation;

  function message(id, text, error = false) {
    const element = $(id);
    element.textContent = text;
    element.classList.toggle('error', error);
  }

  async function api(action, body) {
    const url = new URL(endpoint);
    url.searchParams.set('action', action);
    const options = { credentials: 'same-origin', cache: 'no-store', headers: { Accept: 'application/json' } };
    if (body) {
      options.method = 'POST';
      options.headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify({ ...body, csrf: state.csrf });
    }
    const response = await fetch(url, options);
    if (!(response.headers.get('Content-Type') || '').includes('application/json')) {
      throw new Error('The account service is not connected here. You can still try a local media preview.');
    }
    const data = await response.json();
    if (!response.ok || !data.ok) {
      if (response.status === 401) await refreshSession(false);
      throw new Error(data.error || 'The request could not be completed. Please try again.');
    }
    return data;
  }

  function planName(id) {
    return state.plans.find((plan) => plan.id === id)?.name || ({ free: 'Free', premium: 'Premium', 'premium-plus': 'Premium+' }[id]) || 'Free';
  }

  function renderSession() {
    $('signedOut').hidden = state.authenticated;
    $('signedIn').hidden = !state.authenticated;
    $('accountState').textContent = state.authenticated ? 'Signed in' : state.configured ? 'Free signup' : 'Preview access';
    $('accountAvailability').textContent = state.configured
      ? 'Create your account to save a private music and video library.'
      : 'Account signup is waiting for server setup. Try the light studio below.';
    $('accountSubmit').disabled = !state.configured;
    $('accountLink').textContent = state.authenticated ? 'My account' : 'Sign up / Log in';
    $('saveMediaButton').disabled = !state.authenticated || !state.capabilities.upload || !state.file;
    const limits = state.capabilities.maxFileBytes;
    const sizeInfo = limits ? ` ${Math.floor(limits.audio / 1048576)} MB per song; ${Math.floor(limits.video / 1048576)} MB per video.` : '';
    $('uploadAvailability').textContent = state.authenticated
      ? `Saved uploads stay in your private library.${sizeInfo}`
      : `Local previews work without an account. Sign in to save a private upload.${sizeInfo}`;
    if (state.user) {
      $('memberGreeting').textContent = `Welcome, ${state.user.name}.`;
      $('memberEmail').textContent = state.user.email;
      $('memberPlan').textContent = planName(state.user.effectivePlan);
      $('memberRequest').textContent = planName(state.user.requestedPlan);
    }
    for (const plan of state.plans) {
      const songs = document.querySelector(`[data-plan-songs="${plan.id}"]`);
      const videos = document.querySelector(`[data-plan-videos="${plan.id}"]`);
      if (songs) songs.textContent = plan.songs;
      if (videos) videos.textContent = plan.videos;
    }
  }

  async function refreshSession(loadLibrary = true) {
    let data;
    try {
      data = await api('session');
    } catch (error) {
      Object.assign(state, { configured: false, authenticated: false, csrf: null, user: null, library: [] });
      renderSession();
      renderLibrary();
      message('accountMessage', error.message);
      return;
    }
    Object.assign(state, { configured: data.configured, authenticated: data.authenticated, csrf: data.csrf, user: data.user, plans: data.plans || [], capabilities: data.capabilities || {} });
    renderSession();
    if (!state.authenticated) {
      state.library = [];
      state.deleting = null;
      renderLibrary();
    } else if (loadLibrary) {
      try { await refreshLibrary(); } catch { /* Library has its own visible error; account state remains valid. */ }
    }
  }

  function authMode(mode) {
    state.authMode = mode;
    const signup = mode === 'signup';
    $('signupTab').classList.toggle('active', signup);
    $('signupTab').setAttribute('aria-pressed', String(signup));
    $('loginTab').classList.toggle('active', !signup);
    $('loginTab').setAttribute('aria-pressed', String(!signup));
    $('nameField').hidden = !signup;
    $('accountName').required = signup;
    $('planField').hidden = !signup;
    $('signupNote').hidden = !signup;
    $('passwordHint').hidden = !signup;
    $('accountPassword').autocomplete = signup ? 'new-password' : 'current-password';
    $('accountPassword').minLength = signup ? 12 : 1;
    $('accountSubmit').textContent = signup ? 'Create my account' : 'Log in';
    message('accountMessage', '');
  }

  $('signupTab').addEventListener('click', () => authMode('signup'));
  $('loginTab').addEventListener('click', () => authMode('login'));
  $('accountForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!state.configured) return;
    const button = $('accountSubmit');
    button.disabled = true;
    message('accountMessage', state.authMode === 'signup' ? 'Creating your account…' : 'Signing in…');
    try {
      await api(state.authMode, { name: $('accountName').value.trim(), email: $('accountEmail').value.trim(), password: $('accountPassword').value, requestedPlan: $('requestedPlan').value });
      $('accountPassword').value = '';
      await refreshSession();
      message('accountMessage', state.authMode === 'signup' ? 'Your account is ready. Free storage is active; billing is off.' : 'You’re signed in. Your private library is ready.');
    } catch (error) {
      message('accountMessage', error.message, true);
    } finally {
      button.disabled = !state.configured;
    }
  });

  $('logoutButton').addEventListener('click', async () => {
    $('logoutButton').disabled = true;
    try {
      await api('logout', {});
      if (state.item?.saved) clearPlayer();
      await refreshSession();
      message('accountMessage', 'You’re logged out.');
    } catch (error) {
      message('accountMessage', error.message, true);
    } finally {
      $('logoutButton').disabled = false;
    }
  });

  document.querySelectorAll('.plan-select').forEach((button) => {
    button.addEventListener('click', () => {
      if (state.authenticated) {
        message('accountMessage', 'You already have an account. Contact Mirroried LED support to request a plan change.');
      } else {
        authMode('signup');
        $('requestedPlan').value = button.dataset.plan;
      }
      $('account').scrollIntoView({ behavior: 'auto', block: 'start' });
      (state.authenticated ? $('logoutButton') : $('accountName')).focus({ preventScroll: true });
    });
  });

  function mediaKind(file) {
    const extension = file.name.split('.').pop().toLowerCase();
    if (['mp3', 'wav', 'ogg'].includes(extension)) return 'audio';
    if (['mp4', 'webm'].includes(extension)) return 'video';
    return null;
  }

  $('mediaFile').addEventListener('change', () => {
    const file = $('mediaFile').files[0];
    state.file = null;
    message('uploadMessage', '');
    if (file) {
      const kind = mediaKind(file);
      if (!kind) {
        message('uploadMessage', 'Choose an MP3, WAV, OGG, MP4 or WebM file.', true);
      } else if (file.size === 0) {
        message('uploadMessage', 'This file is empty. Choose another file.', true);
      } else {
        state.file = file;
      }
      $('selectedFile').textContent = `${file.name} · ${(file.size / 1048576).toFixed(1)} MB`;
    } else {
      $('selectedFile').textContent = 'No file selected.';
    }
    $('localPreviewButton').disabled = !state.file;
    renderSession();
  });

  function clearPlayer() {
    stopDemo();
    player.pause();
    player.removeAttribute('src');
    player.load();
    $('playerContainer').hidden = true;
    if (state.localUrl) URL.revokeObjectURL(state.localUrl);
    state.localUrl = null;
    state.item = null;
    $('previewName').textContent = 'Your light canvas.';
    $('previewStatus').textContent = 'Illustration';
    $('playerDescription').textContent = 'Play the demo, or choose your own media.';
    cancelAnimationFrame(animation);
    drawIdle();
  }

  function loadMedia(item) {
    clearPlayer();
    state.item = item;
    if (item.file) {
      state.localUrl = URL.createObjectURL(item.file);
      player.src = state.localUrl;
    } else {
      player.src = item.url;
    }
    player.classList.toggle('audio-only', item.kind === 'audio');
    $('playerContainer').hidden = false;
    $('previewName').textContent = item.name;
    $('previewStatus').textContent = item.saved ? 'Private library' : 'Local preview';
    $('playerDescription').textContent = 'Press play to synchronize the LED preview.';
    $('previewMode').value = item.kind === 'video' ? 'video' : 'music';
    $('previewMode').options[1].disabled = item.kind !== 'video';
    message('uploadMessage', item.saved ? 'Playing from your private media library.' : 'Ready to preview. This file stays on your device until you choose Save to my library.');
    player.load();
  }

  $('localPreviewButton').addEventListener('click', () => {
    if (state.file) loadMedia({ name: state.file.name, kind: mediaKind(state.file), file: state.file, saved: false });
  });

  function upload(file) {
    return new Promise((resolve, reject) => {
      const request = new XMLHttpRequest();
      const url = new URL(endpoint);
      url.searchParams.set('action', 'upload');
      request.open('POST', url);
      request.timeout = 180000;
      request.setRequestHeader('Accept', 'application/json');
      request.upload.addEventListener('progress', (event) => {
        if (event.lengthComputable) $('uploadProgress').value = event.loaded / event.total * 100;
      });
      request.addEventListener('load', () => {
        try {
          const data = JSON.parse(request.responseText);
          if (request.status >= 200 && request.status < 300 && data.ok) resolve(data);
          else reject(new Error(data.error || 'Upload failed. Please try again.'));
        } catch {
          reject(new Error('The server could not accept this upload. Try a smaller file or contact support.'));
        }
      });
      request.addEventListener('error', () => reject(new Error('The connection was interrupted. Your local file is still available.')));
      request.addEventListener('timeout', () => reject(new Error('The upload took too long. Try a smaller file.')));
      const form = new FormData();
      form.append('file', file);
      form.append('csrf', state.csrf);
      request.send(form);
    });
  }

  $('uploadForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!state.authenticated || !state.file) return;
    const file = state.file;
    const limit = state.capabilities.maxFileBytes?.[mediaKind(file)];
    if (limit && file.size > limit) {
      message('uploadMessage', `This file exceeds the ${Math.floor(limit / 1048576)} MB upload limit. It can still be previewed locally.`, true);
      return;
    }
    $('saveMediaButton').disabled = true;
    $('uploadProgress').hidden = false;
    $('uploadProgress').value = 0;
    message('uploadMessage', 'Uploading to your private library…');
    try {
      await upload(file);
      await refreshLibrary();
      message('uploadMessage', 'Uploaded. Your media is saved in your private library.');
    } catch (error) {
      message('uploadMessage', error.message, true);
    } finally {
      $('uploadProgress').hidden = true;
      renderSession();
    }
  });

  async function refreshLibrary() {
    try {
      const data = await api('library');
      state.library = data.items;
      renderLibrary(data);
      message('libraryMessage', '');
    } catch (error) {
      message('libraryMessage', error.message, true);
      throw error;
    }
  }

  function renderLibrary(data) {
    const list = $('mediaLibrary');
    list.replaceChildren();
    $('libraryEmpty').hidden = state.library.length > 0;
    $('libraryEmpty').textContent = state.authenticated
      ? 'Your library is empty. Save a song or video to start your collection.'
      : 'Your saved songs and videos will appear here. Local previews are not uploaded or saved.';
    $('libraryUsage').textContent = data
      ? `${data.usage.songs}/${data.limits.songs} songs · ${data.usage.videos}/${data.limits.videos} videos`
      : 'Sign in to save media';
    for (const item of state.library) {
      const row = document.createElement('li');
      row.className = 'media-item';
      const icon = document.createElement('span');
      icon.className = 'media-icon';
      icon.textContent = item.kind === 'audio' ? '♫' : '▶';
      icon.setAttribute('aria-hidden', 'true');
      const info = document.createElement('div');
      info.className = 'media-item-info';
      const title = document.createElement('strong');
      title.textContent = item.name;
      const detail = document.createElement('small');
      detail.textContent = `${item.kind === 'audio' ? 'Song' : 'Video'} · ${(item.bytes / 1048576).toFixed(1)} MB`;
      info.append(title, detail);
      const actions = document.createElement('div');
      actions.className = 'media-item-actions';
      const playButton = document.createElement('button');
      playButton.type = 'button';
      playButton.textContent = 'Preview';
      playButton.setAttribute('aria-label', `Preview ${item.name}`);
      playButton.addEventListener('click', () => {
        const url = new URL(item.url, window.location.href);
        if (url.origin !== window.location.origin) {
          message('libraryMessage', 'This media address could not be opened.', true);
          return;
        }
        loadMedia({ ...item, url: url.href, saved: true });
        $('previewName').scrollIntoView({ behavior: 'auto', block: 'center' });
        player.focus({ preventScroll: true });
      });
      const removeButton = document.createElement('button');
      removeButton.type = 'button';
      removeButton.className = 'delete-button';
      removeButton.textContent = state.deleting === item.id ? 'Confirm remove' : 'Remove';
      removeButton.setAttribute('aria-label', `${state.deleting === item.id ? 'Confirm removal of' : 'Remove'} ${item.name}`);
      removeButton.addEventListener('click', async () => {
        if (state.deleting !== item.id) {
          state.deleting = item.id;
          renderLibrary(data);
          message('libraryMessage', 'Choose Confirm remove to delete this saved file, or Cancel to keep it.');
          return;
        }
        removeButton.disabled = true;
        try {
          await api('delete', { id: item.id });
          state.deleting = null;
          if (state.item?.id === item.id) clearPlayer();
          await refreshLibrary();
          message('libraryMessage', 'Removed from your private library.');
        } catch (error) {
          message('libraryMessage', error.message, true);
          removeButton.disabled = false;
        }
      });
      actions.append(playButton, removeButton);
      if (state.deleting === item.id) {
        const cancel = document.createElement('button');
        cancel.type = 'button';
        cancel.className = 'delete-button';
        cancel.textContent = 'Cancel';
        cancel.addEventListener('click', () => { state.deleting = null; renderLibrary(data); message('libraryMessage', ''); });
        actions.append(cancel);
      }
      row.append(icon, info, actions);
      list.append(row);
    }
  }

  function ensureAudio() {
    if (!audioContext) {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (!AudioContext) throw new Error('Music visualization is not supported in this browser. Try a recent Chrome, Edge or Safari.');
      audioContext = new AudioContext();
      analyser = audioContext.createAnalyser();
      analyser.fftSize = 1024;
      analyser.smoothingTimeConstant = .75;
      frequencies = new Uint8Array(analyser.frequencyBinCount);
      analyser.connect(audioContext.destination);
      mediaSource = audioContext.createMediaElementSource(player);
      mediaSource.connect(analyser);
    }
    return audioContext.resume();
  }

  function brightness() { return Number($('brightness').value) / 100; }
  function drawMatrix(colorAt) {
    if (!context) return;
    context.fillStyle = '#030a11';
    context.fillRect(0, 0, canvas.width, canvas.height);
    const cols = 32, rows = 18, size = canvas.width / cols;
    for (let y = 0; y < rows; y++) {
      for (let x = 0; x < cols; x++) {
        context.fillStyle = colorAt(x, y, cols, rows);
        context.beginPath();
        context.arc((x + .5) * size, (y + .5) * size, size * .31, 0, Math.PI * 2);
        context.fill();
      }
    }
  }

  function drawIdle() {
    drawMatrix((x, y, cols, rows) => {
      const wave = (Math.sin(x * .31) + Math.cos(x * .17)) * 2.2 + rows / 2;
      const light = Math.max(0, 1 - Math.abs(y - wave) / 5);
      return `hsl(${160 + x / cols * 135} 72% ${4 + light * 39 * brightness()}%)`;
    });
  }

  function drawMusic() {
    if (!analyser) { drawIdle(); return; }
    analyser.getByteFrequencyData(frequencies);
    drawMatrix((x, y, cols, rows) => {
      const start = Math.floor(Math.pow(x / cols, 2.2) * frequencies.length * .65);
      const end = Math.max(start + 1, Math.floor(Math.pow((x + 1) / cols, 2.2) * frequencies.length * .65));
      let peak = 0;
      for (let bin = start; bin < end; bin++) peak = Math.max(peak, frequencies[bin]);
      const height = peak / 255 * rows;
      const lit = rows - y <= height;
      return lit ? `hsl(${155 + x / cols * 145} 84% ${Math.min(65, (29 + y * 1.4) * brightness() + 12)}%)` : '#0b1721';
    });
  }

  function drawVideo() {
    if (player.readyState < 2 || !player.videoWidth || !sampleContext) { drawIdle(); return; }
    try {
      sampleContext.drawImage(player, 0, 0, 32, 18);
      const pixels = sampleContext.getImageData(0, 0, 32, 18).data;
      const level = brightness();
      drawMatrix((x, y, cols) => {
        const offset = (y * cols + x) * 4;
        return `rgb(${Math.round(pixels[offset] * level)} ${Math.round(pixels[offset + 1] * level)} ${Math.round(pixels[offset + 2] * level)})`;
      });
    } catch {
      message('uploadMessage', 'This video can play, but its pixels could not be read for the LED preview.', true);
      drawIdle();
    }
  }

  function tick() {
    if (demo || (!player.paused && !player.ended)) {
      if (!demo && $('previewMode').value === 'video') drawVideo();
      else drawMusic();
      animation = requestAnimationFrame(tick);
    }
  }

  player.addEventListener('play', async () => {
    stopDemo();
    try { await ensureAudio(); } catch (error) { message('uploadMessage', error.message, true); }
    if (player.paused) return;
    cancelAnimationFrame(animation);
    $('previewStatus').textContent = 'Preview playing';
    $('playerDescription').textContent = 'Lights follow the playback on this device.';
    tick();
  });
  player.addEventListener('pause', () => {
    if (!state.item) return;
    cancelAnimationFrame(animation);
    $('previewStatus').textContent = player.ended ? 'Preview ended' : 'Preview paused';
    $('playerDescription').textContent = 'Press play to continue the synchronized preview.';
  });
  player.addEventListener('seeked', () => { if ($('previewMode').value === 'video') drawVideo(); });
  player.addEventListener('error', () => {
    if (state.item) message('uploadMessage', 'This file could not be played. Try another file or check its audio/video format.', true);
  });
  $('brightness').addEventListener('input', () => {
    $('brightnessValue').textContent = `${$('brightness').value}%`;
    if (player.paused && !demo) {
      if (state.item?.kind === 'video' && $('previewMode').value === 'video') drawVideo();
      else drawIdle();
    }
  });
  $('previewMode').addEventListener('change', () => {
    if (player.paused && !demo) {
      if ($('previewMode').value === 'video') drawVideo();
      else drawIdle();
    }
  });

  function stopDemo() {
    if (!demo) return;
    clearTimeout(demo.timer);
    for (const source of demo.sources) { try { source.stop(); } catch { /* Already ended. */ } }
    for (const gain of demo.gains) gain.disconnect();
    demo = null;
    $('demoButton').textContent = 'Play demo';
    $('previewStatus').textContent = state.item ? 'Preview paused' : 'Illustration';
    cancelAnimationFrame(animation);
    drawIdle();
  }

  $('demoButton').addEventListener('click', async () => {
    if (demo) { stopDemo(); $('playerDescription').textContent = 'Choose your media, or play the demo again.'; return; }
    player.pause();
    try {
      await ensureAudio();
      demo = { sources: [], gains: [], timer: null };
      const start = audioContext.currentTime + .03;
      const notes = [110, 164.81, 220, 146.83, 110, 196, 164.81, 220];
      for (let beat = 0; beat < 24; beat++) {
        for (const frequency of [notes[beat % notes.length], 55]) {
          const source = audioContext.createOscillator();
          const gain = audioContext.createGain();
          source.type = frequency === 55 ? 'sine' : 'triangle';
          source.frequency.value = frequency;
          const when = start + beat * .5;
          gain.gain.setValueAtTime(0, when);
          gain.gain.linearRampToValueAtTime(.035, when + .015);
          gain.gain.exponentialRampToValueAtTime(.0001, when + .4);
          source.connect(gain);
          gain.connect(analyser);
          source.start(when);
          source.stop(when + .42);
          demo.sources.push(source);
          demo.gains.push(gain);
        }
      }
      demo.timer = setTimeout(() => { stopDemo(); $('playerDescription').textContent = 'Demo finished. Choose your own music or video next.'; }, 12200);
      $('demoButton').textContent = 'Stop demo';
      $('previewStatus').textContent = 'Demo playing';
      $('playerDescription').textContent = 'Generated music demo · 12 seconds';
      cancelAnimationFrame(animation);
      tick();
    } catch (error) {
      message('uploadMessage', error.message, true);
    }
  });
  document.addEventListener('visibilitychange', () => { if (document.hidden) stopDemo(); });
  window.addEventListener('pagehide', () => { stopDemo(); if (state.localUrl) URL.revokeObjectURL(state.localUrl); });
  $('year').textContent = new Date().getFullYear();
  drawIdle();
  refreshSession();
})();
