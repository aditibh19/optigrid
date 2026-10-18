"use client";
import { useState } from "react";
import { Card, PageHead, Notice, errorMessage } from "@/components/ui";
import { copilotParse, type CopilotReply } from "@/services/api";
import { useVehicles } from "@/hooks/useVehicles";

interface Message { role: "me" | "bot"; text: string; reply?: CopilotReply }

const EXAMPLES = [
  "I need to reach Agra by 6pm with 80% charge",
  "Charge to 90% before I leave at 7am",
  "Get me to 60% as cheaply as possible",
];

const asString = (v: unknown) => (typeof v === "string" ? v : undefined);
const asNumber = (v: unknown) => (typeof v === "number" ? v : undefined);

export default function CopilotPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { selected } = useVehicles();
  const vehicleId = selected?.id;

  async function send(text: string) {
    const message = text.trim();
    if (!message || busy) return;
    setInput(""); setError(null); setBusy(true);
    setMessages((m) => [...m, { role: "me", text: message }]);
    try {
      const reply = await copilotParse(message, vehicleId);
      setMessages((m) => [...m, { role: "bot", text: reply.reply_text, reply }]);
    } catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  }

  return (
    <>
      <PageHead title="Copilot">
        Say what you need in plain language. The copilot pulls out your target charge and deadline, and the
        optimiser, not the language model, decides the charging plan.
      </PageHead>

      <div style={{ maxWidth: 760 }} className="stack">
        <Card>
          <div className="chat" aria-live="polite">
            {messages.length === 0 && (
              <div className="stack">
                <p className="empty" style={{ padding: 0, textAlign: "left" }}>Try one of these, or write your own.</p>
                <div className="preset-row">
                  {EXAMPLES.map((e) => <button key={e} className="chip" onClick={() => send(e)}>{e}</button>)}
                </div>
              </div>
            )}
            {messages.map((m, i) => {
              const opt = m.reply?.optimizer_result ?? null;
              const action = opt ? asString(opt.recommended_action) : undefined;
              const kw = opt ? asNumber(opt.action_kw) : undefined;
              const why = opt ? asString(opt.explanation_paragraph) : undefined;
              return (
                <div key={i} className={`bubble ${m.role}`}>
                  <p>{m.text}</p>
                  {m.reply && (
                    <>
                      <div className="chips">
                        <span className="badge">Intent: {m.reply.intent.replace(/_/g, " ")}</span>
                        {m.reply.extracted_target_soc_pct !== null && <span className="badge">Target {m.reply.extracted_target_soc_pct}%</span>}
                        {m.reply.extracted_deadline && <span className="badge">By {m.reply.extracted_deadline}</span>}
                      </div>
                      {m.reply.validation_errors.map((v) => <p key={v} style={{ marginTop: 8, color: "var(--gold)", fontSize: 13 }}>{v}</p>)}
                      {action && (
                        <p style={{ marginTop: 10, fontSize: 14, color: "var(--text-secondary)" }}>
                          Optimiser says: <strong style={{ color: "var(--text-primary)" }}>{action.replace(/_/g, " ")}{kw ? ` at ${kw} kW` : ""}</strong>. {why}
                        </p>
                      )}
                    </>
                  )}
                </div>
              );
            })}
            {busy && <div className="bubble bot" style={{ color: "var(--text-muted)" }}>Thinking</div>}
          </div>
        </Card>

        {error && <Notice tone="error">{error}</Notice>}

        <form className="row" style={{ flexWrap: "nowrap" }} onSubmit={(e) => { e.preventDefault(); send(input); }}>
          <div className="input-wrap" style={{ flex: 1 }}>
            <input aria-label="Message the copilot" placeholder="For example: I need 80% by 6pm" value={input} onChange={(e) => setInput(e.target.value)} maxLength={2000} />
          </div>
          <button className="btn" type="submit" disabled={busy || !input.trim()}>Send</button>
        </form>
        {!vehicleId && <p style={{ fontSize: 12, color: "var(--text-muted)" }}>No saved vehicle yet, so the copilot assumes a 60 kWh car. Add one on the Journey planner page and the copilot will use its real battery and charge level.</p>}
      </div>
    </>
  );
}
