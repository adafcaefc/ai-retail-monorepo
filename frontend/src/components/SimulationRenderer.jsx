import {
  useMemo,
  useState
} from "react";

import {
  recalculateCollectionSimulation
} from "../api/chatStream.js";


export default function SimulationRenderer({
  data
}) {
  const inputs = useMemo(() => {
    return Array.isArray(data?.inputs)
      ? data.inputs
      : [];
  }, [data]);

  const outputDefinitions =
    Array.isArray(data?.outputs)
      ? data.outputs
      : [];

  const initialValues =
    useMemo(() => {
      return Object.fromEntries(
        inputs.map((input) => [
          input.id,
          getInitialValue(input)
        ])
      );
    }, [inputs]);

  const [
    values,
    setValues
  ] = useState(
    () => initialValues
  );

  const [
    result,
    setResult
  ] = useState(null);

  const [
    loading,
    setLoading
  ] = useState(false);

  const [
    error,
    setError
  ] = useState("");

  const [
    success,
    setSuccess
  ] = useState(false);


  function updateValue(
    inputId,
    rawValue
  ) {
    const numericValue =
      Number(rawValue);

    if (
      !Number.isFinite(
        numericValue
      )
    ) {
      return;
    }

    setValues((current) => {
      const nextValues = {
        ...current
      };

      /*
       * INI BAGIAN PENTING.
       * Nilai disimpan berdasarkan
       * inputId, bukan property literal
       * "normalizedValue".
       */
      nextValues[inputId] =
        numericValue;

      return nextValues;
    });

    setSuccess(false);
  }


  async function handleRecalculate() {
    if (loading) {
      return;
    }

    const cashToCollect =
      getInputValue(
        values,
        [
          "cash_to_collect_idr_mn",
          "cash_to_collect",
          "cash_collection_target",
          "accelerate_collection_idr_mn"
        ],
        0
      );

    const discountPct =
      getInputValue(
        values,
        [
          "discount_pct",
          "early_payment_discount_pct",
          "early_pay_discount_pct",
          "discount"
        ],
        0
      );

    if (cashToCollect <= 0) {
      setError(
        "Cash to collect must be greater than zero."
      );

      return;
    }

    setLoading(true);
    setError("");
    setSuccess(false);

    const controller =
      new AbortController();

    try {
      const simulationResult =
        await recalculateCollectionSimulation({
          customerName:
            getCustomerName(data),

          cashToCollectIdrMn:
            cashToCollect,

          discountPct,

          signal:
            controller.signal
        });
      
      console.log(
        "SIMULATION BACKEND RESULTS",
        simulationResult
      );  
      setResult(
        simulationResult
      );

      setSuccess(true);

    } catch (requestError) {
      setError(
        requestError.message ||
        "Simulation could not be recalculated."
      );

    } finally {
      setLoading(false);
    }
  }


  const renderedOutputs =
    buildRenderedOutputs({
      definitions:
        outputDefinitions,

      result,

      values
    });

  return (
    <section className="simulation-card">
      <header className="simulation-header">
        <div>
          <span className="simulation-kicker">
            What-if simulation
          </span>

          <h3>
            {data?.title ||
              "Collection simulation"}
          </h3>
        </div>

        <span className="simulation-badge">
          Illustrative
        </span>
      </header>


      {data?.calculation_instructions && (
        <p className="simulation-description">
          {
            data.calculation_instructions
          }
        </p>
      )}


      {getCustomerName(data) && (
        <div className="simulation-context">
          <strong>
            Customer
          </strong>

          <span>
            {getCustomerName(data)}
          </span>
        </div>
      )}


      <div className="simulation-grid">
        <div className="simulation-inputs">
          <h4>
            Scenario inputs
          </h4>

          {!inputs.length && (
            <p className="simulation-empty">
              No simulation inputs were
              provided.
            </p>
          )}

          {inputs.map((input) => (
            <SimulationInput
              key={input.id}

              input={input}

              value={
                values[input.id] ??
                getInitialValue(input)
              }

              onChange={(newValue) =>
                updateValue(
                  input.id,
                  newValue
                )
              }
            />
          ))}
        </div>


        <div className="simulation-outputs">
          <h4>
            Scenario outputs
          </h4>

          {!renderedOutputs.length && (
            <p className="simulation-empty">
              No simulation outputs were
              provided.
            </p>
          )}

          <div className="output-grid">
            {renderedOutputs.map(
              (output) => (
                <OutputCard
                  key={output.id}
                  output={output}
                />
              )
            )}
          </div>
        </div>
      </div>


      {error && (
        <div
          className="simulation-error"
          role="alert"
        >
          {error}
        </div>
      )}


      {success && (
        <div
          className="simulation-success"
          role="status"
        >
          Scenario recalculated
          successfully.
        </div>
      )}


      <footer className="simulation-footer">
        <p>
          This is a what-if simulation.
          Recalculation does not modify
          the source receivables ledger.
        </p>

        <button
          type="button"
          className="recalculate-button"

          disabled={
            loading ||
            !inputs.length
          }

          onClick={
            handleRecalculate
          }
        >
          {loading
            ? "Recalculating..."
            : "Recalculate"}
        </button>
      </footer>
    </section>
  );
}


function SimulationInput({
  input,
  value,
  onChange
}) {
  const minimum =
    toFiniteNumber(
      input.min,
      0
    );

  const maximum =
    toFiniteNumber(
      input.max,
      100
    );

  const step =
    toFiniteNumber(
      input.step,
      1
    );

  const normalizedValue =
    clamp(
      toFiniteNumber(
        value,
        minimum
      ),
      minimum,
      maximum
    );


  return (
    <div className="simulation-control">
      <div className="control-heading">
        <label
          htmlFor={
            `${input.id}-number`
          }
        >
          {input.label ||
            input.id}
        </label>

        {input.unit && (
          <span>
            {input.unit}
          </span>
        )}
      </div>


      <div className="control-row">
        <input
          id={`${input.id}-range`}

          type="range"

          min={minimum}
          max={maximum}
          step={step}

          value={
            normalizedValue
          }

          /*
           * onInput membuat thumb slider
           * bergerak langsung saat drag.
           */
          onInput={(event) =>
            onChange(
              event.currentTarget.value
            )
          }

          aria-label={
            input.label ||
            input.id
          }
        />


        <input
          id={`${input.id}-number`}

          className="number-input"

          type="number"

          min={minimum}
          max={maximum}
          step={step}

          value={
            normalizedValue
          }

          onChange={(event) =>
            onChange(
              event.currentTarget.value
            )
          }

          aria-label={
            `${input.label || input.id} value`
          }
        />
      </div>


      <div className="control-scale">
        <span>
          {formatNumber(minimum)}
        </span>

        <span>
          {formatNumber(maximum)}
        </span>
      </div>
    </div>
  );
}


function OutputCard({
  output
}) {
  const hasValue =
    output.value !== null &&
    output.value !== undefined &&
    output.value !== "";

  return (
    <article className="output-card">
      <span className="output-label">
        {output.label}
      </span>

      <strong className="output-value">
        {hasValue
          ? formatNumber(
              output.value
            )
          : "—"}
      </strong>

      {output.unit && (
        <small>
          {output.unit}
        </small>
      )}
    </article>
  );
}


function buildRenderedOutputs({
  definitions,
  result,
  values
}) {
  const cashToCollect =
    getInputValue(
      values,
      [
        "cash_to_collect_idr_mn",
        "cash_to_collect",
        "cash_collection_target",
        "accelerate_collection_idr_mn"
      ],
      null
    );

  const discountPct =
    getInputValue(
      values,
      [
        "discount_pct",
        "early_payment_discount_pct",
        "early_pay_discount_pct",
        "discount"
      ],
      null
    );

  if (!definitions.length) {
    if (
      !result ||
      typeof result !== "object"
    ) {
      return [];
    }

    return Object.entries(result)
      .filter(([, value]) =>
        isDisplayableValue(value)
      )
      .map(([key, value]) => ({
        id: key,
        label: humanizeKey(key),
        value,
        unit: inferUnit(key)
      }));
  }

  return definitions.map(
    (definition, index) => {
      const normalizedLabel =
        normalizeKey(
          definition.label ||
          definition.name ||
          ""
        );

      const outputId =
        normalizeKey(
          definition.id ||
          normalizedLabel ||
          `output_${index}`
        );

      let resultValue =
        findResultValue(
          result,
          [
            outputId,
            definition.id,
            normalizedLabel
          ]
        );

      /*
       * Cash Recovered adalah gross cash
       * yang berhasil ditarik.
       *
       * Jika backend tidak mengembalikan
       * field gross cash secara eksplisit,
       * gunakan Cash to Collect sebagai
       * fallback.
       */
      if (
        resultValue === undefined &&
        isCashRecoveredOutput(
          outputId,
          normalizedLabel
        ) &&
        Number.isFinite(cashToCollect)
      ) {
        resultValue = cashToCollect;
      }

      /*
       * Discount Cost fallback:
       * cash × discount percentage.
       */
      if (
        resultValue === undefined &&
        isDiscountCostOutput(
          outputId,
          normalizedLabel
        ) &&
        Number.isFinite(cashToCollect) &&
        Number.isFinite(discountPct)
      ) {
        resultValue =
          cashToCollect *
          (discountPct / 100);
      }

      /*
       * Net Cash Recovery fallback:
       * gross cash - discount cost.
       */
      if (
        resultValue === undefined &&
        isNetCashOutput(
          outputId,
          normalizedLabel
        ) &&
        Number.isFinite(cashToCollect) &&
        Number.isFinite(discountPct)
      ) {
        const discountCost =
          cashToCollect *
          (discountPct / 100);

        resultValue =
          cashToCollect -
          discountCost;
      }

      return {
        id: outputId,

        label:
          definition.label ||
          definition.name ||
          humanizeKey(outputId),

        value:
          resultValue ??
          definition.value ??
          null,

        unit:
          definition.unit ||
          inferUnit(outputId)
      };
    }
  );
}


function findResultValue(
  result,
  candidates
) {
  if (
    !result ||
    typeof result !== "object"
  ) {
    return undefined;
  }

  /*
   * Normalisasi semua field backend.
   *
   * Contoh:
   * "Gross Cash Collected"
   * menjadi:
   * "gross_cash_collected"
   */
  const normalizedResult =
    Object.fromEntries(
      Object.entries(result).map(
        ([key, value]) => [
          normalizeKey(key),
          value
        ]
      )
    );

  const aliasMap = {
    cash_recovered: [
      "cash_recovered",
      "cash_recovered_idr_mn",
      "gross_cash_recovered",
      "gross_cash_recovered_idr_mn",
      "gross_cash_collected",
      "gross_cash_collected_idr_mn",
      "cash_collected",
      "cash_collected_idr_mn",
      "cash_collected_early",
      "cash_collected_early_idr_mn",
      "cash_freed",
      "cash_freed_idr_mn",
      "cash_to_collect",
      "cash_to_collect_idr_mn"
    ],

    gross_cash_recovered: [
      "gross_cash_recovered",
      "gross_cash_recovered_idr_mn",
      "gross_cash_collected",
      "gross_cash_collected_idr_mn",
      "cash_recovered",
      "cash_recovered_idr_mn",
      "cash_to_collect",
      "cash_to_collect_idr_mn"
    ],

    gross_cash_collected: [
      "gross_cash_collected",
      "gross_cash_collected_idr_mn",
      "gross_cash_recovered",
      "gross_cash_recovered_idr_mn",
      "cash_recovered",
      "cash_recovered_idr_mn",
      "cash_collected",
      "cash_collected_idr_mn",
      "cash_freed",
      "cash_freed_idr_mn",
      "cash_to_collect",
      "cash_to_collect_idr_mn"
    ],

    discount_cost: [
      "discount_cost",
      "discount_cost_idr_mn",
      "early_payment_discount_cost",
      "early_payment_discount_cost_idr_mn"
    ],

    net_cash_recovery: [
      "net_cash_recovery",
      "net_cash_recovery_idr_mn",
      "net_cash_recovered",
      "net_cash_recovered_idr_mn"
    ],

    remaining_overdue_balance: [
      "remaining_overdue_balance",
      "remaining_overdue_balance_idr_mn",
      "remaining_overdue_idr_mn",
      "customer_overdue_after_idr_mn",
      "customer_overdue_after_collection",
      "customer_overdue_after_collection_idr_mn"
    ],

    portfolio_dso_after_collection: [
      "portfolio_dso_after_collection",
      "portfolio_dso_after_collection_days",
      "portfolio_dso_after_days",
      "updated_portfolio_dso",
      "updated_portfolio_dso_days",
      "new_dso",
      "new_dso_days",
      "dso_after_days"
    ],

    updated_portfolio_dso: [
      "updated_portfolio_dso",
      "updated_portfolio_dso_days",
      "portfolio_dso_after_collection",
      "portfolio_dso_after_collection_days",
      "portfolio_dso_after_days",
      "new_dso",
      "new_dso_days",
      "dso_after_days"
    ],

    dso_improvement: [
      "dso_improvement",
      "dso_improvement_days",
      "dso_reduction",
      "dso_reduction_days"
    ]
  };

  const normalizedCandidates =
    candidates
      .filter(Boolean)
      .map(normalizeKey);

  for (
    const candidate
    of normalizedCandidates
  ) {
    const possibleKeys = [
      candidate,
      ...(aliasMap[candidate] || [])
    ];

    for (
      const possibleKey
      of possibleKeys
    ) {
      const normalizedKey =
        normalizeKey(possibleKey);

      if (
        Object.prototype
          .hasOwnProperty.call(
            normalizedResult,
            normalizedKey
          )
      ) {
        return normalizedResult[
          normalizedKey
        ];
      }
    }
  }

  return undefined;
}

function isCashRecoveredOutput(
  outputId,
  normalizedLabel
) {
  const possibleNames = [
    outputId,
    normalizedLabel
  ].map(normalizeKey);

  return possibleNames.some(
    (name) =>
      [
        "cash_recovered",
        "gross_cash_recovered",
        "gross_cash_collected",
        "cash_collected",
        "cash_collected_early",
        "cash_freed"
      ].includes(name)
  );
}


function isDiscountCostOutput(
  outputId,
  normalizedLabel
) {
  const possibleNames = [
    outputId,
    normalizedLabel
  ].map(normalizeKey);

  return possibleNames.some(
    (name) =>
      [
        "discount_cost",
        "early_payment_discount_cost"
      ].includes(name)
  );
}


function isNetCashOutput(
  outputId,
  normalizedLabel
) {
  const possibleNames = [
    outputId,
    normalizedLabel
  ].map(normalizeKey);

  return possibleNames.some(
    (name) =>
      [
        "net_cash_recovery",
        "net_cash_recovered"
      ].includes(name)
  );
}

function getCustomerName(data) {
  return (
    data?.customer_name ||
    data?.submit_data
      ?.customer_name ||
    "PT Anugerah Prima (Customer A)"
  );
}

function getInputValue(
  values,
  candidateIds,
  fallback
) {
  for (
    const candidateId
    of candidateIds
  ) {
    if (
      Object.prototype
        .hasOwnProperty.call(
          values,
          candidateId
        )
    ) {
      return toFiniteNumber(
        values[candidateId],
        fallback
      );
    }
  }

  return fallback;
}


function getInitialValue(input) {
  return toFiniteNumber(
    input.default ??
      input.value,
    0
  );
}


function normalizeKey(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(
      /[^a-z0-9]+/g,
      "_"
    )
    .replace(
      /^_+|_+$/g,
      ""
    );
}


function humanizeKey(value) {
  return String(value || "")
    .replaceAll("_", " ")
    .replace(
      /\b\w/g,
      (character) =>
        character.toUpperCase()
    );
}


function inferUnit(key) {
  const normalized =
    normalizeKey(key);

  if (
    normalized.includes("dso") ||
    normalized.includes("day")
  ) {
    return "days";
  }

  if (
    normalized.includes("pct") ||
    normalized.includes("percent") ||
    normalized.includes("discount_rate")
  ) {
    return "%";
  }

  if (
    normalized.includes("cash") ||
    normalized.includes("cost") ||
    normalized.includes("overdue") ||
    normalized.includes("idr")
  ) {
    return "IDR mn";
  }

  return "";
}


function isDisplayableValue(value) {
  return (
    typeof value === "number" ||
    typeof value === "string"
  );
}


function toFiniteNumber(
  value,
  fallback
) {
  const numericValue =
    Number(value);

  return Number.isFinite(
    numericValue
  )
    ? numericValue
    : fallback;
}


function clamp(
  value,
  minimum,
  maximum
) {
  return Math.min(
    maximum,
    Math.max(
      minimum,
      value
    )
  );
}


function formatNumber(value) {
  const numericValue =
    Number(value);

  if (
    !Number.isFinite(
      numericValue
    )
  ) {
    return String(
      value ?? "—"
    );
  }

  return numericValue.toLocaleString(
    undefined,
    {
      maximumFractionDigits: 2
    }
  );
}