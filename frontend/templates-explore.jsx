/* ============ AI-Video v2 — Templates (Explore view, integrated into app) ============ */
const { useState: teS, useEffect: teE, useCallback: teC } = React;
/* NOTE: uses the shared <Icon> from ui.jsx and the real app shell / nav. */

/* ---- prompt-body highlighter ({{vars}} + # headings) ---- */
function renderPromptBody(body) {
  return body.split('\n').map((line, i) => {
    const isHead = /^\s*#/.test(line);
    const parts = [];
    let last = 0;
    const re = /\{\{(\w+)\}\}/g; let m;
    while ((m = re.exec(line)) !== null) {
      if (m.index > last) parts.push(line.slice(last, m.index));
      parts.push(<span key={i+'-'+m.index} className="v">{m[0]}</span>);
      last = m.index + m[0].length;
    }
    if (last < line.length) parts.push(line.slice(last));
    return (
      <div key={i} className={isHead ? 'h' : ''}>{parts.length ? parts : line || '\u00a0'}</div>
    );
  });
}

/* ===================== ANIMATED PREVIEW ===================== */
function VideoPreview({ anim, run=false, big=false }) {
  let body = null;
  if (anim === 'lecture') body = (
    <>
      <div className="lec-fig" />
      <div className="ax lec-title" />
      <div className="ax lec-u" />
      <div className="ax lec-b lec-b1" />
      <div className="ax lec-b lec-b2" />
      <div className="ax lec-b lec-b3" />
    </>
  );
  else if (anim === 'news') body = (
    <>
      <div className="ax news-live"><i />LIVE</div>
      <div className="news-lower">
        <span className="news-tag">BREAKING</span>
        <div className="ax news-head" />
        <div className="ax news-sub" />
      </div>
      <div className="news-ticker"><div className="ax news-track">최신 소식 · 핵심 업데이트 · 주요 수치 · 다음 이야기 · 최신 소식 · 핵심 업데이트 ·</div></div>
    </>
  );
  else if (anim === 'doc') body = (
    <>
      <div className="ax doc-img" />
      <div className="doc-grad" />
      <div className="doc-bar t" /><div className="doc-bar b" />
      <div className="ax doc-cap" /><div className="ax doc-cap2" />
    </>
  );
  else if (anim === 'timeline') body = (
    <>
      <div className="tl-line" />
      <div className="ax tl-fill" />
      <div className="ax tl-bar n1" /><div className="ax tl-bar n2" /><div className="ax tl-bar n3" /><div className="ax tl-bar n4" />
      <div className="ax tl-node n1" /><div className="ax tl-node n2" /><div className="ax tl-node n3" /><div className="ax tl-node n4" />
      <div className="ax tl-head" />
    </>
  );
  else if (anim === 'whiteboard') body = (
    <svg className="wb-svg" viewBox="0 0 160 90" preserveAspectRatio="xMidYMid meet">
      <line className="ax wb-draw wb-s1" x1="22" y1="26" x2="92" y2="26" />
      <circle className="ax wb-draw wb-accent wb-s2" cx="122" cy="32" r="14" />
      <path className="ax wb-draw wb-s3" d="M34 52 L104 52" />
      <path className="ax wb-draw wb-accent wb-s4" d="M97 46 L104 52 L97 58" />
    </svg>
  );

  return (
    <div className={`te-stage ${big ? 'big' : ''} ${run ? 'run' : ''}`}>
      {body}
      {big && <div className="te-prevcap"><i />애니메이션 미리보기 · 자동 반복</div>}
    </div>
  );
}

/* ===================== CARDS ===================== */
function VideoCard({ t, onOpen }) {
  return (
    <div className="te-card" onClick={onOpen}>
      <VideoPreview anim={t.anim} />
      <div className="tc-body">
        <div className="tc-name">{t.name}<small>{t.ko}</small></div>
        <div className="tc-desc">{t.short}</div>
        <div className="tc-foot">
          <span className="tc-dur"><Icon name="clock" size={13} /> {t.duration}</span>
          <span className="tc-prev"><Icon name="play" size={12} /> 미리보기</span>
        </div>
      </div>
    </div>
  );
}

function PromptCard({ t, onOpen, videoTemplates = [] }) {
  return (
    <div className="tp-card" onClick={onOpen}>
      <div className="tp-top">
        <Icon name="message" size={15} style={{ color:'var(--accent)' }} />
        <span className="tp-name">{t.name}</span>
        <span className="tag-chip">{t.ko}</span>
      </div>
      <div className="tp-purpose">{t.purpose}</div>
      <div className="tp-desc">{t.desc}</div>
      <div className="tp-foot">
        <Icon name="link" size={13} />
        <span>적용 가능 {t.applies.length}개 스타일</span>
        <div className="tp-applies">
          {t.applies.map(id => {
            const v = videoTemplates.find(x => x.id === id);
            return <span key={id} className="tag-chip" style={{ fontSize:9.5 }}>{v ? v.name : id}</span>;
          })}
        </div>
      </div>
    </div>
  );
}

/* ===================== DETAIL CONTENT ===================== */
function VideoDetail({ t, onGenerate, onEdit }) {
  return (
    <>
      <div className="te-dscroll">
        <VideoPreview anim={t.anim} big run />
        <div className="te-metarow">
          <span className="tag-chip"><Icon name="clock" size={11} style={{ verticalAlign:'-1px', marginRight:4 }} />{t.duration}</span>
          <span className="tag-chip accent">{t.ko}</span>
        </div>

        <div className="te-sec">
          <div className="sl"><Icon name="doc" size={13} /> 설명</div>
          <p>{t.desc}</p>
        </div>

        <div className="te-sec">
          <div className="sl"><Icon name="layers" size={13} /> 예상 출력 구조</div>
          <div className="te-steps">
            {t.output.map((s, i) => (
              <div key={i} className="te-step">
                <div className="sd"><span className="sn">{String(i+1).padStart(2,'0')}</span><span className="st">{s}</span></div>
                {i < t.output.length-1 && <Icon name="arrowRight" size={14} className="arr" />}
              </div>
            ))}
          </div>
        </div>

        <div className="te-sec">
          <div className="sl"><Icon name="spark" size={13} /> 사용 시나리오</div>
          <div className="te-chips">
            {t.scenarios.map(s => <span key={s} className="te-chip">{s}</span>)}
          </div>
        </div>
      </div>
      <div className="te-df">
        <button className="btn ghost" style={{ flex:'none' }} onClick={onEdit}><Icon name="edit" size={15} /> 구조 편집</button>
        <button className="btn primary" onClick={onGenerate}><Icon name="spark" size={15} /> 이 스타일로 생성</button>
      </div>
    </>
  );
}

function PromptDetail({ t, copied, onCopy, onGenerate, onPickVideo, videoTemplates = [] }) {
  return (
    <>
      <div className="te-dscroll">
        <div className="te-sec">
          <div className="sl"><Icon name="spark" size={13} /> 프롬프트 목적</div>
          <p style={{ color:'var(--text)', fontWeight:550, fontSize:14 }}>{t.purpose}</p>
          <p style={{ marginTop:6 }}>{t.desc}</p>
        </div>

        <div className="te-sec">
          <div className="sl"><Icon name="message" size={13} /> 프롬프트 전문</div>
          <div className="te-prompt">{renderPromptBody(t.body)}</div>
        </div>

        <div className="te-sec">
          <div className="sl"><Icon name="link" size={13} /> 적용 가능한 Video Template</div>
          <div className="te-applies">
            {t.applies.map(id => {
              const v = videoTemplates.find(x => x.id === id);
              if (!v) return null;
              return (
                <div key={id} className="te-applyrow" onClick={() => onPickVideo(v)}>
                  <span className="ar-ic"><Icon name="template" size={15} /></span>
                  <span className="ar-t">{v.name}<small>{v.ko} · {v.duration}</small></span>
                  <Icon name="arrowRight" size={16} className="ar-go" />
                </div>
              );
            })}
          </div>
        </div>
      </div>
      <div className="te-df">
        <button className="btn ghost" style={{ flex:'none' }} onClick={onCopy}>
          <Icon name={copied ? 'check' : 'copy'} size={15} /> {copied ? '복사됨' : '복사'}
        </button>
        <button className="btn primary" onClick={onGenerate}><Icon name="spark" size={15} /> 이 프롬프트로 생성</button>
      </div>
    </>
  );
}

/* ===================== DETAIL SHELL (Drawer | Modal) ===================== */
function DetailShell({ mode, kind, title, sub, onClose, children }) {
  teE(() => {
    const h = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', h);
    return () => document.removeEventListener('keydown', h);
  }, [onClose]);

  const header = (
    <div className="te-dh">
      <div className="dh-l">
        <span className="dh-ic"><Icon name={kind === 'prompt' ? 'message' : 'template'} size={16} /></span>
        <div style={{ minWidth:0 }}>
          <div className="dh-kind">{kind === 'prompt' ? 'Prompt Template' : 'Video Template'}{sub ? ' · ' + sub : ''}</div>
          <h2>{title}</h2>
        </div>
      </div>
      <button className="te-dclose" onClick={onClose} aria-label="close"><Icon name="x" size={16} /></button>
    </div>
  );

  return (
    <>
      <div className="te-scrim" onClick={onClose} />
      <div className={mode === 'modal' ? 'te-modal' : 'te-drawer'} role="dialog" aria-modal="true">
        {header}
        {children}
      </div>
    </>
  );
}

/* ===================== SCREEN (Templates · Explore) ===================== */
function TemplatesExploreScreen({ view, setView, go, templates = [], videoTemplates: vtProp = [], error }) {
  const [tab, setTab] = teS('video');                 // video | prompt
  const [detailMode, setDetailMode] = teS('drawer');  // drawer | modal
  const [openV, setOpenV] = teS(null);
  const [openP, setOpenP] = teS(null);
  const [copied, setCopied] = teS(false);
  const videoTemplates = vtProp;
  const promptTemplates = templates;

  const closeAll = teC(() => { setOpenV(null); setOpenP(null); }, []);

  const copyPrompt = () => {
    if (openP && navigator.clipboard) navigator.clipboard.writeText(openP.body);
    setCopied(true); setTimeout(() => setCopied(false), 1600);
  };
  const pickVideoFromPrompt = (v) => { setOpenP(null); setTab('video'); setTimeout(() => setOpenV(v), 60); };
  const goGenerate = () => { closeAll(); go && go('generate'); };
  const goManage = () => { closeAll(); setView && setView('manage'); };

  return (
    <div className="md-screen">
      <div className="md-topbar">
        <div className="tt">
          <div className="ti"><Icon name="template" size={16} /></div>
          <h1>Templates</h1>
        </div>
        <div className="te-topbar-r">
          <div className="segmented te-viewtoggle">
            <button className="on" onClick={() => setView && setView('explore')}><Icon name="search" size={13} /> 탐색</button>
            <button onClick={goManage}><Icon name="settings" size={13} /> 관리</button>
          </div>
          <div className="te-modeswitch">
            <span className="lab">상세 보기</span>
            <div className="segmented">
              <button className={detailMode==='drawer'?'on':''} onClick={()=>setDetailMode('drawer')}><Icon name="panel" size={13} /> Drawer</button>
              <button className={detailMode==='modal'?'on':''} onClick={()=>setDetailMode('modal')}><Icon name="square" size={13} /> Modal</button>
            </div>
          </div>
        </div>
      </div>

      {/* two-family tabs */}
      <div className="te-tabbar">
        <button className={`te-segtab ${tab==='video'?'on':''}`} onClick={()=>setTab('video')}>
          <span className="tg-ic"><Icon name="film" size={18} /></span>
          <span className="tg-tx">
            <span className="tg-t">Video Templates <span className="tg-n">{videoTemplates.length}</span></span>
            <span className="tg-s">영상이 어떻게 보이는가 — 스타일 탐색</span>
          </span>
        </button>
        <button className={`te-segtab ${tab==='prompt'?'on':''}`} onClick={()=>setTab('prompt')}>
          <span className="tg-ic"><Icon name="message" size={18} /></span>
          <span className="tg-tx">
            <span className="tg-t">Prompt Templates <span className="tg-n">{promptTemplates.length}</span></span>
            <span className="tg-s">AI가 어떤 방식으로 쓰는가 — 프롬프트 탐색</span>
          </span>
        </button>
      </div>

      <div className="te-body">
        <div className="te-inner">
          <ApiError message={error}/>
          {tab === 'video' ? (
            <>
              <div className="te-intro">
                <div className="tx">
                  <h2>Video Templates</h2>
                  <p>각 카드에서 영상 스타일의 움직임을 바로 확인하고, 클릭하면 미리보기와 상세 정보를 볼 수 있습니다.</p>
                </div>
              </div>
              <div className="te-grid">
                {videoTemplates.map(t => <VideoCard key={t.id} t={t} onOpen={()=>setOpenV(t)} />)}
              </div>
            </>
          ) : (
            <>
              <div className="te-intro">
                <div className="tx">
                  <h2>Prompt Templates</h2>
                  <p>AI가 대본을 생성하는 방식을 결정하는 프롬프트입니다. 전문과 적용 가능한 스타일을 확인하세요.</p>
                </div>
              </div>
              <div className="tp-grid">
                {promptTemplates.map(t => <PromptCard key={t.id} t={t} videoTemplates={videoTemplates} onOpen={()=>setOpenP(t)} />)}
              </div>
            </>
          )}
        </div>
      </div>

      {openV && (
        <DetailShell mode={detailMode} kind="video" title={openV.name} sub={openV.ko} onClose={closeAll}>
          <VideoDetail t={openV} onGenerate={goGenerate} onEdit={goManage} />
        </DetailShell>
      )}
      {openP && (
        <DetailShell mode={detailMode} kind="prompt" title={openP.name} sub={openP.ko} onClose={closeAll}>
          <PromptDetail t={openP} copied={copied} onCopy={copyPrompt} onGenerate={goGenerate} onPickVideo={pickVideoFromPrompt} videoTemplates={videoTemplates} />
        </DetailShell>
      )}
    </div>
  );
}

Object.assign(window, { TemplatesExploreScreen });
