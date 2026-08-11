/* ============ AI-Video v2 — Prompts screen ============ */
const { useState: pUS, useEffect: pUE, useRef: pUR, useMemo: pUM } = React;

const LINE_PX = 20.8; // 13px * 1.6 line-height

/* ---- highlighted code editor (transparent textarea over <pre> overlay) ---- */
function CodeEditor({ value, onChange, readOnly = false, flashVar = null }) {
  const taRef = pUR(null);
  const hlRef = pUR(null);
  const gutRef = pUR(null);
  const [focus, setFocus] = pUS(false);

  const lines = (value || '').split('\n');

  const syncScroll = () => {
    const ta = taRef.current;
    if (!ta) return;
    if (hlRef.current) { hlRef.current.scrollTop = ta.scrollTop; hlRef.current.scrollLeft = ta.scrollLeft; }
    if (gutRef.current) gutRef.current.scrollTop = ta.scrollTop;
  };

  // scroll to + select a flashed variable
  pUE(() => {
    if (!flashVar) return;
    const idx = (value || '').indexOf('{{' + flashVar + '}}');
    if (idx < 0) return;
    const lineNo = (value || '').slice(0, idx).split('\n').length - 1;
    const ta = taRef.current;
    if (ta) {
      ta.scrollTop = Math.max(0, lineNo * LINE_PX - 60);
      syncScroll();
      if (!readOnly) { ta.focus(); ta.setSelectionRange(idx, idx + flashVar.length + 4); }
    }
  }, [flashVar]);

  return (
    <div className={`code-editor ${focus ? 'focus' : ''} ${readOnly ? 'ro' : ''}`}>
      <div className="ce-gutter" ref={gutRef}>
        {lines.map((_, i) => <div key={i}>{i + 1}</div>)}
      </div>
      <div className="ce-area">
        <pre className="ce-hl" ref={hlRef} aria-hidden="true"
          dangerouslySetInnerHTML={{ __html: highlightPrompt(value, flashVar) + '\n' }} />
        <textarea className="ce-ta" ref={taRef} value={value} readOnly={readOnly}
          spellCheck="false" wrap="off"
          role="textbox" aria-multiline="true" aria-label="프롬프트 내용"
          placeholder="프롬프트 내용을 입력하세요…"
          onChange={(e) => onChange(e.target.value)}
          onScroll={syncScroll}
          onFocus={() => setFocus(true)} onBlur={() => setFocus(false)} />
      </div>
    </div>
  );
}

/* ---- variable panel ---- */
function VariablePanel({ body, onVarClick }) {
  const vars = detectVars(body);
  return (
    <div className="varpanel">
      <div className="varpanel-h">
        <span className="vt">변수 ({vars.length}개 감지됨)</span>
        <span className="vt" style={{ color: 'var(--faint)', fontFamily: 'var(--mono)', fontSize: 11 }}>{'{{ }}'} 자동 감지</span>
      </div>
      {vars.length === 0 ? (
        <div style={{ padding: '16px', color: 'var(--faint)', fontSize: 12.5 }}>
          본문에 <code style={{ fontFamily: 'var(--mono)', color: 'var(--accent-2)' }}>{'{{변수}}'}</code> 형태를 입력하면 자동으로 감지됩니다.
        </div>
      ) : (
        <table className="var-tbl">
          <tbody>
            {vars.map((name) => {
              const m = varMeta(name);
              return (
                <tr key={name}>
                  <td className="vn" onClick={() => onVarClick(name)} title="에디터에서 위치 강조">{'{{' + name + '}}'}</td>
                  <td className="vty">{m.type}</td>
                  <td className="vdesc">{m.desc}</td>
                  <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                    <span className={`tag-chip ${m.required ? 'bad' : 'faint'}`}>{m.required ? '필수' : '선택'}</span>
                    {!m.required && m.def && <span className="vdef" style={{ marginLeft: 8 }}>기본: {m.def}</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}

/* ---- version dropdown ---- */
function VersionDropdown({ prompt, viewing, onPick, onBranch, onCompare }) {
  const [open, setOpen] = pUS(false);
  const ref = pUR(null);
  pUE(() => {
    if (!open) return;
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, [open]);

  const ordered = [...prompt.versions].reverse(); // newest first
  return (
    <div className="verwrap" ref={ref}>
      <button className="btn sm verbtn" onClick={() => setOpen((o) => !o)}>
        버전: <span className="vcur">{viewing}</span>
        {viewing === prompt.currentVersion ? ' (현재)' : ''}
        <Icon name="arrowRight" size={13} style={{ transform: 'rotate(90deg)' }} />
      </button>
      {open && (
        <div className="verdrop">
          {ordered.map((ver) => (
            <div key={ver.v} className={`ver-item ${ver.v === prompt.currentVersion ? 'cur' : ''}`}
              onClick={() => { onPick(ver.v); setOpen(false); }}>
              <span className="vv">{ver.v}</span>
              <span className="vdate">{ver.date}</span>
              {ver.v === prompt.currentVersion && <span className="vnow">현재</span>}
            </div>
          ))}
          <div className="vsep" />
          <div className="ver-action" onClick={() => { onBranch(); setOpen(false); }}>
            <Icon name="plus" size={14} /> 새 버전으로 분기
          </div>
          {prompt.versions.length > 1 && (
            <div className="ver-action" onClick={() => { onCompare(); setOpen(false); }}>
              <Icon name="layers" size={14} /> 버전 비교…
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ---- diff view ---- */
function DiffView({ oldVer, newVer }) {
  const { left, right } = lineDiff(oldVer.body, newVer.body);
  return (
    <div className="diff">
      <div className="diff-col">
        <div className="diff-colh"><span className="tag-chip">{oldVer.v}</span> 이전</div>
        <div className="diff-body">
          {left.map((l, i) => (
            <div key={i} className={`diff-line ${l.del ? 'del' : ''}`}>
              <span className="sign">{l.del ? '-' : ' '}</span>{l.text || ' '}
            </div>
          ))}
        </div>
      </div>
      <div className="diff-col">
        <div className="diff-colh"><span className="tag-chip accent">{newVer.v}</span> 현재</div>
        <div className="diff-body">
          {right.map((l, i) => (
            <div key={i} className={`diff-line ${l.add ? 'add' : ''}`}>
              <span className="sign">{l.add ? '+' : ' '}</span>{l.text || ' '}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ---- new prompt form ---- */
function NewPromptForm({ existingIds, onCancel, onCreate }) {
  const [rid, setRid] = pUS('');
  const [name, setName] = pUS('');
  const [type, setType] = pUS('system');
  const [body, setBody] = pUS('');
  const idOk = /^[a-z0-9-]+$/i.test(rid) && !existingIds.includes(rid);
  const showIdErr = rid.length > 0 && !idOk;

  return (
    <div className="md-detail-in">
      <div className="det-head">
        <div><h2 className="dt">새 프롬프트</h2>
          <div className="dmeta"><span>파이프라인에서 호출할 새 프롬프트를 정의합니다.</span></div>
        </div>
      </div>
      <div className="formgrid" style={{ maxWidth: 'none' }}>
        <div className="row2">
          <div className="field">
            <label>역할 ID <span className="hint">— 영문·숫자·하이픈</span></label>
            <input className="input mono-in" value={rid} placeholder="custom-writer"
              onChange={(e) => setRid(e.target.value)} autoFocus />
            {showIdErr && <div className="hint" style={{ color: 'var(--bad)', marginTop: 6 }}>
              {existingIds.includes(rid) ? '이미 존재하는 ID입니다.' : '영문·숫자·하이픈만 사용할 수 있습니다.'}
            </div>}
          </div>
          <div className="field">
            <label>표시 이름</label>
            <input className="input" value={name} placeholder="예: 커스텀 작성기"
              onChange={(e) => setName(e.target.value)} />
          </div>
        </div>
        <div className="field" style={{ maxWidth: 220 }}>
          <label>유형</label>
          <select className="select" value={type} onChange={(e) => setType(e.target.value)}>
            <option value="system">system</option>
            <option value="user">user</option>
          </select>
        </div>
        <div className="field">
          <label>프롬프트 내용</label>
          <CodeEditor value={body} onChange={setBody} />
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
          <button className="btn" onClick={onCancel}>취소</button>
          <button className="btn primary" disabled={!idOk}
            onClick={() => onCreate({ id: rid, name: name || rid, type, body })}>
            <Icon name="check" size={15} /> 생성
          </button>
        </div>
      </div>
    </div>
  );
}

/* ---- screen ---- */
function PromptsScreen() {
  const [prompts, setPrompts] = pUS(loadPrompts);
  const [selId, setSelId] = pUS(null);
  const [viewing, setViewing] = pUS(null);      // version string being viewed
  const [body, setBody] = pUS('');               // editable body of current version
  const [mode, setMode] = pUS('edit');           // edit | diff | new
  const [filter, setFilter] = pUS('all');        // all | system | user
  const [flashVar, setFlashVar] = pUS(null);
  const [saved, setSaved] = pUS(false);
  const [copied, setCopied] = pUS(false);
  const [mobileDetail, setMobileDetail] = pUS(false);

  const persist = (next) => { setPrompts(next); savePrompts(next); };
  const sel = prompts.find((p) => p.id === selId);
  const onCurrent = sel && viewing === sel.currentVersion;
  const viewVerObj = sel && sel.versions.find((v) => v.v === viewing);
  const storedBody = onCurrent ? currentBody(sel) : (viewVerObj ? viewVerObj.body : '');
  const dirty = onCurrent && body !== storedBody;

  const select = (p) => {
    setSelId(p.id); setViewing(p.currentVersion); setBody(currentBody(p));
    setMode('edit'); setSaved(false); setMobileDetail(true);
  };

  const pickVersion = (v) => {
    setViewing(v); setMode('edit');
    const vo = sel.versions.find((x) => x.v === v);
    setBody(vo ? vo.body : '');
  };

  const flash = (name) => { setFlashVar(name); setTimeout(() => setFlashVar(null), 1200); };

  const save = () => {
    const next = prompts.map((p) => {
      if (p.id !== selId) return p;
      const versions = p.versions.map((v) => (v.v === p.currentVersion ? { ...v, body, date: TODAY } : v));
      return { ...p, versions, updatedAt: TODAY };
    });
    persist(next);
    setSaved(true); setTimeout(() => setSaved(false), 2000);
  };

  const branch = () => {
    const num = sel.versions.length + 1;
    const nv = 'v' + num;
    const next = prompts.map((p) => {
      if (p.id !== selId) return p;
      return { ...p, currentVersion: nv, updatedAt: TODAY, versions: [...p.versions, { v: nv, date: TODAY, body }] };
    });
    persist(next);
    setViewing(nv); setMode('edit');
  };

  const restore = () => {
    // copy viewed old body into the editor as an unsaved edit on current version
    setBody(viewVerObj ? viewVerObj.body : body);
    setViewing(sel.currentVersion);
    setMode('edit');
  };

  const copy = () => {
    navigator.clipboard && navigator.clipboard.writeText(body);
    setCopied(true); setTimeout(() => setCopied(false), 1600);
  };

  const startNew = () => { setMode('new'); setSelId(null); setMobileDetail(true); };

  const createPrompt = ({ id, name, type, body: nbody }) => {
    const np = {
      id, name, group: 'custom', type, desc: '사용자 정의 프롬프트', updatedAt: TODAY, currentVersion: 'v1',
      versions: [{ v: 'v1', date: TODAY, body: nbody }],
    };
    persist([...prompts, np]);
    select(np);
  };

  // diff = previous vs current version
  const diffPair = pUM(() => {
    if (!sel || sel.versions.length < 2) return null;
    const cur = sel.versions.find((v) => v.v === sel.currentVersion) || sel.versions[sel.versions.length - 1];
    const idx = sel.versions.indexOf(cur);
    const prev = sel.versions[idx - 1] || sel.versions[0];
    return { oldVer: prev, newVer: cur };
  }, [sel]);

  // filtered + grouped list
  const groups = pUM(() => {
    const list = prompts.filter((p) => filter === 'all' || p.type === filter);
    return {
      pipeline: list.filter((p) => p.group === 'pipeline'),
      custom: list.filter((p) => p.group === 'custom'),
    };
  }, [prompts, filter]);

  const renderRow = (p) => (
    <div key={p.id} role="option" aria-selected={p.id === selId}
      className={`litem ${p.id === selId ? 'on' : ''}`} onClick={() => select(p)}>
      <div className="lrow">
        <span className="lt mono">{p.name}</span>
        <span className={`tag-chip ${p.type === 'system' ? 'accent' : ''}`}>{p.type}</span>
      </div>
      <div className="lm">{p.desc} · {p.currentVersion}</div>
      <div className="lm faint">{p.updatedAt} 수정</div>
    </div>
  );

  const FILTERS = [['all', '전체'], ['system', 'system'], ['user', 'user']];

  return (
    <div className="md-screen">
      <div className="md-topbar">
        <div className="tt">
          <div className="ti"><Icon name="message" size={16} /></div>
          <h1>Prompts</h1>
        </div>
        <button className="btn primary" onClick={startNew}><Icon name="plus" size={16} /> New Prompt</button>
      </div>

      <div className="md prompt" data-mobile={mobileDetail ? 'detail' : 'list'}>
        {/* ---- list ---- */}
        <div className="md-list">
          <div className="ls">
            <div className="segmented" style={{ width: '100%' }}>
              {FILTERS.map(([k, l]) => (
                <button key={k} className={filter === k ? 'on' : ''} style={{ flex: 1, fontSize: 11 }}
                  onClick={() => setFilter(k)}>{l}</button>
              ))}
            </div>
          </div>
          <div className="lscroll">
            {groups.pipeline.length > 0 && <div className="sec-h">Pipeline</div>}
            {groups.pipeline.map(renderRow)}
            {groups.custom.length > 0 && <div className="sec-h">Custom</div>}
            {groups.custom.map(renderRow)}
            {groups.pipeline.length === 0 && groups.custom.length === 0 && (
              <div className="md-empty" style={{ height: 'auto', padding: '40px 16px' }}>
                <p style={{ margin: 0 }}>이 필터에 해당하는 프롬프트가 없습니다.</p>
              </div>
            )}
          </div>
        </div>

        {/* ---- editor ---- */}
        <div className="md-detail">
          {mode === 'new' ? (
            <NewPromptForm existingIds={prompts.map((p) => p.id)}
              onCancel={() => { setMode('edit'); setMobileDetail(false); }} onCreate={createPrompt} />
          ) : !sel ? (
            <div className="md-empty">
              <div className="eic"><Icon name="message" size={24} /></div>
              <h2>프롬프트를 선택하세요</h2>
              <p>왼쪽에서 파이프라인 단계의 프롬프트를 선택해 편집하거나 새 프롬프트를 만드세요.</p>
            </div>
          ) : (
            <div className="md-detail-in">
              <button className="btn ghost sm md-back" onClick={() => setMobileDetail(false)} style={{ marginBottom: 12, marginLeft: -6 }}>
                <Icon name="arrowRight" size={15} style={{ transform: 'rotate(180deg)' }} /> 목록으로
              </button>

              <div className="editor-head">
                <div className="editor-id">
                  {dirty && <span className="unsaved-dot" title="저장되지 않은 변경" />}
                  <div>
                    <div className="rname">{sel.name} <span className={`tag-chip ${sel.type === 'system' ? 'accent' : ''}`} style={{ verticalAlign: 'middle', marginLeft: 4 }}>{sel.type}</span></div>
                    <div className="rdesc">{sel.desc} · 마지막 수정: {sel.updatedAt}</div>
                  </div>
                </div>
                <div className="det-acts">
                  {saved && <span className="saved-flag"><Icon name="check" size={15} /> 저장됨</span>}
                  {copied && <span className="saved-flag"><Icon name="check" size={15} /> 복사됨</span>}
                  <VersionDropdown prompt={sel} viewing={viewing} onPick={pickVersion}
                    onBranch={branch} onCompare={() => setMode('diff')} />
                  <button className="btn sm" onClick={copy}><Icon name="copy" size={14} /> 복사</button>
                  <button className="btn primary sm" disabled={!dirty} onClick={save}>저장</button>
                </div>
              </div>

              {mode === 'diff' && diffPair ? (
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                    <span className="muted" style={{ fontSize: 13 }}>버전 비교 — {diffPair.oldVer.v} → {diffPair.newVer.v}</span>
                    <button className="btn sm" onClick={() => setMode('edit')}>
                      <Icon name="arrowRight" size={14} style={{ transform: 'rotate(180deg)' }} /> 편집으로 돌아가기
                    </button>
                  </div>
                  <DiffView oldVer={diffPair.oldVer} newVer={diffPair.newVer} />
                </div>
              ) : (
                <div>
                  {!onCurrent && (
                    <div className="banner warn">
                      <Icon name="alert" size={16} />
                      <span className="bx"><b>{viewing}</b> 버전을 보고 있습니다. 편집하려면 복원하세요.</span>
                      <span className="bacts">
                        <button className="btn sm" onClick={restore}>이 버전으로 복원</button>
                        <button className="btn sm" onClick={() => pickVersion(sel.currentVersion)}>현재 버전으로</button>
                      </span>
                    </div>
                  )}
                  <CodeEditor value={body} onChange={setBody} readOnly={!onCurrent} flashVar={flashVar} />
                  <VariablePanel body={body} onVarClick={flash} />
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { PromptsScreen });
