import useSWR from "swr";
import { apiGet } from "@/lib/api";
import type { Invitation } from "@/lib/types";

export function useInvitations() {
  const { data, error, mutate } = useSWR<{
    invitations: Invitation[];
    total: number;
  }>("/admin/invitations", apiGet);

  return {
    invitations: data?.invitations ?? [],
    isLoading: !data && !error,
    isError: error,
    mutate,
  };
}
