import { useEffect } from "react";

import { useMonitoring } from "../monitoring/MonitoringProvider.jsx";

/**
 * Top-right stack of toasts announcing newly detected problems (e.g. a
 * customer that has not paid). Fed by MonitoringProvider, which only pushes
 * problems it has never announced before, so this never spams repeats.
 */
export default function ProblemToasts() {
  const { problems, moreProblems, dismissProblem } = useMonitoring();

  if (!problems || problems.length === 0) {
    return null;
  }

  return (
    <div
      className="problem-toast-stack"
      role="region"
      aria-label="Newly detected problems"
    >
      {problems.map((problem) => (
        <ProblemToast
          key={problem.id}
          problem={problem}
          dismiss={dismissProblem}
        />
      ))}

      {moreProblems > 0 ? (
        <div className="problem-toast-more">
          +{moreProblems} more in the alerts bell
        </div>
      ) : null}
    </div>
  );
}

function ProblemToast({ problem, dismiss }) {
  const { id } = problem;

  useEffect(() => {
    const timeout = window.setTimeout(() => dismiss(id), 9000);
    return () => window.clearTimeout(timeout);
  }, [id, dismiss]);

  return (
    <div className="problem-toast" role="alert">
      <span className="problem-toast-icon" aria-hidden="true">
        !
      </span>

      <div className="problem-toast-body">
        <div className="problem-toast-head">
          <span className="problem-toast-agent">{problem.agentName}</span>
          <span className="problem-toast-name">{problem.name}</span>
        </div>
        {problem.issue ? (
          <p className="problem-toast-issue">{problem.issue}</p>
        ) : null}
      </div>

      <button
        type="button"
        className="problem-toast-close"
        aria-label="Dismiss"
        onClick={() => dismiss(id)}
      >
        ×
      </button>
    </div>
  );
}
