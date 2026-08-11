import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import SeverityBadge from "../SeverityBadge";
import type { Severity } from "../../api/types";

describe("SeverityBadge", () => {
  it("T-UI5 test_badge_colore_per_severity: applica la classe corretta per ciascuna severity", () => {
    const cases: Severity[] = ["critical", "error", "warning", "info", "debug"];

    for (const severity of cases) {
      const { container, unmount } = render(<SeverityBadge severity={severity} />);
      expect(container.querySelector(`.severity-${severity}`)).not.toBeNull();
      unmount();
    }
  });

  it("severity_badge_never_wraps: il badge ha la classe 'severity-badge' che ne impedisce il wrap", () => {
    // jsdom non applica styles.css, quindi qui si verifica la classe: la regola
    // `.severity-badge { white-space: nowrap }` sta in styles.css.
    const { getByText } = render(<SeverityBadge severity="critical" />);
    const badge = getByText("Critica");
    expect(badge).toHaveClass("severity-badge");
    expect(badge).toHaveClass("severity-critical");
  });
});
