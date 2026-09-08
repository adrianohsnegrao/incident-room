import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import type { Incident, Investigation, Overview, Skill } from "./types";

type Page = "overview" | "incidents" | "skills" | "evaluation" | "help";

const nav: Array<{ id: Page; label: string; icon: string }> = [
  { id: "overview", label: "Visão geral", icon: "▦" },
  { id: "incidents", label: "Incidentes", icon: "!" },
  { id: "skills", label: "Runbooks", icon: "◇" },
  { id: "evaluation", label: "Avaliações", icon: "✓" },
  { id: "help", label: "Como funciona", icon: "?" },
];

const pageCopy: Record<Page, { eyebrow: string; title: string; description: string }> = {
  overview: { eyebrow: "CENTRAL OPERACIONAL", title: "Investigue antes de agir.", description: "Evidências, hipóteses e decisões humanas em uma única linha do tempo." },
  incidents: { eyebrow: "FILA DE INCIDENTES", title: "O que precisa de atenção agora.", description: "Abra um incidente para revisar contexto, diagnóstico e mitigação proposta." },
  skills: { eyebrow: "PROCEDIMENTOS VERSIONADOS", title: "Cada investigação segue um runbook.", description: "Skills definem gatilhos, ferramentas, limites, instruções e contrato de saída." },
  evaluation: { eyebrow: "QUALIDADE DO SISTEMA", title: "Comportamento mensurável, não confiança cega.", description: "A suíte verifica diagnóstico, segurança, aprovação e encerramento." },
  help: { eyebrow: "ENTENDA O FLUXO", title: "Um investigador assistido, não um operador autônomo.", description: "O sistema reúne evidências e propõe ações; a autoridade continua com a pessoa." },
};

const severityLabel: Record<string, string> = { P1: "Crítico", P2: "Alto", P3: "Moderado", P4: "Baixo" };
const statusLabel: Record<string, string> = {
  awaiting_approval: "Aguardando aprovação",
  inconclusive: "Inconclusivo",
  completed: "Concluído",
  mitigated: "Mitigação aprovada",
  rejected: "Mitigação rejeitada",
};
const verdictLabel: Record<string, string> = { supported: "Sustentada", refuted: "Refutada", inconclusive: "Inconclusiva" };

function formatTime(value: string) {
  return new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

function Severity({ value }: { value: string }) {
  return <span className={`severity severity-${value.toLowerCase()}`}>{value} · {severityLabel[value]}</span>;
}

function Metric({ label, value, note }: { label: string; value: string | number; note: string }) {
  return <article className="metric"><span>{label}</span><strong>{value}</strong><small>{note}</small></article>;
}

function IncidentRow({ incident, investigation, onOpen }: { incident: Incident; investigation: Investigation; onOpen: () => void }) {
  return (
    <button className="incident-row" onClick={onOpen}>
      <div className="incident-main"><Severity value={incident.severity} /><strong>{incident.title}</strong><span>{incident.service} · {formatTime(incident.started_at)}</span></div>
      <div className="incident-diagnosis"><span>DIAGNÓSTICO</span><p>{investigation.diagnosis}</p></div>
      <div className="incident-status"><b>{investigation.confidence}%</b><span>{statusLabel[investigation.status]}</span></div>
      <span className="arrow">›</span>
    </button>
  );
}

function OverviewPage({ data, onOpen }: { data: Overview; onOpen: (incident: Incident) => void }) {
  const pairs = data.incidents.map((incident) => ({ incident, investigation: data.investigations.find((item) => item.incident_id === incident.id)! }));
  return (
    <>
      <section className="notice"><div className="pulse">!</div><div><strong>{data.summary.awaiting_approval} mitigações aguardam revisão humana</strong><p>Nenhuma alteração operacional foi executada automaticamente.</p></div><span>Modo seguro</span></section>
      <section className="metrics-grid">
        <Metric label="INCIDENTES" value={data.summary.open_incidents} note="dataset operacional sintético" />
        <Metric label="DIAGNÓSTICO" value={`${data.evaluation.diagnosis_accuracy}%`} note={`${data.evaluation.correct_diagnoses}/${data.evaluation.total_cases} golden cases`} />
        <Metric label="ENCERRAMENTO SEGURO" value={`${data.evaluation.safe_termination_rate}%`} note="todos dentro do orçamento" />
        <Metric label="EVIDÊNCIAS ISOLADAS" value={data.summary.quarantined_evidence} note="prompt injection bloqueado" />
      </section>
      <section className="panel">
        <div className="section-heading"><div><span>PRIORIDADE OPERACIONAL</span><h2>Incidentes em investigação</h2></div><small>Clique para abrir o dossiê</small></div>
        <div className="incident-list">{pairs.slice(0, 5).map(({ incident, investigation }) => <IncidentRow key={incident.id} incident={incident} investigation={investigation} onOpen={() => onOpen(incident)} />)}</div>
      </section>
      <section className="two-columns">
        <article className="panel compact"><div className="section-heading"><div><span>RALPH LOOP LIMITADO</span><h2>Hipótese → evidência → crítica</h2></div></div><p className="body-copy">Uma hipótese refutada retorna ao grafo para uma nova tentativa. O ciclo termina ao encontrar suporte, atingir limites ou reconhecer que faltam evidências.</p><div className="loop"><b>Formular</b><i>→</i><b>Investigar</b><i>→</i><b>Criticar</b><i>↺</i></div></article>
        <article className="panel compact"><div className="section-heading"><div><span>AUTORIDADE</span><h2>A IA propõe. A pessoa decide.</h2></div></div><p className="body-copy">Restart, rollback, scaling e mudanças de configuração permanecem pendentes. Aprovar aqui registra a decisão demonstrativa, sem executar comandos reais.</p></article>
      </section>
    </>
  );
}

function IncidentsPage({ data, onOpen }: { data: Overview; onOpen: (incident: Incident) => void }) {
  return <section className="panel"><div className="section-heading"><div><span>{data.incidents.length} CASOS</span><h2>Fila completa</h2></div><div className="legend"><span><i className="dot p1" />P1</span><span><i className="dot p2" />P2</span><span><i className="dot p3" />P3</span></div></div><div className="incident-list">{data.incidents.map((incident) => <IncidentRow key={incident.id} incident={incident} investigation={data.investigations.find((item) => item.incident_id === incident.id)!} onOpen={() => onOpen(incident)} />)}</div></section>;
}

function SkillsPage({ skills }: { skills: Skill[] }) {
  return <div className="skill-grid">{skills.map((skill) => <article className="skill-card" key={skill.id}><header><div><span>SKILL · {skill.version}</span><h2>{skill.name}</h2></div><b>{skill.id}</b></header><p>{skill.description}</p><div className="limits"><span><b>{skill.max_hypotheses}</b> hipóteses</span><span><b>{skill.max_tool_calls}</b> tool calls</span><span><b>{skill.context_budget_items}</b> itens de contexto</span></div><h3>Ferramentas permitidas</h3><div className="tags">{skill.allowed_tools.map((tool) => <span key={tool}>{tool}</span>)}</div><h3>Procedimento</h3><ol>{skill.instructions.map((item) => <li key={item}>{item}</li>)}</ol></article>)}</div>;
}

function EvaluationPage({ data }: { data: Overview }) {
  const metrics = [
    ["Diagnósticos corretos", `${data.evaluation.diagnosis_accuracy}%`, `${data.evaluation.correct_diagnoses}/${data.evaluation.total_cases}`],
    ["Encerramento seguro", `${data.evaluation.safe_termination_rate}%`, "Dentro dos limites"],
    ["Injection bloqueado", `${data.evaluation.injection_block_rate}%`, "Conteúdo isolado"],
    ["Conformidade de aprovação", `${data.evaluation.approval_compliance}%`, "Nenhuma mutação automática"],
  ];
  return <><section className="evaluation-hero"><div><span>GOLDEN DATASET v1.0</span><h2>Gate aprovado para demonstração</h2><p>Os resultados medem fixtures determinísticas. Não representam desempenho geral de um modelo real.</p></div><strong>APROVADO</strong></section><section className="evaluation-grid">{metrics.map(([label, value, note]) => <article key={label}><span>{label}</span><strong>{value}</strong><small>{note}</small><div><i style={{ width: value }} /></div></article>)}</section><section className="panel compact"><div className="section-heading"><div><span>EFICIÊNCIA</span><h2>Média de {data.evaluation.mean_tool_calls} chamadas por investigação</h2></div></div><p className="body-copy">A métrica verifica se o agente obtém evidências suficientes sem prolongar o loop. Cada skill também possui orçamento próprio e condições explícitas de parada.</p></section></>;
}

function HelpPage({ onTutorial }: { onTutorial: () => void }) {
  const steps = [
    ["01", "Classificar", "Identifica categoria, serviço e severidade do alerta."],
    ["02", "Selecionar skill", "Carrega o runbook, ferramentas e limites adequados."],
    ["03", "Montar contexto", "Seleciona evidências e isola conteúdo não confiável."],
    ["04", "Formular hipótese", "Cria uma explicação que possa ser testada."],
    ["05", "Investigar", "Consulta métricas, logs, deploys e dependências permitidas."],
    ["06", "Criticar", "Sustenta, refuta ou revisa a hipótese dentro do orçamento."],
    ["07", "Diagnosticar", "Apresenta causa, confiança e evidências — ou admite incerteza."],
    ["08", "Decidir", "Uma pessoa aprova ou rejeita qualquer mitigação mutável."],
  ];
  return <><section className="explanation"><div><span>INVESTIGAÇÃO AGENTIC</span><h2>O contexto muda; a autoridade não.</h2></div><p>Logs e alertas são tratados como dados, nunca como instruções. O grafo pode revisar hipóteses, mas não recebe permissão para executar mudanças em infraestrutura.</p></section><section className="flow-grid">{steps.map(([number, title, description]) => <article key={number}><span>{number}</span><h3>{title}</h3><p>{description}</p></article>)}</section><button className="secondary" onClick={onTutorial}>Refazer tutorial</button></>;
}

function IncidentDrawer({ incident, investigation, skill, busy, onClose, onRun, onDecision }: { incident: Incident; investigation: Investigation; skill: Skill; busy: boolean; onClose: () => void; onRun: () => void; onDecision: (decision: "approve" | "reject") => void }) {
  return <div className="drawer-backdrop" onMouseDown={onClose}><aside className="drawer" onMouseDown={(event) => event.stopPropagation()} aria-label={`Dossiê de ${incident.title}`}><button className="close" onClick={onClose} aria-label="Fechar">×</button><header className="drawer-head"><Severity value={incident.severity} /><span>{incident.id} · {incident.service}</span><h2>{incident.title}</h2><p>{incident.alert}</p></header><div className="drawer-actions"><button className="secondary" onClick={onRun} disabled={busy}>{busy ? "Investigando..." : "Executar novamente"}</button><span className={`status status-${investigation.status}`}>{statusLabel[investigation.status]}</span></div><section className="diagnosis"><span>DIAGNÓSTICO</span><h3>{investigation.diagnosis}</h3><div><b>{investigation.confidence}% de confiança</b><small>{investigation.tool_calls}/{investigation.max_tool_calls} tool calls</small></div></section>{investigation.quarantined_evidence.length > 0 && <section className="quarantine"><b>Conteúdo não confiável isolado</b><p>{investigation.quarantined_evidence[0].title}: {investigation.quarantined_evidence[0].content}</p></section>}<section className="drawer-section"><div className="section-heading"><div><span>RALPH LOOP</span><h3>Hipóteses avaliadas</h3></div></div><div className="hypotheses">{investigation.hypotheses.map((item) => <article key={item.number} className={`hypothesis ${item.verdict}`}><span>{String(item.number).padStart(2, "0")}</span><div><b>{item.statement}</b><p>{item.rationale}</p><small>{item.tool_calls.join(" → ") || "Sem chamadas"}</small></div><em>{verdictLabel[item.verdict]}</em></article>)}</div></section><section className="drawer-section"><div className="section-heading"><div><span>CONTEXTO</span><h3>Evidências utilizadas</h3></div><small>{investigation.context_used.length}/{skill.context_budget_items} itens</small></div><div className="evidence-list">{investigation.context_used.map((item) => <article key={item.id}><span>{item.source}</span><b>{item.title}</b><p>{item.content}</p><small>{formatTime(item.timestamp)}</small></article>)}</div></section><section className="mitigation"><span>MITIGAÇÃO PROPOSTA</span><h3>{investigation.proposed_mitigation}</h3>{investigation.approval_status === "pending" ? <><p>Aprovar registra uma decisão demonstrativa. Nenhum comando real será executado.</p><div><button className="reject" onClick={() => onDecision("reject")} disabled={busy}>Rejeitar</button><button className="approve" onClick={() => onDecision("approve")} disabled={busy}>Aprovar mitigação</button></div></> : <b>{investigation.approval_status === "approved" ? "Aprovada pelo operador" : investigation.approval_status === "rejected" ? "Rejeitada pelo operador" : "Nenhuma ação necessária"}</b>}</section><section className="drawer-section"><div className="section-heading"><div><span>AUDITORIA</span><h3>Trajetória completa</h3></div><small>{investigation.trace.length} etapas</small></div><div className="trace">{investigation.trace.map((step) => <article key={step.index}><i className={step.status} /><div><b>{step.title}</b><p>{step.detail}</p><small>{step.node}{step.tool ? ` · ${step.tool}` : ""} · {step.duration_ms.toFixed(1)} ms</small></div></article>)}</div></section></aside></div>;
}

function Tutorial({ onClose }: { onClose: () => void }) {
  const [step, setStep] = useState(0);
  const slides = [
    ["Uma central de investigação", "Escolha um incidente para entender sintomas, evidências, hipóteses e diagnóstico. Não é necessário conversar com um chatbot."],
    ["Skills controlam o processo", "Cada categoria carrega um runbook versionado com ferramentas permitidas, orçamento de contexto e limites do loop."],
    ["Você mantém a autoridade", "A mitigação fica pendente até uma pessoa revisar. O protótipo nunca executa rollback, restart ou alteração real."],
  ];
  return <div className="tutorial-backdrop"><section className="tutorial"><span>PRIMEIRO ACESSO · {step + 1}/3</span><h2>{slides[step][0]}</h2><p>{slides[step][1]}</p><div className="tutorial-visual">{step === 0 ? "Alerta → investigação → diagnóstico" : step === 1 ? "Skill → contexto → Ralph Loop" : "Proposta → revisão humana → auditoria"}</div><footer><div className="tutorial-dots">{slides.map((_, index) => <i className={index === step ? "active" : ""} key={index} />)}</div><button className="primary" onClick={() => step < 2 ? setStep(step + 1) : onClose()}>{step < 2 ? "Continuar" : "Explorar a central"}</button></footer></section></div>;
}

export default function App() {
  const [data, setData] = useState<Overview | null>(null);
  const [page, setPage] = useState<Page>("overview");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [tutorial, setTutorial] = useState(() => localStorage.getItem("incident-room-tutorial") !== "done");

  const load = async () => { try { setData(await api.overview()); setError(""); } catch (reason) { setError(reason instanceof Error ? reason.message : "Falha ao carregar a central."); } };
  useEffect(() => { void load(); }, []);
  const selectedIncident = data?.incidents.find((item) => item.id === selectedId) ?? null;
  const selectedInvestigation = data?.investigations.find((item) => item.incident_id === selectedId) ?? null;
  const selectedSkill = data?.skills.find((item) => item.id === selectedIncident?.skill_id) ?? null;
  const copy = pageCopy[page];

  const content = useMemo(() => {
    if (!data) return null;
    if (page === "overview") return <OverviewPage data={data} onOpen={(incident) => setSelectedId(incident.id)} />;
    if (page === "incidents") return <IncidentsPage data={data} onOpen={(incident) => setSelectedId(incident.id)} />;
    if (page === "skills") return <SkillsPage skills={data.skills} />;
    if (page === "evaluation") return <EvaluationPage data={data} />;
    return <HelpPage onTutorial={() => setTutorial(true)} />;
  }, [data, page]);

  const run = async () => { if (!selectedIncident) return; setBusy(true); try { await api.investigate(selectedIncident.id); await load(); } catch (reason) { setError(reason instanceof Error ? reason.message : "Falha ao investigar."); } finally { setBusy(false); } };
  const decide = async (decision: "approve" | "reject") => { if (!selectedInvestigation) return; setBusy(true); try { await api.decide(selectedInvestigation.id, decision); await load(); } catch (reason) { setError(reason instanceof Error ? reason.message : "Falha ao registrar decisão."); } finally { setBusy(false); } };
  const closeTutorial = () => { localStorage.setItem("incident-room-tutorial", "done"); setTutorial(false); };

  if (!data && !error) return <div className="loading"><div /><p>Preparando a sala de incidentes...</p></div>;
  if (!data) return <div className="loading"><p>{error}</p><button className="primary" onClick={() => void load()}>Tentar novamente</button></div>;

  return <div className="app-shell"><aside className="sidebar"><div className="brand"><div>IR</div><span><strong>Incident Room</strong><small>Operations workspace</small></span></div><nav aria-label="Navegação principal">{nav.map((item) => <button key={item.id} className={page === item.id ? "active" : ""} onClick={() => setPage(item.id)}><span>{item.icon}</span>{item.label}</button>)}</nav><div className="sidebar-foot"><i /><div><strong>Ambiente local</strong><small>Fixtures determinísticas</small></div></div></aside><main className="main"><header className="topbar"><div><span>{copy.eyebrow}</span><h1>{copy.title}</h1><p>{copy.description}</p></div><div><button className="help" onClick={() => setTutorial(true)}>Como usar</button><span className="mode">Simulação segura</span></div></header>{error && <div className="error">{error}<button onClick={() => setError("")}>×</button></div>}<div className="content">{content}</div></main>{selectedIncident && selectedInvestigation && selectedSkill && <IncidentDrawer incident={selectedIncident} investigation={selectedInvestigation} skill={selectedSkill} busy={busy} onClose={() => setSelectedId(null)} onRun={run} onDecision={decide} />}{tutorial && <Tutorial onClose={closeTutorial} />}</div>;
}
