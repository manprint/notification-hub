import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";

export const PAGE_SIZE = 20;

export interface CursorPagination {
  /** Numero di pagina a video, da 1. */
  page: number;
  hasPrev: boolean;
  hasNext: boolean;
  /** Si sta scaricando la pagina richiesta: i pulsanti restano spenti. */
  loading: boolean;
  onPrev: () => void;
  onNext: () => void;
}

interface CursorSource<TPage> {
  pages: TPage[] | undefined;
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  fetchNextPage: () => unknown;
}

/** Il parametro d'URL di una tabella paginata: chi cambia un filtro lo toglie. */
export function isPageParam(key: string): boolean {
  return key === "page" || key.startsWith("page_");
}

/**
 * Pagine numerate sopra una query a cursore.
 *
 * L'API non conosce l'OFFSET: la pagina N si raggiunge scaricando in ordine le
 * pagine precedenti, che restano nella cache dell'infinite query. La pagina
 * sta nell'URL (`paramKey`), cosi' il ritorno dal dettaglio riapre la stessa
 * pagina; se la cache e' scaduta, le pagine mancanti si riscaricano in fila.
 * Chi cambia i filtri deve togliere il parametro (isPageParam): un reset fatto
 * qui, da piu' tabelle nella stessa pagina, si sovrascriverebbe a vicenda.
 */
export function useCursorPages<TPage>(source: CursorSource<TPage>, paramKey = "page") {
  const [searchParams, setSearchParams] = useSearchParams();
  const raw = Number(searchParams.get(paramKey));
  const wanted = Number.isInteger(raw) && raw > 1 ? raw - 1 : 0;
  const pages = source.pages ?? [];
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = source;

  const missing = pages.length > 0 && wanted >= pages.length;
  useEffect(() => {
    if (missing && hasNextPage && !isFetchingNextPage) void fetchNextPage();
  }, [missing, hasNextPage, isFetchingNextPage, fetchNextPage]);

  const index = pages.length === 0 ? 0 : Math.min(wanted, pages.length - 1);

  function goTo(target: number) {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (target > 0) next.set(paramKey, String(target + 1));
        else next.delete(paramKey);
        return next;
      },
      { replace: true },
    );
  }

  const loading = missing && hasNextPage;
  const pagination: CursorPagination = {
    page: index + 1,
    hasPrev: index > 0,
    hasNext: index < pages.length - 1 || hasNextPage,
    loading,
    onPrev: () => goTo(index - 1),
    onNext: () => goTo(index + 1),
  };
  return { current: pages[index] as TPage | undefined, pagination };
}
