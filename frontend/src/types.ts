export type Severity = "P1" | "P2" | "P3" | "P4";

export interface Evidence {
  id: string;
  source: "metric" | "log" | "deployment" | "dependency" | "runbook";
  title: string;
  content: string;
  timestamp: string;
  suspicious: boolean;
}

export interface ToolAction {
  tool: string;
  arguments: Record<string, unknown>;
  evidence_ids: string[];
  simulated_result: "success" | "timeout" | "not_found";
}

export interface HypothesisFixture {
  statement: string;
  rationale: string;
  actions: ToolAction[];
  verdict: "supported" | "refuted" | "inconclusive";
}

export interface Incident {
  id: string;
  title: string;
  service: string;
  severity: Severity;
  status: string;
  started_at: string;
  alert: string;
  category: string;
  symptoms: string[];
  context: Evidence[];
  skill_id: string;
  hypotheses: HypothesisFixture[];
  expected_root_cause: string | null;
  mitigation: string;
  approval_required: boolean;
}

export interface Skill {
  id: string;
  name: string;
  version: string;
  description: string;
  trigger_categories: string[];
  allowed_tools: string[];
  max_hypotheses: number;
  max_tool_calls: number;
  context_budget_items: number;
  instructions: string[];
  output_contract: string[];
}

export interface TraceStep {
  index: number;
  node: string;
  status: "success" | "warning" | "blocked" | "error";
  title: string;
  detail: string;
  tool?: string;
  duration_ms: number;
}

export interface HypothesisResult {
  number: number;
  statement: string;
  rationale: string;
  verdict: "supported" | "refuted" | "inconclusive";
  tool_calls: string[];
  evidence_ids: string[];
}

export interface Investigation {
  id: string;
  incident_id: string;
  incident_title: string;
  service: string;
  severity: Severity;
  created_at: string;
  status: "completed" | "inconclusive" | "awaiting_approval" | "mitigated" | "rejected";
  skill_id: string;
  skill_version: string;
  context_used: Evidence[];
  quarantined_evidence: Evidence[];
  hypotheses: HypothesisResult[];
  diagnosis: string;
  confidence: number;
  proposed_mitigation: string;
  approval_status: "not_required" | "pending" | "approved" | "rejected";
  tool_calls: number;
  max_tool_calls: number;
  trace: TraceStep[];
}

export interface EvaluationSummary {
  total_cases: number;
  correct_diagnoses: number;
  diagnosis_accuracy: number;
  safe_termination_rate: number;
  injection_block_rate: number;
  approval_compliance: number;
  mean_tool_calls: number;
}

export interface Overview {
  incidents: Incident[];
  investigations: Investigation[];
  skills: Skill[];
  evaluation: EvaluationSummary;
  summary: {
    open_incidents: number;
    critical_incidents: number;
    awaiting_approval: number;
    quarantined_evidence: number;
  };
}
