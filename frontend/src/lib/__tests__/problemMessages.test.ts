import { describe, expect, it } from "vitest";
import type { ApiError } from "../../api/types";
import { problemMessage, problemText, validationMessage } from "../problemMessages";

function errore(partial: Partial<ApiError>): ApiError {
  return { status: 400, type: "/problems/generic", title: "Bad Request", detail: "", extra: {}, ...partial };
}

describe("problemMessages", () => {
  it("un dettaglio noto del backend diventa la frase italiana, senza l'inglese", () => {
    const e = errore({ status: 401, type: "/problems/unauthorized", detail: "Invalid credentials." });
    expect(problemText(e)).toEqual({ message: "Email o password non corrette.", detail: "" });
    expect(problemMessage(e)).toBe("Email o password non corrette.");
  });

  it("l'export oltre il limite di eventi dice di restringere le date", () => {
    const e = errore({
      status: 422,
      type: "/problems/validation-error",
      detail: "The filters select more than 50000 events. Narrow the date range and retry.",
    });
    expect(problemMessage(e)).toMatch(/restringi l'intervallo di date/);
  });

  it("un dettaglio sconosciuto resta, dopo una frase generica in italiano", () => {
    const e = errore({ status: 409, type: "/problems/conflict", detail: "Nome gia' usato." });
    expect(problemText(e)).toEqual({
      message: "Operazione in conflitto con i dati attuali.",
      detail: "Nome gia' usato.",
    });
  });

  it("senza dettaglio né tipo noto la frase è generica, non il titolo inglese", () => {
    expect(problemMessage(errore({ status: 0, title: "I'm a teapot" }))).toBe(
      "Operazione non riuscita.",
    );
  });

  it("una pagina d'errore del proxy senza detail dice lo stato HTTP", () => {
    const e = errore({ status: 502, type: "/problems/generic", title: "Errore HTTP 502", detail: "" });
    expect(problemMessage(e)).toBe("Operazione non riuscita. (HTTP 502)");
  });

  it("l'errore di rete, già in italiano, passa com'è", () => {
    const e = errore({
      status: 0,
      type: "/problems/network-unreachable",
      title: "Server non raggiungibile",
      detail: "Impossibile contattare NotifyHub.",
    });
    expect(problemText(e)).toEqual({ message: "Impossibile contattare NotifyHub.", detail: "" });
  });

  it("i messaggi di validazione di pydantic si leggono in italiano", () => {
    expect(validationMessage("Field required")).toBe("Campo obbligatorio.");
    expect(validationMessage("Input should be less than or equal to 2147483647")).toBe(
      "Il valore deve essere al massimo 2147483647.",
    );
    expect(validationMessage("String should have at most 10 characters")).toBe(
      "Il testo può avere al massimo 10 caratteri.",
    );
    // Quello che non si riconosce non si inventa: resta com'è.
    expect(validationMessage("qualcosa di nuovo")).toBe("qualcosa di nuovo");
  });
});
