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
});
