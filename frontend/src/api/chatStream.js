function parseSseFrame(frame) {
  let eventName = "message";
  const dataLines = [];

  for (const line of frame.split(/\r?\n/)) {
    if (line.startsWith("event:")) {
      eventName = line.slice(6).trim();
    }

    if (line.startsWith("data:")) {
      dataLines.push(
        line.slice(5).trimStart()
      );
    }
  }

  if (!dataLines.length) {
    return null;
  }

  const rawData = dataLines.join("\n");

  return {
    name: eventName,
    data: JSON.parse(rawData)
  };
}

export async function streamChat({
  agent,
  message,
  conversationId,
  legalEntityId,
  period,
  categoryGroup,
  signal,
  onEvent
}) {
  const response = await fetch(
    "/api/html/chat",
    {
      method: "POST",

      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream"
      },

      body: JSON.stringify({
        agent,
        message,
        conversation_id:
          conversationId,
        // The board's active server_filters selections, so a question asked
        // while the board is scoped is answered about that same slice
        // rather than the whole ledger — see scope.py server-side.
        legal_entity_id:
          legalEntityId,
        period,
        category_group:
          categoryGroup
      }),

      signal
    }
  );

  if (!response.ok) {
    const detail =
      await response.text();

    throw new Error(
      `Request failed (${response.status})${
        detail ? `: ${detail}` : ""
      }`
    );
  }

  if (!response.body) {
    throw new Error(
      "Streaming responses are not supported by this browser."
    );
  }

  const reader =
    response.body.getReader();

  const decoder =
    new TextDecoder();

  let buffer = "";

  while (true) {
    const { value, done } =
      await reader.read();

    buffer += decoder.decode(
      value || new Uint8Array(),
      {
        stream: !done
      }
    );

    const frames =
      buffer.split(/\r?\n\r?\n/);

    buffer = frames.pop() || "";

    for (const frame of frames) {
      if (!frame.trim()) {
        continue;
      }

      const parsed =
        parseSseFrame(frame);

      if (parsed) {
        onEvent(parsed);
      }
    }

    if (done) {
      break;
    }
  }

  if (buffer.trim()) {
    const parsed =
      parseSseFrame(buffer);

    if (parsed) {
      onEvent(parsed);
    }
  }
}

export async function fetchConversations() {
  const response = await fetch(
    "/api/html/conversations"
  );

  if (!response.ok) {
    throw new Error(
      "Could not load conversations."
    );
  }

  return response.json();
}

export async function fetchConversation(
  conversationId
) {
  const response = await fetch(
    `/api/html/conversations/${conversationId}`
  );

  if (!response.ok) {
    throw new Error(
      "Could not load the selected conversation."
    );
  }

  return response.json();
}

/*
 * Each board has its own simulator behind its own endpoint. The simulation
 * block carries the `action` that produced it, so that is what picks the
 * route — this used to post every scenario to the collection endpoint no
 * matter which board it came from, which is why Treasury, Finance and Leakage
 * could never recalculate.
 */
const SIMULATION_ENDPOINTS = {
  calculate_collection_scenario:
    "collection",

  simulate_cashflow:
    "treasury",

  simulate_finance:
    "finance",

  simulate_leakage:
    "leakage"
};


export async function
recalculateSimulation({
  action,
  values,
  submitData,
  signal
}) {
  const board =
    SIMULATION_ENDPOINTS[action];

  if (!board) {
    throw new Error(
      "This simulation is not " +
      "connected to a simulator " +
      `(action: ${action || "missing"}).`
    );
  }

  const response = await fetch(
    `/api/html/simulations/${board}/recalculate`,
    {
      method: "POST",

      headers: {
        "Content-Type":
          "application/json"
      },

      /*
       * Slider ids already match the field names their endpoint expects, so
       * the values are sent as they are. The old code remapped everything
       * into the collection request shape, which silently dropped every
       * lever the collection simulator does not have.
       */
      body: JSON.stringify({
        ...(submitData || {}),
        ...values
      }),

      signal
    }
  );

  if (!response.ok) {
    let detail = "";

    try {
      const errorBody =
        await response.json();

      detail =
        errorBody.detail ||
        JSON.stringify(
          errorBody
        );
    } catch {
      detail =
        await response.text();
    }

    throw new Error(
      detail ||
      `Simulation failed (${response.status})`
    );
  }

  const responseBody =
    await response.json();

  return (
    responseBody.result ||
    responseBody
  );
}