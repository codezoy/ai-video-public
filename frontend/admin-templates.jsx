/* ============ AI-Video v2 — Templates screen ============ */
const { useState: tUS, useMemo: tUM } = React;

const TODAY = '2026-06-14';

/* ---- drag-reorder stage editor ---- */
function StageEditor({ steps, onChange }) {
  const [dragI, setDragI] = tUS(null);
  const [overI, setOverI] = tUS(null);

  const setStep = (i, patch) => onChange(steps.map((s, j) => (j === i ? { ...s, ...patch } : s)));
  const addStep = () => onChange([...steps, { id: newStepId(), label: '', en: '', min: 1, max: 2, desc: '' }]);
  const delStep = (i) => onChange(steps.filter((_, j) => j !== i));

  const drop = (to) => {
    if (dragI === null || dragI === to) { setDragI(null); setOverI(null); return; }
    const next = [...steps];
    const [moved] = next.splice(dragI, 1);
    next.splice(to, 0, moved);
    onChange(next);
    setDragI(null); setOverI(null);
  };

  return (
    <div className="stage-list">
      {steps.map((s, i) => (
        <div key={s.id}
          className={`stage-row ${dragI === i ? 'drag' : ''} ${overI === i && dragI !== i ? 'over' : ''}`}
          onDragOver={(e) => { e.preventDefault(); setOverI(i); }}
          onDrop={() => drop(i)}>
          <div className="stage-top">
            <span className="stage-grip" draggable
              onDragStart={() => setDragI(i)}
              onDragEnd={() => { setDragI(null); setOverI(null); }}
              title="드래그하여 순서 변경">⠿</span>
            <span className="stage-num">{String(i + 1).padStart(2, '0')}</span>
            <span className="stage-name">
              {s.label || '새 단계'}{s.en && <small>{s.en}</small>}
            </span>
            <button className="btn ghost sm" onClick={() => delStep(i)} title="단계 삭제">
              <Icon name="x" size={15} />
            </button>
          </div>
          <div className="stage-fields">
            <div>
              <span className="mini-l">레이블</span>
              <input className="input sm" value={s.label} placeholder="단계 이름"
                onChange={(e) => setStep(i, { label: e.target.value })} />
            </div>
            <div>
              <span className="mini-l">최소 (분)</span>
              <input className="input sm mono-in" type="number" min="0" value={s.min}
                onChange={(e) => setStep(i, { min: +e.target.value })} />
            </div>
            <div>
              <span className="mini-l">최대 (분)</span>
              <input className="input sm mono-in" type="number" min="0" value={s.max}
                onChange={(e) => setStep(i, { max: +e.target.value })} />
            </div>
          </div>
          <div className="stage-desc">
            <span className="mini-l">설명</span>
            <input className="input sm" value={s.desc} placeholder="이 단계에서 다루는 내용"
              onChange={(e) => setStep(i, { desc: e.target.value })} />
          </div>
        </div>
      ))}
      <button className="btn stage-add" onClick={addStep}><Icon name="plus" size={15} /> 단계 추가</button>
    </div>
  );
}

/* ---- preview tab ---- */
function TemplatePreview({ t }) {
  return (
    <div className="preview-wrap">
      <div className="preview-cap"><Icon name="spark" size={13} /> 미리보기 — Generate 화면에서의 표시</div>
      <div className="prev-card">
        <div className="prev-tplrow">
          <span className="prev-dot" />
          <div style={{ flex: 1 }}>
            <div className="pt">{t.name || '제목 없음'}</div>
            <div className="pm">{t.steps.length}단계 · {t.band}</div>
          </div>
          <span className="tag-chip accent">선택됨</span>
        </div>
        <div className="prev-steps">
          {t.steps.map((s, i) => (
            <div key={s.id} className="prev-step">
              <span className="pn">{String(i + 1).padStart(2, '0')}</span>
              <span className="ps">{s.label || '—'}</span>
              <span className="pd">{s.min === s.max ? `${s.min}분` : `${s.min}-${s.max}분`}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ---- delete modal ---- */
function DeleteModal({ name, onCancel, onConfirm }) {
  return (
    <div className="overlay" onClick={onCancel}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="del-h" onClick={(e) => e.stopPropagation()}>
        <h3 id="del-h"><span className="micon"><Icon name="alert" size={18} /></span> 템플릿 삭제</h3>
        <div className="mbody">
          <b>"{name}"</b>를 삭제합니다. 이 작업은 되돌릴 수 없으며 Generate 화면에서도 제거됩니다.
        </div>
        <div className="modal-foot">
          <button className="btn" onClick={onCancel}>취소</button>
          <button className="btn danger" onClick={onConfirm}><Icon name="x" size={15} /> 삭제</button>
        </div>
      </div>
    </div>
  );
}

/* ---- screen (admin / management view) ---- */
function TemplatesManageScreen({ view, setView }) {
  const [templates, setTemplates] = tUS(loadTemplates);
  const [selId, setSelId] = tUS(null);
  const [draft, setDraft] = tUS(null);
  const [tab, setTab] = tUS('basic');
  const [q, setQ] = tUS('');
  const [saved, setSaved] = tUS(false);
  const [delOpen, setDelOpen] = tUS(false);
  const [mobileDetail, setMobileDetail] = tUS(false);

  const persist = (next) => { setTemplates(next); saveTemplates(next); };

  const stored = templates.find((t) => t.id === selId);
  const dirty = draft && stored && JSON.stringify(draft) !== JSON.stringify(stored);
  const isNew = draft && !stored;

  const select = (t) => { setSelId(t.id); setDraft(JSON.parse(JSON.stringify(t))); setTab('basic'); setSaved(false); setMobileDetail(true); };

  const newTemplate = () => {
    const t = {
      id: 'tpl_' + Math.random().toString(36).slice(2, 8),
      name: '', desc: '', band: '10-15분', isDefault: false, active: true, updatedAt: TODAY,
      steps: [{ id: newStepId(), label: '', en: '', min: 1, max: 2, desc: '' }],
    };
    persist([t, ...templates]);
    select(t);
    setTab('basic');
  };

  const save = () => {
    let d = { ...draft, updatedAt: TODAY };
    let next = templates.map((t) => (t.id === d.id ? d : t));
    if (d.isDefault) next = next.map((t) => (t.id === d.id ? t : { ...t, isDefault: false }));
    persist(next);
    setDraft(JSON.parse(JSON.stringify(d)));
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const remove = () => {
    persist(templates.filter((t) => t.id !== selId));
    setSelId(null); setDraft(null); setDelOpen(false); setMobileDetail(false);
  };

  const patch = (p) => setDraft((d) => ({ ...d, ...p }));

  const filtered = tUM(() => {
    const qq = q.trim().toLowerCase();
    if (!qq) return templates;
    return templates.filter((t) => t.name.toLowerCase().includes(qq) || t.desc.toLowerCase().includes(qq));
  }, [templates, q]);

  const TABS = [['basic', '기본 정보'], ['stages', '단계 설정'], ['preview', '미리보기']];

  return (
    <div className="md-screen">
      <div className="md-topbar">
        <div className="tt">
          <div className="ti"><Icon name="template" size={16} /></div>
          <h1>Templates</h1>
        </div>
        <div className="te-topbar-r">
          <div className="segmented te-viewtoggle">
            <button onClick={() => setView && setView('explore')}><Icon name="search" size={13} /> 탐색</button>
            <button className="on" onClick={() => setView && setView('manage')}><Icon name="settings" size={13} /> 관리</button>
          </div>
          <button className="btn primary" onClick={newTemplate}><Icon name="plus" size={16} /> New Template</button>
        </div>
      </div>

      <div className="md tpl" data-mobile={mobileDetail ? 'detail' : 'list'}>
        {/* ---- list ---- */}
        <div className="md-list">
          <div className="ls">
            <div className="search">
              <Icon name="search" size={16} className="ic" />
              <input placeholder="템플릿 검색…" value={q} onChange={(e) => setQ(e.target.value)} />
            </div>
          </div>
          <div className="lscroll">
            {templates.length === 0 ? null : filtered.length === 0 ? (
              <div className="md-empty" style={{ height: 'auto', padding: '40px 16px' }}>
                <div className="eic"><Icon name="search" size={20} /></div>
                <p style={{ margin: 0 }}>'{q}'와 일치하는 템플릿이 없습니다.</p>
              </div>
            ) : filtered.map((t) => (
              <div key={t.id} role="option" aria-selected={t.id === selId}
                className={`litem ${t.id === selId ? 'on' : ''} ${t.active ? '' : 'off'}`}
                onClick={() => select(t)}>
                <div className="lrow">
                  <Icon name="template" size={15} className="lic" />
                  <span className="lt">{t.name || '제목 없는 템플릿'}</span>
                  <span className={`tag-chip ${t.active ? 'ok' : 'faint'}`}>{t.active ? '활성' : '비활성'}</span>
                </div>
                <div className="lm">{t.steps.length}단계 · {t.band} · {t.isDefault ? '기본' : '사용자'}</div>
              </div>
            ))}
          </div>
        </div>

        {/* ---- detail ---- */}
        <div className="md-detail">
          {templates.length === 0 ? (
            <div className="md-empty">
              <div className="eic"><Icon name="template" size={24} /></div>
              <h2>아직 템플릿이 없습니다</h2>
              <p>영상 구조 템플릿을 만들어 Generate 화면에서 사용하세요.</p>
              <button className="btn primary" onClick={newTemplate}><Icon name="plus" size={16} /> 첫 번째 템플릿 만들기</button>
            </div>
          ) : !draft ? (
            <div className="md-empty">
              <div className="eic"><Icon name="layers" size={24} /></div>
              <h2>템플릿을 선택하세요</h2>
              <p>왼쪽 목록에서 템플릿을 선택해 편집하거나 새 템플릿을 만드세요.</p>
            </div>
          ) : (
            <div className="md-detail-in">
              <button className="btn ghost sm md-back" onClick={() => setMobileDetail(false)} style={{ marginBottom: 12, marginLeft: -6 }}>
                <Icon name="arrowRight" size={15} style={{ transform: 'rotate(180deg)' }} /> 목록으로
              </button>

              <div className="det-head">
                <div>
                  <h2 className="dt">
                    {dirty && <span className="unsaved-dot" title="저장되지 않은 변경" />}
                    {draft.name || '제목 없는 템플릿'}
                  </h2>
                  <div className="dmeta">
                    <span>마지막 수정: {draft.updatedAt}</span>
                    {draft.isDefault && <span className="tag-chip accent">기본</span>}
                    {!draft.active && <span className="tag-chip faint">비활성</span>}
                  </div>
                </div>
                <div className="det-acts">
                  {saved && <span className="saved-flag"><Icon name="check" size={15} /> 저장됨</span>}
                  <button className="btn sm" onClick={() => patch({ active: !draft.active })}>
                    {draft.active ? '비활성화' : '활성화'}
                  </button>
                  <button className="btn sm" style={{ color: 'var(--bad)' }} onClick={() => setDelOpen(true)}>삭제</button>
                  <button className="btn primary sm" disabled={!dirty && !isNew} onClick={save}>저장</button>
                </div>
              </div>

              <div className="segmented det-tabs">
                {TABS.map(([k, l]) => (
                  <button key={k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{l}</button>
                ))}
              </div>

              {tab === 'basic' && (
                <div className="formgrid">
                  <div className="field">
                    <label>템플릿명 <span className="hint">— 목록과 Generate에 표시됩니다</span></label>
                    <input className="input" value={draft.name} placeholder="예: 이운규식 7단 구조"
                      onChange={(e) => patch({ name: e.target.value })} autoFocus />
                  </div>
                  <div className="field">
                    <label>설명 <span className="hint">— 선택</span></label>
                    <textarea className="textarea" rows="3" value={draft.desc} placeholder="용도와 특징을 요약하세요…"
                      onChange={(e) => patch({ desc: e.target.value })} />
                  </div>
                  <div className="field" style={{ maxWidth: 280 }}>
                    <label>기본 영상 길이</label>
                    <select className="select" value={draft.band} onChange={(e) => patch({ band: e.target.value })}>
                      {LENGTH_BANDS.map((b) => <option key={b}>{b}</option>)}
                    </select>
                  </div>
                  <div className="toggle-field" onClick={() => patch({ isDefault: !draft.isDefault })}>
                    <div><div className="tf-t">기본 템플릿</div><div className="tf-d">Generate 화면의 기본값으로 사용합니다.</div></div>
                    <div className={`sw ${draft.isDefault ? 'on' : ''}`} />
                  </div>
                  <div className="toggle-field" onClick={() => patch({ active: !draft.active })}>
                    <div><div className="tf-t">활성화 상태</div><div className="tf-d">OFF이면 목록에 흐리게 표시되고 선택할 수 없습니다.</div></div>
                    <div className={`sw ${draft.active ? 'on' : ''}`} />
                  </div>
                </div>
              )}

              {tab === 'stages' && (
                <StageEditor steps={draft.steps} onChange={(steps) => patch({ steps })} />
              )}

              {tab === 'preview' && <TemplatePreview t={draft} />}
            </div>
          )}
        </div>
      </div>

      {delOpen && <DeleteModal name={draft?.name || '제목 없는 템플릿'} onCancel={() => setDelOpen(false)} onConfirm={remove} />}
    </div>
  );
}

Object.assign(window, { TemplatesManageScreen });
