import React, { useEffect, useState } from "react";
import {
  LayoutDashboard,
  FileText,
  BookOpen,
  ShieldCheck,
  AlertTriangle,
  SlidersHorizontal,
  BarChart3,
  Search,
  PanelLeftClose,
  Download,
  Plus,
  ArrowRight,
  Sparkles,
  TrendingUp,
  TrendingDown,
  CircleDollarSign,
  Activity,
  ShieldAlert,
  CheckCircle2,
  ChevronRight,
  Play,
  Save,
  GitCompareArrows,
  Filter,
  X,
  Database,
  Clock3,
  ExternalLink,
  Send,
  Building2,
  Menu,
  UserPlus,
  KeyRound,
  LockKeyhole,
  UserCheck,
  LogOut,
  CircleX,
  Eye,
  EyeOff,
  Factory,
} from "lucide-react";
import { API, apiRequest } from "../api/client";
import { EXCEPTIONS, META, POLICY_TYPE_ORDER, policyDisplayName } from "../config";
import { AuthField, Badge, Bars, Card, DataTable, Heading, Insight, LineChart, Metric, NO_CLIPBOARD, PasswordPolicy, SecretInput, money } from "../components/ui";

export default function ControlsWorkspace({ session }) {
  const [controls, setControls] = useState([]);
  const [selectedControlId, setSelectedControlId] = useState(null);
  const [controlPage, setControlPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    apiRequest("/api/controls", {}, session.token)
      .then((rows) => {
        setControls(rows);
        setControlPage(0);
        setSelectedControlId((current) => current || rows[0]?.control_id || null);
      })
      .catch((requestError) => setError(requestError.message))
      .finally(() => setLoading(false));
  }, [session.token]);

  const controlsPerPage = 10;
  const pageCount = Math.max(1, Math.ceil(controls.length / controlsPerPage));
  const safePage = Math.min(controlPage, pageCount - 1);
  const pageControls = controls.slice(
    safePage * controlsPerPage,
    (safePage + 1) * controlsPerPage,
  );
  const selectedControl = controls.find((control) => control.control_id === selectedControlId) || pageControls[0];
  const rows = pageControls.map((control) => [
    control.library_policy_id,
    control.control_id,
    control.clause_number,
    control.control_type,
    control.frequency,
    `${control.effectiveness}%`,
    control.status,
  ]);
  const selectedRow = rows.find((row) => row[1] === selectedControl?.control_id);
  const effective = controls.filter((control) => control.status === "Effective").length;
  const average = controls.length
    ? Math.round(controls.reduce((total, control) => total + control.effectiveness, 0) / controls.length)
    : 0;
  const automated = controls.filter((control) => control.automation === "Automated").length;
  const goToControlPage = (nextPage) => {
    const boundedPage = Math.max(0, Math.min(pageCount - 1, nextPage));
    setControlPage(boundedPage);
    setSelectedControlId(controls[boundedPage * controlsPerPage]?.control_id || null);
  };

  return (
    <div className="controls-workspace">
      <div className="control-metrics">
        <ControlMetric label="Total Controls" value={controls.length.toLocaleString()} detail="Mapped to policy clauses" />
        <ControlMetric label="Effective" value={`${effective}/${controls.length}`} detail="Latest test cycle" tone="success" />
        <ControlMetric label="Avg Effectiveness" value={`${average}%`} detail="Across manufactured controls" />
        <ControlMetric label="Automated" value={automated.toLocaleString()} detail="Machine-executed checks" />
      </div>
      <div className="controls-layout">
        <Card title="Controls Register" className="controls-register">
          {loading && <div className="data-message">Loading controls...</div>}
          {error && <div className="data-message error">{error}</div>}
          {!loading && !error && controls.length === 0 && (
            <div className="data-message">Generate controls from Data Manufacturing to populate this register.</div>
          )}
          <DataTable
            headers={["Policy", "Control", "Clause", "Type", "Frequency", "Effectiveness", "Status"]}
            rows={rows}
            selected={selectedRow}
            onSelect={(row) => setSelectedControlId(row[1])}
            render={(value, index, row) => {
              const control = controls.find((item) => item.control_id === row[1]);
              if (index === 0) {
                return <div className="control-name-cell"><strong>{control.policy_name}</strong><small>Policy ID {control.library_policy_id} - {control.policy_code}</small></div>;
              }
              if (index === 1) {
                return <div className="control-name-cell"><strong>{control.control_name}</strong><small>{control.control_id} - {control.control_owner}</small></div>;
              }
              return index === 6 ? <Badge>{value}</Badge> : value;
            }}
          />
          <div className="table-footer request-pagination">
            <span>
              Showing {controls.length ? safePage * controlsPerPage + 1 : 0}-
              {Math.min((safePage + 1) * controlsPerPage, controls.length)} of {controls.length.toLocaleString()}
            </span>
            <div>
              <button
                type="button"
                disabled={safePage === 0}
                onClick={() => goToControlPage(safePage - 1)}
                aria-label="Previous 10 controls"
              >
                &lt;
              </button>
              <span>Page {safePage + 1} of {pageCount}</span>
              <button
                type="button"
                disabled={safePage >= pageCount - 1}
                onClick={() => goToControlPage(safePage + 1)}
                aria-label="Next 10 controls"
              >
                &gt;
              </button>
            </div>
          </div>
        </Card>
        <Card title="Control Detail" className="control-detail">
          {!selectedControl && <div className="data-message">Select a manufactured control to view its details.</div>}
          {selectedControl && (
            <>
              <div className="detail-title"><div><h3>{selectedControl.control_name}</h3><small>{selectedControl.control_id} - Policy ID {selectedControl.library_policy_id} - {selectedControl.policy_code}</small></div></div>
              <div className="control-facts">
                <p><span>Policy:</span> <strong>{selectedControl.policy_name}</strong></p>
                <p><span>Policy ID:</span> <strong>{selectedControl.library_policy_id}</strong></p>
                <p><span>Clause:</span> <strong>{selectedControl.clause_number}</strong></p>
                <p><span>Type:</span> <strong>{selectedControl.control_type}</strong></p>
                <p><span>Automation:</span> <strong>{selectedControl.automation}</strong></p>
                <p><span>Owner:</span> <strong>{selectedControl.control_owner}</strong></p>
                <p><span>Frequency:</span> <strong>{selectedControl.frequency}</strong></p>
                <p><span>Last Tested:</span> <strong>{selectedControl.last_tested}</strong></p>
                <p><span>Failures (90d):</span> <strong>{selectedControl.failures_90d}</strong></p>
              </div>
              <div className="control-description"><h4>Control Description</h4><p>{selectedControl.control_description}</p></div>
              <div className="effectiveness-score"><span>Effectiveness Score</span><strong>{selectedControl.effectiveness}%</strong><div><i style={{ width: `${selectedControl.effectiveness}%` }} /></div></div>
              <div className="control-assessment"><h4><Sparkles size={14} /> AI Control Assessment</h4><p>{selectedControl.assessment}</p></div>
            </>
          )}
        </Card>
      </div>
    </div>
  );
}

function ControlMetric({ label, value, detail, tone = "" }) {
  return (
    <div className={`card control-metric ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}

