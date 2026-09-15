import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { SessionProvider } from "../../hooks/useSession";
import { ToastProvider } from "../../hooks/useToast";

export function renderWithProviders(ui: ReactNode, initialEntries: string[] = ["/"]) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries}>
        <SessionProvider>
          <ToastProvider>{ui}</ToastProvider>
        </SessionProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
