/* ============ AI-Video v2 — seed data + API integration ============ */

const STAGE_GROUP_MAP = {
  script:               'planning',
  polish:               'planning',
  critique:             'planning',
  regen:                'planning',
  scenes:               'planning',
  scene_review:         'planning',
  scene_quality:        'planning',
  content_repair:       'planning',
  topic_guard:          'planning',
  tts:                  'voice',
  whisper_align:        'voice',
  caption_segment:      'voice',
  caption_from_narration:'voice',
  caption_validate:     'voice',
  motion_anchor:        'visuals',
  assets:               'visuals',
  template:             'visuals',
  visual_plan:          'visuals',
  render:               'render',
  visual_correct:       'render',
  scene_render:         'render',
  final_concat:         'render',
  caption_overlay:      'render',
  compose:              'render',
  qa:                   'qa',
  final:                'qa',
};

const STAGES = [
  { key:'planning', label:'Planning', desc:'Script & scene generation' },
  { key:'voice',    label:'Voice',    desc:'Text-to-speech synthesis' },
  { key:'visuals',  label:'Visuals',  desc:'Caption & motion' },
  { key:'render',   label:'Render',   desc:'Video rendering' },
  { key:'qa',       label:'QA',       desc:'Quality assurance' },
];

const TEMPLATES = [];
const DURATIONS_SHORTS  = ['30s','60s','90s','3분'];
const DURATIONS_LECTURE = ['5분','10분','20분','30분','직접 입력'];
const DURATIONS = DURATIONS_SHORTS;
const PROVIDERS = ['OpenAI','Claude','Gemini'];
const LANGS = ['한국어','English','中文'];

const LANG_TO_API = { '한국어':'ko', 'English':'en', '中文':'zh-CN' };

function resolveApiBase() {
  const host = window.location.hostname;
  if (host === 'localhost' || host === '127.0.0.1' || host === '') return 'http://localhost:8901';
  return `${window.location.protocol}//${host}:8901`;
}

const API_BASE = resolveApiBase();

const LOG_LINES = {
  scenes:                'scene layout built from "{tpl}" template',
  tts:                   'voiceover synthesized ({lang})',
  caption_from_narration:'captions generated from narration',
  caption_validate:      'caption validation passed',
  motion_anchor:         'motion anchors set',
  render:                'slides rendered · 1080p',
  scene_render:          'scene video rendered · h264',
  final_concat:          'video concatenated · h264',
  qa:                    'quality assurance complete',
};

function uid() {
  const hex = '0123456789abcdef';
  const blk = n => Array.from({length:n}, () => hex[Math.floor(Math.random()*16)]).join('');
  return `run_${blk(8)}-${blk(4)}-${blk(4)}-${blk(4)}-${blk(12)}`;
}

function durationToSec(dur) {
  if (dur === '30s') return 30;
  if (dur === '60s') return 60;
  if (dur === '90s') return 90;
  if (dur === '3분')  return 180;
  if (dur === '5분')  return 300;
  if (dur === '10분') return 600;
  if (dur === '20분') return 1200;
  if (dur === '30분') return 1800;
  const m = String(dur).match(/^(\d+)/);
  if (m) return parseInt(m[1], 10) * 60;
  return 300;
}

function normalizeRun(apiRun) {
  const rawStatus = (apiRun.status || '').toUpperCase();
  const status = (rawStatus === 'DONE' || rawStatus === 'COMPLETED' || rawStatus.startsWith('STOPPED_AFTER_'))
    ? 'done'
    : rawStatus === 'CANCELLED'
    ? 'cancelled'
    : (rawStatus === 'FAILED' || rawStatus === 'FAIL' || rawStatus === 'ERROR')
    ? 'failed'
    : rawStatus === 'QUEUED'
    ? 'queued'
    : 'running';

  const apiStages = apiRun.stages || [];

  const failedStage = apiStages.find(s => s.status === 'FAILED');
  const failedGroupKey = failedStage
    ? (STAGE_GROUP_MAP[failedStage.stage_key] ?? null)
    : null;
  const failedAt = failedGroupKey !== null
    ? STAGES.findIndex(s => s.key === failedGroupKey)
    : null;

  const runningDetail = apiStages.find(s => s.status === 'RUNNING');
  const runningGroupIdx = runningDetail
    ? STAGES.findIndex(s => s.key === (STAGE_GROUP_MAP[runningDetail.stage_key] ?? ''))
    : -1;

  const maxDoneGroupIdx = apiStages
    .filter(s => ['DONE', 'SKIP', 'PASS'].includes(s.status))
    .map(s => STAGES.findIndex(g => g.key === (STAGE_GROUP_MAP[s.stage_key] ?? '')))
    .filter(i => i >= 0)
    .reduce((max, i) => Math.max(max, i), -1);

  const stageIndex = runningGroupIdx >= 0
    ? runningGroupIdx
    : (maxDoneGroupIdx >= 0 ? maxDoneGroupIdx + 1 : 0);

  const tgtSec = apiRun.target_duration_sec;
  const durLabel = tgtSec
    ? (tgtSec < 60 ? `${tgtSec}s` : `${Math.round(tgtSec / 60)} min`)
    : '2 min';

  return {
    id: apiRun.run_id,
    run_id: apiRun.run_id,
    topic: apiRun.topic,
    status,
    stageIndex,
    failedAt,
    error: failedStage ? failedStage.error_msg : null,
    createdAt: apiRun.started_at ? new Date(apiRun.started_at).getTime() : Date.now(),
    endedAt: apiRun.completed_at ? new Date(apiRun.completed_at).getTime() : null,
    lang: apiRun.language || 'ko',
    language: apiRun.language || 'ko',
    stages: apiStages,
    progress_percent: apiRun.progress_percent,
    stage_progress: apiRun.stage_progress || null,
    available_artifacts: apiRun.available_artifacts || [],
    current_stage: apiRun.current_stage,
    final_mp4_path: apiRun.final_mp4_path,
    artifact_count: apiRun.artifact_count,
    download_url: apiRun.final_mp4_path ? `${API_BASE}/runs/${encodeURIComponent(apiRun.run_id)}/download` : null,
    scene_count: apiRun.scene_count,
    duration_sec: apiRun.duration_sec,
    contents: apiRun.contents,
    target_duration_sec: tgtSec,
    mode: apiRun.mode,
    profile_name: apiRun.profile_name || null,
    prompt_filename: apiRun.prompt_filename || null,
    video_template: apiRun.video_template || null,
    video_templates_used: apiRun.video_templates_used || null,
    run_type: apiRun.run_type || 'TEST',
    template: apiRun.mode || 'template',
    duration: durLabel,
    provider: 'OpenAI',
    sceneCount: apiRun.scene_count || 0,
    tts_provider: apiRun.tts_provider || null,
    tts_voice: apiRun.tts_voice || null,
    tts_fallback_used: apiRun.tts_fallback_used || false,
    tts_audio_duration_sec: apiRun.tts_audio_duration_sec || null,
    tts_cache_used: apiRun.tts_cache_used ?? null,
    queue_position: apiRun.queue_position ?? null,
  };
}

function normalizeTemplate(apiTemplate, index = 0) {
  const name = apiTemplate.name || apiTemplate.filename || `template-${index + 1}`;
  const filename = apiTemplate.filename || `${name}.md`;
  const anims = ['lecture', 'news', 'doc', 'timeline', 'whiteboard'];
  return {
    id: filename,
    name,
    filename,
    ko: filename,
    anim: anims[index % anims.length],
    short: `${filename} · ${apiTemplate.size_bytes || 0} bytes`,
    duration: 'API',
    desc: `${name} is loaded from /templates.`,
    purpose: `${name} prompt loaded from /templates.`,
    applies: [],
    body: apiTemplate.content || `${name}\n${filename}\n${apiTemplate.size_bytes || 0} bytes`,
    output: ['API template file', filename],
    scenarios: ['API'],
    size_bytes: apiTemplate.size_bytes || 0,
  };
}

function normalizeProfile(apiProfile) {
  return {
    name: apiProfile.name,
    max_duration_sec: apiProfile.max_duration_sec,
    min_scenes: apiProfile.min_scenes,
    max_scenes: apiProfile.max_scenes,
    max_scene_narration_chars: apiProfile.max_scene_narration_chars,
    max_total_narration_chars: apiProfile.max_total_narration_chars,
    fast_path: !!apiProfile.fast_path,
  };
}

async function fetchJSON(path) {
  const url = `${API_BASE}${path}`;
  try {
    const res = await fetch(url);
    if (!res.ok) {
      let detail = '';
      try {
        const err = await res.json();
        detail = err.detail ? `: ${err.detail}` : '';
      } catch (e) {
        detail = '';
      }
      throw new Error(`GET ${url} failed: ${res.status}${detail}`);
    }
    return res.json();
  } catch (e) {
    if (e && e.message && e.message.startsWith(`GET ${url} failed`)) throw e;
    throw new Error(`GET ${url} failed; reason: ${e && e.message ? e.message : e}`);
  }
}

function stageStates(run) {
  const total = STAGES.length;
  if (run.status === 'done')   return STAGES.map(()=> 'done');
  if (run.status === 'failed') {
    const fi = run.failedAt ?? run.stageIndex ?? 0;
    return STAGES.map((_,i)=> i<fi ? 'done' : i===fi ? 'failed' : 'waiting');
  }
  const cur = run.stageIndex ?? 0;
  return STAGES.map((_,i)=> i<cur ? 'done' : i===cur ? 'running' : 'waiting');
}

function progressPct(run){
  if (run.status==='done') return 100;
  if (run.status==='failed') return Math.round(((run.failedAt ?? 0)/STAGES.length)*100);
  const cur = run.stageIndex ?? 0;
  return Math.round(((cur + 0.5)/STAGES.length)*100);
}

function fmtClock(ts){
  const d = new Date(ts);
  return d.toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'});
}
function fmtFull(ts){
  if(!ts) return '—';
  const d = new Date(ts);
  return d.toLocaleString('en-CA',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).replace(',', '');
}
function elapsed(run){
  const end = run.endedAt ?? Date.now();
  const s = Math.max(0, Math.floor((end - run.createdAt)/1000));
  const m = Math.floor(s/60); const ss = s%60;
  return `${m}m ${String(ss).padStart(2,'0')}s`;
}
function relTime(ts){
  const s = Math.floor((Date.now()-ts)/1000);
  if (s<60) return 'just now';
  const m = Math.floor(s/60); if (m<60) return `${m}m ago`;
  const h = Math.floor(m/60); if (h<24) return `${h}h ago`;
  return `${Math.floor(h/24)}d ago`;
}

function buildLog(run){
  const states = stageStates(run);
  const out = [];
  let t = run.createdAt;
  STAGES.forEach((st,i) => {
    const state = states[i];
    if (state === 'waiting') { out.push({ ts:null, tag:st.key, msg:'waiting…', state:'pending' }); return; }

    const live = run.stage_progress;
    if (st.key === 'voice' && live && live.stage_key === 'tts') {
      out.push({
        ts: live.updated_at ? new Date(live.updated_at).getTime() : Date.now(),
        tag: st.key,
        msg: `${live.label} ${live.percent}% (${live.completed}/${live.total})`,
        state: live.completed >= live.total ? 'ok' : 'cur',
      });
      return;
    }

    const apiStage = run.stages && run.stages.find
      ? run.stages.find(s => s.stage_key === st.key)
      : null;

    if (apiStage && apiStage.started_at) {
      const ts = new Date(apiStage.started_at).getTime();
      const msg = apiStage.error_msg || LOG_LINES[st.key] || st.desc;
      out.push({ ts, tag:st.key, msg, state: state==='running'?'cur' : state==='failed'?'bad' : 'ok' });
      if (state==='failed') out.push({ ts:ts+1000, tag:st.key, msg:apiStage.error_msg||run.error||'stage failed', state:'bad' });
    } else {
      t += 22000 + (i*7000);
      const msg = (LOG_LINES[st.key] || st.desc)
        .replace('{n}', run.sceneCount||6)
        .replace('{x}', 2)
        .replace('{tpl}', run.template||'template')
        .replace('{lang}', run.lang||'ko');
      out.push({ ts:t, tag:st.key, msg, state: state==='running'?'cur' : state==='failed'?'bad' : 'ok' });
      if (state==='failed') out.push({ ts:t+1000, tag:st.key, msg:run.error||'stage failed', state:'bad' });
    }
  });
  return out;
}

async function loadRunsAPI() {
  const data = await fetchJSON('/runs?limit=1000');
  if (!data || !Array.isArray(data.runs)) throw new Error('/runs response missing runs[]');
  return data.runs.map(normalizeRun);
}

async function loadRunAPI(runId) {
  const data = await fetchJSON(`/runs/${encodeURIComponent(runId)}`);
  return normalizeRun(data);
}

async function loadTemplatesAPI() {
  const data = await fetchJSON('/templates');
  if (!Array.isArray(data)) throw new Error('/templates response is not an array');
  return data.map(normalizeTemplate);
}

const _VIDEO_TEMPLATE_META = {
  TitleOpen:    { ko: '타이틀 오프닝', anim: 'lecture',    short: '강렬한 첫 인상 타이틀 화면', duration: '5s',  desc: '영상 시작을 위한 타이틀 오프닝 Composition', output: ['타이틀 텍스트', '서브타이틀'], scenarios: ['인트로', '오프닝'] },
  Explain:      { ko: '개념 설명',    anim: 'lecture',    short: '핵심 개념을 명확하게 설명',  duration: '10s', desc: '개념·정의를 시각적으로 설명하는 Composition', output: ['제목', '본문', '키워드'], scenarios: ['개념', '설명'] },
  ListReveal:   { ko: '목록 공개',    anim: 'whiteboard', short: '순차적 목록 항목 공개',      duration: '8s',  desc: '리스트 항목을 순차적으로 표시하는 Composition', output: ['항목 목록', '순차 애니메이션'], scenarios: ['리스트', '항목'] },
  Quote:        { ko: '인용구',      anim: 'doc',        short: '핵심 인용문 강조 표시',      duration: '6s',  desc: '인용구·명언을 강조하는 Composition', output: ['인용 텍스트', '출처'], scenarios: ['인용', '강조'] },
  OutroCta:     { ko: '아웃트로',    anim: 'lecture',    short: '행동 유도 마무리 화면',      duration: '8s',  desc: '영상 마무리 CTA Composition', output: ['마무리 메시지', 'CTA'], scenarios: ['아웃트로', '마무리'] },
  FlowSteps:    { ko: '흐름 단계',   anim: 'whiteboard', short: '단계별 프로세스 흐름 표시',  duration: '12s', desc: '순서·단계를 시각화하는 Composition', output: ['단계 목록', '흐름 화살표'], scenarios: ['프로세스', '순서'] },
  ArchTree:     { ko: '구조 트리',   anim: 'whiteboard', short: '계층 구조 트리 다이어그램',  duration: '10s', desc: '계층·아키텍처 구조를 표시하는 Composition', output: ['트리 구조', '노드'], scenarios: ['구조', '아키텍처'] },
  Timeline:     { ko: '타임라인',    anim: 'timeline',   short: '시간 순서 이벤트 표시',      duration: '10s', desc: '시간 순서에 따른 이벤트 Composition', output: ['이벤트 목록', '타임라인'], scenarios: ['역사', '순서'] },
  CompareTwo:   { ko: '비교',       anim: 'news',       short: '두 항목 나란히 비교',        duration: '8s',  desc: '두 가지를 나란히 비교하는 Composition', output: ['항목 A', '항목 B'], scenarios: ['비교', '대조'] },
  TableCompare: { ko: '표 비교',     anim: 'news',       short: '다중 항목 표 형태 비교',     duration: '10s', desc: '여러 항목을 표로 비교하는 Composition', output: ['표 헤더', '행 데이터'], scenarios: ['비교 표', '데이터'] },
  KeywordCards: { ko: '키워드 카드', anim: 'doc',        short: '핵심 키워드 카드 나열',      duration: '8s',  desc: '키워드를 카드 형태로 표시하는 Composition', output: ['키워드 목록', '카드 그리드'], scenarios: ['키워드', '용어'] },
  SummaryCard:  { ko: '요약 카드',   anim: 'doc',        short: '핵심 내용 요약 카드',        duration: '8s',  desc: '내용을 요약 카드로 표시하는 Composition', output: ['요약 포인트', '핵심 내용'], scenarios: ['요약', '정리'] },
};

function normalizeVideoTemplate(apiTemplate, index = 0) {
  const name = apiTemplate.name;
  const meta = _VIDEO_TEMPLATE_META[name] || {
    ko: name, anim: 'lecture', short: `${name} Composition`, duration: '8s',
    desc: `${name} Remotion Composition`, output: [name], scenarios: [name],
  };
  return {
    id: name,
    name,
    filename: apiTemplate.filename,
    ko: meta.ko,
    anim: meta.anim,
    short: meta.short,
    duration: meta.duration,
    desc: meta.desc,
    purpose: `${name} Video Template — Remotion Composition`,
    applies: [],
    body: `${name}\n${apiTemplate.filename}`,
    output: meta.output,
    scenarios: meta.scenarios,
    _isVideoTemplate: true,
  };
}

async function loadVideoTemplatesAPI() {
  const data = await fetchJSON('/templates/video-templates');
  if (!Array.isArray(data)) throw new Error('/templates/video-templates response is not an array');
  return data.map(normalizeVideoTemplate);
}

async function loadProfilesAPI() {
  const data = await fetchJSON('/profiles');
  if (!Array.isArray(data)) throw new Error('/profiles response is not an array');
  return data.map(normalizeProfile);
}

async function cancelRunAPI(runId) {
  const url = `${API_BASE}/runs/${encodeURIComponent(runId)}/cancel`;
  const res = await fetch(url, { method: 'POST' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(`Cancel failed: ${res.status} ${err.detail || ''}`);
  }
  return res.json();
}

async function deleteRunAPI(runId) {
  const url = `${API_BASE}/runs/${encodeURIComponent(runId)}`;
  const res = await fetch(url, { method: 'DELETE' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(`Delete failed: ${res.status} ${err.detail || ''}`);
  }
  return res.json();
}

async function bulkDeleteTestRunsAPI() {
  const url = `${API_BASE}/runs/bulk-test`;
  const res = await fetch(url, { method: 'DELETE' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(`Bulk delete failed: ${res.status} ${err.detail || ''}`);
  }
  return res.json();
}

async function loadQueueStatusAPI() {
  return fetchJSON('/queue/status');
}

async function moveQueueRunAPI(runId, direction) {
  const res = await fetch(`${API_BASE}/queue/${encodeURIComponent(runId)}/move-${direction}`, { method: 'POST' });
  if (!res.ok) {
    const err = await res.json().catch(()=>({}));
    throw new Error(err.detail || `Move ${direction} failed (${res.status})`);
  }
  return res.json();
}

async function reorderQueueAPI(runIds) {
  const res = await fetch(`${API_BASE}/queue/reorder`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ run_ids: runIds }),
  });
  if (!res.ok) {
    const err = await res.json().catch(()=>({}));
    throw new Error(err.detail || `Reorder failed (${res.status})`);
  }
  return res.json();
}

async function bulkCancelQueuedAPI(runIds = null) {
  const res = await fetch(`${API_BASE}/queue/bulk-cancel`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ run_ids: runIds }),
  });
  if (!res.ok) {
    const err = await res.json().catch(()=>({}));
    throw new Error(err.detail || `Bulk cancel failed (${res.status})`);
  }
  return res.json();
}

function loadRuns() { return []; }
function saveRuns() {}

Object.assign(window, {
  STAGES, TEMPLATES, DURATIONS, DURATIONS_SHORTS, DURATIONS_LECTURE, PROVIDERS, LANGS,
  LANG_TO_API, API_BASE,
  uid, durationToSec, normalizeRun, normalizeTemplate, normalizeProfile, normalizeVideoTemplate,
  stageStates, progressPct, buildLog,
  fmtClock, fmtFull, elapsed, relTime,
  loadRuns, saveRuns, loadRunsAPI, loadRunAPI, loadTemplatesAPI, loadProfilesAPI, loadVideoTemplatesAPI,
  cancelRunAPI, deleteRunAPI, bulkDeleteTestRunsAPI, loadQueueStatusAPI, moveQueueRunAPI, reorderQueueAPI,
  bulkCancelQueuedAPI,
});
