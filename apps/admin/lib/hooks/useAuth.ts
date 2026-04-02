import useSWR from "swr";
import { apiGet } from "@/lib/api";
import type { User } from "@/lib/types";

export function useAuth() {
  const { data, error, mutate } = useSWR<User>("/auth/me", apiGet, {
    revalidateOnFocus: false,
    shouldRetryOnError: false,
  });

  return {
    user: data,
    isLoading: !data && !error,
    isError: error,
    mutate,
  };
}
