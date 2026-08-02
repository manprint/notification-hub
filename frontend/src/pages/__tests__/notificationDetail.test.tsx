import { screen, waitFor } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import NotificationDetailPage from "../NotificationDetailPage";
import {
  fixtureNotificationDetailInline,
  fixtureNotificationDetailObject,
} from "../../api/mocks/handlers";
import { renderWithProviders } from "./testUtils";

function renderDetail(id: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/notifications/:id" element={<NotificationDetailPage />} />
    </Routes>,
    [`/notifications/${id}`],
  );
}

describe("NotificationDetailPage", () => {
  it("T-UI10 test_payload_offloaded_mostra_download: storage_backend object mostra il download, non il corpo", async () => {
    renderDetail("n4");

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Scarica contenuto completo" })).toBeInTheDocument();
    });

    expect(screen.queryByText(fixtureNotificationDetailObject.content_preview)).not.toBeInTheDocument();
    expect(document.querySelector("pre")).not.toBeInTheDocument();
  });

  it("T-UI11 test_origine_severity_mostrata: con severity_source rule compare il pattern vincente", async () => {
    renderDetail("n1");

    await waitFor(() => {
      expect(screen.getByText(fixtureNotificationDetailInline.matched_pattern)).toBeInTheDocument();
    });
  });
});
