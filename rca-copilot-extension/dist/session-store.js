"use strict";
/**
 * session-store.ts
 * Holds RCA session state across multiple Copilot Chat turns.
 * Lives in the extension's memory for the VS Code session lifetime.
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.sessionStore = exports.SessionStore = void 0;
class SessionStore {
    sessions = new Map();
    counter = 0;
    create(params) {
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
    addEvidence(sessionId, agent, data) {
        const session = this.sessions.get(sessionId);
        if (!session)
            return;
        session.evidence.push({ agent, timestamp: new Date(), data });
        if (!session.agentsRun.includes(agent)) {
            session.agentsRun.push(agent);
        }
    }
    get(sessionId) {
        return this.sessions.get(sessionId);
    }
    /** Get the most recent active session */
    latest() {
        const all = [...this.sessions.values()];
        return all.filter((s) => s.status === "active").at(-1);
    }
    complete(sessionId) {
        const s = this.sessions.get(sessionId);
        if (s)
            s.status = "complete";
    }
    list() {
        return [...this.sessions.values()].sort((a, b) => b.createdAt.getTime() - a.createdAt.getTime());
    }
}
exports.SessionStore = SessionStore;
// Singleton — shared across all agents in the extension process
exports.sessionStore = new SessionStore();
//# sourceMappingURL=session-store.js.map