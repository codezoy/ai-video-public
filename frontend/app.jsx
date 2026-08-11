/* ============ AI-Video v2 — app: routing, polling, theme ============ */
const { useState:US, useEffect:UE, useRef:UR, useCallback:UC } = React;

function parseHash() {
  const h = (location.hash || '#/dashboard').replace(/^#\//,'');
  const [path, query=''] = h.split('?');
  const parts = path.split('/').filter(Boolean);
  const qp = new URLSearchParams(query);
  if (parts[0]==='runs' && parts[1]) return { name:'detail', runId:decodeURIComponent(parts[1]), sub:qp.get('tab')||'progress' };
  if (parts[0]==='runs') return { name:'runs', filter:qp.get('status')||'all' };
  const name = parts[0]||'dashboard';
  const valid = ['dashboard','generate','runs','detail','settings','templates'].includes(name)?name:'dashboard';
  if (valid==='templates') return { name:'templates', view: qp.get('view')||'explore' };
  return { name: valid };
}

function App() {
  const [route,setRoute] = US(parseHash());
  const [runs,setRuns] = US([]);
  const [templates,setTemplates] = US([]);
  const [videoTemplates,setVideoTemplates] = US([]);
  const [profiles,setProfiles] = US([]);
  const [apiErrors,setApiErrors] = US({});
  const [detailRuns,setDetailRuns] = US({});
  const [detailLoading,setDetailLoading] = US(false);
  const [theme,setThemePref] = US(()=> localStorage.getItem('aiv2_theme') || 'dark');
  const [ttsProvider,setTtsProvider] = US(()=> localStorage.getItem('tts_provider') || 'azure');
  const [ttsVoices,setTtsVoices] = US(()=>{
    try { return JSON.parse(localStorage.getItem('tts_default_voices') || '{}'); }
    catch (_) { return {}; }
  });
  const [toasts,setToasts] = US([]);
  const [generatePrefill, setGeneratePrefill] = US(null);
  const [queueStatus, setQueueStatus] = US(null);
  const runsRef = UR(runs);

  UE(()=>{ runsRef.current = runs; }, [runs]);

  window.__AIVIDEO_STATE = {
    route,
    runs,
    templates,
    videoTemplates,
    profiles,
    apiErrors,
    counts: {
      all: runs.length,
      running: runs.filter(r=>r.status==='running').length,
      done: runs.filter(r=>r.status==='done').length,
      failed: runs.filter(r=>r.status==='failed').length,
      cancelled: runs.filter(r=>r.status==='cancelled').length,
    },
  };

  // ---- load runs from API on mount + periodic refresh ----
  UE(()=>{
    const fetchRuns = () => loadRunsAPI()
      .then(data => {
        setRuns(data);
        setApiErrors(es => ({...es, runs:null}));
      })
      .catch(e => {
        console.error('[API] loadRunsAPI failed:', e);
        setApiErrors(es => ({...es, runs:e.message}));
      });
    fetchRuns();
    const iv = setInterval(fetchRuns, 30000);
    return () => clearInterval(iv);
  }, []);

  UE(()=>{
    const fetchQueueStatus = () => loadQueueStatusAPI()
      .then(data => setQueueStatus(data))
      .catch(e => console.error('[API] loadQueueStatusAPI failed:', e));
    fetchQueueStatus();
    const iv = setInterval(fetchQueueStatus, 30000);
    return () => clearInterval(iv);
  }, []);

  UE(()=>{
    loadTemplatesAPI()
      .then(data => {
        setTemplates(data);
        setApiErrors(es => ({...es, templates:null}));
      })
      .catch(e => {
        console.error('[API] loadTemplatesAPI failed:', e);
        setApiErrors(es => ({...es, templates:e.message}));
      });
    loadVideoTemplatesAPI()
      .then(data => {
        setVideoTemplates(data);
        setApiErrors(es => ({...es, videoTemplates:null}));
      })
      .catch(e => {
        console.error('[API] loadVideoTemplatesAPI failed:', e);
        setApiErrors(es => ({...es, videoTemplates:e.message}));
      });
    loadProfilesAPI()
      .then(data => {
        setProfiles(data);
        setApiErrors(es => ({...es, profiles:null}));
      })
      .catch(e => {
        console.error('[API] loadProfilesAPI failed:', e);
        setApiErrors(es => ({...es, profiles:e.message}));
      });
  }, []);

  // ---- theme (system-aware) ----
  UE(()=>{
    const apply = () => {
      const sysDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      const eff = theme==='system' ? (sysDark?'dark':'light') : theme;
      document.documentElement.setAttribute('data-theme', eff);
    };
    apply();
    localStorage.setItem('aiv2_theme', theme);
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    if (theme==='system'){ mq.addEventListener('change', apply); return ()=>mq.removeEventListener('change', apply); }
  },[theme]);

  UE(()=>{
    fetch(`${API_BASE}/tts/settings`)
      .then(r=>{ if(!r.ok) throw new Error(`TTS settings request failed (${r.status})`); return r.json(); })
      .then(d=>{
        setTtsProvider(d.default_provider || 'azure');
        setTtsVoices(d.default_voices || {});
      })
      .catch(e=>console.error('[API] load TTS settings failed:', e));
  },[]);
  UE(()=>{ localStorage.setItem('tts_provider', ttsProvider); },[ttsProvider]);
  UE(()=>{ localStorage.setItem('tts_default_voices', JSON.stringify(ttsVoices)); },[ttsVoices]);

  const saveTtsSettings = UC(async (defaultProvider, defaultVoices)=>{
    setTtsProvider(defaultProvider);
    setTtsVoices(defaultVoices);
    const res = await fetch(`${API_BASE}/tts/settings`, {
      method:'PUT', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({default_provider:defaultProvider, default_voices:defaultVoices}),
    });
    if (!res.ok) {
      const err = await res.json().catch(()=>({}));
      throw new Error(err.detail || `TTS settings save failed (${res.status})`);
    }
  },[]);

  // ---- hash sync ----
  UE(()=>{
    const onHash = ()=> setRoute(parseHash());
    window.addEventListener('hashchange', onHash);
    return ()=> window.removeEventListener('hashchange', onHash);
  },[]);

  // ---- navigation helpers ----
  const go = UC((name, filter)=>{
    if (name==='runs' && filter) location.hash = `#/runs?status=${filter}`;
    else location.hash = `#/${name}`;
  },[]);
  const openRun = UC((id, tab='progress')=>{ location.hash = `#/runs/${id}${tab!=='progress'?`?tab=${tab}`:''}`; },[]);
  const setFilter = UC((f)=>{ location.hash = `#/runs?status=${f}`; },[]);
  const setTemplatesView = UC((v)=>{ location.hash = v==='manage' ? '#/templates?view=manage' : '#/templates'; },[]);
  const setSub = UC((tab)=>{
    const id = route.runId;
    location.hash = `#/runs/${id}${tab!=='progress'?`?tab=${tab}`:''}`;
  },[route.runId]);

  // ---- toast ----
  const toast = UC((t)=>{
    const id = Math.random().toString(36).slice(2);
    setToasts(ts=>[...ts,{...t,id}]);
    setTimeout(()=> setToasts(ts=>ts.filter(x=>x.id!==id)), 4200);
  },[]);

  const refreshRuns = UC(async ()=>{
    const data = await loadRunsAPI();
    setRuns(data);
    setApiErrors(es => ({...es, runs:null}));
    return data;
  },[]);

  // ---- create run via POST /runs ----
  const createRun = UC(async (cfg)=>{
    const body = {
      topic: cfg.topic,
      language: LANG_TO_API[cfg.lang] || 'ko',
      force: !!cfg.force,
      dry_run: !!cfg.dry,
      target_duration_sec: durationToSec(cfg.duration),
    };
    if (cfg.contents) body.contents = cfg.contents;
    if (cfg.template) body.prompt_filename = cfg.template + '.md';
    body.run_type = cfg.run_type || 'TEST';
    if (cfg.ttsProvider) body.tts_provider = cfg.ttsProvider;

    try {
      const res = await fetch(`${API_BASE}/runs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await res.json().catch(()=>({}));
        toast({ kind:'error', title:'Run failed to start', body: err.detail || `Server error ${res.status}` });
        return;
      }
      const data = await res.json();
      const runId = data.run_id;
      await refreshRuns().catch(e => {
        console.error('[API] refresh after POST /runs failed:', e);
        setApiErrors(es => ({...es, runs:e.message}));
      });
      toast({ kind:'run', title:'Run started', body: cfg.topic, runId });
      openRun(runId);
    } catch(e) {
      toast({ kind:'error', title:'Network error', body: e.message });
    }
  },[]);

  function secToDuration(sec) {
    if (!sec) return '60s';
    if (sec === 30) return '30s';
    if (sec === 60) return '60s';
    if (sec === 90) return '90s';
    if (sec === 180) return '3분';
    if (sec === 300) return '5분';
    if (sec === 600) return '10분';
    if (sec === 1200) return '20분';
    if (sec === 1800) return '30분';
    if (sec < 180) return '60s';
    return `${Math.round(sec / 60)}분`;
  }

  // ---- retry failed run: prefill Generate screen, user confirms ----
  const retryRun = UC((runId)=>{
    const run = runsRef.current.find(r => r.id === runId);
    if (!run) { toast({ kind:'info', title:'Run not found', body:'Please use Generate to start a new run' }); return; }
    setGeneratePrefill({
      topic: run.topic,
      contents: run.contents || '',
      template: (run.prompt_filename || '').replace(/\.md$/, ''),
      profile: run.profile_name || run.mode || 'SHORTS',
      duration: secToDuration(run.target_duration_sec),
      lang: run.lang === 'ko' ? '한국어' : run.lang === 'zh-CN' ? '中文' : 'English',
      force: true,
      dry: false,
    });
    go('generate');
  },[]);

  // ---- regenerate done run: prefill Generate screen, user confirms ----
  const regenerateRun = UC((run)=>{
    setGeneratePrefill({
      topic: run.topic,
      contents: run.contents || '',
      template: (run.prompt_filename || '').replace(/\.md$/, ''),
      profile: run.profile_name || run.mode || 'SHORTS',
      duration: secToDuration(run.target_duration_sec),
      lang: run.lang === 'ko' ? '한국어' : run.lang === 'zh-CN' ? '中文' : 'English',
      force: false,
      dry: false,
    });
    go('generate');
  },[]);

  // ---- poll running runs every 5s via GET /runs/:id ----
  UE(()=>{
    const pollAll = async () => {
      const running = runsRef.current.filter(r => r.status === 'running' || r.status === 'queued');
      if (running.length === 0) return;
      for (const run of running) {
        try {
          const res = await fetch(`${API_BASE}/runs/${run.id}`);
          if (!res.ok) {
            console.error(`[API] GET /runs/${run.id} failed: ${res.status}`);
            continue;
          }
          const apiRun = await res.json();
          const normalized = normalizeRun(apiRun);
          setRuns(rs => rs.map(r => r.id === run.id ? normalized : r));
          setDetailRuns(ds => ({...ds, [run.id]: normalized}));
        } catch(e) {
          console.error(`[API] poll run failed: ${run.id}`, e);
        }
      }
    };
    const iv = setInterval(pollAll, 5000);
    return ()=> clearInterval(iv);
  }, []);

  UE(()=>{
    if (route.name !== 'detail' || !route.runId) return;
    setDetailLoading(true);
    loadRunAPI(route.runId)
      .then(run => {
        setDetailRuns(ds => ({...ds, [route.runId]: run}));
        setRuns(rs => rs.some(r => r.id === run.id) ? rs.map(r => r.id === run.id ? run : r) : [run, ...rs]);
        setApiErrors(es => ({...es, detail:null}));
      })
      .catch(e => {
        console.error(`[API] loadRunAPI failed: ${route.runId}`, e);
        setApiErrors(es => ({...es, detail:e.message}));
      })
      .finally(() => setDetailLoading(false));
  }, [route.name, route.runId]);

  const runningCount = runs.filter(r=>r.status==='running').length;

  let screen;
  if (route.name==='dashboard') screen = <Dashboard runs={runs} go={go} openRun={openRun} error={apiErrors.runs}/>;
  else if (route.name==='generate') screen = <Generate onCreate={createRun} templates={templates} profiles={profiles} error={apiErrors.templates || apiErrors.profiles} prefill={generatePrefill} onPrefillApplied={()=>setGeneratePrefill(null)}/>;
  else if (route.name==='runs') screen = <Runs runs={runs} filter={route.filter||'all'} setFilter={setFilter} openRun={openRun} go={go} error={apiErrors.runs} onReload={refreshRuns} toast={toast} queueStatus={queueStatus}/>;
  else if (route.name==='detail') {
    const run = detailRuns[route.runId] || runs.find(r=>r.id===route.runId);
    screen = <RunDetail run={run} loading={detailLoading} error={apiErrors.detail} sub={route.sub||'progress'} setSub={setSub} onRetry={retryRun} onRegenerate={regenerateRun} back={()=>go('runs')} toast={toast} onReload={refreshRuns}/>;
  }
  else if (route.name==='settings') screen = <Settings theme={theme} setTheme={setThemePref} ttsProvider={ttsProvider} ttsVoices={ttsVoices} saveTtsSettings={saveTtsSettings}/>;
  else if (route.name==='templates') screen = (route.view==='manage')
    ? <TemplatesManageScreen view="manage" setView={setTemplatesView}/>
    : <TemplatesExploreScreen view="explore" setView={setTemplatesView} go={go} templates={templates} videoTemplates={videoTemplates} error={apiErrors.templates || apiErrors.videoTemplates}/>;

  const navName = route.name==='detail' ? 'runs' : route.name;
  const toggleTheme = ()=> setThemePref(t=> (document.documentElement.getAttribute('data-theme')==='dark')?'light':'dark');

  return (
    <div className="shell">
      <Sidebar route={{name:navName}} runningCount={runningCount} go={go}/>
      <div className="content">
        <MobileTop theme={document.documentElement.getAttribute('data-theme')} toggleTheme={toggleTheme}/>
        {screen}
      </div>
      <BottomNav route={{name:navName}} runningCount={runningCount} go={go}/>
      <Toasts toasts={toasts} onOpen={openRun}/>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App/>);
