import { useEffect, useRef, useState } from "react";
import { Boxes, ChevronRight, LoaderCircle, Network, Workflow } from "lucide-react";
import type { AgentMessage } from "../../lib/types";
import { agentStreamUrls } from "../../lib/api";

/** The agent hierarchy for one incident, filled in as each tier answers.
 *
 * Components answer in about a second, the facility tier a second later, the
 * system tier last. Rendering each as it lands means the panel is useful
 * immediately instead of blank until the slowest agent returns.
 */
export default function AgentAnalysis({
  dataset,
  facilityId,
  at,
  active,
}: {
  dataset: string;
  facilityId: string;
  at: number;
  active: boolean;
}) {
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [done, setDone] = useState(false);
  const [failure, setFailure] = useState("");
  // Re-run whenever the replay time moves, because the readings the agents
  // were describing are no longer the readings on screen.
  const key = `${dataset}:${facilityId}:${at}`;
  const seen = useRef("");

  useEffect(() => {
    if (!active || seen.current === key) return;
    seen.current = key;
    setMessages([]);
    setDone(false);
    setFailure("");
    const controller = new AbortController();

    (async () => {
      try {
        // Try the backend directly first so the stream is not buffered, then
        // fall back to the proxy path if that origin is not reachable.
        const candidates = agentStreamUrls(dataset, facilityId, at);
        let response: Response | undefined;
        for (const [index, url] of candidates.entries()) {
          try {
            response = await fetch(url, { signal: controller.signal });
            break;
          } catch (reachError) {
            if (controller.signal.aborted) return;
            if (index === candidates.length - 1) throw reachError;
          }
        }
        if (!response) throw new Error("Agents unreachable.");
        if (!response.ok || !response.body) {
          const detail = await response.json().catch(() => null);
          throw new Error(detail?.detail || `Agents unavailable (${response.status}).`);
        }
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        for (;;) {
          const { done: finished, value } = await reader.read();
          if (finished) break;
          buffer += decoder.decode(value, { stream: true });
          // SSE frames are separated by a blank line; the tail may be partial.
          const frames = buffer.split("\n\n");
          buffer = frames.pop() || "";
          for (const frame of frames) {
            const line = frame.split("\n").find((l) => l.startsWith("data: "));
            if (!line) continue;
            const message: AgentMessage = JSON.parse(line.slice(6));
            if (message.tier === "done") setDone(true);
            else if (message.tier === "error") setFailure(message.error || "Agent error.");
            else setMessages((all) => [...all, message]);
          }
        }
        setDone(true);
      } catch (error) {
        if (!controller.signal.aborted) setFailure((error as Error).message);
      }
    })();

    return () => controller.abort();
  }, [key, active, dataset, facilityId, at]);

  if (!active) return null;

  const system = messages.find((m) => m.tier === "system");
  const facilities = messages.filter((m) => m.tier === "facility");
  const components = messages.filter((m) => m.tier === "component");
  const own = facilities.find((m) => m.facility_id === facilityId);
  const siblings = facilities.filter((m) => m.facility_id !== facilityId);

  return (
    <section className="inspector-section agent-analysis">
      <div className="section-heading">
        <Workflow size={14} />
        <h2>Agent analysis</h2>
        {!done && !failure && (
          <span className="agent-progress">
            <LoaderCircle size={11} className="spin" />
            {messages.length ? `${messages.length} reported` : "starting"}
          </span>
        )}
      </div>

      {failure && (
        <p className="inline-error" role="alert">
          {failure}
        </p>
      )}

      {system && (
        <div className="agent-card system-tier">
          <div className="agent-label">
            <Network size={13} />
            System {system.system_id}
            <small>shared fleet</small>
          </div>
          <p>{agentText(system)}</p>
        </div>
      )}

      {own && (
        <div className="agent-card facility-tier">
          <div className="agent-label">
            <Boxes size={13} />
            {friendly(own.facility_id)}
          </div>
          <p>{agentText(own)}</p>
        </div>
      )}

      {siblings.length > 0 && (
        <details className="agent-siblings">
          <summary>
            Competing for the same trucks ({siblings.length}){" "}
            <ChevronRight size={13} />
          </summary>
          {siblings.map((sibling) => (
            <div className="agent-card facility-tier" key={sibling.facility_id}>
              <div className="agent-label">
                <Boxes size={13} />
                {friendly(sibling.facility_id)}
              </div>
              <p>{agentText(sibling)}</p>
            </div>
          ))}
        </details>
      )}

      {components.length > 0 && (
        <details className="agent-components" open>
          <summary>
            Component agents ({components.length}) <ChevronRight size={13} />
          </summary>
          {components.map((component) => (
            <div className="agent-component" key={component.asset_id}>
              <span className="component-kind">{component.kind}</span>
              <div>
                <code>{component.asset_id}</code>
                <p>{agentText(component)}</p>
              </div>
            </div>
          ))}
        </details>
      )}

      <p className="fine-print">
        Agents explain figures the planner already computed and verified. They
        do not calculate, and any number they state that is not in their data is
        rejected before it reaches this panel.
      </p>
    </section>
  );
}

/** An agent's prose, or the verified fact it was given when the prose failed. */
function agentText(message: AgentMessage): string {
  if (message.verified && message.text) return message.text;
  const assessment = message.payload?.assessment;
  if (typeof assessment === "string") return assessment;
  return message.error || "No reading available.";
}

function friendly(id?: string): string {
  return id ? id.replace(/^.*_FACILITY_/, "Facility ") : "Facility";
}
