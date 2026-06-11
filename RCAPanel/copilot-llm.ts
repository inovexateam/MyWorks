/**
 * copilot-llm.ts
 *
 * Wraps the VS Code Language Model API (vscode.lm).
 * This is what lets us use GitHub Copilot's model for FREE —
 * no OpenAI key, no Anthropic key, no Azure key.
 *
 * The user just needs:
 *   - VS Code with GitHub Copilot extension installed
 *   - A GitHub Copilot subscription (individual or business)
 *
 * HOW IT WORKS:
 *   vscode.lm.selectChatModels() asks Copilot "give me a model handle"
 *   model.sendRequest() sends messages through Copilot's inference
 *   The response streams back token by token
 *   We collect it and return as a string
 *
 * This is the OFFICIAL VS Code extension API — fully supported by Microsoft.
 */

import * as vscode from "vscode";

export interface LLMMessage {
  role: "user" | "assistant";
  content: string;
}

export interface LLMOptions {
  system: string;
  messages: LLMMessage[];
  token: vscode.CancellationToken;
  /** Stream partial text back as it arrives */
  onChunk?: (text: string) => void;
  jsonMode?: boolean;
}

/**
 * Get the best available Copilot model.
 * Prefers gpt-4o, falls back to gpt-4, then whatever is available.
 */
export async function getCopilotModel(): Promise<vscode.LanguageModelChat> {
  // Try GPT-4o first (most capable, best for code analysis)
  let models = await vscode.lm.selectChatModels({
    vendor: "copilot",
    family: "gpt-4o",
  });

  if (models.length > 0) return models[0];

  // Fallback to gpt-4
  models = await vscode.lm.selectChatModels({
    vendor: "copilot",
    family: "gpt-4",
  });

  if (models.length > 0) return models[0];

  // Last resort — take any available model
  models = await vscode.lm.selectChatModels({ vendor: "copilot" });

  if (models.length === 0) {
    throw new Error(
      "No Copilot model available. Make sure GitHub Copilot extension is installed and you are signed in."
    );
  }

  return models[0];
}

/**
 * Main LLM call — uses Copilot's model, streams response.
 * Returns the full text when complete.
 */
export async function callCopilot(options: LLMOptions): Promise<string> {
  const { system, messages, token, onChunk, jsonMode } = options;

  const model = await getCopilotModel();

  // Build the message array for the VS Code LM API
  const craftedMessages: vscode.LanguageModelChatMessage[] = [
    // System message goes first as a "user" turn (VS Code LM API convention)
    vscode.LanguageModelChatMessage.User(
      `<system>\n${system}${jsonMode ? "\n\nIMPORTANT: Respond ONLY with valid JSON. No markdown fences, no preamble." : ""}\n</system>`
    ),
    // Then the actual conversation
    ...messages.map((m) =>
      m.role === "user"
        ? vscode.LanguageModelChatMessage.User(m.content)
        : vscode.LanguageModelChatMessage.Assistant(m.content)
    ),
  ];

  try {
    const response = await model.sendRequest(craftedMessages, {}, token);

    let fullText = "";
    for await (const chunk of response.text) {
      fullText += chunk;
      onChunk?.(chunk);
    }

    return fullText;
  } catch (err: any) {
    if (err instanceof vscode.LanguageModelError) {
      if (err.code === vscode.LanguageModelError.NotFound.name) {
        throw new Error("Copilot model not found. Is GitHub Copilot installed?");
      }
      if (err.code === vscode.LanguageModelError.Blocked.name) {
        throw new Error("Request blocked by Copilot content policy.");
      }
      if (err.code === vscode.LanguageModelError.NoPermissions.name) {
        throw new Error("No permission to use Copilot language models.");
      }
    }
    throw err;
  }
}

/**
 * Convenience: call Copilot and parse JSON response.
 * Strips markdown fences if the model wraps the response in them.
 */
export async function callCopilotJSON<T>(options: Omit<LLMOptions, "jsonMode">): Promise<T> {
  const raw = await callCopilot({ ...options, jsonMode: true });

  // Strip ```json ... ``` fences if present
  const clean = raw
    .replace(/^```json\s*/i, "")
    .replace(/^```\s*/i, "")
    .replace(/```\s*$/i, "")
    .trim();

  try {
    return JSON.parse(clean) as T;
  } catch {
    // Try to extract JSON object from surrounding text
    const match = clean.match(/\{[\s\S]*\}/);
    if (match) {
      return JSON.parse(match[0]) as T;
    }
    throw new Error(`Copilot returned non-JSON: ${clean.slice(0, 200)}`);
  }
}
