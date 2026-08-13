/* ============ AI-Video v2 — screens ============ */
const { useState:uS, useEffect:uE, useMemo:uM, useRef:uR } = React;

/* ---------------- Dashboard ---------------- */
function ApiError({ message }) {
  if (!message) return null;
  return (
    <div className="card pad" style={{marginBottom:16,color:'var(--bad)'}}>
      <b>API error</b>
      <div className="muted" style={{fontSize:13,marginTop:4}}>{message}</div>
    </div>
  );
}

function Dashboard({ runs, go, openRun, error }) {
  const counts = {
    running: runs.filter(r=>r.status==='running').length,
    done:    runs.filter(r=>r.status==='done').length,
    failed:  runs.filter(r=>r.status==='failed').length,
  };
  const recent = [...runs].sort((a,b)=>b.createdAt-a.createdAt).slice(0,5);
  return (
    <div className="page">
      <div className="topbar">
        <div>
          <h1 className="h1">Dashboard</h1>
          <p className="sub">Overview of your video generation runs.</p>
        </div>
        <button className="btn primary" onClick={()=>go('generate')}><Icon name="plus" size={17}/> New video</button>
      </div>

      <div className="grid-stats">
        <div className="card stat running" onClick={()=>go('runs','running')}>
          <div className="lab"><span className="dot"/>In progress</div>
          <div className="num">{counts.running}</div>
          <Icon name="arrowRight" size={16} className="arrow"/>
        </div>
        <div className="card stat done" onClick={()=>go('runs','done')}>
          <div className="lab"><span className="dot"/>Completed</div>
          <div className="num">{counts.done}</div>
          <Icon name="arrowRight" size={16} className="arrow"/>
        </div>
        <div className="card stat failed" onClick={()=>go('runs','failed')}>
          <div className="lab"><span className="dot"/>Failed</div>
          <div className="num">{counts.failed}</div>
          <Icon name="arrowRight" size={16} className="arrow"/>
        </div>
      </div>
      <ApiError message={error}/>

      <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:6}}>
        <h2 className="section-h" style={{margin:0}}>Recent videos</h2>
        <button className="btn ghost sm" onClick={()=>go('runs')}>View all <Icon name="arrowRight" size={14}/></button>
      </div>
      <div className="rowlist">
        {recent.map(r => (
          <div key={r.id} className="runrow" onClick={()=>openRun(r.id)}>
            <div className={`thumb ${r.status==='done'?'play':''}`}/>
            <div className="meta">
              <div className="title">{r.topic}</div>
              <div className="id">{r.template} · {r.duration}</div>
            </div>
            <StatusPill status={r.status}/>
            <div className="when">{r.status==='running'? STAGES[r.stageIndex]?.label : relTime(r.endedAt||r.createdAt)}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ---------------- Generate ---------------- */
const PROFILE_KO = { LECTURE: '강의형', SHORTS: '쇼츠형' };
const PROMPT_TEMPLATE_LABELS = {
  writer_system: '일반 강의',
  'writer_system.md': '일반 강의',
};
function promptTemplateLabel(name) {
  if (!name) return '';
  return PROMPT_TEMPLATE_LABELS[name] || PROMPT_TEMPLATE_LABELS[String(name).replace(/\.md$/, '')] || name;
}
const GENERATE_TTS_PROVIDERS = [
  ['chatterbox', 'chatterbox (default)'],
  ['azure', 'azure'],
];

function Generate({ onCreate, templates = [], profiles = [], error, prefill, onPrefillApplied }) {
  const [topic,setTopic] = uS('');
  const [contents,setContents] = uS('');
  const [template,setTemplate] = uS('');
  const [profile,setProfile] = uS('');
  const [duration,setDuration] = uS('60s');
  const [customMin,setCustomMin] = uS('');
  const [provider,setProvider] = uS('OpenAI');
  const [lang,setLang] = uS('한국어');
  const [force,setForce] = uS(false);
  const [dry,setDry] = uS(false);
  const [run_type, setRunType] = uS('TEST');
  const [ttsProvider,setTtsProvider] = uS('chatterbox');

  const isLecture = profile === 'LECTURE';
  const durList = isLecture ? DURATIONS_LECTURE : DURATIONS_SHORTS;
  const isCustom = isLecture && duration === '직접 입력';
  const valid = topic.trim().length > 1 && templates.length > 0 && profiles.length > 0
    && (!isCustom || (customMin.trim() !== '' && !isNaN(parseInt(customMin,10))));

  uE(()=>{
    if (!template && templates.length) {
      const first = templates.find(t => t.size_bytes > 0) || templates[0];
      setTemplate(first.name);
    }
  }, [templates, template]);
  uE(()=>{
    if (!profile && profiles.length) {
      const lecture = profiles.find(p => p.name === 'LECTURE') || profiles[0];
      setProfile(lecture.name);
    }
  }, [profiles, profile]);
  uE(()=>{
    if (profile === 'LECTURE') setDuration('5분');
    else if (profile === 'SHORTS') setDuration('60s');
  }, [profile]);
  uE(()=>{
    if (!prefill) return;
    if (prefill.topic !== undefined) setTopic(prefill.topic);
    if (prefill.contents !== undefined) setContents(prefill.contents);
    if (prefill.template !== undefined) setTemplate(prefill.template);
    if (prefill.profile !== undefined) setProfile(prefill.profile);
    if (prefill.duration !== undefined) setDuration(prefill.duration);
    if (prefill.lang !== undefined) setLang(prefill.lang);
    if (prefill.force !== undefined) setForce(prefill.force);
    if (prefill.dry !== undefined) setDry(prefill.dry);
    if (prefill.run_type !== undefined) setRunType(prefill.run_type);
    onPrefillApplied && onPrefillApplied();
  }, [prefill]);

  function handleCreate() {
    let dur = duration;
    if (isCustom) {
      const mins = parseInt(customMin, 10);
      dur = `${mins}분`;
    }
    onCreate({topic:topic.trim(),contents,template,profile,duration:dur,provider,lang,force,dry,run_type,ttsProvider});
  }

  return (
    <div className="page">
      <div className="topbar">
        <div>
          <h1 className="h1">새 영상 만들기</h1>
        </div>
      </div>

      <div className="formgrid">
        <ApiError message={error}/>
        <div className="field">
          <label>주제</label>
          <input className="input" placeholder="예: 패션의 기본" value={topic} onChange={e=>setTopic(e.target.value)} autoFocus/>
        </div>
        <div className="field">
          <label>내용 <span className="hint">— 참고 자료나 핵심 포인트 (선택)</span></label>
          <textarea className="textarea" placeholder="참고 자료, 핵심 포인트, 또는 개요를 붙여넣으세요…" value={contents} onChange={e=>setContents(e.target.value)}/>
        </div>

        <div className="row2">
          <div className="field">
            <label>프롬프트 템플릿</label>
            <select className="select" value={template} onChange={e=>setTemplate(e.target.value)}>
              {templates.map(t=><option key={t.id} value={t.name} disabled={t.size_bytes === 0}>{promptTemplateLabel(t.name)}{t.size_bytes === 0 ? ' (비어있음)' : ''}</option>)}
            </select>
          </div>
          <div className="field">
            <label>영상 유형</label>
            <select className="select" value={profile} onChange={e=>setProfile(e.target.value)}>
              {profiles.map(p=><option key={p.name} value={p.name}>{PROFILE_KO[p.name] || p.name}</option>)}
            </select>
          </div>
        </div>

        <div className="field">
          <label>영상 길이</label>
          <div className="chips">
            {durList.map(d=><button key={d} className={`chip ${duration===d?'on':''}`} onClick={()=>setDuration(d)}>{d}</button>)}
          </div>
          {isCustom && (
            <div style={{marginTop:8,display:'flex',alignItems:'center',gap:8}}>
              <input className="input" style={{width:100}} type="number" min="1" placeholder="분" value={customMin} onChange={e=>setCustomMin(e.target.value)}/>
              <span className="muted" style={{fontSize:13}}>분 단위 입력</span>
            </div>
          )}
        </div>

        <div className="field">
          <label>언어</label>
          <select className="select" value={lang} onChange={e=>setLang(e.target.value)}>
            {LANGS.map(l=><option key={l}>{l}</option>)}
          </select>
        </div>

        <div className="field">
          <label>TTS Provider</label>
          <select className="select" value={ttsProvider} onChange={e=>setTtsProvider(e.target.value)}>
            {GENERATE_TTS_PROVIDERS.map(([id,label])=><option key={id} value={id}>{label}</option>)}
          </select>
        </div>

        <div className="field">
          <label>실행 유형</label>
          <div className="chips">
            <button className={`chip ${run_type==='TEST'?'on':''}`} onClick={()=>setRunType('TEST')}>TEST</button>
            <button className={`chip ${run_type==='PRODUCTION'?'on':''}`} onClick={()=>setRunType('PRODUCTION')}>PRODUCTION</button>
          </div>
        </div>

        <div className="row2">
          <div className="toggle-field" onClick={()=>setForce(f=>!f)}>
            <div><div className="tf-t">강제 재생성</div><div className="tf-d">캐시 무시, 전 단계 재빌드</div></div>
            <div className={`sw ${force?'on':''}`}/>
          </div>
          <div className="toggle-field" onClick={()=>setDry(d=>!d)}>
            <div><div className="tf-t">테스트 실행</div><div className="tf-d">계획만 — 음성/렌더 없음</div></div>
            <div className={`sw ${dry?'on':''}`}/>
          </div>
        </div>

        <div style={{display:'flex',gap:12,alignItems:'center',marginTop:4}}>
          <button className="btn primary" disabled={!valid} onClick={handleCreate}>
            <Icon name="spark" size={17}/> 생성하기
          </button>
          {!valid && <span className="muted" style={{fontSize:13}}>{templates.length === 0 || profiles.length === 0 ? '템플릿과 프로필이 로드되어야 생성할 수 있습니다.' : topic.trim().length <= 1 ? '주제를 입력해주세요.' : '영상 길이(분)를 입력해주세요.'}</span>}
        </div>
      </div>
    </div>
  );
}

/* ---------------- Runs list ---------------- */
function Runs({ runs, filter, setFilter, openRun, go, error, onReload, toast, queueStatus }) {
  const [q,setQ] = uS('');
  const [page, setPage] = uS(1);
  const [pageSize, setPageSize] = uS(30);
  const [typeFilter, setTypeFilter] = uS('all');
  const [bulkDeleting, setBulkDeleting] = uS(false);
  const [showBulkModal, setShowBulkModal] = uS(false);
  const [bulkModalInput, setBulkModalInput] = uS('');
  const [selectedIds, setSelectedIds] = uS(new Set());
  const [bulkCancelling, setBulkCancelling] = uS(false);
  const [showBulkCancelModal, setShowBulkCancelModal] = uS(false);
  const [bulkCancelAll, setBulkCancelAll] = uS(false);
  const counts = {
    all: runs.length,
    queued: runs.filter(r=>r.status==='queued').length,
    running: runs.filter(r=>r.status==='running').length,
    done: runs.filter(r=>r.status==='done').length,
    failed: runs.filter(r=>r.status==='failed').length,
    cancelled: runs.filter(r=>r.status==='cancelled').length,
    production: runs.filter(r=>r.run_type==='PRODUCTION').length,
    test: runs.filter(r=>r.run_type==='TEST'||!r.run_type).length,
  };
  const list = uM(()=>{
    let l = [...runs].sort((a,b)=>b.createdAt-a.createdAt);
    if (filter==='queued') {
      l = l.filter(r=>r.status==='queued').sort((a,b)=>(a.queue_position??Infinity)-(b.queue_position??Infinity));
    } else if (filter!=='all') {
      l = l.filter(r=>r.status===filter);
    }
    if (typeFilter==='production') l = l.filter(r=>r.run_type==='PRODUCTION');
    else if (typeFilter==='test') l = l.filter(r=>r.run_type==='TEST'||!r.run_type);
    const qq = q.trim().toLowerCase();
    if (qq) l = l.filter(r=> r.topic.toLowerCase().includes(qq) || r.id.toLowerCase().includes(qq));
    return l;
  },[runs,filter,typeFilter,q]);
  const totalPages = Math.max(1, Math.ceil(list.length / pageSize));
  const pagedList = uM(()=>list.slice((page-1)*pageSize, page*pageSize), [list, page, pageSize]);
  uE(()=>{ setPage(1); }, [filter, typeFilter]);

  const FILTERS = [['all','All'],['queued','Queue'],['running','Running'],['done','Done'],['failed','Failed'],['cancelled','Cancelled']];
  const TYPE_FILTERS = [['all','전체'],['production','운영'],['test','테스트']];
  const anyRunning = counts.running>0;

  function handleBulkDeleteTest() {
    const testCount = counts.test;
    if (testCount === 0) { toast && toast({ kind:'info', title:'알림', body:'삭제할 TEST Run이 없습니다.' }); return; }
    setBulkModalInput('');
    setShowBulkModal(true);
  }

  function confirmBulkDelete() {
    setShowBulkModal(false);
    setBulkDeleting(true);
    bulkDeleteTestRunsAPI()
      .then(res => {
        const body = `${res.deleted_count}개 삭제 완료${res.skipped_running > 0 ? ` (RUNNING ${res.skipped_running}개 제외)` : ''}`;
        toast && toast({ kind:'ok', title:'TEST Run 삭제', body });
        onReload && onReload();
      })
      .catch(e => { toast && toast({ kind:'error', title:'삭제 실패', body: e.message }); })
      .finally(() => setBulkDeleting(false));
  }

  const avgMs = queueStatus?.avg_runtime_minutes != null ? queueStatus.avg_runtime_minutes * 60 * 1000 : null;

  function fmtETA(ms) {
    return new Date(ms).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
  }

  function runETA(r) {
    if (!avgMs || r.queue_position == null) return null;
    const startMs = Date.now() + (r.queue_position - 1) * avgMs;
    return { start: startMs, end: startMs + avgMs };
  }

  function toggleSelect(id, e) {
    e.stopPropagation();
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  function toggleSelectAll(e) {
    e.stopPropagation();
    const queuedIds = pagedList.filter(r => r.status === 'queued').map(r => r.id);
    const allSel = queuedIds.length > 0 && queuedIds.every(id => selectedIds.has(id));
    setSelectedIds(allSel ? new Set() : new Set(queuedIds));
  }

  function handleBulkCancel(all) {
    setBulkCancelAll(all);
    setShowBulkCancelModal(true);
  }

  function confirmBulkCancel() {
    setShowBulkCancelModal(false);
    setBulkCancelling(true);
    const ids = bulkCancelAll ? null : [...selectedIds];
    bulkCancelQueuedAPI(ids)
      .then(res => {
        toast && toast({ kind: 'ok', title: '취소 완료', body: `${res.cancelled_count}개 취소 완료` });
        setSelectedIds(new Set());
        onReload && onReload();
      })
      .catch(e => toast && toast({ kind: 'error', title: '취소 실패', body: e.message }))
      .finally(() => setBulkCancelling(false));
  }

  return (
    <div className="page">
      <div className="topbar">
        <div>
          <h1 className="h1">Runs <span style={{fontSize:'0.85rem',fontWeight:400,color:'var(--muted)',marginLeft:6}}>{runs.length}개</span></h1>
          <p className="sub">Full generation history — filter, search, and open any run.</p>
        </div>
        <div style={{display:'flex',gap:10,alignItems:'center'}}>
          {anyRunning && <span className="poll"><span className="pd"/>live · 5s</span>}
          <button className="btn primary" onClick={()=>go('generate')}><Icon name="plus" size={17}/> New video</button>
        </div>
      </div>

      <div className="toolbar">
        <div className="segmented">
          {FILTERS.map(([k,l])=>(
            <button key={k} className={filter===k?'on':''} onClick={()=>{ setFilter(k); setPage(1); }}>
              {l}<span className="cnt">{counts[k]}</span>
            </button>
          ))}
        </div>
        <div className="search">
          <Icon name="search" size={16} className="ic"/>
          <input placeholder="Search title or run id…" value={q} onChange={e=>{ setQ(e.target.value); setPage(1); }}/>
        </div>
      </div>
      <div className="toolbar" style={{marginTop:4,paddingTop:8,borderTop:'1px solid var(--border)'}}>
        <div className="segmented">
          {TYPE_FILTERS.map(([k,l])=>(
            <button key={k} className={typeFilter===k?'on':''} onClick={()=>{ setTypeFilter(k); setPage(1); }}>
              {l}<span className="cnt">{counts[k]}</span>
            </button>
          ))}
        </div>
        <button className="btn ghost sm" onClick={handleBulkDeleteTest} disabled={bulkDeleting||counts.test===0} style={{marginLeft:'auto',color:'var(--err,#e55)'}}>
          {bulkDeleting ? '삭제 중…' : `TEST ${counts.test}개 삭제`}
        </button>
      </div>
      <ApiError message={error}/>

      {filter==='queued' && queueStatus && (
        <div className="card pad" style={{marginBottom:12,display:'flex',gap:24,alignItems:'center',flexWrap:'wrap'}}>
          <div>
            <div className="muted" style={{fontSize:12,marginBottom:2}}>대기 중</div>
            <div style={{fontSize:22,fontWeight:700,color:'var(--accent-2)'}}>{queueStatus.queued_count}</div>
          </div>
          <div>
            <div className="muted" style={{fontSize:12,marginBottom:2}}>실행 중</div>
            <div style={{fontSize:22,fontWeight:700}}>{queueStatus.running_count}</div>
          </div>
          <div>
            <div className="muted" style={{fontSize:12,marginBottom:2}}>동시 실행 한도</div>
            <div style={{fontSize:22,fontWeight:700}}>{queueStatus.max_concurrent_runs}</div>
          </div>
          {queueStatus.avg_runtime_minutes != null && (
            <div>
              <div className="muted" style={{fontSize:12,marginBottom:2}}>평균 소요</div>
              <div style={{fontSize:22,fontWeight:700}}>{queueStatus.avg_runtime_minutes}<span style={{fontSize:13,fontWeight:400,marginLeft:2}}>분</span></div>
            </div>
          )}
          {queueStatus.avg_runtime_minutes != null && queueStatus.queued_count > 0 && (
            <div>
              <div className="muted" style={{fontSize:12,marginBottom:2}}>총 예상 대기</div>
              <div style={{fontSize:22,fontWeight:700}}>{Math.round(queueStatus.avg_runtime_minutes * queueStatus.queued_count)}<span style={{fontSize:13,fontWeight:400,marginLeft:2}}>분</span></div>
            </div>
          )}
          <div style={{marginLeft:'auto',display:'flex',gap:8,alignItems:'center'}}>
            <div className="muted" style={{fontSize:12,opacity:.7}}>☰ ⇈↑↓⇊ 순서 조정</div>
            <button className="btn ghost sm" style={{color:'var(--err,#e55)'}} disabled={bulkCancelling||queueStatus.queued_count===0} onClick={()=>handleBulkCancel(true)}>
              {bulkCancelling ? '취소 중…' : `전체 취소 (${queueStatus.queued_count})`}
            </button>
          </div>
        </div>
      )}

      {filter==='queued' && selectedIds.size > 0 && (
        <div style={{display:'flex',gap:8,alignItems:'center',marginBottom:8,padding:'8px 12px',background:'var(--surface-2,rgba(255,255,255,.05))',borderRadius:8,border:'1px solid var(--border)'}}>
          <span style={{fontSize:13,color:'var(--muted)'}}>{selectedIds.size}개 선택됨</span>
          <button className="btn ghost sm" style={{color:'var(--err,#e55)',marginLeft:'auto'}} disabled={bulkCancelling} onClick={()=>handleBulkCancel(false)}>
            선택 취소
          </button>
          <button className="btn ghost sm" style={{opacity:.6}} onClick={()=>setSelectedIds(new Set())}>선택 해제</button>
        </div>
      )}

      {list.length===0 ? (
        <div className="empty">
          <div className="eic"><Icon name="list" size={22}/></div>
          {filter==='queued' ? 'Queue가 비어 있습니다.' : 'No runs match this view.'}
        </div>
      ) : (
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr>
              {filter==='queued' && <th style={{width:32,padding:'0 4px'}}><input type="checkbox" checked={pagedList.filter(r=>r.status==='queued').length>0&&pagedList.filter(r=>r.status==='queued').every(r=>selectedIds.has(r.id))} onChange={toggleSelectAll} onClick={e=>e.stopPropagation()}/></th>}
              <th>Status</th><th>Title</th><th>Created</th><th>Stage / ETA</th><th>Elapsed</th><th></th>
            </tr></thead>
            <tbody>
              {pagedList.map(r=>{
                const eta = r.status==='queued' ? runETA(r) : null;
                const st = r.status==='running'? STAGES[r.stageIndex]?.label
                  : r.status==='queued'? (r.queue_position != null ? `#${r.queue_position}번` : '대기 중')
                  : r.status==='failed'? (STAGES[r.failedAt]?.label ?? '?') : 'Done';
                return (
                  <tr key={r.id} onClick={()=>openRun(r.id)}>
                    {filter==='queued' && (
                      <td style={{padding:'0 4px'}} onClick={e=>e.stopPropagation()}>
                        {r.status==='queued' && <input type="checkbox" checked={selectedIds.has(r.id)} onChange={e=>toggleSelect(r.id,e)}/>}
                      </td>
                    )}
                    <td><StatusPill status={r.status}/></td>
                    <td><div className="tt">{r.topic}</div><div className="id">{r.id}</div></td>
                    <td className="muted mono">{fmtClock(r.createdAt)}</td>
                    <td className="muted">
                      <div>{st}</div>
                      {r.status==='queued' && !avgMs && (
                        <div style={{fontSize:10,marginTop:2,opacity:.5}}>ETA 없음 (완료 이력 부족)</div>
                      )}
                      {eta && (
                        <div style={{fontSize:11,marginTop:2,opacity:.7}}>
                          <span>시작 {fmtETA(eta.start)}</span>
                          <span style={{margin:'0 4px'}}>·</span>
                          <span>완료 {fmtETA(eta.end)}</span>
                        </div>
                      )}
                    </td>
                    <td className="muted mono">{elapsed(r)}</td>
                    <td style={{textAlign:'right'}}>
                      {r.status==='done' && <span className="btn ghost sm"><Icon name="download" size={15}/> MP4</span>}
                      {r.status==='failed' && <span className="btn ghost sm"><Icon name="retry" size={15}/> Retry</span>}
                      {r.status==='running' && <span className="btn ghost sm">View <Icon name="arrowRight" size={14}/></span>}
                      {r.status==='queued' && (
                        <span style={{display:'flex',gap:3,justifyContent:'flex-end'}}>
                          {[['⇈','top'],['↑','up'],['↓','down'],['⇊','bottom']].map(([lbl,dir])=>{
                            const dis = (dir==='top'||dir==='up') ? r.queue_position===1 : r.queue_position===queueStatus?.queued_count;
                            return <span key={dir} className="btn ghost sm" title={dir} style={{opacity:dis?0.4:1,pointerEvents:dis?'none':'auto'}} onClick={e=>{e.stopPropagation();moveQueueRunAPI(r.id,dir).then(()=>onReload&&onReload()).catch(err=>{if(toast)toast({kind:'error',title:'이동 실패',body:err.message});});}}>{lbl}</span>;
                          })}
                          <span className="btn ghost sm" style={{color:'var(--err,#e55)'}} onClick={e=>{e.stopPropagation();cancelRunAPI(r.id).then(()=>onReload&&onReload()).catch(err=>{if(toast)toast({kind:'error',title:'Cancel failed',body:err.message});});}}>Cancel</span>
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {list.length > 0 && (
        <div className="pagination">
          <select className="pg-size" value={pageSize} onChange={e=>{ setPageSize(+e.target.value); setPage(1); }}>
            {[10,30,100].map(n=><option key={n} value={n}>{n} / page</option>)}
          </select>
          <span className="pg-info">{`${(page-1)*pageSize+1}–${Math.min(page*pageSize,list.length)} / ${list.length}`}</span>
          <span className="pg-info" style={{marginLeft:4}}>{`Page ${page} / ${totalPages}`}</span>
          <button className="btn ghost sm pg-btn" disabled={page<=1} onClick={()=>setPage(p=>p-1)}>←</button>
          <button className="btn ghost sm pg-btn" disabled={page>=totalPages} onClick={()=>setPage(p=>p+1)}>→</button>
        </div>
      )}

      {showBulkModal && (
        <div className="modal-overlay" onClick={e=>{ if(e.target===e.currentTarget){ setShowBulkModal(false); } }}>
          <div className="modal-box">
            <div className="mh">TEST Run 일괄 삭제</div>
            <div className="mb">
              <strong>{counts.test}개</strong>의 TEST Run을 영구 삭제합니다.<br/>
              RUNNING 중인 Run은 자동으로 건너뜁니다.
              <span className="warn">⚠ PRODUCTION Run은 이 작업에 영향받지 않습니다.</span>
            </div>
            <label>계속하려면 아래에 <strong style={{fontFamily:'var(--mono)',color:'var(--bad)'}}>DELETE TEST</strong> 를 입력하세요</label>
            <input
              className="modal-input"
              placeholder="DELETE TEST"
              value={bulkModalInput}
              onChange={e=>setBulkModalInput(e.target.value)}
              onKeyDown={e=>{ if(e.key==='Enter' && bulkModalInput==='DELETE TEST') confirmBulkDelete(); }}
              autoFocus
            />
            <div className="mfoot">
              <button className="btn ghost sm" onClick={()=>setShowBulkModal(false)}>취소</button>
              <button className="btn danger sm" disabled={bulkModalInput!=='DELETE TEST'} onClick={confirmBulkDelete}>
                삭제 실행
              </button>
            </div>
          </div>
        </div>
      )}

      {showBulkCancelModal && (
        <div className="modal-overlay" onClick={e=>{ if(e.target===e.currentTarget){ setShowBulkCancelModal(false); } }}>
          <div className="modal-box">
            <div className="mh">Queue 취소 확인</div>
            <div className="mb">
              {bulkCancelAll
                ? <><strong>{queueStatus?.queued_count ?? '전체'}개</strong>의 QUEUED 항목을 모두 취소합니다.</>
                : <><strong>{selectedIds.size}개</strong> 선택 항목 중 QUEUED 상태인 것을 취소합니다.</>
              }
              <br/>RUNNING 중인 Run은 영향받지 않습니다.
            </div>
            <div className="mfoot">
              <button className="btn ghost sm" onClick={()=>setShowBulkCancelModal(false)}>돌아가기</button>
              <button className="btn danger sm" onClick={confirmBulkCancel}>
                취소 실행
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ---------------- Run Detail ---------------- */
function RunDetail({ run, loading, error, sub, setSub, onRetry, onRegenerate, back, toast, onReload }) {
  if (loading && !run) return (
    <div className="page"><div className="empty">
      <div className="eic"><Icon name="clock" size={22}/></div>
      Loading run...
    </div></div>
  );
  if (error && !run) return (
    <div className="page"><div className="empty">
      <div className="eic"><Icon name="alert" size={22}/></div>
      {error} <a onClick={back} style={{color:'var(--accent-2)',cursor:'pointer'}}>Back to Runs</a>
    </div></div>
  );
  if (!run) return (
    <div className="page"><div className="empty">
      <div className="eic"><Icon name="alert" size={22}/></div>
      Run not found. <a onClick={back} style={{color:'var(--accent-2)',cursor:'pointer'}}>Back to Runs</a>
    </div></div>
  );
  const states = stageStates(run);
  const pct = progressPct(run);
  const canCopyRunId = !!normalizeCopyText(run.id);
  const copyId = async (e) => {
    e?.preventDefault?.();
    e?.stopPropagation?.();
    const result = await copyTextToClipboard(run.id, { label: 'Run ID' });
    if (result.ok) toast({kind:'check',title:'Run ID copied',body:result.text});
    else toast({kind:'error',title:'Run ID copy failed',body:result.error});
  };
  const [cancelling, setCancelling] = uS(false);
  const [deleting, setDeleting] = uS(false);
  async function handleCancel() {
    setCancelling(true);
    try {
      await cancelRunAPI(run.id);
      toast({kind:'check',title:'Cancel requested',body:'Run will stop at next checkpoint.'});
    } catch(e) {
      toast({kind:'run',title:'Cancel failed',body:e.message});
    } finally { setCancelling(false); }
  }
  async function handleDelete() {
    if (!window.confirm(`"${run.topic}" 런을 삭제하시겠습니까?\n이 작업은 취소할 수 없습니다.`)) return;
    setDeleting(true);
    try {
      await deleteRunAPI(run.id);
      toast({kind:'check',title:'Run deleted',body:run.id});
      back();
    } catch(e) {
      toast({kind:'run',title:'Delete failed',body:e.message});
      setDeleting(false);
    }
  }

  const availableByKey = Object.fromEntries((run.available_artifacts || []).map(a=>[a.key,a]));
  const artifactDefs = [
    { key:'script', ext:'md', cls:'', name:'Source Content' },
    { key:'scenes', ext:'json', cls:'', name:'Scene JSON' },
    { key:'audio', ext:'zip', cls:'mp3', name:'Voiceover' },
    { key:'video', ext:'mp4', cls:'mp4', name:'Final video' },
  ];
  const artifacts = artifactDefs.map(def => {
    const actual = availableByKey[def.key];
    const size = actual ? actual.size_bytes < 1024*1024
      ? `${Math.max(1, Math.round(actual.size_bytes/1024))} KB`
      : `${(actual.size_bytes/1024/1024).toFixed(1)} MB` : '';
    const count = actual && actual.file_count > 1 ? `${actual.file_count} files · ` : '';
    return {...def, ready:!!actual, file:actual ? `${actual.filename} · ${count}${size}` : 'waiting for file…', href:actual ? `${API_BASE}${actual.download_url}` : null};
  });

  const SUBS = [['progress','Progress'],['artifacts','Artifacts'],['logs','Logs']];

  return (
    <div className="page">
      <button className="btn ghost sm" onClick={back} style={{marginBottom:14, marginLeft:-6}}>
        <Icon name="arrowRight" size={15} style={{transform:'rotate(180deg)'}}/> Runs
      </button>

      <div className="detail-head">
        <div>
          <h1 className="h1">{run.topic}</h1>
          <div className="crumb">/runs/{run.id}</div>
        </div>
        <div style={{display:'flex',gap:8,alignItems:'center'}}>
          {(run.status==='running' || run.status==='queued') && (
            <button className="btn danger sm" onClick={handleCancel} disabled={cancelling}>
              {cancelling ? 'Cancelling…' : run.status==='queued' ? 'Cancel Queue' : 'Cancel'}
            </button>
          )}
          <StatusPill status={run.status}/>
        </div>
      </div>

      <div className="card pad" style={{marginBottom:18}}>
        <div className="detail-head" style={{margin:0,alignItems:'center'}}>
          <dl className="kv" style={{flex:1}}>
            <dt>Run ID</dt><dd className="idval">{run.id}<button className="copybtn" onClick={copyId} title="Copy run ID" aria-label="Copy run ID" disabled={!canCopyRunId}><Icon name="copy" size={14}/></button></dd>
            <dt>Prompt Template</dt><dd>{run.prompt_filename ? promptTemplateLabel(run.prompt_filename) : <span className="muted">—</span>}</dd>
            <dt>Video Template</dt><dd>{run.video_template ? (
              run.video_templates_used && run.video_templates_used !== `["${run.video_template}"]`
                ? (() => { try { const a=JSON.parse(run.video_templates_used); return a.join(', '); } catch(e){ return run.video_template; } })()
                : run.video_template
            ) : <span className="muted">—</span>}</dd>
            <dt>Profile / Mode</dt><dd>{[run.mode, run.lang].filter(Boolean).join(' · ') || <span className="muted">—</span>}</dd>
            <dt>Duration</dt><dd>{run.target_duration_sec ? `${run.target_duration_sec}s` : run.duration || <span className="muted">—</span>}</dd>
            {run.sceneCount > 0 && <><dt>Scenes</dt><dd>{run.sceneCount} scenes</dd></>}
            <dt>Output</dt><dd>{
              run.status === 'done' && run.download_url
                ? <a href={run.download_url} className="link">final.mp4 · {run.duration}</a>
                : run.status === 'done'
                ? <span className="muted">최종 영상 없음</span>
                : run.status === 'failed'
                ? <span className="muted">생성 실패</span>
                : run.status === 'queued'
                ? <span className="muted">대기 중{run.queue_position != null ? ` (#${run.queue_position}번)` : ''}</span>
                : run.status === 'running'
                ? <span className="muted">생성 중…</span>
                : <span className="muted">스크립트 단계에서 중단됨</span>
            }</dd>
            <dt>Created</dt><dd className="mono" style={{fontSize:12.5}}>{fmtFull(run.createdAt)}</dd>
            <dt>{run.status==='running'?'Elapsed':run.status==='queued'?'Queue 진입':'Completed'}</dt>
            <dd className="mono" style={{fontSize:12.5}}>{run.status==='running'? elapsed(run)+' · running' : run.status==='queued'? fmtFull(run.createdAt)+' · 대기 중' : fmtFull(run.endedAt)}</dd>
            {run.tts_provider && <><dt>TTS Provider</dt><dd>{run.tts_provider}{run.tts_fallback_used ? <span className="muted" style={{marginLeft:6,fontSize:11}}>(fallback used)</span> : null}</dd></>}
            {run.tts_provider && <><dt>TTS Voice</dt><dd className="mono" style={{fontSize:12.5}}>{run.tts_voice || '—'}</dd></>}
            {run.tts_audio_duration_sec != null && <><dt>Audio Duration</dt><dd>{run.tts_audio_duration_sec.toFixed(1)}s</dd></>}
            {run.tts_cache_used != null && run.tts_provider && <><dt>TTS Cache</dt><dd>{run.tts_cache_used ? <span style={{color:'var(--good,#22c55e)'}}>Hit</span> : 'Miss'}</dd></>}
          </dl>
          {(run.status==='running' || run.status==='queued') && <span className="poll"><span className="pd"/>auto-refresh 5s</span>}
        </div>

        <div style={{marginTop:18}}>
          <Pipeline run={run}/>
          <div className="progressbar"><i style={{width:pct+'%'}}/></div>
          <div className="muted mono" style={{fontSize:11.5,marginTop:8,display:'flex',justifyContent:'space-between'}}>
            <span>{run.status==='running'? `Stage ${run.stageIndex+1}/${STAGES.length} — ${STAGES[run.stageIndex]?.label}` : run.status==='queued'? 'Queue 대기 중 — 실행 준비 완료' : run.status==='failed'? `Failed at ${STAGES[run.failedAt]?.label ?? 'unknown stage'}` : 'All stages complete'}</span>
            <span>{pct}%</span>
          </div>
        </div>
      </div>

      <div className="subtabs">
        {SUBS.map(([k,l])=>(
          <button key={k} className={`subtab ${sub===k?'on':''}`} onClick={()=>setSub(k)}>{l}
            {k==='artifacts' && <span className="b">{artifacts.filter(a=>a.ready).length}</span>}
          </button>
        ))}
      </div>

      {sub==='progress' && (
        <div>
          {run.status==='failed' && (
            <div className="failbox">
              <div className="fh">
                <div style={{display:'flex',alignItems:'center',gap:10}}>
                  <Icon name="alert" size={18} style={{color:'var(--bad)'}}/>
                  <b>Failed at {STAGES[run.failedAt]?.label ?? 'unknown'} stage</b>
                </div>
                <div style={{display:'flex',gap:8}}>
                  <button className="btn danger sm" onClick={()=>onRetry(run.id)}><Icon name="retry" size={15}/> Retry from {STAGES[run.failedAt]?.label ?? 'last stage'}</button>
                  <button className="btn ghost sm" onClick={handleDelete} disabled={deleting}><Icon name="x" size={15}/> Delete</button>
                </div>
              </div>
              <div className="codebox" style={{whiteSpace:'pre-wrap'}}>{run.error}</div>
            </div>
          )}
          {run.status==='done' && (
            <div>
              <div className="videoframe" onClick={()=>setSub('artifacts')} style={{cursor:'pointer'}}>
                <div className="playbtn"><Icon name="play" size={22}/></div>
                <div className="muted" style={{fontSize:13}}>Preview ready</div>
                <div className="vmeta">final.mp4 · 1080p · {run.duration}</div>
              </div>
              <div style={{marginTop:12,display:'flex',gap:8}}>
                <button className="btn ghost sm" onClick={()=>onRegenerate && onRegenerate(run)}>
                  <Icon name="retry" size={15}/> Regenerate
                </button>
                <button className="btn ghost sm" onClick={handleDelete} disabled={deleting}>
                  <Icon name="x" size={15}/> Delete
                </button>
              </div>
            </div>
          )}
          {run.status==='running' && (
            <div className="card pad" style={{marginTop:0}}>
              <div style={{display:'flex',alignItems:'center',gap:10,marginBottom:10}}>
                <div className="lab"><span className="dot"/>Running</div>
                <span className="muted" style={{fontSize:13}}>Stage {run.stageIndex+1}/{STAGES.length}</span>
              </div>
              <div style={{fontSize:14,fontWeight:600}}>{STAGES[run.stageIndex]?.label ?? '—'}</div>
              <div className="muted" style={{fontSize:13,marginTop:4}}>{STAGES[run.stageIndex]?.desc ?? ''}</div>
            </div>
          )}
          {run.status==='cancelled' && (
            <div className="failbox" style={{borderColor:'var(--border)'}}>
              <div className="fh">
                <div style={{display:'flex',alignItems:'center',gap:10}}>
                  <Icon name="x" size={18} style={{color:'var(--muted)'}}/>
                  <b>Run cancelled</b>
                </div>
                <div style={{display:'flex',gap:8}}>
                  <button className="btn ghost sm" onClick={()=>onRetry(run.id)}><Icon name="retry" size={15}/> Retry</button>
                  <button className="btn ghost sm" onClick={handleDelete} disabled={deleting}><Icon name="x" size={15}/> Delete</button>
                </div>
              </div>
            </div>
          )}
          {run.status==='queued' && (
            <div className="card pad" style={{marginTop:0,borderColor:'var(--accent-soft)'}}>
              <div style={{display:'flex',alignItems:'center',gap:10,marginBottom:10}}>
                <StatusPill status="queued"/>
                {run.queue_position != null && (
                  <span className="muted" style={{fontSize:13}}>대기 순서 #{run.queue_position}번</span>
                )}
              </div>
              <div style={{fontSize:14,fontWeight:600}}>실행 대기 중</div>
              <div className="muted" style={{fontSize:13,marginTop:4}}>다른 런 완료 후 자동으로 시작됩니다.</div>
              <div style={{marginTop:12,display:'flex',gap:8}}>
                <button className="btn danger sm" onClick={handleCancel} disabled={cancelling}>
                  {cancelling ? 'Cancelling…' : 'Cancel Queue'}
                </button>
                <button className="btn ghost sm" onClick={handleDelete} disabled={deleting}><Icon name="x" size={15}/> Delete</button>
              </div>
              <div style={{marginTop:10,display:'flex',gap:6,flexWrap:'wrap'}}>
                {[['⇈ 맨 위','top'],['↑ 위','up'],['↓ 아래','down'],['⇊ 맨 아래','bottom']].map(([lbl,dir])=>(
                  <button key={dir} className="btn ghost sm" disabled={(dir==='top'||dir==='up')&&run.queue_position===1} onClick={()=>moveQueueRunAPI(run.id,dir).then(()=>onReload&&onReload()).catch(err=>{if(toast)toast({kind:'error',title:'이동 실패',body:err.message});})}>{lbl}</button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {sub==='artifacts' && (
        <div className="arts">
          {artifacts.map(a=>{
            const ready = a.ready;
            return (
              <div key={a.name} className={`card art ${ready?'':'locked'}`}>
                <div className={`ext ${a.cls}`}>{a.ext.toUpperCase()}</div>
                <div className="info"><b>{a.name}</b><small>{a.file}</small></div>
                <div className="acts">
                  {ready ? <>
                    {a.cls==='mp4' && a.href ? <a className="btn sm" href={a.href} target="_blank" rel="noopener noreferrer"><Icon name="play" size={14}/> Preview</a> : null}
                    <a className="btn sm" href={a.href}><Icon name="download" size={14}/> Download</a>
                  </> : <span className="pill waiting"><Icon name="clock" size={11}/> pending</span>}
                </div>
              </div>
            );
          })}
          {run.status==='done' && (
            <div style={{display:'flex',gap:10,marginTop:6}}>
              {run.download_url ? <a className="btn primary" href={run.download_url}><Icon name="download" size={16}/> Download MP4</a> : <button className="btn primary" disabled><Icon name="download" size={16}/> Download MP4</button>}
              <button className="btn"><Icon name="folder" size={16}/> Open output folder</button>
            </div>
          )}
        </div>
      )}

      {sub==='logs' && <LogView run={run}/>}
    </div>
  );
}

/* ---------------- Settings ---------------- */
function Settings({ theme, setTheme, ttsProvider, ttsVoices = {}, saveTtsSettings }) {
  const OPTS = [['system','System','monitor'],['light','Light','sun'],['dark','Dark','moon']];
  const [providers, setProviders] = uS([]);
  const [voices, setVoices] = uS([]);
  const [gatewayOnline, setGatewayOnline] = uS(null);
  const [refreshing, setRefreshing] = uS(false);
  const [providerError, setProviderError] = uS('');
  const [voiceError, setVoiceError] = uS('');
  const [voicesLoading, setVoicesLoading] = uS(false);
  const voiceRequest = uR(0);

  const currentProvider = ttsProvider || 'azure';
  const currentVoice = ttsVoices[currentProvider] || '';

  const persistSettings = async (provider, voices) => {
    setProviderError('');
    try { await saveTtsSettings(provider, voices); }
    catch (e) { setProviderError(e.message || 'TTS settings save failed'); }
  };

  const loadProviders = async () => {
    const r = await fetch(`${API_BASE}/tts/providers`);
    if (!r.ok) throw new Error(`Provider status request failed (${r.status})`);
    const d = await r.json();
    setGatewayOnline(d.gateway_online);
    setProviders((d.providers || []).filter(p => !p.deprecated));
  };

  const loadVoices = async (providerId) => {
    const requestId = ++voiceRequest.current;
    setVoicesLoading(true);
    setVoiceError('');
    try {
      const r = await fetch(`${API_BASE}/tts/providers/${encodeURIComponent(providerId)}/voices`);
      if (!r.ok) {
        let errorMsg = `Voice request failed (HTTP ${r.status})`;
        try { const b = await r.json(); if (b.detail) errorMsg = b.detail; } catch (_) {}
        throw new Error(errorMsg);
      }
      const d = await r.json();
      if (requestId !== voiceRequest.current) return;
      const nextVoices = d.voices || [];
      setVoices(nextVoices);
    } catch (e) {
      if (requestId !== voiceRequest.current) return;
      setVoices([]);
      setVoiceError(e.message || 'Voice request failed');
    } finally {
      if (requestId === voiceRequest.current) setVoicesLoading(false);
    }
  };

  const doRefresh = async () => {
    setRefreshing(true);
    setProviderError('');
    try {
      await Promise.all([loadProviders(), loadVoices(currentProvider)]);
    } catch (e) {
      setProviderError(e.message || 'Provider status request failed');
    } finally {
      setRefreshing(false);
    }
  };

  uE(() => {
    setRefreshing(true);
    loadProviders()
      .catch(e => setProviderError(e.message || 'Provider status request failed'))
      .finally(() => setRefreshing(false));
  }, []);
  uE(() => { loadVoices(currentProvider); }, [currentProvider]);

  const languageLabel = (language) => ({multi:'Multi',ko:'한국어','ko-KR':'한국어',en:'English','en-US':'English',zh:'中文','zh-CN':'中文',ja:'日本語'}[language] || language || 'N/A');
  const providerStatus = (p) => !p.configured ? 'Not Configured' : p.operational===false ? 'API Error' : 'Configured';
  const providerStatusClass = (p) => !p.configured || p.operational===false ? 'not-configured' : 'configured';

  return (
    <div className="page">
      <div className="topbar"><div><h1 className="h1">Settings</h1><p className="sub">Personalize the studio.</p></div></div>
      <div className="card pad tts-settings-card">
        <div className="set-row">
          <div><div className="st">Theme</div><div className="sd">Applies across desktop &amp; mobile. System follows your OS.</div></div>
          <div className="theme-opts">
            {OPTS.map(([k,l,ic])=>(
              <button key={k} className={`theme-opt theme-${k} ${theme===k?'on':''}`} onClick={()=>setTheme(k)}
                style={{background: k==='light'?'#fbfbfa':k==='dark'?'#0e0e11':'linear-gradient(90deg,#fbfbfa 50%,#0e0e11 50%)'}}>
                <span className="tl" style={{color:k==='light'?'#1a1a1d':'#ededf0'}}>{l}</span>
              </button>
            ))}
          </div>
        </div>
        <div className="set-row tts-row">
          <div className="tts-section-head">
            <div><div className="st">Default TTS Provider</div><div className="sd">Used for API runs that do not specify a provider.</div></div>
            <button className="btn primary tts-refresh-btn" onClick={doRefresh} disabled={refreshing}>
              <Icon name="retry" size={16}/>{refreshing ? 'Refreshing…' : 'Refresh TTS'}
            </button>
          </div>
          <div className="tts-gateway-status" aria-label="TTS gateway status">
            <span><b>Gateway Status</b><small>Connection to TTS Gateway</small></span>
            <span className={`tts-status ${gatewayOnline===true?'ok':gatewayOnline===false?'bad':'neutral'}`}>
              {gatewayOnline===true?'ONLINE':gatewayOnline===false?'OFFLINE':'CHECKING'}
            </span>
          </div>
          {providerError && <div className="tts-error">{providerError}</div>}
          <div className="tts-provider-grid">
            {providers.map(p=>(
              <button key={p.id}
                className={`tts-provider-card ${currentProvider===p.id?'on':''}`}
                onClick={()=>{
                  setVoices([]);
                  if (currentProvider===p.id) loadVoices(p.id);
                  else { setVoicesLoading(true); persistSettings(p.id, ttsVoices); }
                }}
                aria-pressed={currentProvider===p.id}>
                <span className="tts-provider-name">{p.name}</span>
                <span className="tts-provider-source">{p.type==='local-gateway' ? `Gateway · :${p.port}` : 'Cloud provider'}</span>
                <span className="tts-provider-state"><span>Provider Status</span><b className={providerStatusClass(p)}>{providerStatus(p)}</b></span>
                {p.detail && <span className="tts-provider-detail" title={p.detail}>{p.detail}</span>}
              </button>
            ))}
          </div>
        </div>
        <div className="set-row tts-row">
          <div className="tts-voice-head">
            <div><div className="st">Default Voice per Provider</div><div className="sd">{voices.length} voice/capability option{voices.length===1?'':'s'} for the selected provider.</div></div>
          </div>
          {voiceError && <div className="tts-error">{voiceError}</div>}
          <div className="tts-voice-grid" aria-busy={voicesLoading}>
            {voicesLoading && <div className="tts-empty">Loading voices…</div>}
            {!voicesLoading && voices.length===0 && <div className="tts-empty">No voices returned by this provider.</div>}
            {!voicesLoading && voices.map(v=>(
              <button key={v.id}
                className={`tts-voice-card ${currentVoice===v.id?'on':''} ${v.status_label==='coming_soon'?'coming-soon':''}`}
                onClick={()=>{ if(v.status_label!=='coming_soon') persistSettings(currentProvider, {...ttsVoices,[currentProvider]:v.id}); }}
                aria-pressed={currentVoice===v.id}
                aria-disabled={v.status_label==='coming_soon'}
                title={v.status_label==='coming_soon'?'Coming Soon — not yet available':undefined}>
                <span className="tts-voice-eyebrow">{v.kind==='capability'?'Capability':'Voice Name'}</span>
                <strong>{v.name || v.id}</strong>
                {v.status_label==='coming_soon' && <span className="tts-coming-soon-badge">Coming Soon</span>}
                <span className="tts-voice-meta">
                  <span><small>Language</small>{v.uses_generate_language ? 'Uses Generate language' : languageLabel(v.language)}</span>
                  <span><small>Reference</small>{v.reference_required?'Required':'Not required'}</span>
                  <span><small>Status</small>{v.status_label==='coming_soon'?'Coming Soon':'Ready'}</span>
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { Dashboard, Generate, Runs, RunDetail, Settings });
