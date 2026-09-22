import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { REVOKE_DELAY_MS, saveBlob } from "../download";

describe("saveBlob", () => {
  const revokeObjectURL = vi.fn();
  let collegataAlClick: boolean | null = null;
  let clickSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.useFakeTimers();
    collegataAlClick = null;
    revokeObjectURL.mockReset();
    Object.defineProperty(URL, "createObjectURL", {
      value: vi.fn(() => "blob:file"),
      configurable: true,
    });
    Object.defineProperty(URL, "revokeObjectURL", { value: revokeObjectURL, configurable: true });
    clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(function (this: HTMLAnchorElement) {
        collegataAlClick = this.isConnected;
      });
  });

  afterEach(() => {
    clickSpy.mockRestore();
    vi.useRealTimers();
  });

  it("clicca un'ancora attaccata al documento e poi la toglie", () => {
    saveBlob(new Blob(["x"]), "file.txt");

    // Firefox ignora il click su un'ancora che non sta nel DOM.
    expect(collegataAlClick).toBe(true);
    expect(document.querySelector('a[download="file.txt"]')).toBeNull();
  });

  it("revoca l'URL solo dopo il margine, non subito dopo il click", () => {
    saveBlob(new Blob(["x"]), "file.txt");

    // Revocato subito, Firefox e Safari possono non trovare piu' il blob.
    expect(revokeObjectURL).not.toHaveBeenCalled();
    vi.advanceTimersByTime(REVOKE_DELAY_MS - 1);
    expect(revokeObjectURL).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:file");
  });
});
