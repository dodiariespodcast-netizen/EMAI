export type UserRole = "owner" | "admin" | "scheduler" | "physician";

export interface User {
  id: string;
  org_id: string;
  email: string;
  role: UserRole;
  physician_id: string | null;
  is_active: boolean;
}

export interface Token {
  access_token: string;
  token_type: string;
  user: User;
}

export interface OAuthIdentity {
  id: string;
  provider: string;
  email: string;
  created_at: string;
}

export type EmploymentType = "employed" | "locums" | "contract" | "moonlighter";

export interface Physician {
  id: string;
  org_id: string;
  first_name: string;
  last_name: string;
  email: string;
  credentials: string;
  is_active: boolean;
  fte: number;
  seniority_years: number;
  night_preference: number;
  weekend_preference: number;
  holiday_preference: number;
  max_consecutive_shifts: number | null;
  min_rest_hours: number | null;
  max_shifts_per_period: number | null;
  employment_type: EmploymentType;
  hourly_rate: number | null;
  calendar_token: string;
  site_ids: string[];
}

export interface Site {
  id: string;
  org_id: string;
  name: string;
  timezone: string;
}

export type ShiftCategory = "day" | "night" | "swing" | "admin";

export interface ShiftType {
  id: string;
  org_id: string;
  site_id: string;
  name: string;
  category: ShiftCategory;
  start_time: string;
  end_time: string;
  duration_hours: number;
  required_physicians: number;
}

export interface ShiftInstance {
  id: string;
  org_id: string;
  site_id: string;
  shift_type_id: string;
  schedule_run_id: string | null;
  date: string;
  start_datetime: string;
  end_datetime: string;
  category: ShiftCategory;
  required_physicians: number;
  is_holiday: boolean;
}

export type TimeOffType = "vacation" | "cme" | "personal" | "sick" | "other";
export type RequestPriority = "must" | "preferred";
export type RequestStatus = "pending" | "approved" | "denied" | "withdrawn";

export interface TimeOffRequest {
  id: string;
  org_id: string;
  physician_id: string;
  start_date: string;
  end_date: string;
  request_type: TimeOffType;
  priority: RequestPriority;
  status: RequestStatus;
  reason: string | null;
  raw_text: string | null;
}

export interface ShiftPreference {
  id: string;
  org_id: string;
  physician_id: string;
  effective_start: string;
  effective_end: string;
  category: ShiftCategory | "weekend" | "holiday";
  level: number;
  note: string | null;
}

export type ScheduleRunStatus = "draft" | "published" | "archived";

export interface Assignment {
  id: string;
  shift_instance_id: string;
  physician_id: string;
  status: string;
}

export interface AssignmentDetail extends Assignment {
  schedule_run_id: string;
  schedule_run_status: ScheduleRunStatus;
  site_id: string;
  site_name: string;
  date: string;
  start_datetime: string;
  end_datetime: string;
  category: ShiftCategory;
  shift_type_name: string;
}

export interface ScheduleRun {
  id: string;
  org_id: string;
  site_id: string;
  period_start: string;
  period_end: string;
  status: ScheduleRunStatus;
  objective_value: number | null;
  solver_status: string | null;
  solve_seconds: number | null;
  unfilled_shift_count: number;
  stats: Record<string, unknown>;
  ai_summary: string | null;
}

export interface ScheduleRunDetail extends ScheduleRun {
  assignments: Assignment[];
}

export interface SchedulingRule {
  org_id: string;
  max_consecutive_shifts: number;
  min_rest_hours: number;
  max_nights_in_a_row: number;
  weight_unfilled_shift: number;
  weight_fairness: number;
  weight_preference: number;
  weight_preferred_time_off: number;
  weight_seniority: number;
}

export interface FairnessRow {
  physician_id: string;
  physician_name: string;
  total_shifts: number;
  target_shifts: number;
  night_shifts: number;
  weekend_shifts: number;
  holiday_shifts: number;
  preferred_requests_granted: number;
  preferred_requests_total: number;
}

export type SwapStatus = "open" | "claimed" | "approved" | "rejected" | "cancelled";

export interface ShiftSwapRequest {
  id: string;
  org_id: string;
  assignment_id: string;
  offering_physician_id: string;
  target_physician_id: string | null;
  claimed_by_physician_id: string | null;
  status: SwapStatus;
  note: string | null;
}

export type CredentialType =
  | "state_license"
  | "dea"
  | "board_certification"
  | "malpractice_insurance"
  | "acls"
  | "bls"
  | "pals"
  | "hospital_privileges"
  | "other";

export interface Credential {
  id: string;
  org_id: string;
  physician_id: string;
  credential_type: CredentialType;
  identifier: string | null;
  issuing_state: string | null;
  issued_date: string | null;
  expires_on: string | null;
  note: string | null;
}

export interface AuditLogEntry {
  id: string;
  user_id: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  details: Record<string, unknown>;
  created_at: string;
}
