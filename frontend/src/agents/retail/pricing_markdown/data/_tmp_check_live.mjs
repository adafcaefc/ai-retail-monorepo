import { readFileSync } from "node:fs";
import { buildDashboardFromFixture } from "./selectors.js";

const payload = JSON.parse(
  readFileSync(
    "C:/Users/erika/AppData/Local/Temp/claude/c---EY-ai-retail-monorepo/547abe84-8d4d-468a-9841-079116a944fc/scratchpad/a5_live.json",
    "utf-8",
  ),
);
const dash = buildDashboardFromFixture(payload, {}, {});
console.log(JSON.stringify(dash.kpis, null, 2));
