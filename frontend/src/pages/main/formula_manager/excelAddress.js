// Worked examples cite the workbook cell they came from, e.g. ENGINE_STORE!J4.
//
// The real link target is not wired up yet, so every address resolves to "#".
// This is deliberately the ONLY place that builds the href: swap the body here
// once the destination is known and every citation on the page follows.

export function excelAddressHref() {
  return "#";
}

/** Split "ENGINE_STORE!J4" into its sheet and cell for display. */
export function splitAddress(address) {
  const separator = String(address ?? "").indexOf("!");
  if (separator === -1) {
    return { sheet: "", cell: String(address ?? "") };
  }
  return {
    sheet: address.slice(0, separator),
    cell: address.slice(separator + 1)
  };
}
