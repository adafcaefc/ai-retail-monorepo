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
          conversationId
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

export async function
recalculateCollectionSimulation({
  customerName,
  cashToCollectIdrMn,
  discountPct,
  signal
}) {
  const response = await fetch(
    "/api/html/simulations/collections/recalculate",
    {
      method: "POST",

      headers: {
        "Content-Type":
          "application/json"
      },

      body: JSON.stringify({
        customer_name:
          customerName,

        cash_to_collect_idr_mn:
          Number(
            cashToCollectIdrMn
          ),

        discount_pct:
          Number(
            discountPct
          )
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