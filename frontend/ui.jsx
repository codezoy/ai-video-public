/* ============ AI-Video v2 — icons + shared UI ============ */
const { useState, useEffect, useRef } = React;

// ---- minimal line icon set (stroke, inherits color) ----
const PATHS = {
  home:'M3 10.5 12 3l9 7.5M5 9.5V20h5v-6h4v6h5V9.5',
  spark:'M12 3v4m0 10v4m9-9h-4M7 12H3m13.5-6.5-2.8 2.8M9.3 14.7l-2.8 2.8m11 0-2.8-2.8M9.3 9.3 6.5 6.5',
  layers:'M12 3 2 8.5 12 14l10-5.5L12 3ZM2 15.5 12 21l10-5.5M2 12 12 17.5 22 12',
  list:'M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01',
  settings:'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z M19.4 13a7.6 7.6 0 0 0 .1-2l2-1.6-2-3.4-2.4 1a7.6 7.6 0 0 0-1.7-1l-.4-2.5h-4l-.4 2.5a7.6 7.6 0 0 0-1.7 1l-2.4-1-2 3.4L4.5 11a7.6 7.6 0 0 0 0 2l-2 1.6 2 3.4 2.4-1a7.6 7.6 0 0 0 1.7 1l.4 2.5h4l.4-2.5a7.6 7.6 0 0 0 1.7-1l2.4 1 2-3.4-2-1.6Z',
  search:'M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16ZM21 21l-4.3-4.3',
  plus:'M12 5v14M5 12h14',
  download:'M12 3v12m0 0 4-4m-4 4-4-4M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2',
  folder:'M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z',
  play:'M6 4l14 8-14 8V4Z',
  retry:'M3 12a9 9 0 1 0 3-6.7M3 4v4h4',
  check:'M5 12.5 10 17l9-10',
  x:'M6 6l12 12M18 6 6 18',
  arrowRight:'M5 12h14m-6-6 6 6-6 6',
  copy:'M9 9V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-4M5 9h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2Z',
  alert:'M12 9v4m0 4h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z',
  clock:'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM12 7v5l3 2',
  film:'M3 4h18v16H3V4Zm0 4h18M3 16h18M7 4v16M17 4v16',
  doc:'M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9l-6-6Zm0 0v6h6',
  audio:'M9 18V6l10-2v12M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0Zm10-2a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z',
  sun:'M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10ZM12 1v2m0 18v2M4.2 4.2l1.4 1.4m12.8 12.8 1.4 1.4M1 12h2m18 0h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4',
  moon:'M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z',
  monitor:'M3 4h18v12H3V4Zm6 16h6m-3-4v4',
  template:'M3 4h18v5H3V4Zm0 9h7v7H3v-7Zm11 0h7v7h-7v-7Z',
  message:'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v10Z',
  panel:'M4 5h16v14H4V5Zm6 0v14',
  square:'M5 5h14v14H5V5Z',
  edit:'M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5Z',
  link:'M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1',
};
function Icon({ name, size=18, className='', style }) {
  return (
    <svg className={className} style={style} width={size} height={size} viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      {PATHS[name].split('M').filter(Boolean).map((d,i)=><path key={i} d={'M'+d} />)}
    </svg>
  );
}

function normalizeCopyText(value) {
  if (value == null) return '';
  const text = typeof value === 'string' ? value : String(value);
  return text.trim().length ? text : '';
}

async function copyTextToClipboard(value, { label = 'Value' } = {}) {
  const text = normalizeCopyText(value);
  if (!text) return { ok: false, reason: 'invalid', error: `${label} is empty`, text: '' };
  if (!navigator.clipboard || typeof navigator.clipboard.writeText !== 'function') {
    return { ok: false, reason: 'unsupported', error: 'Clipboard API is not available', text };
  }
  try {
    await navigator.clipboard.writeText(text);
    return { ok: true, text };
  } catch (error) {
    return {
      ok: false,
      reason: 'write-failed',
      error: error && error.message ? error.message : 'Clipboard write failed',
      text,
    };
  }
}

function StatusPill({ status }) {
  const label = { running:'RUNNING', done:'DONE', failed:'FAILED', cancelled:'CANCELLED', waiting:'QUEUED', queued:'QUEUED' }[status] || status;
  return <span className={`pill ${status}`}><span className="pdot" />{label}</span>;
}

const NAV = [
  { key:'dashboard', label:'Dashboard', icon:'home' },
  { key:'generate',  label:'Generate',  icon:'spark' },
  { key:'runs',      label:'Runs',      icon:'list' },
  { key:'templates', label:'Templates', icon:'template', div:true },
  { key:'settings',  label:'Settings',  icon:'settings', div:true },
];
const MOBILE_NAV = NAV.filter(n => n.key !== 'generate');

function Sidebar({ route, runningCount, go }) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="logo"><Icon name="film" size={17} /></div>
        <div className="name">AI-Video<small>creator studio</small></div>
      </div>
      {NAV.map(n => (
        <React.Fragment key={n.key}>
          {n.div && <div className="nav-div" />}
          <a className={`navlink ${route.name===n.key?'on':''}`} onClick={()=>go(n.key)}>
            <Icon name={n.icon} size={18} className="ic" />
            {n.label}
            {n.key==='runs' && runningCount>0 && <span className="count">{runningCount}</span>}
          </a>
        </React.Fragment>
      ))}
      <div className="grow" />
      <div className="who"><div className="av">C</div>creator@local</div>
    </aside>
  );
}

function BottomNav({ route, runningCount, go }) {
  const renderItem = n => (
    <a key={n.key} className={route.name===n.key?'on':''} onClick={()=>go(n.key)}>
      <Icon name={n.icon} size={20} />
      {n.label}
      {n.key==='runs' && runningCount>0 && <span className="nb">{runningCount}</span>}
    </a>
  );
  const leftItems = MOBILE_NAV.slice(0, 2);
  const rightItems = MOBILE_NAV.slice(2);

  return (
    <nav className="bottomnav" aria-label="Mobile navigation">
      {leftItems.map(renderItem)}
      <div className="bottomnav-gap" aria-hidden="true" />
      {rightItems.map(renderItem)}
      <a className={`bottomnav-fab ${route.name==='generate'?'on':''}`} onClick={()=>go('generate')} aria-label="Generate video">
        <Icon name="plus" size={24} />
      </a>
    </nav>
  );
}

function MobileTop({ theme, toggleTheme }) {
  return (
    <div className="mobile-top">
      <div className="brand">
        <div className="logo"><Icon name="film" size={16} /></div>
        <div className="name" style={{fontSize:15}}>AI-Video</div>
      </div>
      <button className="btn ghost sm" onClick={toggleTheme} aria-label="toggle theme">
        <Icon name={theme==='dark'?'sun':'moon'} size={18} />
      </button>
    </div>
  );
}

// ---- pipeline strip ----
function Pipeline({ run }) {
  const states = stageStates(run);
  return (
    <div className="pipeline">
      {STAGES.map((st,i) => {
        const s = states[i];
        const glyph = s==='done' ? <Icon name="check" size={12}/>
          : s==='failed' ? <Icon name="x" size={12}/>
          : s==='running' ? '●' : i+1;
        return (
          <div key={st.key} className={`pstep ${s}`} title={st.desc}>
            <div className="pi">{glyph}</div>
            <div className="pl">{st.label}</div>
          </div>
        );
      })}
    </div>
  );
}

// ---- log viewer ----
function LogView({ run }) {
  const lines = buildLog(run);
  const ref = useRef(null);
  useEffect(()=>{ if(ref.current) ref.current.scrollTop = ref.current.scrollHeight; }, [run.stageIndex, run.status]);
  return (
    <div className="logbox" ref={ref}>
      {lines.map((l,i)=>(
        <div key={i} className={l.state==='pending'?'pending':''}>
          <span className="ts">{l.ts?fmtClock(l.ts):'--:--'}</span>{' '}
          <span className={`tag ${l.state==='ok'?'':l.state==='bad'?'bad':l.state==='cur'?'':''}`}>[{l.tag}]</span>{' '}
          {l.msg}{l.state==='cur' && <span className="cur"> ▍</span>}
        </div>
      ))}
    </div>
  );
}

// ---- toast host ----
function Toasts({ toasts, onOpen }) {
  return (
    <div className="toasts">
      {toasts.map(t => (
        <div key={t.id} className={`toast ${t.kind}`}>
          <div className="tic"><Icon name={t.kind==='run'?'spark':'check'} size={16} /></div>
          <div className="tx"><b>{t.title}</b><small>{t.body}</small></div>
          {t.runId && <a onClick={()=>onOpen(t.runId)}>View →</a>}
        </div>
      ))}
    </div>
  );
}

Object.assign(window, { Icon, StatusPill, Sidebar, BottomNav, MobileTop, Pipeline, LogView, Toasts, NAV, normalizeCopyText, copyTextToClipboard });
