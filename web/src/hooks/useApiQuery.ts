import { useCallback, useEffect, useRef, useState, type DependencyList } from "react";

import { ApiError } from "../api/client";

interface QueryState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
}

export interface ApiQueryResult<T> extends QueryState<T> {
  refresh: () => void;
}

function messageOf(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) {
    return error.message;
  }
  return "请求失败，请稍后重试";
}

export function useApiQuery<T>(
  loader: (signal: AbortSignal) => Promise<T>,
  dependencies: DependencyList,
): ApiQueryResult<T> {
  const loaderRef = useRef(loader);
  loaderRef.current = loader;
  const [revision, setRevision] = useState(0);
  const [state, setState] = useState<QueryState<T>>({
    data: null,
    error: null,
    loading: true,
  });

  useEffect(() => {
    const controller = new AbortController();
    setState((current) => ({ ...current, loading: true, error: null }));

    loaderRef.current(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) {
          setState({ data, error: null, loading: false });
        }
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setState((current) => ({
            data: current.data,
            error: messageOf(error),
            loading: false,
          }));
        }
      });

    return () => controller.abort();
    // The caller owns the semantic dependency list; the loader is kept stable by ref.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...dependencies, revision]);

  const refresh = useCallback(() => {
    setRevision((value) => value + 1);
  }, []);

  return { ...state, refresh };
}
