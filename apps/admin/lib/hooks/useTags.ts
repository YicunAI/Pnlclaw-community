import useSWR from "swr";
import { apiGet } from "@/lib/api";
import type { UserTag } from "@/lib/types";

export function useTags() {
  const { data, error, mutate } = useSWR<{ tags: UserTag[]; total: number }>(
    "/admin/tags",
    apiGet
  );

  return {
    tags: data?.tags ?? [],
    isLoading: !data && !error,
    isError: error,
    mutate,
  };
}
