(function (root) {
  'use strict';
  const mm = inch => inch * 25.4;
  const round = n => Math.round(n * 100) / 100;
  function interior(state, catalog) {
    const rim = catalog.rules.frameLipIn + (state.rim.enabled ? state.rim.rows * catalog.rules.rowGapIn : 0);
    return { x: rim, y: rim, width: state.size[0] - rim * 2, height: state.size[1] - rim * 2 };
  }
  function artBox(state, catalog) {
    const room = interior(state, catalog);
    const ratio = Math.max(0.1, Math.min(10, state.artwork?.aspect || 1));
    const fit = Math.min(room.width - 2 * catalog.rules.artClearanceIn, (room.height - 2 * catalog.rules.artClearanceIn) * ratio);
    const width = fit * state.artScale / 100, height = width / ratio;
    return { x: (state.size[0] - width) / 2, y: (state.size[1] - height) / 2, width, height };
  }
  // Examine every uniform rectangular tiling and orientation. Rank by unused physical area,
  // then panel count and pitch. Pixel count is never substituted for physical dimensions.
  function candidates(state, catalog) {
    if (state.rear === 'none' || !state.artwork?.approved) return [];
    const area = artBox(state, catalog), room = interior(state, catalog);
    const out = [];
    for (const panel of catalog.panels.filter(p => p.family === state.rear && p.stock !== 0)) {
      for (const rotated of [false, true]) {
        if (rotated && panel.widthMm === panel.heightMm) continue;
        const pw = (rotated ? panel.heightMm : panel.widthMm) / 25.4;
        const ph = (rotated ? panel.widthMm : panel.heightMm) / 25.4;
        const cols = Math.ceil((area.width - 1e-8) / pw), rows = Math.ceil((area.height - 1e-8) / ph);
        const count = rows * cols, width = pw * cols, height = ph * rows;
        if (width > room.width + 1e-8 || height > room.height + 1e-8 || (panel.stock !== null && panel.stock < count)) continue;
        const cells = [];
        for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) cells.push({ x: (state.size[0] - width) / 2 + c * pw, y: (state.size[1] - height) / 2 + r * ph, width: pw, height: ph });
        out.push({ key: panel.id + (rotated ? '-r' : '-n'), panelId: panel.id, name: panel.name, family: panel.family, rotated, rows, cols, count, width, height, pitchMm: panel.pitchMm, pixels: count * panel.pixelsX * panel.pixelsY, unusedArea: round(width * height - area.width * area.height), utilization: round(100 * area.width * area.height / (width * height)), stockConfirmed: panel.stock !== null, cells });
      }
    }
    return out.sort((a, b) => a.unusedArea - b.unusedArea || a.count - b.count || a.pitchMm - b.pitchMm || a.key.localeCompare(b.key));
  }
  function controllers(state, catalog) {
    return catalog.controllers.filter(c => c.family === (state.rear === 'hub75' ? 'hub75' : 'addressable'));
  }
  function plan(state, catalog) {
    const layouts = candidates(state, catalog);
    const layout = layouts.find(x => x.key === state.layoutKey) || layouts[0] || null;
    const rimPixels = state.rim.enabled ? state.rim.rows * state.rim.countPerRow : 0;
    const rearPixels = layout?.pixels || 0;
    const available = controllers(state, catalog).filter(c => c.available);
    const controller = available.find(c => c.id === state.controllerId) || available[0];
    const warnings = [];
    if (!state.artwork?.approved) warnings.push('Choose and approve your engraving artwork.');
    if (state.rear !== 'none' && state.artwork?.approved && !layout) warnings.push('No catalog panel layout fits this artwork and frame. Reduce artwork size or choose a larger mirror.');
    if (layout && !layout.stockConfirmed) warnings.push('The team will confirm panel stock and measured dimensions.');
    if (layout?.family === 'hub75') warnings.push('The team will verify the panel scan mode, driver and MatrixPortal firmware for this layout.');
    if (state.audioReactive) warnings.push('Audio response needs a compatible microphone or network audio source and validated firmware.');
    if (!state.rim.enabled && state.rear === 'none') warnings.push('Include rim strips or rear panels to light this mirror.');
    const hardware = [
      { id: 'mirror', label: 'Two-way front mirror + rear mirror', quantity: 1, required: true },
      { id: 'frame', label: `${state.size[0]} × ${state.size[1]} in frame · ${state.depthIn} in depth · ${state.finish}`, quantity: 1, required: true },
      { id: 'diffuser', label: 'Frosted backside engraving + diffuser / spacer', quantity: 1, required: true },
      { id: 'backplate', label: 'Serviceable backplate + cable channels', quantity: 1, required: true },
      { id: 'controller', label: controller?.name || 'Controller review', quantity: 1, required: true },
      { id: 'power', label: '5V regulated power supply · team-sized for actual parts', quantity: 1, required: true },
      { id: 'wiring', label: 'Fused distribution, common ground, power injection + connectors', quantity: 1, required: true }
    ];
    if (rimPixels) hardware.push({ id: 'rim', label: `WS2812B rim · ${state.rim.rows} row${state.rim.rows > 1 ? 's' : ''} × ${state.rim.countPerRow} LEDs`, quantity: rimPixels, required: true });
    if (layout) hardware.push({ id: 'panels', label: `${layout.name} panels + mounts`, quantity: layout.count, required: true });
    if (state.rear === 'hub75' && rimPixels) hardware.push({ id: 'rim-controller', label: catalog.controllers.find(c => c.id === state.rimControllerId && c.family === 'addressable' && c.available)?.name || 'QuinLED Digi-Uno', quantity: 1, required: true });
    if (layout?.family === 'hub75') hardware.push({ id: 'ribbon', label: 'HUB75 ribbon / power leads + panel support', quantity: layout.count, required: true });
    if (state.audioReactive) hardware.push({ id: 'audio', label: 'Compatible microphone or network audio bridge · team verified', quantity: 1, required: true });
    if (state.extras.wallMount) hardware.push({ id: 'mount', label: 'Wall mounting kit', quantity: 1, required: false });
    if (state.extras.remote) hardware.push({ id: 'remote', label: 'Compatible local control / remote option', quantity: 1, required: false });
    // Only addressable current has a stated conservative planning assumption. HUB75 current is
    // intentionally omitted until a manufacturer's data / measured inventory part is verified.
    const addressablePixels = rimPixels + (state.rear === 'flex' ? rearPixels : 0);
    return { layout, layouts, controller, rimPixels, rearPixels, totalPixels: rimPixels + rearPixels, hardware, warnings,
      addressableEstimateAmps: round(addressablePixels * 0.06), hub75PowerPending: state.rear === 'hub75',
      ready: !!state.artwork?.approved && (state.rear === 'none' || !!layout) && (state.rim.enabled || state.rear !== 'none') && !!controller };
  }
  function initial(catalog) {
    return { version: 1, size: catalog.sizes[0], depthIn: catalog.rules.defaultDepthIn, finish: 'Matte black', rim: { enabled: true, addressable: true, rows: 1, countPerRow: 72, color: '#2dd4bf' }, audioReactive: false, artwork: null, artScale: 65, rear: 'flex', controllerId: 'digi-uno', rimControllerId: 'digi-uno', layoutKey: 'auto', extras: { wallMount: true, remote: false } };
  }
  const api = { mm, round, interior, artBox, candidates, controllers, plan, initial };
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.MirrorBuilderEngine = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
