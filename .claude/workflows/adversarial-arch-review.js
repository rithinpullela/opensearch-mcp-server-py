export const meta = {
  name: 'adversarial-arch-review',
  description: 'Adversarial critic: compares old vs new architecture and challenges the rebuild decisions; appends to a running review log. Re-runnable per checkpoint.',
  phases: [
    { title: 'Survey', detail: 'Gather the diff old-vs-new + read the changed modules and the master plan' },
    { title: 'Critique', detail: 'Parallel adversarial reviewers, each a distinct lens, try to find what is wrong' },
    { title: 'Synthesize', detail: 'Consolidate into a verdict and append to ADVERSARIAL_REVIEW_LOG.md' },
  ],
}

const REPO = '/Users/rithinp/Documents/OS/MCP/os-mcp/opensearch-mcp-server-py'
const PY = REPO + '/.venv-clean/bin/python'

// args: { checkpoint?: string, baseRef?: string, headRef?: string, focus?: string }
// baseRef defaults to the commit BEFORE the rebuild started; headRef defaults to HEAD.
const checkpoint = (args && args.checkpoint) || 'checkpoint'
const baseRef = (args && args.baseRef) || 'main'
const headRef = (args && args.headRef) || 'HEAD'
const focus = (args && args.focus) || 'the entire rebuild so far'

const CONTEXT = [
  'CONTEXT: A from-scratch-ish modular rebuild of the OpenSearch MCP server (opensearch-mcp-server-py).',
  'The OLD architecture: low-level mcp.server.Server + a 1297-line tools.py TOOL_REGISTRY dict literal,',
  '687-line tool_params.py, a runtime OpenAPI->tools generator (boot-time GitHub fetch), duplicated boot',
  'pipeline across stdio/streaming servers, process-global mutable state (global_state.py).',
  'The NEW direction (see REBUILD_MASTER_PLAN.md): STAY on low-level Server, modularize into per-domain',
  'register() modules + typed ToolRegistry; delete the OpenAPI generator (4 tools become static,',
  'golden-snapshot-locked); add version_cache, auth_strategy, pydantic Settings; immutable ServerContext;',
  'fix real defects (per-call version round-trip, response-size memory safety, isError contract, etc).',
  'PRIME DIRECTIVE: no drift from observable behavior without a documented reason. ~525 unit tests + ~30',
  'integration tests are the 1:1 oracle.',
  'Read these for grounding (under docs/rebuild/): DECISION_LOG.md (authoritative — the shipped reality), AUDIT_FINDINGS.md, DESIGN_DECISIONS.md, ERROR_LOGGING_EVALUATION.md. NOTE: REBUILD_MASTER_PLAN.md / FASTMCP_REBUILD_*.md are PARTIALLY SUPERSEDED (see docs/rebuild/README.md) — DECISION_LOG.md + the code are authoritative.',
].join(' ')

// ---------- Phase 1: survey ----------
phase('Survey')

const SURVEY_SCHEMA = {
  type: 'object',
  required: ['changedFiles', 'newModules', 'summary', 'oldVsNew'],
  properties: {
    summary: { type: 'string', description: 'what this checkpoint changed, in plain terms' },
    changedFiles: { type: 'array', items: { type: 'string' }, description: 'files added/modified/deleted in the range, with a word on each' },
    newModules: { type: 'array', items: { type: 'string' }, description: 'new src modules introduced + their responsibility' },
    oldVsNew: { type: 'string', description: 'a concrete old-architecture-vs-new-architecture comparison for the parts touched' },
  },
}

const survey = await agent(
  [
    CONTEXT,
    'You are surveying the rebuild for an adversarial review. Repo: ' + REPO + '. Read-only.',
    'Checkpoint label: ' + checkpoint + '. Focus: ' + focus + '.',
    'Run: cd ' + REPO + ' && git --no-pager diff --stat ' + baseRef + '..' + headRef + '  and  git --no-pager log --oneline ' + baseRef + '..' + headRef,
    'Then read the NEW/CHANGED src modules (use the diff to find them) and skim REBUILD_MASTER_PLAN.md.',
    'Produce a precise survey: what changed, the new modules + responsibilities, and a concrete OLD-vs-NEW comparison of the touched areas.',
  ].join('\n'),
  { label: 'survey', phase: 'Survey', schema: SURVEY_SCHEMA }
)

const surveyJson = JSON.stringify(survey)
log('Surveyed checkpoint "' + checkpoint + '": ' + (survey.changedFiles || []).length + ' files, ' + (survey.newModules || []).length + ' new modules')

// ---------- Phase 2: adversarial critique (parallel lenses) ----------
phase('Critique')

const CRITIQUE_SCHEMA = {
  type: 'object',
  required: ['lens', 'overallTake', 'findings', 'praise'],
  properties: {
    lens: { type: 'string' },
    overallTake: { type: 'string', description: 'a candid 2-4 sentence bird-eye verdict from this lens' },
    findings: {
      type: 'array',
      description: 'concrete criticisms — be adversarial, cite file:line, no vague nits',
      items: {
        type: 'object',
        required: ['severity', 'title', 'detail', 'recommendation'],
        properties: {
          severity: { type: 'string', description: 'BLOCKER | MAJOR | MINOR | QUESTION' },
          title: { type: 'string' },
          detail: { type: 'string', description: 'what is wrong / risky / over-engineered / drifting, with evidence' },
          recommendation: { type: 'string' },
        },
      },
    },
    praise: { type: 'array', items: { type: 'string' }, description: 'decisions that are genuinely good (keep the review honest, not just negative)' },
  },
}

const lenses = [
  { label: 'lens:architecture',
    prompt: 'LENS = ARCHITECTURE & DESIGN. Challenge the structural decisions: is the modular layout (ToolRegistry/ToolSpec, compose_registry/modules manifest, ServerContext, compat leaf, generated/ package) actually simpler than the old monolith, or just differently complex? Are the seams right? Is staying on the low-level Server (vs high-level FastMCP) still justified given what was built? Any abstraction that does not earn its keep? Any layering/cohesion/coupling problem? Is the import-time registration of generated tools in tools.py a good idea or a hidden side-effect footgun?' },
  { label: 'lens:fidelity',
    prompt: 'LENS = FIDELITY (OLD vs NEW behavior). The prime directive is no observable drift without a documented reason. Hunt for places where the new code could behave differently from the old: registry order, tool count, schemas (the 4 generated tools), error text, the version gate, request shapes. Did the generator deletion preserve EXACTLY what the generator produced (order, schema dicts, GET-with-body, NDJSON)? Is the golden-snapshot oracle actually strong (dict-equal vs byte-equal — is that a gap)? Cross-check against the golden fixture and AUDIT_FINDINGS corrections.' },
  { label: 'lens:code-quality',
    prompt: 'LENS = CODE QUALITY & CORRECTNESS. Review the actual new code (registry.py, modules.py, compat.py, context.py, version_cache.py, auth_strategy.py, settings.py, domains/generated/*). Look for real bugs, async-safety issues (the version_cache asyncio.Lock + global-lock-across-keys concern), edge cases, error handling, type issues, dead code, tests that are tautological or over-mocked. Are the docstrings accurate or do they claim things the code does not do? Run the venv python to probe if useful.' },
  { label: 'lens:simplicity',
    prompt: 'LENS = SIMPLICITY / OVER-ENGINEERING / YAGNI. The user wants "easy to understand, contribute, maintain". Is anything gold-plated? Too many tiny files? Indirection a contributor would trip over? Is the version_cache / auth_strategy / settings machinery proportionate to the problem, or heavier than the bug it fixes? Would a new contributor understand the boot flow? Is the unwired-then-wire-later approach leaving confusing half-migrated state? Be the voice that says "this is too much" where true.' },
  { label: 'lens:minimal-diff',
    prompt: [
      'LENS = MINIMAL-DIFF / REVIEWER-FRIENDLINESS (EXPLICIT USER PRIORITY).',
      'The user said: do NOT heavily move away from the existing code; a reviewer of the new code must NOT find it unnecessarily hard; there must be a MIDDLE GROUND.',
      'Correctness / maintenance / latency / memory / efficiency are the top priority, but gratuitous code churn is itself a real cost.',
      'Evaluate: is the diff vs the OLD baseline larger than it needs to be? Are there changes that are pure reorganization-for-its-own-sake rather than fixing a cited defect from AUDIT_FINDINGS/DESIGN_DECISIONS?',
      'Could a change have been a smaller surgical edit to an existing file instead of a new module/abstraction?',
      'Are there NEW modules not yet wired in that may not earn their place (version_cache, auth_strategy, settings, registry, modules, context, compat)?',
      'Quantify churn: run `cd ' + REPO + ' && git --no-pager diff --shortstat ' + baseRef + '..' + headRef + ' -- src/` and break it down.',
      'For each significant change ask: would a reviewer diffing this against the old code understand WHY in under 30 seconds?',
      'Flag anything that trades reviewer-approachability for marginal cleanliness. Recommend where to PREFER editing-in-place over rewriting.',
      'This lens DEFENDS the user constraint: do not unnecessarily change a lot of code.',
    ].join(' ') },
]

const critiques = (await parallel(
  lenses.map((l) => () => agent(
    [
      CONTEXT,
      'You are an ADVERSARIAL reviewer. Repo: ' + REPO + '. Venv: ' + PY + '. Read-only (Read/Grep/Bash-introspection only; do NOT modify files).',
      'Checkpoint: ' + checkpoint + '. Diff range: ' + baseRef + '..' + headRef + '.',
      'Survey of what changed: ' + surveyJson,
      l.prompt,
      'Default to skepticism. Find the real problems; cite file:line. But stay honest — list genuine strengths in praise[]. Severity: BLOCKER (must fix before proceeding) / MAJOR / MINOR / QUESTION (needs a decision/clarification).',
    ].join('\n'),
    { label: l.label, phase: 'Critique', schema: CRITIQUE_SCHEMA }
  ))
)).filter(Boolean)

const allFindings = critiques.flatMap((c) => (c.findings || []).map((f) => ({ ...f, lens: c.lens })))
const blockers = allFindings.filter((f) => f.severity === 'BLOCKER')
const majors = allFindings.filter((f) => f.severity === 'MAJOR')
log('Critique: ' + allFindings.length + ' findings (' + blockers.length + ' BLOCKER, ' + majors.length + ' MAJOR) across ' + critiques.length + ' lenses')

// ---------- Phase 3: synthesize + append to running log ----------
phase('Synthesize')

const synthesis = await agent(
  [
    'You are the lead adversarial reviewer writing a checkpoint entry to a RUNNING review log.',
    'APPEND (do not overwrite) a new section to ' + REPO + '/docs/rebuild/ADVERSARIAL_REVIEW_LOG.md. If the file does not exist, create it with a top title first.',
    'Read the existing file first (if present) so you append below prior entries.',
    '',
    'This checkpoint: "' + checkpoint + '"  (diff ' + baseRef + '..' + headRef + ').',
    'Survey: ' + surveyJson,
    'Critiques from 4 lenses (architecture, fidelity, code-quality, simplicity): ' + JSON.stringify(critiques),
    '',
    'Write the appended section with this shape:',
    '## [<checkpoint>] — <one-line headline verdict>  (<short date-free tag, e.g. P0-P3>)',
    '- A 3-5 sentence bird-eye OLD-vs-NEW assessment: is the rebuild on track, simpler, faithful?',
    '- A findings table: severity | lens | finding | recommendation (BLOCKERs first, then MAJOR, MINOR, QUESTION).',
    '- "What is genuinely good" — the consolidated praise.',
    '- "Decisions to revisit" — QUESTIONs the human should weigh in on.',
    '- A one-line VERDICT: PROCEED / PROCEED-WITH-FIXES / STOP-AND-FIX.',
    'Be concrete and honest; this log is the human-facing zoomed-out view of the rebuild quality over time.',
    '',
    'After writing, return a tight summary: the verdict, blocker count, major count, and the single most important thing to address.',
  ].join('\n'),
  { label: 'synthesize', phase: 'Synthesize' }
)

return {
  checkpoint,
  range: baseRef + '..' + headRef,
  totalFindings: allFindings.length,
  blockers: blockers.length,
  majors: majors.length,
  blockerTitles: blockers.map((b) => b.title),
  majorTitles: majors.map((m) => m.title),
  synthesis,
}
