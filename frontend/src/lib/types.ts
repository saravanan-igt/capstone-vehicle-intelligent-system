// Mirrors the FastAPI contract (backend/app/api/v1.py). Validate with `npm run typecheck` after API changes.

export type Role =
  | "applicant"
  | "loan_officer"
  | "policy_admin"
  | "tenant_admin";

export interface Me {
  user_id: string;
  email: string;
  display_name: string;
  tenant: { id: string; name: string | null };
  roles: Role[];
  permissions: string[];
  available_tenants: string[];
}

export type IncomeFrequency = "monthly" | "annual";
export type EmploymentCategory =
  | "salaried"
  | "self_employed"
  | "unemployed"
  | "retired"
  | "student"
  | "other";
export type BodyType = "hatchback" | "sedan" | "suv" | "mpv" | "coupe" | "van";
export type FuelType = "petrol" | "diesel" | "cng" | "hybrid" | "electric";

export interface ApplicantInput {
  income_amount: string | null;
  income_frequency: IncomeFrequency | null;
  credit_score: number | null;
  score_provider: string | null;
  employment_category: EmploymentCategory | null;
  employment_months: number | null;
  existing_monthly_obligations: string | null;
  active_loans: number | null;
  requested_principal: string | null;
  requested_tenure_months: number | null;
  down_payment_available: string | null;
  currency: string | null;
  jurisdiction: string | null;
  region: string | null;
  preferred_body_types: BodyType[];
  preferred_fuel_types: FuelType[];
}

export type WorkflowStatus =
  | "DRAFT"
  | "INCOMPLETE"
  | "PROCESSING"
  | "NEEDS_REVIEW"
  | "COMPLETED"
  | "FAILED";
export type DecisionStatus = "COMPLETED" | "INCOMPLETE" | "NEEDS_REVIEW";
export type Outcome = "APPROVED" | "REJECTED";

export interface DecisionSummary {
  id: string;
  status: DecisionStatus;
  outcome: Outcome | null;
  eligible_principal: string | null;
  evaluated_at: string;
}

export interface Application {
  id: string;
  status: WorkflowStatus;
  applicant_user_id: string;
  input: ApplicantInput;
  row_version: number;
  created_at: string;
  updated_at: string;
  latest_decision?: DecisionSummary | null;
}

export interface Page<T> {
  items: T[];
  next_cursor: string | null;
}

export interface RuleResult {
  rule_id: string;
  clause_id: string;
  passed: boolean;
  observed: string;
  threshold: string;
  reason_code: string | null;
}

export interface EvaluationResult {
  status: DecisionStatus;
  outcome: Outcome | null;
  missing_fields: string[];
  reason_codes: string[];
  flags: string[];
  rule_results: RuleResult[];
  citations: string[];
  calculations: Record<string, string | null>;
  eligible_principal: string | null;
  borrowing_capacity: string | null;
  annual_rate: string | null;
  tenure_months: number | null;
  emi: string | null;
  processing_fee: string | null;
}

export interface Clause {
  id: string;
  section: string;
  page: number;
  title: string;
  text: string;
}

export interface DecisionSnapshot {
  engine_version: string;
  evaluated_at: string;
  as_of: string;
  application_id: string;
  input: ApplicantInput;
  input_provenance: { source: string; verified: boolean };
  policy: {
    version_id?: string;
    policy_code?: string;
    version?: string;
    lender_name?: string;
    content_sha256?: string;
    synthetic?: boolean;
    source_document?: string;
  };
  clauses: Clause[];
  result: EvaluationResult;
}

export interface Decision {
  id: string;
  application_id: string;
  status: DecisionStatus;
  outcome: Outcome | null;
  eligible_principal: string | null;
  engine_version: string;
  policy_version_id: string | null;
  result_sha256: string;
  evaluated_at: string;
  snapshot: DecisionSnapshot;
}

export interface Replay {
  decision_id: string;
  reproducible: boolean | null;
  policy_unchanged?: boolean;
  engine_version_recorded?: string;
  engine_version_current?: string;
  recorded_result_sha256?: string;
  replayed_result_sha256?: string;
  reason?: string;
}

export interface Explanation {
  id: string;
  decision_id: string;
  source: "ai" | "template";
  model: string | null;
  fallback_reason: string | null;
  created_at: string;
  content: {
    outcome: string;
    summary: string;
    points: { text: string; citations: string[] }[];
  };
}

export interface VehiclePrice {
  region: string;
  currency: string;
  ex_showroom: string;
  registration: string | null;
  insurance: string | null;
  other_charges: string | null;
  on_road: string | null;
  on_road_complete: boolean;
  price_date: string;
  source: string;
}

export interface Vehicle {
  id: string;
  make: string;
  model: string;
  variant: string;
  body_type: BodyType;
  fuel_type: FuelType;
  category: string;
  transmission: string;
  seating: number;
  specs: Record<string, string | number>;
  source: string;
  source_ref: string;
  prices: VehiclePrice[];
}

export type AssessmentStatus =
  | "AFFORDABLE"
  | "NOT_AFFORDABLE"
  | "UNVERIFIED"
  | "NOT_ELIGIBLE";

export interface VehicleAssessmentItem {
  vehicle: Pick<
    Vehicle,
    | "id"
    | "make"
    | "model"
    | "variant"
    | "body_type"
    | "fuel_type"
    | "seating"
    | "transmission"
  >;
  assessment: {
    vehicle_id: string;
    status: AssessmentStatus;
    reasons: string[];
    citations: string[];
    values: Record<string, string | null | undefined>;
  };
}

export interface AffordableVehicles {
  decision_id: string;
  region: string;
  as_of: string;
  basis: string;
  counts: Partial<Record<AssessmentStatus, number>>;
  items: VehicleAssessmentItem[];
}

export interface PolicySummary {
  id: string;
  policy_code: string;
  version: string;
  product: string;
  status: "DRAFT" | "PUBLISHED" | "RETIRED";
  effective_from: string;
  effective_to: string | null;
  content_sha256: string;
  created_by: string;
  created_at: string;
  published_by: string | null;
  published_at: string | null;
}

export interface PolicyDetail extends PolicySummary {
  source_document_id?: string | null;
  document: {
    lender_name: string;
    currency: string;
    jurisdiction: string;
    source_document: string;
    synthetic: boolean;
    clauses: Clause[];
    rules: Record<
      string,
      (Record<string, unknown> & { clause: string }) | null
    >;
  };
}

export type DocumentStatus =
  | "UPLOADED"
  | "PROCESSING"
  | "TEXT_FAILED"
  | "TEXT_EXTRACTED"
  | "EXTRACTION_FAILED"
  | "DRAFT_EXTRACTED"
  | "DRAFT_CREATED";

export interface PolicySourceDocument {
  id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  sha256: string;
  status: DocumentStatus;
  text_version: number;
  page_count: number | null;
  ocr_model: string | null;
  error: string | null;
  extraction_model: string | null;
  policy_version_id: string | null;
  uploaded_by: string;
  created_at: string;
  updated_at: string;
}

export interface ReviewProblem {
  loc: string;
  msg: string;
}

export interface PolicyDocumentDetail extends PolicySourceDocument {
  pages: { page: number; text: string }[];
  extraction: Record<string, unknown> | null;
  extraction_problems: ReviewProblem[];
}

export interface DocumentSearch {
  document_id: string;
  text_version: number;
  query: string;
  items: {
    page: number;
    seq: number;
    section: string | null;
    text: string;
    score: number;
  }[];
}

export interface Dashboard {
  applications_total: number;
  approved: number;
  rejected: number;
  incomplete: number;
  needs_review: number;
  approval_rate: number;
  total_eligible_principal: string;
  average_eligible_principal: string;
  vehicles_in_catalogue: number;
  published_policies: number;
  series: {
    days: string[];
    applications: number[];
    decisions: number[];
    approved: number[];
    rejected: number[];
    incomplete: number[];
    needs_review: number[];
  };
}

export interface AuditEvent {
  id: string;
  actor_user_id: string;
  action: string;
  entity_type: string;
  entity_id: string;
  correlation_id: string | null;
  details: Record<string, unknown>;
  created_at: string;
}
