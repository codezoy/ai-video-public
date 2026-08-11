/* ============ AI-Video v2 — admin seed data (Templates / Prompts) ============ */

/* ---------------- Templates ---------------- */
// length bands shown in selects + meta
const LENGTH_BANDS = ['5분 이하', '5-10분', '10-15분', '15분 이상'];

const SEED_TEMPLATES = [
  {
    id: 'tpl_lwk7',
    name: '이운규식 7단 구조',
    desc: '핵심 주장 → 개념 → 사례 → 반론 → 종합으로 이어지는 지식 학습 영상의 표준 골격.',
    band: '10-15분',
    isDefault: true,
    active: true,
    updatedAt: '2026-06-10',
    steps: [
      { id: 's1', label: '선언', en: 'Declaration', min: 1, max: 2, desc: '핵심 주장을 한 문장으로 던진다.' },
      { id: 's2', label: '개념', en: 'Concept', min: 2, max: 3, desc: '주제의 기본 개념과 용어를 정의한다.' },
      { id: 's3', label: '확장', en: 'Expansion', min: 1, max: 2, desc: '개념을 실제 맥락으로 넓힌다.' },
      { id: 's4', label: '사례', en: 'Example', min: 2, max: 3, desc: '구체적 사례로 이해를 돕는다.' },
      { id: 's5', label: '반론', en: 'Counter', min: 1, max: 2, desc: '흔한 오해와 반례를 짚는다.' },
      { id: 's6', label: '종합', en: 'Synthesis', min: 1, max: 2, desc: '핵심을 다시 엮어 정리한다.' },
      { id: 's7', label: '결론', en: 'Conclusion', min: 1, max: 1, desc: '행동 제안으로 마무리한다.' },
    ],
  },
  {
    id: 'tpl_short',
    name: '단문 요약형',
    desc: '한 가지 개념을 짧고 빠르게 전달하는 쇼츠용 3단 구조.',
    band: '5분 이하',
    isDefault: false,
    active: true,
    updatedAt: '2026-06-08',
    steps: [
      { id: 's1', label: '훅', en: 'Hook', min: 0, max: 1, desc: '질문이나 충격적 사실로 시선을 잡는다.' },
      { id: 's2', label: '핵심', en: 'Core', min: 1, max: 2, desc: '한 가지 메시지를 명확히 전달한다.' },
      { id: 's3', label: '마무리', en: 'Wrap', min: 0, max: 1, desc: '한 줄 요약과 행동 유도로 닫는다.' },
    ],
  },
  {
    id: 'tpl_compare',
    name: '제품 비교형',
    desc: '두 대상의 기준별 장단점을 나란히 비교하는 구조.',
    band: '5-10분',
    isDefault: false,
    active: true,
    updatedAt: '2026-06-05',
    steps: [
      { id: 's1', label: '도입', en: 'Intro', min: 1, max: 1, desc: '비교 대상과 기준을 소개한다.' },
      { id: 's2', label: 'A 분석', en: 'Subject A', min: 1, max: 2, desc: '첫 번째 대상의 특징을 정리한다.' },
      { id: 's3', label: 'B 분석', en: 'Subject B', min: 1, max: 2, desc: '두 번째 대상의 특징을 정리한다.' },
      { id: 's4', label: '대조', en: 'Contrast', min: 1, max: 2, desc: '기준별로 둘을 직접 대조한다.' },
      { id: 's5', label: '추천', en: 'Verdict', min: 1, max: 1, desc: '상황별 추천으로 결론짓는다.' },
    ],
  },
  {
    id: 'tpl_exp',
    name: '실험형',
    desc: '새 내러티브 구조를 시험하는 비공개 초안. Generate에 노출되지 않는다.',
    band: '15분 이상',
    isDefault: false,
    active: false,
    updatedAt: '2026-05-28',
    steps: [
      { id: 's1', label: '관찰', en: 'Observe', min: 2, max: 3, desc: '현상을 있는 그대로 묘사한다.' },
      { id: 's2', label: '가설', en: 'Hypothesis', min: 2, max: 3, desc: '가능한 설명을 제시한다.' },
      { id: 's3', label: '검증', en: 'Test', min: 3, max: 5, desc: '근거로 가설을 검증한다.' },
    ],
  },
];

/* ---------------- Prompt variable metadata ---------------- */
// looked up by detected {{name}}; falls back to string/required when unknown
const VAR_META = {
  topic:       { type: '문자열', desc: '영상 주제', required: true },
  duration:    { type: '정수',   desc: '목표 영상 길이 (분)', required: false, def: '10' },
  template:    { type: '문자열', desc: '구조 템플릿', required: true },
  script:      { type: '문자열', desc: '원본 대본', required: true },
  tone:        { type: '문자열', desc: '목표 톤', required: false, def: '친근함' },
  maxSceneSec: { type: '정수',   desc: '장면당 최대 길이 (초)', required: false, def: '12' },
  scenes:      { type: '배열',   desc: '장면 메타데이터', required: true },
  audioLen:    { type: '정수',   desc: '합성 오디오 길이 (초)', required: true },
  reference:   { type: '문자열', desc: '참고 자료', required: false },
};

/* ---------------- Prompts ---------------- */
const P_WRITER_V3 = `# 역할
당신은 이운규식 7단 구조를 기반으로 IT 지식 학습 영상의
대본을 작성하는 전문 작가입니다.

# 입력 변수
{{topic}}: 영상 주제
{{duration}}: 목표 영상 길이 (분)
{{template}}: 사용할 구조 템플릿

# 작성 규칙
- 각 단계는 하나의 핵심 메시지만 담는다.
- 시청자가 소리 내어 읽기 좋은 구어체로 쓴다.
- 전문 용어는 처음 등장할 때 한 문장으로 정의한다.
- {{duration}}분 분량에 맞춰 단계별 호흡을 조절한다.

# 출력 형식
각 장면을 다음 스키마로 반환한다.
{ "scene": <번호>, "stage": <단계명>, "narration": <내레이션> }`;

const P_WRITER_V2 = `# 역할
당신은 IT 지식 학습 영상의 대본을 작성하는 전문 작가입니다.

# 입력 변수
{{topic}}: 영상 주제

# 작성 규칙
- 각 장면은 하나의 핵심 메시지만 담는다.
- 구어체로 자연스럽게 쓴다.

# 출력 형식
장면별 내레이션을 순서대로 반환한다.`;

const P_WRITER_V1 = `# 역할
당신은 영상 대본 작가입니다. {{topic}}에 대한
짧은 설명 대본을 작성하세요.`;

const P_POLISH = `# 역할
당신은 영상 대본의 문장을 다듬는 편집자입니다.

# 입력 변수
{{script}}: 원본 대본
{{tone}}: 목표 톤 (예: 친근함, 전문적)

# 다듬기 규칙
- 중복 표현과 군더더기를 제거한다.
- 문장을 짧고 명확하게 만든다.
- {{tone}} 톤을 일관되게 유지한다.
- 의미는 절대 바꾸지 않는다.`;

const P_SEG = `# 역할
당신은 완성된 대본을 영상 장면 단위로 분할하는 분석가입니다.

# 입력 변수
{{script}}: 다듬어진 대본
{{maxSceneSec}}: 장면당 최대 길이 (초)

# 분할 규칙
- 한 장면은 {{maxSceneSec}}초를 넘지 않는다.
- 화면 전환이 자연스러운 지점에서 자른다.
- 각 장면에 시각 자료 유형을 태그한다.`;

const P_QA = `# 역할
당신은 생성된 영상의 품질을 검수하는 QA 에이전트입니다.

# 입력 변수
{{scenes}}: 장면 메타데이터 배열
{{audioLen}}: 합성된 오디오 길이 (초)

# 검수 항목
- 장면별 영상 / 오디오 길이 일치 여부
- 내레이션과 자막의 불일치
- 금칙어 및 사실 오류 가능성

오류 발견 시 { "pass": false, "issues": [...] } 형식으로 반환한다.`;

const P_CUSTOM1 = `주제: {{topic}}
참고 자료:
{{reference}}

위 자료를 바탕으로 {{duration}}분 분량의
학습 영상 대본을 만들어 주세요.`;

const SEED_PROMPTS = [
  {
    id: 'writer', name: 'writer', group: 'pipeline', type: 'system',
    desc: '대본 작성 프롬프트', updatedAt: '2026-06-12', currentVersion: 'v3',
    versions: [
      { v: 'v1', date: '2026-05-20', body: P_WRITER_V1 },
      { v: 'v2', date: '2026-06-01', body: P_WRITER_V2 },
      { v: 'v3', date: '2026-06-12', body: P_WRITER_V3 },
    ],
  },
  {
    id: 'polisher', name: 'polisher', group: 'pipeline', type: 'system',
    desc: '문장 다듬기 프롬프트', updatedAt: '2026-06-09', currentVersion: 'v2',
    versions: [
      { v: 'v1', date: '2026-05-22', body: '# 역할\n당신은 대본을 다듬는 편집자입니다.\n{{script}}를 더 매끄럽게 고치세요.' },
      { v: 'v2', date: '2026-06-09', body: P_POLISH },
    ],
  },
  {
    id: 'segmenter', name: 'segmenter', group: 'pipeline', type: 'system',
    desc: '장면 분할 프롬프트', updatedAt: '2026-06-11', currentVersion: 'v4',
    versions: [
      { v: 'v1', date: '2026-05-18', body: '# 역할\n대본을 장면으로 나눕니다.\n{{script}}를 장면 배열로 변환하세요.' },
      { v: 'v2', date: '2026-05-30', body: '# 역할\n대본을 장면으로 분할합니다.\n{{script}}\n장면당 길이를 균등하게 맞춥니다.' },
      { v: 'v3', date: '2026-06-06', body: '# 역할\n당신은 대본을 장면 단위로 분할하는 분석가입니다.\n{{script}}\n{{maxSceneSec}}초 제한을 지킵니다.' },
      { v: 'v4', date: '2026-06-11', body: P_SEG },
    ],
  },
  {
    id: 'qa', name: 'qa', group: 'pipeline', type: 'system',
    desc: '품질 검수 프롬프트', updatedAt: '2026-05-25', currentVersion: 'v1',
    versions: [
      { v: 'v1', date: '2026-05-25', body: P_QA },
    ],
  },
  {
    id: 'custom-1', name: 'custom-1', group: 'custom', type: 'user',
    desc: '사용자 예시 입력 템플릿', updatedAt: '2026-06-03', currentVersion: 'v2',
    versions: [
      { v: 'v1', date: '2026-05-27', body: '주제: {{topic}}\n위 주제로 대본을 만들어 주세요.' },
      { v: 'v2', date: '2026-06-03', body: P_CUSTOM1 },
    ],
  },
];

/* ---------------- helpers ---------------- */
// detect {{var}} occurrences, return unique names in order of appearance
function detectVars(body) {
  const out = [];
  const re = /\{\{(\w+)\}\}/g;
  let m;
  while ((m = re.exec(body || '')) !== null) {
    if (!out.includes(m[1])) out.push(m[1]);
  }
  return out;
}

function varMeta(name) {
  return VAR_META[name] || { type: '문자열', desc: '—', required: true };
}

// current version body of a prompt
function currentBody(p) {
  const cur = p.versions.find(x => x.v === p.currentVersion) || p.versions[p.versions.length - 1];
  return cur ? cur.body : '';
}

// naive set-membership line diff → left(old)/right(new) tagged lines
function lineDiff(oldText, newText) {
  const oldLines = (oldText || '').split('\n');
  const newLines = (newText || '').split('\n');
  const oldSet = new Set(oldLines);
  const newSet = new Set(newLines);
  return {
    left: oldLines.map(l => ({ text: l, del: !newSet.has(l) })),
    right: newLines.map(l => ({ text: l, add: !oldSet.has(l) })),
  };
}

function escapeHtml(s) {
  return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// highlight prompt body → HTML string for the editor overlay
function highlightPrompt(text, flashVar) {
  return (text || '').split('\n').map(line => {
    const isHead = /^\s*#/.test(line);
    let h = escapeHtml(line).replace(/\{\{(\w+)\}\}/g, (m, name) => {
      const fl = flashVar === name ? ' flash' : '';
      return `<span class="varhl${fl}">${m}</span>`;
    });
    if (isHead) h = `<span class="ce-head1">${h}</span>`;
    return h;
  }).join('\n');
}

/* ---------------- stores ---------------- */
const TPL_KEY = 'aiv2_templates_v1';
const PROMPT_KEY = 'aiv2_prompts_v1';

function loadTemplates() {
  try { const r = localStorage.getItem(TPL_KEY); if (r) return JSON.parse(r); } catch (e) {}
  return JSON.parse(JSON.stringify(SEED_TEMPLATES));
}
function saveTemplates(t) { try { localStorage.setItem(TPL_KEY, JSON.stringify(t)); } catch (e) {} }

function loadPrompts() {
  try { const r = localStorage.getItem(PROMPT_KEY); if (r) return JSON.parse(r); } catch (e) {}
  return JSON.parse(JSON.stringify(SEED_PROMPTS));
}
function savePrompts(p) { try { localStorage.setItem(PROMPT_KEY, JSON.stringify(p)); } catch (e) {} }

function newStepId() { return 's' + Math.random().toString(36).slice(2, 7); }

Object.assign(window, {
  LENGTH_BANDS, VAR_META, SEED_TEMPLATES, SEED_PROMPTS,
  detectVars, varMeta, currentBody, lineDiff, escapeHtml, highlightPrompt,
  loadTemplates, saveTemplates, loadPrompts, savePrompts, newStepId,
});
