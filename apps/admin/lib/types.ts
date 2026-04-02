// ---------- Core entities ----------

export interface User {
  id: string;
  email: string;
  display_name: string;
  /** Alias some endpoints return alongside `display_name` */
  name?: string;
  avatar_url: string | null;
  role: "admin" | "user" | "moderator" | "operator";
  status: "active" | "suspended" | "banned";
  totp_enabled?: boolean;
  created_at: string;
  updated_at: string;
  last_login?: string | null;
  country?: string | null;
  city?: string | null;
  oauth_accounts?: OAuthAccount[];
  tags?: UserTag[];
}

export interface OAuthAccount {
  id: string;
  provider: "google" | "github" | "twitter";
  provider_user_id: string;
  email: string | null;
  name: string | null;
  avatar_url: string | null;
  linked_at: string;
}

export interface Session {
  id: string;
  user_id: string;
  ip_address: string;
  user_agent: string;
  device: string | null;
  os: string | null;
  browser: string | null;
  country: string | null;
  city: string | null;
  created_at: string;
  last_active: string;
  is_current: boolean;
}

export interface LoginHistoryEntry {
  id: string;
  user_id: string;
  provider: string;
  ip_address: string;
  country: string | null;
  city: string | null;
  device: string | null;
  os: string | null;
  browser: string | null;
  success: boolean;
  failure_reason: string | null;
  created_at: string;
}

export interface ActivityLogEntry {
  id: string;
  user_id: string;
  action: string;
  details: string | null;
  ip_address: string | null;
  created_at: string;
}

export interface AdminNote {
  id: string;
  user_id: string;
  admin_id: string;
  admin_name: string;
  content: string;
  created_at: string;
}

export interface UserTag {
  id: string;
  name: string;
  color: string;
  description: string | null;
  user_count?: number;
  created_at: string;
}

export interface Invitation {
  id: string;
  code: string;
  role: string;
  max_uses: number;
  used_count: number;
  note: string | null;
  created_by: string;
  created_at: string;
  expires_at: string;
}

// ---------- Analytics ----------

export interface AnalyticsOverview {
  total_users: number;
  active_24h: number;
  active_7d: number;
  active_30d: number;
  new_signups_today: number;
  total_sessions: number;
  banned_users: number;
}

export interface ActiveUsersData {
  date: string;
  count: number;
}

export interface SignupData {
  date: string;
  count: number;
}

export interface ProviderData {
  provider: string;
  count: number;
  percentage: number;
}

export interface GeoData {
  country: string;
  country_code: string;
  count: number;
  percentage: number;
}

export interface DeviceData {
  devices: { name: string; count: number; percentage: number }[];
  os: { name: string; count: number; percentage: number }[];
  browsers: { name: string; count: number; percentage: number }[];
}

export interface RetentionData {
  cohort: string;
  size: number;
  retention: number[];
}

export interface LoginStatsData {
  date: string;
  success: number;
  failure: number;
}

// ---------- API wrappers ----------

export interface APIResponse<T> {
  data: T;
  message?: string;
}

export interface Pagination {
  offset: number;
  limit: number;
  total: number;
}

export interface PaginatedResponse<T> {
  users: T[];
  total: number;
}

export interface ErrorInfo {
  message: string;
  code?: string;
  details?: Record<string, unknown>;
}

// ---------- Request types ----------

export interface BulkActionRequest {
  user_ids: string[];
  action: "ban" | "suspend" | "activate" | "delete";
  reason?: string;
}

export interface CreateTagRequest {
  name: string;
  color: string;
  description?: string;
}

export interface CreateInvitationRequest {
  role: string;
  max_uses: number;
  expires_in_hours: number;
  note?: string;
}

// ---------- Query params ----------

export interface UserQueryParams {
  page?: number;
  limit?: number;
  search?: string;
  status?: string;
  tag?: string;
  sort_by?: string;
  sort_order?: "asc" | "desc";
}
