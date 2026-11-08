import { useState } from "react";
import { BellRing, Check, ChevronRight, UserRound, X } from "lucide-react";
import type { Dashboard } from "../../lib/types";
import { operatorById, type Operator } from "../../lib/operators";

/** Who is covering which system tonight, and a pager for each of them.
 *
 * Assignments live in this session only. The button sends nothing: it marks the
 * row so an operator can see at a glance who has already been raised.
 */
export default function OperatorAssignment({
  data,
  people,
  assignments,
  onAssign,
  onView,
  onClose,
}: {
  data: Dashboard;
  people: Operator[];
  assignments: Record<string, number>;
  onAssign: (systemId: string, operatorId: number) => void;
  onView: (systemId: string) => void;
  onClose: () => void;
}) {
  const [paged, setPaged] = useState<Record<string, string>>({});

  const incidentsBySystem = data.alerts.reduce<Record<string, number>>(
    (totals, alert) => ({
      ...totals,
      [alert.system_id]: (totals[alert.system_id] || 0) + 1,
    }),
    {},
  );

  return (
    <aside className="operator-view glass" aria-label="Operator assignments">
      <div className="operator-heading">
        <UserRound size={16} />
        <div>
          <h2>Operator assignments</h2>
          <p>Who is covering each system on this shift</p>
        </div>
        <button
          className="icon-button"
          onClick={onClose}
          aria-label="Close operator assignments"
        >
          <X size={16} />
        </button>
      </div>

      <div className="operator-rows">
        {data.systems.map((system) => {
          const assignedId = assignments[system.id];
          const operator = operatorById(people, assignedId);
          const open = incidentsBySystem[system.id] || 0;
          const sent = paged[system.id];
          return (
            <div className="operator-row" key={system.id}>
              <div className="operator-system">
                <button
                  className="system-link"
                  onClick={() => onView(system.id)}
                  title={`Show System ${system.id} in the 3D view`}
                >
                  System {system.id}
                  <ChevronRight size={12} />
                </button>
                <small>
                  {system.facilities.length} facilities
                  {open > 0 ? ` · ${open} active` : " · clear"}
                </small>
              </div>

              <label className="operator-picker">
                <span className="technical-label">Assigned operator</span>
                <select
                  aria-label={`Operator assigned to system ${system.id}`}
                  value={assignedId ?? ""}
                  onChange={(e) => onAssign(system.id, Number(e.target.value))}
                >
                  {people.map((person) => (
                    <option key={person.id} value={person.id}>
                      #{person.id} · {person.name}
                    </option>
                  ))}
                </select>
              </label>

              <div className="operator-contact">
                <code>{operator ? operator.pager : "—"}</code>
                <button
                  className={"pager-button " + (sent ? "sent" : "")}
                  disabled={!operator}
                  onClick={() =>
                    setPaged((all) => ({
                      ...all,
                      [system.id]: new Date().toLocaleTimeString("en-GB", {
                        hour: "2-digit",
                        minute: "2-digit",
                        timeZone: "UTC",
                        hour12: false,
                      }),
                    }))
                  }
                >
                  {sent ? <Check size={13} /> : <BellRing size={13} />}
                  {sent ? `Paged ${sent} UTC` : "Ping pager"}
                </button>
              </div>
            </div>
          );
        })}
      </div>

      <p className="fine-print">
        Assignments and pages are held in this browser session for demonstration.
        No message is transmitted and the roster is not part of the EOG dataset.
      </p>
    </aside>
  );
}
