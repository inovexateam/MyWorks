/**
 * session-store.ts
 * Holds RCA session state across multiple Copilot Chat turns.
 * Lives in the extension's memory for the VS Code session lifetime.
 */

export interface AgentEvidence {
  agent: string;
  timestamp: Date;
  data: Record<string, any>;
}

export interface RCASession {
  id: string;
  createdAt: Date;
  incident: string;
  severity: string;
  repoUrl?: string;
  evidence: AgentEvidence[];
  agentsRun: string[];
  status: "active" | "complete";
}

export class SessionStore {
  private sessions = new Map<string, RCASession>();
  private counter = 0;

  create(params: { incident: string; severity: string; repoUrl?: string }): string {
    this.counter++;
    const id = `rca-${Date.now().toString(36)}-${this.counter}`;
    this.sessions.set(id, {
      id,
      createdAt: new Date(),
      incident: params.incident,
      severity: params.severity,
      repoUrl: params.repoUrl,
      evidence: [],
      agentsRun: [],
      status: "active",
    });
    return id;
  }

  addEvidence(sessionId: string, agent: string, data: Record<string, any>): void {
    const session = this.sessions.get(sessionId);
    if (!session) return;
    session.evidence.push({ agent, timestamp: new Date(), data });
    if (!session.agentsRun.includes(agent)) {
      session.agentsRun.push(agent);
    }
  }

  get(sessionId: string): RCASession | undefined {
    return this.sessions.get(sessionId);
  }

  /** Get the most recent active session */
  latest(): RCASession | undefined {
    const all = [...this.sessions.values()];
    return all.filter((s) => s.status === "active").at(-1);
  }

  complete(sessionId: string): void {
    const s = this.sessions.get(sessionId);
    if (s) s.status = "complete";
  }

  list(): RCASession[] {
    return [...this.sessions.values()].sort(
      (a, b) => b.createdAt.getTime() - a.createdAt.getTime()
    );
  }
}

// Singleton — shared across all agents in the extension process
export const sessionStore = new SessionStore();
