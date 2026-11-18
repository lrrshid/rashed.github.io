// Animated capability-development scene (decorative, no external files): a night sky over the coast, fixed-wing
// drones and a swarm crossing, quadcopters hovering with sensor cones, a ground station with a turning radar and
// data links, an unmanned surface vessel on the sea and an unmanned ground vehicle on the sand, under a HUD frame.
// Built as SVG; motion is CSS animation (css/scene.css), stopped when the viewer prefers reduced motion.
// variant 'full' fills a page background; 'banner' shows the band around the horizon for a page header.

const NS = 'http://www.w3.org/2000/svg';

function s(tag, attrs = {}, ...children) {
  const el = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === null) continue;
    if (k === 'delay') el.style.animationDelay = v;          // CSSOM, allowed by the content security policy
    else if (k === 'duration') el.style.animationDuration = v;
    else el.setAttribute(k, String(v));
  }
  for (const c of children.flat()) if (c) el.append(c);
  return el;
}

// Deterministic "random" numbers, so the scene looks the same on every visit.
function seeded(seed) {
  let x = seed;
  return () => { x = (x * 16807) % 2147483647; return (x - 1) / 2147483646; };
}

function gradient(id, stops, attrs = {}, tag = 'linearGradient') {
  return s(tag, { id, ...attrs }, stops.map(([offset, cls]) => s('stop', { offset, class: cls })));
}

// A medium-altitude fixed-wing drone, nose to the right, about 160 units wide.
function fixedWing() {
  return s('g', { class: 'drone-body' },
    s('path', { class: 'hull', d: 'M-80 0 C-60 -9 40 -10 70 -4 C80 -2 84 0 80 3 C60 7 -50 8 -80 4 Z' }),
    s('path', { class: 'wing', d: 'M-10 -2 L-34 -46 L-18 -46 L22 -2 Z' }),
    s('path', { class: 'wing far', d: 'M-6 4 L-26 38 L-12 38 L22 4 Z' }),
    s('path', { class: 'wing', d: 'M-74 0 L-92 -22 L-82 -22 L-62 0 Z' }),
    s('path', { class: 'wing far', d: 'M-74 3 L-92 20 L-84 20 L-64 3 Z' }),
    s('circle', { class: 'sensor', cx: 52, cy: 7, r: 5 }),
    s('circle', { class: 'nav-light red', cx: -30, cy: -44, r: 2.6 }),
    s('circle', { class: 'nav-light green', cx: -22, cy: 36, r: 2.6 }));
}

// A quadcopter seen slightly from below, about 120 units wide, with spinning rotors and a sensor cone.
function quad() {
  const arm = (x) => s('line', { class: 'arm', x1: 0, y1: 0, x2: x, y2: -10 });
  const rotor = (x, i) => s('g', {},
    s('line', { class: 'mast', x1: x, y1: -10, x2: x, y2: -16 }),
    s('ellipse', { class: 'rotor', cx: x, cy: -17, rx: 26, ry: 3.2, delay: `${-i * 0.07}s` }));
  return s('g', { class: 'drone-body' },
    s('path', { class: 'cone', d: 'M-10 10 L-70 190 L70 190 L10 10 Z' }),
    arm(-46), arm(-18), arm(18), arm(46),
    [-46, -18, 18, 46].map(rotor),
    s('rect', { class: 'hull', x: -20, y: -9, width: 40, height: 16, rx: 7 }),
    s('circle', { class: 'sensor', cx: 0, cy: 10, r: 6 }),
    s('circle', { class: 'nav-light green', cx: -46, cy: -10, r: 2.4 }),
    s('circle', { class: 'nav-light red', cx: 46, cy: -10, r: 2.4 }));
}

// A small chevron for the swarm.
function chevron() {
  return s('path', { class: 'swarm-unit', d: 'M-9 0 L9 0 L0 -5 Z M-12 2 L12 2 L0 -9 Z' });
}

export function capabilityScene(variant = 'full') {
  const banner = variant === 'banner';
  const rnd = seeded(20261111);
  const svg = s('svg', {
    class: `scene-svg scene-${variant}`, viewBox: banner ? '0 300 1600 380' : '0 0 1600 900',
    preserveAspectRatio: 'xMidYMid slice', 'aria-hidden': 'true', focusable: 'false', direction: 'ltr',
  });
  // Shapes run past the frame so the mouse parallax (followPointer) never uncovers an edge.
  const seaShape = 'M-120 612 L760 612 C700 700 640 780 520 900 L-120 900 Z';

  svg.append(s('defs', {},
    gradient('sc-sky', [[0, 'sky-0'], [0.55, 'sky-1'], [1, 'sky-2']], { x1: 0, y1: 0, x2: 0, y2: 1 }),
    gradient('sc-glow', [[0, 'glow-0'], [1, 'glow-1']], { cx: 0.5, cy: 0.5, r: 0.5 }, 'radialGradient'),
    gradient('sc-sea', [[0, 'sea-0'], [1, 'sea-1']], { x1: 0, y1: 0, x2: 0, y2: 1 }),
    gradient('sc-sand', [[0, 'sand-0'], [1, 'sand-1']], { x1: 0, y1: 0, x2: 0, y2: 1 }),
    gradient('sc-cone', [[0, 'cone-0'], [1, 'cone-1']], { x1: 0, y1: 0, x2: 0, y2: 1 }),
    gradient('sc-sweep', [[0, 'sweep-0'], [1, 'sweep-1']], { x1: 0, y1: 0, x2: 1, y2: 0 }),
    gradient('sc-vignette', [[0.55, 'vig-0'], [1, 'vig-1']], { cx: 0.5, cy: 0.5, r: 0.75 }, 'radialGradient'),
    s('clipPath', { id: 'sc-sea-clip' }, s('path', { d: seaShape }))));

  // sky, stars, horizon glow
  svg.append(s('rect', { class: 'sky', x: -120, y: -120, width: 1840, height: 1140 }));
  // Depth layers, far to near: they follow the mouse by different distances (css/scene.css). The HUD stays still.
  const depth = [0, 1, 2, 3].map((n) => s('g', { class: `depth depth-${n}` }));
  svg.append(...depth);
  const stars = s('g', { class: 'stars' });
  for (let i = 0; i < 90; i += 1) {
    stars.append(s('circle', { class: 'star', cx: (rnd() * 1600).toFixed(1), cy: (rnd() * 520).toFixed(1),
      r: (0.6 + rnd() * 1.5).toFixed(2), delay: `${(-rnd() * 6).toFixed(2)}s`, duration: `${(3 + rnd() * 5).toFixed(2)}s` }));
  }
  depth[0].append(stars);
  depth[1].append(s('ellipse', { class: 'glow', cx: 800, cy: 600, rx: 900, ry: 220 }));

  // distant dunes (two layers drifting slowly) and the horizon line
  const dunes = (cls, y, amp, step) => {
    let d = `M-240 ${y}`;
    for (let x = -240; x <= 3400; x += step) d += ` Q${x + step / 2} ${y - amp * (0.4 + ((x / step) % 3) * 0.3)} ${x + step} ${y}`;
    return s('g', { class: `drift ${cls}` }, s('path', { class: 'dune', d: `${d} L3600 640 L-240 640 Z` }));
  };
  depth[1].append(dunes('drift-slow far-dunes', 600, 34, 260));
  depth[2].append(dunes('drift-fast near-dunes', 612, 22, 180));

  // sea (left) and sand (right) with a shoreline
  depth[2].append(s('path', { class: 'sea', d: seaShape }));
  const waves = s('g', { class: 'waves', 'clip-path': 'url(#sc-sea-clip)' });
  for (let i = 0; i < 9; i += 1) {
    const y = 630 + i * 30;
    waves.append(s('g', { class: 'wave-row', delay: `${-i * 0.7}s` },
      s('path', { class: 'wave', d: `M${-160 + (i % 2) * 40} ${y} q40 -7 80 0${' t80 0'.repeat(12)}` })));
  }
  depth[2].append(waves);
  depth[2].append(s('path', { class: 'sand', d: 'M760 612 L1720 612 L1720 900 L520 900 C640 780 700 700 760 612 Z' }));
  const grid = s('g', { class: 'grid' });
  for (let i = 0; i < 9; i += 1) {
    const y = 616 + (i * i * 3.6) + i * 6;
    grid.append(s('line', { x1: 640, y1: y, x2: 1720, y2: y }));
  }
  for (let i = 0; i <= 12; i += 1) {
    const x = 760 + i * 80;
    grid.append(s('line', { x1: 1180 + (x - 1180) * 0.2, y1: 612, x2: 1180 + (x - 1180) * 2.4, y2: 900 }));
  }
  depth[2].append(grid);
  depth[2].append(s('line', { class: 'horizon', x1: -120, y1: 612, x2: 1720, y2: 612 }));

  // ground station: radar (flattened), mast and dish, data links
  const station = s('g', { transform: 'translate(1180 690)' });
  const radar = s('g', { transform: 'scale(1 0.34)' },
    [70, 140, 210].map((r) => s('circle', { class: 'radar-ring', cx: 0, cy: 0, r })),
    s('line', { class: 'radar-ring', x1: -210, y1: 0, x2: 210, y2: 0 }),
    s('line', { class: 'radar-ring', x1: 0, y1: -210, x2: 0, y2: 210 }),
    s('g', { class: 'radar-sweep' }, s('path', { class: 'sweep', d: 'M0 0 L210 0 A210 210 0 0 0 148.5 -148.5 Z' })),
    [[120, -60], [-150, 90], [60, 150], [-80, -150]].map(([x, y], i) => s('circle', { class: 'blip', cx: x, cy: y, r: 7,
      delay: `${i * 1.1}s` })));
  station.append(radar,
    s('rect', { class: 'building', x: -34, y: -30, width: 68, height: 30, rx: 2 }),
    s('line', { class: 'mast-line', x1: 18, y1: -30, x2: 18, y2: -92 }),
    s('path', { class: 'dish', d: 'M2 -96 A18 18 0 0 0 34 -82 Z' }),
    s('circle', { class: 'nav-light red', cx: 18, cy: -94, r: 2.6 }),
    s('rect', { class: 'window', x: -26, y: -22, width: 10, height: 6 }),
    s('rect', { class: 'window', x: -10, y: -22, width: 10, height: 6 }));
  // links from the dish to the hovering quadcopters (positions below)
  const links = s('g', { class: 'links' },
    [[430, 460], [770, 410], [1010, 500]].map(([x, y], i) => s('path', { class: 'link', d: `M1198 604 Q${(1198 + x) / 2} ${y - 80} ${x} ${y + 14}`,
      delay: `${-i * 0.5}s` })));
  depth[2].append(links, station);

  // quadcopters hovering with sensor cones
  [[430, 460, 0.9], [770, 410, 0.75], [1010, 500, 1]].forEach(([x, y, k], i) => {
    depth[3].append(s('g', { transform: `translate(${x} ${y}) scale(${k})` },
      s('g', { class: 'hover', delay: `${-i * 1.3}s` }, quad())));
  });

  // unmanned surface vessel with its wake, unmanned ground vehicle on the sand
  depth[2].append(s('g', { transform: 'translate(170 760)' }, s('g', { class: 'patrol-sea' },
    s('path', { class: 'wake', d: 'M-10 6 L-150 -6 M-10 10 L-150 22' }),
    s('path', { class: 'hull', d: 'M-12 0 L110 0 L132 -10 L-6 -10 Z' }),
    s('path', { class: 'hull-top', d: 'M14 -10 L30 -26 L70 -26 L84 -10 Z' }),
    s('line', { class: 'mast-line', x1: 52, y1: -26, x2: 52, y2: -46 }),
    s('circle', { class: 'nav-light green', cx: 52, cy: -48, r: 2.4 }))));
  depth[2].append(s('g', { transform: 'translate(1330 820)' }, s('g', { class: 'patrol-land' },
    s('rect', { class: 'hull', x: -46, y: -26, width: 92, height: 22, rx: 5 }),
    s('rect', { class: 'hull-top', x: -18, y: -42, width: 40, height: 16, rx: 3 }),
    s('line', { class: 'mast-line', x1: 14, y1: -42, x2: 24, y2: -70 }),
    s('circle', { class: 'nav-light red', cx: 24, cy: -71, r: 2.4 }),
    s('rect', { class: 'track', x: -50, y: -6, width: 100, height: 12, rx: 6 }),
    [-34, -12, 10, 32].map((x) => s('circle', { class: 'wheel', cx: x, cy: 0, r: 4.5 })))));

  // fixed-wing drones crossing, and a swarm in formation
  depth[3].append(s('g', { transform: 'translate(0 360)' }, s('g', { class: 'fly fly-ltr' }, s('g', { class: 'bank' }, fixedWing()))));
  depth[3].append(s('g', { transform: 'translate(0 230) scale(0.55)' }, s('g', { class: 'fly fly-rtl' }, s('g', { transform: 'scale(-1 1)' }, fixedWing()))));
  const swarm = s('g', { class: 'fly fly-swarm' });
  [[0, 0], [-34, 16], [-34, -16], [-68, 32], [-68, -32], [-102, 48], [-102, -48]].forEach(([x, y], i) => {
    swarm.append(s('g', { transform: `translate(${x} ${y})` }, s('g', { class: 'hover small', delay: `${-i * 0.4}s` }, chevron())));
  });
  depth[3].append(s('g', { transform: 'translate(0 150)' }, swarm));

  // HUD scanning line (the corner frame and the coordinates are page elements below, pinned to the corners)
  svg.append(s('g', { class: 'hud' }, s('rect', { class: `scanline scan-${variant}`, x: 0, y: banner ? 300 : 0, width: 1600, height: 3 })));
  svg.append(s('rect', { class: 'vignette', x: 0, y: 0, width: 1600, height: 900 }));

  const wrap = document.createElement('div');
  wrap.className = `scene scene-wrap-${variant}`;
  wrap.setAttribute('aria-hidden', 'true');
  // The HUD frame: corners and coordinates pinned to the section's corners, whatever the window's shape.
  const frame = document.createElement('div');
  frame.className = 'scene-hud';
  for (const corner of ['ts', 'te', 'bs', 'be']) {
    const el = document.createElement('span');
    el.className = `hud-corner hud-${corner}`;
    frame.append(el);
  }
  const coords = document.createElement('span');
  coords.className = 'hud-coords';
  coords.dir = 'ltr';
  coords.textContent = 'N 24°28′  E 54°22′  ·  UAV · UGV · USV · UUV';
  frame.append(coords);
  wrap.append(svg, frame);
  return wrap;
}

// Mouse movement over a page section that holds a scene (the sign-in page, the home banner). It sets on the section
// --mx/--my (pointer position, -1..1 from the centre) and --px/--py (pointer position in px): the scene's depth layers
// shift by different distances, a soft gold light follows the pointer, and the sign-in card tilts toward it
// (css/scene.css). Nothing happens when the viewer prefers reduced motion.
export function followPointer(host) {
  if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  let frame = 0;
  let last = null;
  const apply = () => {
    frame = 0;
    const r = host.getBoundingClientRect();
    if (!last || !r.width || !r.height) return;
    const x = Math.min(Math.max(last.clientX - r.left, 0), r.width);
    const y = Math.min(Math.max(last.clientY - r.top, 0), r.height);
    host.style.setProperty('--mx', ((x / r.width) * 2 - 1).toFixed(3));
    host.style.setProperty('--my', ((y / r.height) * 2 - 1).toFixed(3));
    host.style.setProperty('--px', `${Math.round(x)}px`);
    host.style.setProperty('--py', `${Math.round(y)}px`);
  };
  host.addEventListener('pointerenter', () => host.classList.add('pointer-in'));
  host.addEventListener('pointermove', (e) => { last = e; if (!frame) frame = window.requestAnimationFrame(apply); });
  host.addEventListener('pointerleave', () => {
    last = null;
    host.classList.remove('pointer-in');
    host.style.setProperty('--mx', '0');
    host.style.setProperty('--my', '0');
  });
}
