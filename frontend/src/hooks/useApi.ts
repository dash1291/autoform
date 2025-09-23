import { useState, useEffect } from "react";
import { apiClient } from "@/lib/api";

interface UseApiState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

export function useApi<T>(
  apiCall: () => Promise<T>,
  dependencies: any[] = [],
): UseApiState<T> & { refetch: () => Promise<void> } {
  const [state, setState] = useState<UseApiState<T>>({
    data: null,
    loading: true,
    error: null,
  });

  const fetchData = async () => {
    try {
      setState((prev) => ({ ...prev, loading: true, error: null }));
      const data = await apiCall();
      setState({ data, loading: false, error: null });
    } catch (error) {
      setState({
        data: null,
        loading: false,
        error: error instanceof Error ? error.message : "An error occurred",
      });
    }
  };

  useEffect(() => {
    fetchData();
  }, dependencies);

  return {
    ...state,
    refetch: fetchData,
  };
}

// Specific hooks for common operations
export function useProjects() {
  return useApi(() => apiClient.getProjects());
}

export function useProject(id: string) {
  return useApi(() => apiClient.getProject(id), [id]);
}

export function useDeployments(projectId: string) {
  return useApi(() => apiClient.getDeployments(projectId), [projectId]);
}

export function useEnvironmentVariables(projectId: string) {
  return useApi(
    () => apiClient.getEnvironmentVariables(projectId),
    [projectId],
  );
}

// Mutation hook for API calls that modify data
export function useApiMutation<T, U>(
  mutationFn: (data: U) => Promise<T>,
): {
  mutate: (data: U) => Promise<T>;
  loading: boolean;
  error: string | null;
} {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mutate = async (data: U): Promise<T> => {
    try {
      setLoading(true);
      setError(null);
      const result = await mutationFn(data);
      setLoading(false);
      return result;
    } catch (err) {
      const errorMessage =
        err instanceof Error ? err.message : "An error occurred";
      setError(errorMessage);
      setLoading(false);
      throw err;
    }
  };

  return { mutate, loading, error };
}
