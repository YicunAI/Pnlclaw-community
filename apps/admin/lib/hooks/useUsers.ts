import useSWR, { type KeyedMutator } from "swr";
import { apiGet } from "@/lib/api";
import type {
  User,
  ActivityLogEntry,
  LoginHistoryEntry,
  Session,
  AdminNote,
  UserQueryParams,
  Pagination,
} from "@/lib/types";

/** Unwrapped list body from `GET /admin/users`. */
export interface UsersResponse {
  users: User[];
  total: number;
}

function buildQuery(params: UserQueryParams): string {
  const searchParams = new URLSearchParams();
  const limit = params.limit ?? 50;
  const page = params.page ?? 1;
  const offset = (page - 1) * limit;
  searchParams.set("offset", String(offset));
  searchParams.set("limit", String(limit));
  if (params.search) searchParams.set("search", params.search);
  if (params.status) searchParams.set("status", params.status);
  if (params.tag) searchParams.set("tag", params.tag);
  if (params.sort_by) searchParams.set("sort_by", params.sort_by);
  if (params.sort_order) searchParams.set("sort_order", params.sort_order);
  const qs = searchParams.toString();
  return qs ? `?${qs}` : "";
}

export interface UsersPageResult {
  users: User[] | undefined;
  /** Pagination derived from list payload + request params (meta.pagination is not in unwrapped body). */
  pagination: (Pagination & { page: number; pages: number }) | undefined;
  isLoading: boolean;
  isError: unknown;
  mutate: KeyedMutator<UsersResponse>;
}

export function useUsers(params: UserQueryParams = {}): UsersPageResult {
  const limit = params.limit ?? 50;
  const page = params.page ?? 1;
  const offset = (page - 1) * limit;

  const query = buildQuery(params);
  const { data, error, mutate } = useSWR<UsersResponse>(
    `/admin/users${query}`,
    apiGet
  );

  const total = data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / limit));

  return {
    users: data?.users,
    pagination: data
      ? { offset, limit, total, page, pages }
      : undefined,
    isLoading: !data && !error,
    isError: error,
    mutate,
  };
}

export function useUser(userId: string | undefined) {
  const { data, error, mutate } = useSWR<User>(
    userId ? `/admin/users/${userId}` : null,
    apiGet
  );

  return {
    user: data,
    isLoading: !data && !error,
    isError: error,
    mutate,
  };
}

export function useUserActivity(userId: string | undefined) {
  const { data, error, mutate } = useSWR<
    { activities: ActivityLogEntry[]; total: number } | undefined
  >(userId ? `/admin/users/${userId}/activity` : null, apiGet);

  return {
    activity: data?.activities ?? [],
    isLoading: !data && !error,
    isError: error,
    mutate,
  };
}

export function useUserLoginHistory(userId: string | undefined) {
  const { data, error, mutate } = useSWR<
    { entries: LoginHistoryEntry[]; total: number } | undefined
  >(userId ? `/admin/users/${userId}/login-history` : null, apiGet);

  return {
    loginHistory: data?.entries ?? [],
    isLoading: !data && !error,
    isError: error,
    mutate,
  };
}

export function useUserSessions(userId: string | undefined) {
  const { data, error, mutate } = useSWR<
    { sessions: Session[]; total: number } | undefined
  >(userId ? `/admin/users/${userId}/sessions` : null, apiGet);

  return {
    sessions: data?.sessions ?? [],
    isLoading: !data && !error,
    isError: error,
    mutate,
  };
}

export function useUserNotes(userId: string | undefined) {
  const { data, error, mutate } = useSWR<
    { notes: AdminNote[]; total: number } | undefined
  >(userId ? `/admin/users/${userId}/notes` : null, apiGet);

  return {
    notes: data?.notes ?? [],
    isLoading: !data && !error,
    isError: error,
    mutate,
  };
}
