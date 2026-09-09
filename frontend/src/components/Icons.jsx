// Inline stroke icons - a tiny hand-picked set so we don't pull in an icon
// package we can't verify offline. All share one 24x24 grid and inherit color.
const S = { width: 20, height: 20, viewBox: "0 0 24 24", fill: "none",
  stroke: "currentColor", strokeWidth: 1.7, strokeLinecap: "round", strokeLinejoin: "round" };

export const Icon = {
  dashboard: (p) => (<svg {...S} {...p}><path d="M3 13h8V3H3zM13 21h8V3h-8zM3 21h8v-6H3z"/></svg>),
  fridge: (p) => (<svg {...S} {...p}><rect x="6" y="2" width="12" height="20" rx="2"/><path d="M6 10h12M9 6v1M9 13v2"/></svg>),
  add: (p) => (<svg {...S} {...p}><path d="M12 5v14M5 12h14"/></svg>),
  receipt: (p) => (<svg {...S} {...p}><path d="M5 3v18l2-1 2 1 2-1 2 1 2-1 2 1V3l-2 1-2-1-2 1-2-1-2 1z"/><path d="M9 8h6M9 12h6"/></svg>),
  recipe: (p) => (<svg {...S} {...p}><path d="M4 3h16v13a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5z"/><path d="M8 3v5M12 3v5M16 3v5"/></svg>),
  impact: (p) => (<svg {...S} {...p}><path d="M4 19V5M4 19h16M8 15l3-4 3 2 4-6"/></svg>),
  insight: (p) => (<svg {...S} {...p}><path d="M9 18h6M10 21h4"/><path d="M12 3a6 6 0 0 0-4 10c.7.7 1 1.3 1 2h6c0-.7.3-1.3 1-2a6 6 0 0 0-4-10z"/></svg>),
  model: (p) => (<svg {...S} {...p}><circle cx="12" cy="12" r="3"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3M6 6l2 2M16 16l2 2M18 6l-2 2M8 16l-2 2"/></svg>),
  clock: (p) => (<svg {...S} {...p}><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>),
  check: (p) => (<svg {...S} {...p}><path d="M20 6 9 17l-5-5"/></svg>),
  x: (p) => (<svg {...S} {...p}><path d="M18 6 6 18M6 6l12 12"/></svg>),
  trash: (p) => (<svg {...S} {...p}><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/></svg>),
  snow: (p) => (<svg {...S} {...p}><path d="M12 2v20M4.9 6.5 19.1 17.5M19.1 6.5 4.9 17.5M12 5 9 8m3-3 3 3M12 19l-3-3m3 3 3-3M5 9l1 3-1 3M19 9l-1 3 1 3"/></svg>),
  leaf: (p) => (<svg {...S} {...p}><path d="M4 20c0-8 6-14 16-14 0 10-6 14-14 14"/><path d="M4 20c4-6 8-8 12-9"/></svg>),
  drop: (p) => (<svg {...S} {...p}><path d="M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11z"/></svg>),
  coin: (p) => (<svg {...S} {...p}><circle cx="12" cy="12" r="9"/><path d="M15 9.5C15 8 13.7 7 12 7s-3 1-3 2.3c0 3 6 1.7 6 4.7 0 1.3-1.3 2.3-3 2.3s-3-1-3-2.3M12 5.5v13"/></svg>),
  fire: (p) => (<svg {...S} {...p}><path d="M12 3c1 3-1 4-1 6a2 2 0 0 0 4 0c0-1 0-2-.5-3 2 1.5 3.5 4 3.5 7a6 6 0 0 1-12 0c0-3 2-5 3-7 .5 1 1 2 3-3z"/></svg>),
  plate: (p) => (<svg {...S} {...p}><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4"/></svg>),
  arrowRight: (p) => (<svg {...S} {...p}><path d="M5 12h14M13 6l6 6-6 6"/></svg>),
  menu: (p) => (<svg {...S} {...p}><path d="M4 6h16M4 12h16M4 18h16"/></svg>),
  refresh: (p) => (<svg {...S} {...p}><path d="M21 12a9 9 0 1 1-3-6.7L21 8M21 4v4h-4"/></svg>),
  info: (p) => (<svg {...S} {...p}><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/></svg>),
  warn: (p) => (<svg {...S} {...p}><path d="M12 3 2 20h20zM12 10v4M12 17h.01"/></svg>),
  logout: (p) => (<svg {...S} {...p}><path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 12h10M13 8l-3 4 3 4"/></svg>),
  box: (p) => (<svg {...S} {...p}><path d="M3 8l9-5 9 5v8l-9 5-9-5z"/><path d="M3 8l9 5 9-5M12 13v8"/></svg>),
  mic: (p) => (<svg {...S} {...p}><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2M12 19v4M8 23h8"/></svg>),
  camera: (p) => (<svg {...S} {...p}><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>),
  sparkles: (p) => (<svg {...S} {...p}><path d="M12 2l2.4 7.2L21 12l-6.6 2.8L12 22l-2.4-7.2L3 12l6.6-2.8zM19 2l1 3 3 1-3 1-1 3-1-3-3-1 3-1z"/></svg>),
  message: (p) => (<svg {...S} {...p}><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>),
  cart: (p) => (<svg {...S} {...p}><circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/></svg>),
};
export default Icon;

