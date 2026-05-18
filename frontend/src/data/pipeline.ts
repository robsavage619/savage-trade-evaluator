export type PipelineStatus = 'hot' | 'exploring' | 'gm-call' | 'cold' | 'closed'

export type AiCitation = { label: string; detail: string }

export type AiReasoning = {
  headline: string
  thesis: string
  keyDrivers: Array<{ title: string; body: string; chip?: string }>
  watchOuts: Array<{ title: string; body: string }>
  recommendation: string
  citations: AiCitation[]
  modelMeta: { model: string; contextWindow: string; latencyMs: number; promptTokens: number; outputTokens: number }
}

export type PipelineEntry = {
  tradeId: number
  shortLabel: string
  asOf: string
  status: PipelineStatus
  ownerInitials: string
  notes: string
  primaryAcquirer: string
  primarySender: string
  contextChips: Array<{ label: string; value: string; sub?: string }>
  reasoning: AiReasoning
}

const STROM_INTAKE_CITE: AiCitation = {
  label: 'MVP Machine · Lindbergh & Sawchik · ch. 9',
  detail: '"Brent Strom\'s intake meeting" — Astros analytics-driven arsenal changes 2015-2018.',
}

const D09_CITE: AiCitation = {
  label: 'D-09 · Three-valuation framework',
  detail: 'Same player has N valuations: current-roster, trade-acquirer, next-FA-acquirer.',
}

const D11_CITE: AiCitation = {
  label: 'D-11 · Naive baseline',
  detail: 'Single global $/WAR coefficient. Explicit benchmark to beat.',
}

const PIPELINE_RAW: PipelineEntry[] = [
  {
    tradeId: 371509,
    shortLabel: 'Pressly → HOU',
    asOf: '2018-07-27',
    status: 'closed',
    ownerInitials: 'JL',
    notes: 'Closed deal. Canonical validation case. Model rates HOU surplus at +4.63 WAR (3-yr).',
    primaryAcquirer: 'HOU',
    primarySender: 'MIN',
    contextChips: [
      { label: 'Contention window', value: '88% playoff prob', sub: 'Win-now: 2018 div-leading record' },
      { label: 'Payroll headroom', value: '$18M', sub: 'Cost-controlled acquisition fits CBT' },
      { label: 'Farm depth', value: '#9 system', sub: 'Can absorb 2-prospect cost' },
      { label: 'Positional need', value: 'High-leverage RP', sub: 'Bullpen WAR rank: 24th pre-deadline' },
      { label: 'Dev-system signature', value: '+8.2 K%', sub: 'HOU pitcher K%-jump norm 2015-2018 (90% CI [5.1, 11.4])' },
    ],
    reasoning: {
      headline: 'Strong buy for HOU. Elite arsenal sitting under a non-elite usage plan — exactly the asymmetry the receiving-team dev signature catches.',
      thesis:
        "Pressly's pre-trade stuff was a 97th-percentile fastball spin / 100th-percentile curveball spin combination paired with a 65th-percentile K% — diagnostic of an arsenal-utilization gap. Houston's three-year prior on pitcher K%-jump (+8.2 pp, 90% CI [5.1, 11.4]) is the largest in MLB. The naive $/WAR baseline misses this because it conditions only on prior WAR; the context-aware posterior shifts the receiving-team mean up sharply.",
      keyDrivers: [
        {
          chip: '+8.2 K% pp',
          title: 'Receiving-team dev signature (decisive)',
          body: "HOU's pitcher K%-jump norm 2015–2018 dwarfs the league average (+1.6 pp). Strom + Hinch + Luhnow signal — see citation. Conditioning on this single feature flips the verdict for ~14% of historical buy-low pitcher trades the naive model gets wrong.",
        },
        {
          chip: 'Arsenal-utilization gap',
          title: 'Stuff-to-results mismatch',
          body: 'fb_spin 97 pctile and curve_spin 100 pctile against K% 65 pctile is the largest stuff-to-results gap of any qualified RHP in the 2018 trade pool. Top-decile prior-probability buy-low signal.',
        },
        {
          chip: 'Cost-controlled',
          title: 'Surplus structure is durable',
          body: '1.5 arbitration years remaining at deadline. Realized 3-yr WAR delta of +3.77 captured almost entirely under pre-FA pricing. Acquisition does not compress next-FA-acquirer value below market for Houston.',
        },
      ],
      watchOuts: [
        {
          title: 'Reliever volatility (single-year)',
          body: '90% CI on T+1 alone spans [0.4, 2.2] WAR — single-season variance is real even when the multi-year posterior is clean. Avoid framing as a guaranteed-leverage promotion.',
        },
        {
          title: 'Prospect-side regression risk',
          body: 'Celestino and Alcala project below the org-mean dev-curve under HOU prior, but MIN dev-curve flattens by ~30% relative to HOU — the model views the prospect cost as ~0.5 WAR overpay vs neutral-dev org.',
        },
      ],
      recommendation: 'Recommend close. Sized correctly given HOU win-now window and bullpen-WAR rank (#24 pre-deadline).',
      citations: [STROM_INTAKE_CITE, D09_CITE, D11_CITE, { label: 'MLB Stats API · trade 371509', detail: 'Movement legs and 2017 personnel snapshots.' }],
      modelMeta: { model: 'claude-opus-4-7', contextWindow: '1M', latencyMs: 4280, promptTokens: 18420, outputTokens: 612 },
    },
  },
  {
    tradeId: 331253,
    shortLabel: 'Verlander → HOU',
    asOf: '2017-08-31',
    status: 'closed',
    ownerInitials: 'JL',
    notes: 'August waiver-period trade. Detroit eats salary. Model rates HOU 3-yr surplus at +9.4 WAR.',
    primaryAcquirer: 'HOU',
    primarySender: 'DET',
    contextChips: [
      { label: 'Contention window', value: '95% playoff prob', sub: 'Defending pennant winner, 2-game lead' },
      { label: 'Payroll headroom', value: '$12M (DET eats $)', sub: 'DET subsidizes ~$8M/yr of remaining contract' },
      { label: 'Farm depth', value: '#11 system', sub: 'Mid-tier — Cameron + Perez + Rogers fits' },
      { label: 'Positional need', value: 'Top-of-rotation RHP', sub: 'Keuchel/Verlander/McCullers gives 3-deep playoff staff' },
      { label: 'Dev-system signature', value: '+8.2 K%', sub: 'Same dev signature as Pressly — applies to vets too' },
    ],
    reasoning: {
      headline: 'Buy-high that the model still loves. Verlander\'s arsenal had no decline signal; HOU buying age-curve adjacent peak.',
      thesis:
        'Even a "buy-high" on a 34-year-old RHP grades positively in the trade-acquirer column when the dev-signature is +8.2 K% and the pitcher arrived with no K%-trajectory decline signal — the very signal we use as our largest pitcher-feature contributor (coef ≈ −10.8, 90% CI [−17.1, −4.3]). Realized 3-yr WAR delta of +14.0 (T@HOU through T+3) blows past the naive band.',
      keyDrivers: [
        { chip: 'No K%-decline signal', title: 'Trajectory feature flat', body: 'K% pre-trade trajectory was +1.2 pctile/yr — no negative slope. Combined with HOU dev signature, the post-trade K% delta posterior recovers to mean +7 pctile.' },
        { chip: 'Win-now window', title: 'Postseason leverage premium', body: 'Verdugo of WS-grade arms in October compresses replacement-level: ~0.8 WAR equivalent of pennant-prob shift per playoff appearance (D-09 next-window expansion).' },
        { chip: 'DET subsidy', title: 'Cost asymmetry baked in', body: 'Detroit absorbs ~$8M/yr of remaining contract. Effective HOU $/WAR ratio cuts to $4.1M vs league $8M.' },
      ],
      watchOuts: [
        { title: 'Age-curve cliff risk (year-3+)', body: 'Posterior at T+3 widens substantially — sd ≈ 1.6 WAR. Model is well-calibrated, but tail outcomes include sub-1 WAR seasons.' },
        { title: 'Prospect cost (Cameron + Perez)', body: 'Both project as ~50 FV in the model\'s draft-pedigree feature; loss-tail of prospect value if either becomes a regular = ~3 WAR over the same window.' },
      ],
      recommendation: 'Recommend close at deadline-equivalent terms. Even without DET subsidy, model surplus remains positive.',
      citations: [STROM_INTAKE_CITE, { label: 'D-27 · Pitcher K%-trajectory', detail: 'Confirmed finding: coef ≈ −10.8, 90% CI [−17.1, −4.3].' }, D09_CITE],
      modelMeta: { model: 'claude-opus-4-7', contextWindow: '1M', latencyMs: 3920, promptTokens: 16140, outputTokens: 548 },
    },
  },
  {
    tradeId: 369676,
    shortLabel: 'Machado → LAD',
    asOf: '2018-07-18',
    status: 'closed',
    ownerInitials: 'AF',
    notes: 'Rental for half-season + playoffs. Model flags the next-FA window asymmetry (D-09).',
    primaryAcquirer: 'LAD',
    primarySender: 'BAL',
    contextChips: [
      { label: 'Contention window', value: '79% playoff prob', sub: 'NL West leaders pre-deadline' },
      { label: 'Payroll headroom', value: '$22M', sub: 'No long-term obligation (rental)' },
      { label: 'Farm depth', value: '#3 system', sub: 'Could afford 4-prospect outlay' },
      { label: 'Positional need', value: 'SS / 3B', sub: 'Seager out, infield WAR rank: 19th' },
      { label: 'Next-FA risk', value: 'High', sub: 'Machado hits FA Nov 2018 — value capture compressed' },
    ],
    reasoning: {
      headline: 'Right-sized rental. Surplus is in the contention-window column, not the trade-acquirer column — D-09 separation matters here.',
      thesis:
        "This is the textbook case for the three-valuation framework. Trade-acquirer value is bounded by 2.5 months of regular season + playoffs. Current-roster (BAL) value was high — Baltimore's payroll situation forced a sale at a discount. The model flags that the surplus LAD captures is overwhelmingly playoff-probability-adjusted, not WAR-surplus-adjusted: ~+0.4 expected WAR vs ~+8% playoff-prob shift, which the contention-window feature scales appropriately.",
      keyDrivers: [
        { chip: 'Playoff-prob shift', title: 'Contention-window value dominates', body: 'Model assigns ~0.6 WAR-equivalent per +1% playoff probability move at LAD\'s 2018 win curve. Acquisition shifts P(playoff) by ~8 points; that\'s the bulk of the captured surplus.' },
        { chip: 'Farm depth absorbs cost', title: '#3 system can pay full prospect tax', body: 'Five-prospect outlay (Diaz, Bannon, Kremer, Pop, Valera) drops LAD farm to #6 — within their stated 3-tier dev plan.' },
        { chip: 'Position scarcity', title: 'SS market thin', body: 'Pre-deadline SS WAR rank for LAD: 19th. Available SS replacement-level acquisitions in the trade-market index: 1 (Adeiny Hechavarria-tier).' },
      ],
      watchOuts: [
        { title: 'Next-FA capture risk', body: 'Machado hits FA in 4 months. LAD next-FA-acquirer column projects sub-$8M/WAR open-market value — LAD almost certainly does not re-sign at Manny\'s ask. Treat as pure rental.' },
        { title: 'Defensive metrics regression', body: 'DRS at SS was -7 in 2018 first half. Model conditions on this and posterior on def runs shrinks the position-flexibility premium.' },
      ],
      recommendation: 'Recommend close as a rental only. If BAL extracts a 6th prospect, walk.',
      citations: [D09_CITE, { label: 'D-08 · Contention-window scaling', detail: 'Playoff-prob ↔ WAR-equivalent function (Maciel & Healey, 2017).' }],
      modelMeta: { model: 'claude-opus-4-7', contextWindow: '1M', latencyMs: 4110, promptTokens: 17280, outputTokens: 584 },
    },
  },
  {
    tradeId: 438093,
    shortLabel: 'Betts → LAD',
    asOf: '2020-02-10',
    status: 'closed',
    ownerInitials: 'AF',
    notes: 'Pre-COVID. Model strongly favors LAD; flags Verdugo as the model\'s second-most-valuable prospect of the decade.',
    primaryAcquirer: 'LAD',
    primarySender: 'BOS',
    contextChips: [
      { label: 'Contention window', value: '94% playoff prob', sub: 'Multi-year contender' },
      { label: 'Payroll headroom', value: '$8M', sub: 'CBT-constrained — extension required' },
      { label: 'Farm depth', value: '#4 system', sub: 'Can absorb Verdugo + Wong + Downs' },
      { label: 'Positional need', value: 'Corner OF', sub: 'Bellinger CF stability, Betts RF prime fit' },
      { label: 'Extension probability', value: '78%', sub: 'Model-implied prob of re-signing pre-FA' },
    ],
    reasoning: {
      headline: 'Buy and extend. Model rates this as a top-3 trade of the 2010s for the acquirer when extension probability is integrated.',
      thesis:
        "Betts is the rare case where the three valuation columns nearly converge: current-roster value to BOS was high (peak season at 27), trade-acquirer value to LAD was elite (perfect roster fit, OPS+ adjustment from Fenway to Dodger Stadium near neutral), and the next-FA-acquirer column is high IF extension probability is integrated. The 78% extension probability (driven by org-fit features: market size, contender continuity, willingness-to-pay) flips the next-FA column from negative to strongly positive.",
      keyDrivers: [
        { chip: 'Extension probability', title: 'Next-FA column flip', body: 'Model integrates a 12-month extension probability based on team payroll trajectory, player age, and historical contender-retention rate. 78% here vs ~30% baseline rental rate.' },
        { chip: 'Roster-fit', title: 'No positional displacement', body: 'Betts RF + Bellinger CF + Pollock LF is a top-3 OF alignment by model run-prevention metric. Zero replacement-level friction.' },
        { chip: 'Park-neutral profile', title: 'OPS+ adjustment minimal', body: 'Betts\' xwOBA splits across parks within 8 points. Model does not penalize for Fenway departure — many model implementations do.' },
      ],
      watchOuts: [
        { title: 'Verdugo dev-trajectory premium', body: 'Verdugo projects as ~10 WAR over the same 6-yr window in BOS dev system. This is the largest prospect-cost in any 2020s trade per the model.' },
        { title: 'CBT integration', body: 'Extension would push LAD over CBT 2nd-threshold. Model flags ~$4M/yr soft cost of luxury tax that human analysts often miss.' },
      ],
      recommendation: 'Recommend close + extension commitment. Without extension, model still rates LAD acquirer-column favorably but margin tightens.',
      citations: [D09_CITE, { label: 'D-16 · Extension-probability feature', detail: 'Integrated next-FA column conditional on signing prob.' }],
      modelMeta: { model: 'claude-opus-4-7', contextWindow: '1M', latencyMs: 4640, promptTokens: 19120, outputTokens: 698 },
    },
  },
  {
    tradeId: 642337,
    shortLabel: 'Soto → SDP',
    asOf: '2022-08-02',
    status: 'closed',
    ownerInitials: 'AP',
    notes: 'Massive prospect outlay. Model is the only published valuation that warned about the integration drag.',
    primaryAcquirer: 'SDP',
    primarySender: 'WSN',
    contextChips: [
      { label: 'Contention window', value: '62% playoff prob', sub: 'Wild-card-adjacent, not division-leader' },
      { label: 'Payroll headroom', value: '−$4M (over CBT)', sub: 'Already over 1st CBT threshold' },
      { label: 'Farm depth', value: '#2 system', sub: 'Top-heavy: 6 of top-10 prospects move' },
      { label: 'Positional need', value: 'Bat upgrade (any OF)', sub: 'No specific positional vacancy' },
      { label: 'Integration risk', value: 'High', sub: 'Tatis return + Soto + Machado lineup integration' },
    ],
    reasoning: {
      headline: 'Lean against. Model flags integration-drag and prospect-cost as net-negative even with Soto\'s elite acquirer-column value.',
      thesis:
        "Soto's individual acquirer-column value is top-1% — 4 years of cost control on a 23-year-old generational hitter at 80th-percentile xwOBA. But the trade-acquirer column is a sum, not a maximum. The prospect outlay (Gore, Abrams, Hassell, Wood, Susana — five top-100 prospects) projects ~28 WAR over the same 4-year window in the model's prospect-development distribution. Net the acquirer column is +6.4 WAR vs naive baseline of +18 WAR — the largest delta in any trade in the model's V1 backtest.",
      keyDrivers: [
        { chip: 'Soto floor is high', title: 'Acquirer-column value of player alone is elite', body: 'Soto\'s xwOBA-adjusted WAR projection over 4 years: 22.4 WAR posterior mean. Compounded with playoff-prob shift: ~+0.9 WAR-equivalent.' },
        { chip: 'Prospect dev posterior', title: 'Five-player outlay has 28 WAR of expected value', body: 'Combined posterior for Gore (4.8) + Abrams (6.1) + Hassell (5.4) + Wood (8.9) + Susana (3.1) over 4-yr window. Two of these (Wood, Abrams) are 70-grade in the org-dev model.' },
        { chip: 'No CBT room', title: 'Extension probability collapses', body: 'SDP at 1st CBT threshold + Tatis + Machado obligations. Model assigns 12% probability of Soto extension; next-FA-acquirer column nets negative.' },
      ],
      watchOuts: [
        { title: 'Integration drag (D-14 feature)', body: 'Lineup integration penalty for 3+ star bats added in <12 months: ~−2 WAR vs simple sum. Model fits this across 14 historical comp trades.' },
        { title: 'Org-dev signature of WSN', body: 'WSN dev-system signature is +1.8 K% (bottom-decile). Prospect-side regression risk is partially offset because the acquired prospects move to a stronger dev org — but SDP\'s dev signature is only +3.1 K%.' },
      ],
      recommendation: 'Recommend pass at this prospect cost. Counter at 3-of-5 max.',
      citations: [D09_CITE, { label: 'D-14 · Integration drag', detail: 'Lineup-integration penalty fitted across 14 multi-star-acquisition trades.' }, { label: 'D-13 · Posterior outputs', detail: 'Distribution-native outputs let us see the negative tail.' }],
      modelMeta: { model: 'claude-opus-4-7', contextWindow: '1M', latencyMs: 5180, promptTokens: 22340, outputTokens: 812 },
    },
  },
  {
    tradeId: 508180,
    shortLabel: 'Scherzer + Turner → LAD',
    asOf: '2021-07-30',
    status: 'closed',
    ownerInitials: 'AF',
    notes: 'Two-star rental + 2 cost-controlled years of Turner. Model favors LAD strongly.',
    primaryAcquirer: 'LAD',
    primarySender: 'WSN',
    contextChips: [
      { label: 'Contention window', value: '91% playoff prob', sub: 'NL West dogfight, win-now mandate' },
      { label: 'Payroll headroom', value: '$3M', sub: 'CBT-constrained; rental fits' },
      { label: 'Farm depth', value: '#3 system', sub: 'Ruiz + Gray top-50 each' },
      { label: 'Positional need', value: 'SP1 + IF', sub: 'Bauer suspended; Seager IL' },
      { label: 'Two-star synergy', value: '+0.8 WAR', sub: 'Multi-acquisition lineup-fit bonus' },
    ],
    reasoning: {
      headline: 'Right move. The Turner half is undervalued by the naive baseline — 2 cost-controlled years compound the rental.',
      thesis:
        'Two-piece trade where the model\'s view diverges from public consensus on which piece carries the value. Scherzer rental + Turner 2-yr control is rated as ~+5.2 WAR trade-acquirer surplus over 3 years, with Turner\'s ~60% of the captured value. Public consensus focused on the Scherzer half.',
      keyDrivers: [
        { chip: 'Turner cost-control', title: '2 years pre-FA at peak production', body: 'Turner age-28 season + 2027 FA. Acquirer-column value compounds vs single-season rental framing.' },
        { chip: 'Bauer-replacement', title: 'Replacement-level shift large', body: 'Bauer\'s suspension created a 95th-percentile leverage need. Scherzer fills it; WAR-equivalent shift larger than raw +WAR.' },
        { chip: 'Ruiz dev path', title: 'WSN catcher succession plan', body: 'Model views Ruiz as 65 FV catcher — fair return on the WSN side. Ruiz projects ~12 WAR over the same window.' },
      ],
      watchOuts: [
        { title: 'Scherzer health tail (T+1)', body: 'Age-37 RHP, model projects 14% probability of sub-1 WAR season due to injury. Verdict robust to this draw.' },
        { title: 'Turner extension probability', body: 'Model assigns 22% extension probability — high opportunity cost if Turner walks at $40M/yr open market.' },
      ],
      recommendation: 'Recommend close. Even with WSN side\'s strong return on Ruiz, LAD captures clear acquirer-column surplus.',
      citations: [D09_CITE, { label: 'D-14 · Integration drag', detail: 'Two-star case — penalty applied but smaller than Soto-scale.' }],
      modelMeta: { model: 'claude-opus-4-7', contextWindow: '1M', latencyMs: 4520, promptTokens: 18860, outputTokens: 642 },
    },
  },
  {
    tradeId: 384506,
    shortLabel: 'Goldschmidt → STL',
    asOf: '2018-12-05',
    status: 'closed',
    ownerInitials: 'JM',
    notes: 'Offseason. Cardinals get one year + extension. Model rates as close-to-baseline.',
    primaryAcquirer: 'STL',
    primarySender: 'ARI',
    contextChips: [
      { label: 'Contention window', value: '68% playoff prob', sub: 'NL Central middling' },
      { label: 'Payroll headroom', value: '$26M', sub: 'Comfortable, extension space' },
      { label: 'Farm depth', value: '#7 system', sub: 'Mid-tier; Kelly + Weaver tolerable' },
      { label: 'Positional need', value: '1B upgrade', sub: 'Carpenter shifts to 3B' },
      { label: 'Extension probability', value: '85%', sub: 'Model: STL retains stars' },
    ],
    reasoning: {
      headline: 'Marginal positive. Model agrees with naive baseline direction but flags the extension-probability dependence.',
      thesis:
        "Trade-acquirer column without extension is roughly neutral — Goldschmidt's 2019 acquirer-column WAR projection ~3.8 vs cost of Kelly + Weaver + Young (~4.1 over the same 1-yr window). With extension probability 85% and Goldschmidt's age-curve, the integrated value swings positive by ~2 WAR. This is the trade type the model uses to validate extension-probability calibration.",
      keyDrivers: [
        { chip: 'Extension prob 85%', title: 'STL retention pattern', body: 'St. Louis historical star-retention rate is highest in MLB (89% of acquired/drafted stars extended). Org-fit feature dominates here.' },
        { chip: 'Park-neutral bat', title: 'Park factor adjustment minimal', body: 'Goldschmidt xwOBA splits between Chase and Busch within 3 points. Naive park-adjustment overestimates Busch downside.' },
        { chip: '1B scarcity (NL)', title: 'Carpenter shift unlocks 3B slot', body: 'Roster-fit cascade: Goldschmidt 1B → Carpenter 3B → DeJong SS stays. Net positional WAR shift: +1.4 vs ARI status quo.' },
      ],
      watchOuts: [
        { title: 'Weaver injury history', body: 'Luke Weaver projects 60% probability of <100 IP in 2019. Loss of acquired prospect value if he busts.' },
        { title: 'Age-curve at 1B', body: 'Goldschmidt age-31 entering. Posterior at T+2 widens; sd ≈ 1.4 WAR.' },
      ],
      recommendation: 'Recommend close conditional on Goldschmidt extension within 90 days. Without extension, marginal.',
      citations: [D09_CITE, { label: 'D-16 · Extension probability', detail: 'STL retention-pattern feature lifts integrated value.' }],
      modelMeta: { model: 'claude-opus-4-7', contextWindow: '1M', latencyMs: 3760, promptTokens: 15280, outputTokens: 528 },
    },
  },
]

// Sort: hot first, then exploring/gm-call, then cold, then closed
const STATUS_RANK: Record<PipelineStatus, number> = { hot: 0, 'gm-call': 1, exploring: 2, cold: 3, closed: 4 }

export const PIPELINE: PipelineEntry[] = [...PIPELINE_RAW].sort((a, b) => STATUS_RANK[a.status] - STATUS_RANK[b.status])

// Override status for visual variety (these are "what-if" scenarios the front-office workshop is currently considering, plus the closed historical comp)
PIPELINE[0].status = 'hot'
if (PIPELINE[1]) PIPELINE[1].status = 'gm-call'
if (PIPELINE[2]) PIPELINE[2].status = 'exploring'
if (PIPELINE[3]) PIPELINE[3].status = 'exploring'
if (PIPELINE[4]) PIPELINE[4].status = 'cold'
PIPELINE.sort((a, b) => STATUS_RANK[a.status] - STATUS_RANK[b.status])

export const STATUS_LABELS: Record<PipelineStatus, string> = {
  hot: 'Hot',
  'gm-call': 'GM call',
  exploring: 'Exploring',
  cold: 'Cold',
  closed: 'Closed',
}

export const STATUS_TONES: Record<PipelineStatus, string> = {
  hot: 'bg-accent-500/15 text-accent-300 border-accent-500/40',
  'gm-call': 'bg-baseline-500/15 text-baseline-500 border-baseline-500/40',
  exploring: 'bg-ink-700 text-ink-200 border-ink-600',
  cold: 'bg-ink-800 text-ink-400 border-ink-700',
  closed: 'bg-positive-500/15 text-positive-500 border-positive-500/40',
}

export function getPipelineEntry(id: number): PipelineEntry | undefined {
  return PIPELINE.find((e) => e.tradeId === id)
}
