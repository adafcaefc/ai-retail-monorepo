// Frontend agent registry. Add an agent = add a folder + one import line.
// Canonical ids (folder.agent) match the backend registry exactly.

import finance from "./finance/finance/index.js";
import leakage from "./finance/leakage/index.js";
import collection from "./finance/collection/index.js";
import treasury from "./finance/treasury/index.js";

// Sidebar order.
export const AGENT_LIST = [finance, leakage, collection, treasury];

export const AGENTS = Object.fromEntries(
  AGENT_LIST.map((agent) => [agent.id, agent])
);

export const AGENT_IDS = AGENT_LIST.map((agent) => agent.id);

export default AGENTS;
