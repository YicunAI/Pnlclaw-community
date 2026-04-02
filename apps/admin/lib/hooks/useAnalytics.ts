import useSWR from "swr";
import { apiGet } from "@/lib/api";
import type {
  AnalyticsOverview,
  ActiveUsersData,
  SignupData,
  ProviderData,
  GeoData,
  DeviceData,
  RetentionData,
  LoginStatsData,
} from "@/lib/types";

function mapActiveUsersRows(
  rows: { date?: string; active_count?: number }[]
): ActiveUsersData[] {
  return rows.map((r) => ({
    date: String(r.date ?? ""),
    count: Number(r.active_count ?? 0),
  }));
}

function mapSignupRows(
  rows: { date?: string; signup_count?: number }[]
): SignupData[] {
  return rows.map((r) => ({
    date: String(r.date ?? ""),
    count: Number(r.signup_count ?? 0),
  }));
}

function mapProviderRows(
  rows: { provider?: string; user_count?: number }[]
): ProviderData[] {
  const total = rows.reduce((s, r) => s + Number(r.user_count ?? 0), 0);
  return rows.map((r) => {
    const count = Number(r.user_count ?? 0);
    return {
      provider: String(r.provider ?? ""),
      count,
      percentage: total > 0 ? (count / total) * 100 : 0,
    };
  });
}

function mapGeoRows(
  rows: {
    country?: string | null;
    country_code?: string | null;
    user_count?: number;
  }[]
): GeoData[] {
  const total = rows.reduce((s, r) => s + Number(r.user_count ?? 0), 0);
  return rows.map((r) => {
    const count = Number(r.user_count ?? 0);
    return {
      country: String(r.country ?? ""),
      country_code: String(r.country_code ?? r.country ?? ""),
      count,
      percentage: total > 0 ? (count / total) * 100 : 0,
    };
  });
}

function slicesFromCounts(
  rows: Record<string, string | number | null | undefined>[],
  labelKey: string
): { name: string; count: number; percentage: number }[] {
  const total = rows.reduce((s, r) => s + Number(r.count ?? 0), 0);
  return rows.map((r) => {
    const count = Number(r.count ?? 0);
    const raw = r[labelKey];
    return {
      name: String(raw ?? "Unknown"),
      count,
      percentage: total > 0 ? (count / total) * 100 : 0,
    };
  });
}

function mapDevicePayload(raw: {
  browsers?: { browser?: string; count?: number }[];
  operating_systems?: { os?: string; count?: number }[];
  device_types?: { device_type?: string; count?: number }[];
}): DeviceData {
  return {
    browsers: slicesFromCounts(raw.browsers ?? [], "browser"),
    os: slicesFromCounts(raw.operating_systems ?? [], "os"),
    devices: slicesFromCounts(raw.device_types ?? [], "device_type"),
  };
}

function mapRetentionCohorts(
  rows: {
    cohort_week?: string;
    cohort_size?: number;
    retention_pct?: number;
  }[]
): RetentionData[] {
  return rows.map((r) => ({
    cohort: String(r.cohort_week ?? ""),
    size: Number(r.cohort_size ?? 0),
    retention: [Number(r.retention_pct ?? 0)],
  }));
}

function mapLoginDaily(
  rows: {
    date?: string;
    successful?: number;
    failed?: number;
  }[]
): LoginStatsData[] {
  return rows.map((r) => ({
    date: String(r.date ?? ""),
    success: Number(r.successful ?? 0),
    failure: Number(r.failed ?? 0),
  }));
}

export function useAnalyticsOverview() {
  const { data, error } = useSWR<AnalyticsOverview>(
    "/admin/analytics/overview",
    apiGet
  );

  return {
    overview: data,
    isLoading: !data && !error,
    isError: error,
  };
}

export function useActiveUsers(period: string = "30d") {
  const { data, error } = useSWR(
    `/admin/analytics/users/active?period=${period}`,
    (url) => apiGet<{ period: string; data: unknown[] }>(url)
  );

  const rows = Array.isArray(data?.data) ? data!.data : [];
  const activeUsers = mapActiveUsersRows(
    rows as { date?: string; active_count?: number }[]
  );

  return {
    activeUsers,
    isLoading: !data && !error,
    isError: error,
  };
}

export function useSignups(period: string = "30d") {
  const { data, error } = useSWR(
    `/admin/analytics/users/signups?period=${period}`,
    (url) => apiGet<{ period: string; data: unknown[] }>(url)
  );

  const rows = Array.isArray(data?.data) ? data!.data : [];
  const signups = mapSignupRows(
    rows as { date?: string; signup_count?: number }[]
  );

  return {
    signups,
    isLoading: !data && !error,
    isError: error,
  };
}

export function useProviders() {
  const { data, error } = useSWR(
    "/admin/analytics/users/providers",
    (url) => apiGet<{ providers: unknown[] }>(url)
  );

  const providers = mapProviderRows(
    (data?.providers ?? []) as { provider?: string; user_count?: number }[]
  );

  return {
    providers,
    isLoading: !data && !error,
    isError: error,
  };
}

export function useGeoDistribution() {
  const { data, error } = useSWR(
    "/admin/analytics/users/geo",
    (url) => apiGet<{ countries: unknown[] }>(url)
  );

  const geoData = mapGeoRows(
    (data?.countries ?? []) as {
      country?: string | null;
      country_code?: string | null;
      user_count?: number;
    }[]
  );

  return {
    geoData,
    isLoading: !data && !error,
    isError: error,
  };
}

export function useDeviceDistribution() {
  const { data, error } = useSWR(
    "/admin/analytics/devices",
    (url) =>
      apiGet<{
        browsers?: { browser?: string; count?: number }[];
        operating_systems?: { os?: string; count?: number }[];
        device_types?: { device_type?: string; count?: number }[];
      }>(url)
  );

  const deviceData = data ? mapDevicePayload(data) : undefined;

  return {
    deviceData,
    isLoading: !data && !error,
    isError: error,
  };
}

export function useRetention() {
  const { data, error } = useSWR(
    "/admin/analytics/users/retention",
    (url) => apiGet<{ cohorts: unknown[] }>(url)
  );

  const retention = mapRetentionCohorts(
    (data?.cohorts ?? []) as {
      cohort_week?: string;
      cohort_size?: number;
      retention_pct?: number;
    }[]
  );

  return {
    retention,
    isLoading: !data && !error,
    isError: error,
  };
}

export function useLoginStats(period: string = "7d") {
  const { data, error } = useSWR(
    `/admin/analytics/logins?period=${period}`,
    (url) =>
      apiGet<{
        period: string;
        daily: unknown[];
        by_provider: unknown[];
      }>(url)
  );

  const loginStats = mapLoginDaily(
    (data?.daily ?? []) as {
      date?: string;
      successful?: number;
      failed?: number;
    }[]
  );

  return {
    loginStats,
    isLoading: !data && !error,
    isError: error,
  };
}
