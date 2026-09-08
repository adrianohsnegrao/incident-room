import type { Investigation, Overview } from "./types";

const API_URL = "http://127.0.0.1:8030/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "Falha inesperada." }));
    throw new Error(body.detail ?? "Não foi possível concluir a operação.");
  }
  return response.json() as Promise<T>;
}

export const api = {
  overview: () => request<Overview>("/overview"),
  investigate: (incidentId: string) => request<Investigation>(`/incidents/${incidentId}/investigate`, { method: "POST" }),
  decide: (investigationId: string, decision: "approve" | "reject") => request<Investigation>(`/investigations/${investigationId}/decision`, {
    method: "POST",
    body: JSON.stringify({
      decision,
      reviewer: "Operador de plantão",
      justification: decision === "approve" ? "Evidências revisadas e mitigação autorizada." : "Mitigação rejeitada para revisão adicional.",
    }),
  }),
};
