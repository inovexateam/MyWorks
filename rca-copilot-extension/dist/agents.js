"use strict";
/**
 * agents.ts — All RCA specialist agents
 *
 * Each agent:
 *   1. Has a focused system prompt
 *   2. Calls Copilot's LLM via the VS Code Language Model API (zero cost)
 *   3. Returns typed structured data
 *   4. Streams progress to the Copilot Chat response stream
 */
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.runTriageAgent = runTriageAgent;
exports.runInvestigatorAgent = runInvestigatorAgent;
exports.runCodeAnalystAgent = runCodeAnalystAgent;
exports.runLogAnalystAgent = runLogAnalystAgent;
exports.runSynthesizerAgent = runSynthesizerAgent;
const vscode = __importStar(require("vscode"));
const copilot_llm_1 = require("./copilot-llm");
async function runTriageAgent(params) {
    const { incident, errorMessage, severity, token, stream } = params;
    stream?.progress("🔍 Triage agent classifying incident...");
    const result = await (0, copilot_llm_1.callCopilotJSON)({
        system: `You are a senior SRE triaging a production incident.
Extract structured signals. Detect tech stack from error messages and description.
Decide which specialist agents are needed. Be precise and technical.
Always respond with valid JSON only.`,
        messages: [
            {
                role: "user",
                content: `Triage this production incident:

Incident: ${incident}
${errorMessage ? `Error/Exception:\n${errorMessage}` : ""}
${severity ? `Reported severity: ${severity}` : ""}

Return JSON:
{
  "severity": "P1|P2|P3|P4",
  "category": "memory|performance|crash|data-corruption|security|network|config|dependency|unknown",
  "detectedStack": "e.g. Java 17 + Spring Boot 3 + PostgreSQL + Redis",
  "keySignals": ["signal1", "signal2", "signal3"],
  "suspectedArea": "e.g. connection pool leak in OrderService",
  "needsInvestigator": true,
  "needsCodeAnalyst": true,
  "needsLogAnalyst": false,
  "triageConfidence": 78,
  "summary": "One sentence triage summary"
}

keySignals: max 5 specific technical clues.
triageConfidence: 0-100 how confident you are in the classification.`,
            },
        ],
        token,
    });
    stream?.progress(`✅ Triage complete — ${result.category} / ${result.severity} (${result.detectedStack})`);
    return result;
}
async function runInvestigatorAgent(params) {
    const { repoUrl, focus, token, stream } = params;
    stream?.progress("🔎 Investigator agent fetching GitHub data...");
    // Parse owner/repo from URL
    const match = repoUrl.match(/github\.com\/([^/]+)\/([^/]+)/);
    const owner = match?.[1] ?? "";
    const repo = match?.[2]?.replace(/\.git$/, "") ?? "";
    // Get GitHub token from VS Code settings (optional)
    const config = vscode.workspace.getConfiguration("rca");
    const githubToken = config.get("githubToken") ?? "";
    const headers = {
        "User-Agent": "rca-copilot-extension/1.0",
        Accept: "application/vnd.github.v3+json",
        ...(githubToken ? { Authorization: `Bearer ${githubToken}` } : {}),
    };
    // Fetch recent commits
    let commitsText = "Could not fetch commits.";
    try {
        const res = await fetch(`https://api.github.com/repos/${owner}/${repo}/commits?per_page=20`, { headers, signal: AbortSignal.timeout(8000) });
        if (res.ok) {
            const commits = (await res.json());
            commitsText = commits
                .map((c) => `${c.sha.slice(0, 7)} | ${c.commit.author.date.slice(0, 16)} | ${c.commit.message.split("\n")[0]}`)
                .join("\n");
        }
    }
    catch { /* rate limited or network error — continue */ }
    // Fetch stack manifest (package.json, pom.xml, go.mod, etc.)
    let manifestText = "Not found.";
    const candidates = ["package.json", "pom.xml", "build.gradle", "go.mod", "Cargo.toml",
        "requirements.txt", "pyproject.toml", "Gemfile"];
    for (const file of candidates) {
        try {
            const res = await fetch(`https://raw.githubusercontent.com/${owner}/${repo}/main/${file}`, { signal: AbortSignal.timeout(5000) });
            if (res.ok) {
                manifestText = `[${file}]\n${(await res.text()).slice(0, 1500)}`;
                break;
            }
        }
        catch {
            continue;
        }
    }
    stream?.progress("🤖 Investigator agent analysing commits with Copilot...");
    const result = await (0, copilot_llm_1.callCopilotJSON)({
        system: `You are a senior engineer investigating a production incident by analysing GitHub 
repository data. Identify suspicious commits, correlate deployment timing with incident start, 
and recommend which files the code analyst should inspect next.`,
        messages: [
            {
                role: "user",
                content: `Repository: ${repoUrl}
Owner: ${owner}, Repo: ${repo}
Focus: ${focus ?? "identify any change that could cause a production regression"}

Stack manifest:
${manifestText}

Recent commits:
${commitsText}

Return JSON:
{
  "repo": "${owner}/${repo}",
  "language": "primary language",
  "recentCommits": ["sha | date | message", ...],
  "suspiciousCommits": [
    { "sha": "abc1234", "message": "...", "reason": "why suspicious" }
  ],
  "stackManifest": "detected stack in 1 line",
  "lastDeployHint": "sha or date of likely last deploy",
  "filesToInspect": ["path/to/file.java", "path/to/config.yml"],
  "summary": "2-3 sentence investigator summary"
}

Suspicious = dependency upgrades, removed error handling, new async/concurrent code,
cache config changes, connection pool config, removed rollbacks, large refactors.`,
            },
        ],
        token,
    });
    stream?.progress(`✅ Investigator: ${result.suspiciousCommits.length} suspicious commit(s) found`);
    return result;
}
async function runCodeAnalystAgent(params) {
    const { code, filePath, languageHint, incidentContext, token, stream } = params;
    stream?.progress(`🔬 Code analyst inspecting ${filePath ?? "code snippet"}...`);
    const result = await (0, copilot_llm_1.callCopilotJSON)({
        system: `You are an expert code reviewer performing root cause analysis.
You analyze code in ANY programming language — Python, Java, Go, Node.js, Rust, Ruby, C#, etc.
You identify: memory leaks, resource leaks, race conditions, N+1 queries, deadlocks, 
missing error handling, unbounded collections, blocking async calls, injection vulnerabilities.
You always cite the specific line or pattern. Respond in valid JSON only.`,
        messages: [
            {
                role: "user",
                content: `Analyze this code for root cause candidates.
${languageHint ? `Language: ${languageHint}` : "Auto-detect the language."}
${filePath ? `File: ${filePath}` : ""}
${incidentContext ? `Incident context: ${incidentContext}` : ""}

Code to analyze:
\`\`\`
${code.slice(0, 10000)}
\`\`\`

Return JSON with up to 5 root causes ranked by confidence:
{
  "language": "detected language",
  "framework": "detected framework or none",
  "fileAnalyzed": "${filePath ?? "snippet"}",
  "causes": [
    {
      "rank": 1,
      "title": "Short specific title",
      "confidence": 87,
      "severity": "critical|high|medium|low",
      "category": "memory|concurrency|database|network|config|security|logic|error-handling|performance",
      "explanation": "Technical explanation of why this causes the incident",
      "evidence": "Exact line or pattern that points to this — quote it",
      "lineHint": "~line 42 or function name",
      "immediateAction": "What to do right now to mitigate",
      "permanentFix": "The correct long-term code change"
    }
  ],
  "suspiciousPatterns": ["pattern1", "pattern2"],
  "summary": "2 sentence summary"
}

Focus especially on:
- Unbounded caches / collections (memory leaks)
- Missing close() / try-with-resources / defer (resource leaks)  
- Shared mutable state (race conditions)
- Blocking calls inside event loops / coroutines
- Connection pools not released back
- Empty catch blocks swallowing exceptions
- Retry loops without backoff or circuit breaker`,
            },
        ],
        token,
    });
    stream?.progress(`✅ Code analyst: ${result.causes.length} root cause candidate(s) found`);
    return result;
}
async function runLogAnalystAgent(params) {
    const { logs, service, requestId, timeWindow, token, stream } = params;
    stream?.progress("📋 Log analyst parsing error patterns...");
    const result = await (0, copilot_llm_1.callCopilotJSON)({
        system: `You are a senior SRE analysing production logs and stack traces.
You extract error patterns, correlate trace IDs, identify anomalous time windows,
and pinpoint the originating service. You find signal in noise.
Respond in valid JSON only.`,
        messages: [
            {
                role: "user",
                content: `Analyze these logs/traces for root cause signals.
${service ? `Service: ${service}` : ""}
${requestId ? `Trace/Request ID: ${requestId}` : ""}
${timeWindow ? `Time window: ${timeWindow}` : ""}

Logs:
\`\`\`
${logs.slice(0, 10000)}
\`\`\`

Return JSON:
{
  "errorRate": "e.g. 4.2 errors/sec or N errors in M minutes",
  "topError": "most significant full error message",
  "traceIds": ["id1", "id2"],
  "timelineEvents": [
    { "time": "14:02:33", "event": "First OOM error observed", "severity": "critical" }
  ],
  "suspectedService": "service-name",
  "errorClusters": ["cluster1: 42 occurrences of X", "cluster2: 18 occurrences of Y"],
  "keyFindings": ["finding1", "finding2", "finding3"],
  "summary": "2-3 sentence summary of log analysis"
}`,
            },
        ],
        token,
    });
    stream?.progress(`✅ Log analyst: ${result.keyFindings.length} key finding(s) extracted`);
    return result;
}
// ═══════════════════════════════════════════════════
// SYNTHESIZER AGENT
// Last to run. Merges all evidence.
// Produces ranked RCA with confidence scores.
// ═══════════════════════════════════════════════════
async function runSynthesizerAgent(params) {
    const { incident, triage, investigator, codeAnalysis, logAnalysis, format, token, stream } = params;
    stream?.progress("📝 Synthesizer agent generating final RCA...");
    const formatInstr = format === "postmortem"
        ? "Format as a Google SRE postmortem: ## Summary, ## Impact, ## Timeline, ## Root Cause, ## Contributing Factors, ## Action Items (30/60/90 day), ## Lessons Learned"
        : format === "json"
            ? "Return a JSON object: { summary, overallSeverity, causes[{rank,title,confidence,severity,immediateAction,permanentFix}], nextSteps, timeline }"
            : "Format as clean Markdown. Include: Executive Summary, Root Cause Analysis table (ranked by confidence), Evidence, Immediate Actions, Permanent Fixes, Next Steps.";
    const output = await (0, copilot_llm_1.callCopilot)({
        system: `You are a principal engineer writing an incident root cause analysis.
You synthesize findings from multiple specialist agents into a clear, ranked, actionable report.
Confidence scoring: 75-100% = strong direct evidence. 45-74% = pattern match. 10-44% = speculative.
Be honest about what could NOT be determined. The report is read during active incidents AND by management after.`,
        messages: [
            {
                role: "user",
                content: `Synthesize these investigation findings into a final RCA.

INCIDENT:
${incident}

TRIAGE:
${JSON.stringify(triage, null, 2)}

${investigator ? `INVESTIGATOR FINDINGS:\n${JSON.stringify(investigator, null, 2)}` : ""}
${codeAnalysis ? `CODE ANALYSIS:\n${JSON.stringify(codeAnalysis, null, 2)}` : ""}
${logAnalysis ? `LOG ANALYSIS:\n${JSON.stringify(logAnalysis, null, 2)}` : ""}

${formatInstr}

Always include:
1. Single most likely root cause at the top
2. Confidence score for each cause (honest, not inflated)
3. Immediate mitigation (what to do RIGHT NOW)
4. Permanent fix recommendation
5. 30/60/90-day action items to prevent recurrence
6. What we could NOT determine and why`,
            },
        ],
        token,
        onChunk: (chunk) => stream?.markdown(chunk),
    });
    stream?.progress("✅ RCA complete");
    return output;
}
//# sourceMappingURL=agents.js.map