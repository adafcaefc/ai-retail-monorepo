/*
 * ============================================================
 * CHART INFO REGISTRY
 * Ported one-to-one from INFO_REG in
 * 03_CFO_FinanceAI_Suite_Mockup_v9.4_20260724.html.
 *
 * Every clickable board element carries an info key (`ik`).
 * Clicking it opens an InfoCard first — the card explains the
 * element and offers "Continue in chat", so nothing lands in
 * the transcript until the CFO asks for it.
 *
 * Key shapes (aligned to the LIVE payload, not the mockup DOM):
 *   tile:<kpi.id>     KPI tiles          (ids from each agent's dashboard.py)
 *   view:<viewKey>    focus panel        (dashboard.views[key])
 *   side:top|bottom   side panels        (dashboard.side.top / .bottom)
 *   stat:<stat.id>    what-if stat tiles (ids from summarizeResult)
 *   gauge             what-if gauge
 *   simchart          what-if mini chart
 *
 * Field meanings, unchanged from the mockup:
 *   el  element label shown as the card title
 *   x   plain-language explanation
 *   f   the formula / arithmetic behind the number
 * ============================================================
 */

export const INFO_REGISTRY = {
  "finance.finance": {
    "tile:margin": {
      el: "KPI · EBITDA margin",
      x: "Operating profit as a share of revenue. The headline the CFO reacts to — actual against the 15% target.",
      f: "EBITDA margin = EBITDA / Revenue"
    },
    "tile:ebitda": {
      el: "KPI · EBITDA",
      x: "Operating cash profit: gross margin minus operating expenses.",
      f: "EBITDA = Gross margin − Opex"
    },
    "tile:revenue": {
      el: "KPI · Revenue",
      x: "Total sales across the product lines, measured against budget.",
      f: "Revenue = Σ (Qty × Price) per line"
    },
    "tile:gm": {
      el: "KPI · Gross margin %",
      x: "Revenue minus COGS, as a share of revenue. Moves on input cost and FX.",
      f: "Gross margin % = Gross margin / Revenue"
    },
    "tile:opex": {
      el: "KPI · Opex to revenue",
      x: "Operating cost discipline — how much of every revenue rupiah is eaten below gross margin.",
      f: "Opex/Rev = Total opex / Revenue"
    },

    "view:drivers": {
      el: "Chart · EBITDA driver bridge",
      x: "Splits the profit gap from budget to actual into five causes that add up exactly. The largest negative steps are the margin culprits.",
      f: "Actual = Budget + Volume + Mix + Price + Cost·FX + Opex"
    },
    "view:revenue": {
      el: "Chart · Revenue by product",
      x: "Revenue per line. Total can sit on plan while the blend shifts toward lower-margin lines.",
      f: "Revenue(line) = Qty × Price"
    },
    "view:product": {
      el: "Chart · Gross margin % by product",
      x: "Margin rate per line. Watch for the best line losing volume while the thinnest one grows — that is the mix loss.",
      f: "GM% (line) = (Price − Cost) / Price"
    },
    "view:fx": {
      el: "Chart · FX sensitivity",
      x: "How EBITDA margin moves if the rupiah weakens 3/5/7%, transmitted through imported material cost.",
      f: "New cost = Cost × (1 + import share 55% × FX move%); ≈ −0.2 pts margin per 1%"
    },
    "view:opex": {
      el: "Table · Operating expenses vs budget",
      x: "Every opex line against budget, worst variance first — so the repeatable saving is the top row rather than something you hunt for.",
      f: "Variance = Actual − Budget; Total opex = Σ(lines)"
    },

    "side:top": {
      el: "Side · Margin by product",
      x: "Gross-margin rate per line, showing where the mix hurt.",
      f: "GM% = (Price − Cost) / Price per product"
    },
    "side:bottom": {
      el: "Side · Imported COGS share",
      x: "Share of COGS that is imported (55%) — the channel through which a weaker rupiah reaches the margin.",
      f: "Imported share = Imported COGS / Total COGS = 55%"
    },

    "stat:margin": {
      el: "Sim · Scenario margin",
      x: "The EBITDA margin under the levers you set.",
      f: "= Scenario EBITDA / Scenario Revenue"
    },
    "stat:ebitda": {
      el: "Sim · Scenario EBITDA",
      x: "Operating profit under the levers.",
      f: "= Scenario gross margin − Scenario opex"
    },
    "stat:target": {
      el: "Sim · Gap vs target",
      x: "Distance from the 15% target margin, in points.",
      f: "= (Scenario margin − 15%) × 100"
    },
    gauge: {
      el: "Sim · Path to target",
      x: "How close the scenario margin is to the 15% target.",
      f: "Ratio = Scenario margin / Target 15%"
    },
    simchart: {
      el: "Sim · Now vs Scenario",
      x: "Actual margin against the scenario you built, both measured against target.",
      f: "Now vs Scenario (live) vs Target 15%"
    }
  },

  "finance.treasury": {
    "tile:w5": {
      el: "KPI · Week 5 closing cash",
      x: "The tight week: closing cash falls below the policy buffer.",
      f: "Closing = Opening + Net cash flow"
    },
    "tile:buffer": {
      el: "KPI · Minimum cash buffer",
      x: "Policy floor cash must not fall below.",
      f: "Buffer = policy input"
    },
    "tile:usd": {
      el: "KPI · Net USD exposure",
      x: "USD payables minus USD receivables — the amount actually at FX risk.",
      f: "Net exposure = USD payables − USD receivables"
    },
    "tile:fx_loss": {
      el: "KPI · FX loss if unhedged",
      x: "Cash cost if the rupiah weakens by the adverse move, with the exposure left open.",
      f: "FX loss = Net exposure × Spot × move%"
    },
    "tile:hedge": {
      el: "KPI · Recommended hedge",
      x: "USD the agent proposes to forward-cover: enough to remove most of the downside without over-hedging a position that may not settle.",
      f: "Recommended hedge = Net exposure × target coverage%"
    },

    "view:forecast": {
      el: "Chart · 14-week cash forecast",
      x: "Weekly closing cash against the policy buffer. The dip below the line is the week to solve.",
      f: "Closing(w) = Closing(w−1) + Inflows(w) − Outflows(w)"
    },
    "view:exposure": {
      el: "Chart · Net USD exposure vs hedge",
      x: "The net USD at risk next to the hedge the agent recommends — the visual gap is what stays open.",
      f: "Uncovered = Net exposure − Recommended hedge"
    },
    "view:fx": {
      el: "Chart · FX impact if we do nothing",
      x: "Cash cost of leaving the exposure open, base case against the adverse rate.",
      f: "FX impact = Net exposure × (Adverse rate − Spot)"
    },
    "view:options": {
      el: "Table · Agent option comparison",
      x: "The four ways to handle the exposure — do nothing, forward-cover, buy spot, or hedge half — scored on downside avoided, premium paid, and what each does to liquidity. B and C remove the same FX risk, but C pays cash today and worsens the tight week.",
      f: "Avoided = Hedged USD × |Adverse − Spot|; Premium = Hedged USD × forward points"
    },

    "side:top": {
      el: "Side · Exposure vs hedge",
      x: "Net USD at risk against the recommended cover, showing how much of the position the hedge actually protects.",
      f: "Coverage% = Hedge / Net exposure"
    },
    "side:bottom": {
      el: "Side · Week 5 vs buffer",
      x: "How far Week 5 closing cash sits below the policy buffer.",
      f: "Shortfall = Buffer − Week 5 closing"
    },

    "stat:w5": {
      el: "Sim · Week 5 cash",
      x: "Closing cash in the tight week after the levers you set.",
      f: "= Base Week 5 + Accelerated + Deferred + Credit draw"
    },
    "stat:below": {
      el: "Sim · Weeks below buffer",
      x: "How many forecast weeks still breach the policy floor. Zero is the goal.",
      f: "= count(week where Closing < Buffer)"
    },
    "stat:fx": {
      el: "Sim · FX downside avoided",
      x: "FX loss removed by the forward cover you set, against the premium it costs.",
      f: "= min(Cover, Net exposure) × Spot × move%"
    },
    gauge: {
      el: "Sim · % of exposure covered",
      x: "Share of the net USD exposure the cover protects.",
      f: "Coverage = Cover / Net exposure"
    },
    simchart: {
      el: "Sim · Week 5 now vs scenario",
      x: "Week 5 closing cash before and after the levers, against the buffer line.",
      f: "Now vs Scenario (live) vs Buffer"
    }
  },

  "finance.collection": {
    "tile:ar": {
      el: "KPI · AR outstanding",
      x: "Total receivables on the book.",
      f: "AR = Σ all customer balances"
    },
    "tile:overdue": {
      el: "KPI · Overdue",
      x: "Balance past its due date — the part of AR that is genuinely at risk.",
      f: "Overdue = Σ(1–30 + 31–60 + 61–90 + 90+)"
    },
    "tile:dso": {
      el: "KPI · Days Sales Outstanding",
      x: "Average days to collect, measured against the target.",
      f: "DSO = AR / Annual credit sales × 365"
    },
    "tile:prize": {
      el: "KPI · Cash freed at target",
      x: "Cash released by cutting DSO to target — the size of the prize.",
      f: "Cash freed = (Current DSO − Target) × Daily sales"
    },
    "tile:high_risk": {
      el: "KPI · High-risk exposure",
      x: "Balance owed by customers scored in the High risk tier — chase early, provision if it ages.",
      f: "= Σ balances where risk tier = High"
    },

    "view:aging": {
      el: "Chart · Receivables aging",
      x: "AR split by how overdue it is. The 90+ and 61–90 buckets are the priority — recovery rates fall fast with age.",
      f: "Buckets: Current, 1–30, 31–60, 61–90, 90+ (Σ = total AR)"
    },
    "view:worklist": {
      el: "Table · Who to chase first",
      x: "Overdue accounts ranked by amount and risk, with the recovery you can expect from each.",
      f: "Expected recovery = Overdue × recovery% by tier (Low 95, Med 85, High 40)"
    },
    "view:prize": {
      el: "Chart · DSO to cash",
      x: "Current DSO against target — the gap converted into the cash it would free.",
      f: "Cash freed = (DSO − Target) × Daily sales; Daily = Annual credit sales / 365"
    },
    "view:tiers": {
      el: "Chart · Risk exposure by tier",
      x: "Balances grouped into High / Medium / Low risk, so effort goes where recovery is still likely.",
      f: "Tier from risk score: High ≥67, Medium 34–66, Low <34"
    },
    "view:options": {
      el: "Chart · Three collection options",
      x: "Cash freed at three levels of reach — one call, a focused push on the top 5, or chasing everything overdue. Each bar's label carries the DSO that option buys you.",
      f: "Cash freed = Σ (Overdue × recovery% by tier); New DSO = (AR − freed) / Daily sales"
    },

    "side:top": {
      el: "Side · Aging mix",
      x: "Share of AR sitting in each aging bucket.",
      f: "Bucket share = Bucket / Total AR"
    },
    "side:bottom": {
      el: "Side · DSO vs target",
      x: "Current DSO against the target, and against the scenario once you run one.",
      f: "Gap = DSO − Target"
    },

    "stat:dso": {
      el: "Sim · Scenario DSO",
      x: "Days to collect after the pull and discount you set.",
      f: "= (AR − Cash collected) / Daily sales"
    },
    "stat:cash": {
      el: "Sim · Cash collected",
      x: "Cash pulled forward by the scenario.",
      f: "= Amount pulled from customer × expected recovery%"
    },
    "stat:discount": {
      el: "Sim · Discount cost",
      x: "Margin given away to pull the cash in early — the price of the acceleration.",
      f: "= Cash collected × Discount%"
    },
    gauge: {
      el: "Sim · DSO vs target",
      x: "How close the scenario DSO lands to the target.",
      f: "Ratio = Target DSO / Scenario DSO"
    },
    simchart: {
      el: "Sim · DSO now vs scenario",
      x: "Current DSO against the scenario, both measured against the target line.",
      f: "Now vs Scenario (live) vs Target"
    }
  },

  "finance.leakage": {
    "tile:flagged": {
      el: "KPI · Flagged this cycle",
      x: "Total amount at risk across every item the scan flagged this cycle.",
      f: "At risk = Σ amount-at-risk on flagged rows"
    },
    "tile:fraud": {
      el: "KPI · Fraud held",
      x: "Suspected bank-change fraud held before payment — caught while the cash is still yours.",
      f: "= Amount on bank-change flags"
    },
    "tile:dup": {
      el: "KPI · Duplicates",
      x: "Duplicate payments already made, to claw back from the vendor.",
      f: "= Σ duplicate-payment flags"
    },
    "tile:blocked": {
      el: "KPI · Blocked before payment",
      x: "Amount stopped while still pending, so no cash leaves the building. Certain, unlike recovery.",
      f: "Blocked = Fraud hold + Overbilled pending"
    },
    "tile:protected": {
      el: "KPI · Total protected",
      x: "Blocked plus what you expect to recover at the current claw-back rates.",
      f: "Total = Blocked + Duplicates × dupRec% + Overbill paid × ovRec%"
    },

    "view:categories": {
      el: "Chart · Leakage & fraud by category",
      x: "Amount at risk by anomaly type. Fraud and duplicates are usually the material two.",
      f: "Category total = Σ amount-at-risk where type = category"
    },
    "view:blockvs": {
      el: "Chart · Blocked vs recoverable vs lost",
      x: "Three very different levels of certainty: blocked never leaves the building, recoverable already left and must be clawed back, lost is gone. The three add up to everything flagged.",
      f: "Blocked + Recoverable + Lost = Total at risk"
    },
    "view:recovery": {
      el: "Chart · Recovery scenario",
      x: "Total protected at pessimistic / base / current claw-back rates. Shows how much of 'protected' is cash you actually hold versus an assumption about recovery.",
      f: "Protected(rate) = Blocked + (Duplicates + Overbill paid) × rate%"
    },
    "view:worklist": {
      el: "Table · Action worklist",
      x: "Flagged items ranked by amount at risk, worst first — the queue to work today.",
      f: "Amount-at-risk = full amount (fraud/duplicate) or the gap (overbilling)"
    },
    "view:vendors": {
      el: "Table · Vendor risk radar",
      x: "The same flags clustered by vendor rather than by item, so repeat offenders and duplicated vendor masters surface instead of hiding as one-offs. Ranked by total exposure.",
      f: "Vendor at-risk = Σ that vendor's flagged amounts; score is illustrative 0–100"
    },

    "side:top": {
      el: "Side · Leakage mix",
      x: "Share of the amount at risk by category.",
      f: "Category share = Category / Total at risk"
    },
    "side:bottom": {
      el: "Side · Protected vs at risk",
      x: "How much of the total at risk is protected under current settings.",
      f: "Protected / At risk"
    },

    "stat:total": {
      el: "Sim · Total protected",
      x: "Blocked plus recovered at the recovery rates you set.",
      f: "= Blocked + Duplicates × dupRec% + Overbill paid × ovRec%"
    },
    "stat:blocked": {
      el: "Sim · Blocked",
      x: "Amount held before payment — certain, because the cash never leaves.",
      f: "= Fraud hold + Overbilled pending"
    },
    "stat:recovered": {
      el: "Sim · Recovered",
      x: "Expected claw-back on items already paid — an estimate, not cash in hand.",
      f: "= Duplicates × dupRec% + Overbill paid × ovRec%"
    },
    gauge: {
      el: "Sim · Protected vs at risk",
      x: "Share of the flagged exposure your scenario protects.",
      f: "Ratio = Total protected / At risk"
    },
    simchart: {
      el: "Sim · At risk vs Protected",
      x: "Total amount at risk against what the scenario protects.",
      f: "At risk vs Protected (live)"
    }
  }
};

/**
 * Look up an info entry for an agent + info key.
 * Returns null when the element has no mapping, which lets the
 * caller fall back to going straight to chat.
 */
export function findInfo(agentId, infoKey) {
  if (!agentId || !infoKey) {
    return null;
  }
  return INFO_REGISTRY[agentId]?.[infoKey] || null;
}

/**
 * Build the chat prompt used by "Continue in chat".
 * Mirrors infoToChat() in the mockup: the CFO's question carries
 * the element label, and the agent answers with the live numbers.
 */
export function buildInfoPrompt(entry, context = "") {
  const detail = context ? ` Current reading: ${context}.` : "";

  return (
    `Explain "${entry.el}" on my dashboard.${detail} ` +
    `For reference it is defined as: ${entry.f}. ` +
    "Interpret what it is telling me right now, why it sits at " +
    "this level, and what I should do about it. Keep it concise " +
    "and decision-focused for a CFO."
  );
}
