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
import ControlsWorkspace from "./ControlsWorkspace";

export default function Policy({ session }) {
  const [explorerTab, setExplorerTab] = useState(() => (
    sessionStorage.getItem("policyExplorerTab") === "controls" ? "controls" : "library"
  ));
  const [policies, setPolicies] = useState([]);
  const [selectedPolicyId, setSelectedPolicyId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [relatedPolicies, setRelatedPolicies] = useState([]);
  const [selectedPolicyControls, setSelectedPolicyControls] = useState([]);
  const [policyControlIndex, setPolicyControlIndex] = useState(0);
  const [policyLinksLoading, setPolicyLinksLoading] = useState(false);
  const [policyLinksError, setPolicyLinksError] = useState("");
  const [expandedTypes, setExpandedTypes] = useState(() => new Set(POLICY_TYPE_ORDER));

  useEffect(() => {
    setLoading(true);
    apiRequest("/api/policies", {}, session.token)
      .then((rows) => {
        setPolicies(rows);
        setExpandedTypes(new Set(rows.map((policy) => policy.policy_type).filter(Boolean)));
        const tracedPolicyId = Number(sessionStorage.getItem("complianceTracePolicyId"));
        sessionStorage.removeItem("complianceTracePolicyId");
        setSelectedPolicyId((current) => (
          tracedPolicyId && rows.some((policy) => policy.policy_id === tracedPolicyId)
            ? tracedPolicyId
            : current || rows[0]?.policy_id || null
        ));
      })
      .catch((requestError) => setError(requestError.message))
      .finally(() => setLoading(false));
  }, [session.token]);

  useEffect(() => {
    if (!selectedPolicyId) return;
    setPolicyLinksLoading(true);
    setPolicyLinksError("");
    setRelatedPolicies([]);
    setSelectedPolicyControls([]);
    setPolicyControlIndex(0);
    Promise.all([
      apiRequest(`/api/policies/${selectedPolicyId}/relationships`, {}, session.token),
      apiRequest(`/api/policies/${selectedPolicyId}/controls`, {}, session.token),
    ])
      .then(([relationships, controls]) => {
        setRelatedPolicies(relationships);
        setSelectedPolicyControls(controls);
      })
      .catch((requestError) => setPolicyLinksError(requestError.message))
      .finally(() => setPolicyLinksLoading(false));
  }, [selectedPolicyId, session.token]);

  const selected = policies.find((policy) => policy.policy_id === selectedPolicyId) || policies[0];
  const selectedMappedControl = selectedPolicyControls[policyControlIndex];
  const additionalPolicyTypes = [...new Set(
    policies.map((policy) => policy.policy_type).filter(Boolean),
  )]
    .filter((name) => !POLICY_TYPE_ORDER.includes(name))
    .sort((left, right) => left.localeCompare(right));
  const typeHierarchy = [...POLICY_TYPE_ORDER, ...additionalPolicyTypes].map((name) => ({
    name,
    policies: policies.filter((policy) => policy.policy_type === name),
  }));
  const toggleType = (typeName) => {
    setExpandedTypes((current) => {
      const next = new Set(current);
      if (next.has(typeName)) next.delete(typeName);
      else next.add(typeName);
      return next;
    });
  };
  return (
    <>
      <Heading page="policy" />
      <div className="policy-view-toggle" role="tablist" aria-label="Policy Intelligence views">
        <button
          type="button"
          role="tab"
          aria-selected={explorerTab === "library"}
          className={explorerTab === "library" ? "active" : ""}
          onClick={() => { sessionStorage.removeItem("policyExplorerTab"); setExplorerTab("library"); }}
        >
          Policy Library
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={explorerTab === "controls"}
          className={explorerTab === "controls" ? "active" : ""}
          onClick={() => { sessionStorage.setItem("policyExplorerTab", "controls"); setExplorerTab("controls"); }}
        >
          Controls
        </button>
      </div>
      <div className={`policy-layout ${explorerTab === "controls" ? "controls-view" : ""}`}>
        {explorerTab === "library" ? (
          <>
            <Card className="policy-library-card" title="Policy Library" action={<BookOpen size={15} />}>
              <div className="tree policy-library-list">
                <strong>Policy Types - {typeHierarchy.length} types - {policies.length} documents</strong>
                {typeHierarchy.map((type, typeIndex) => {
                  const expanded = expandedTypes.has(type.name);
                  return (
                    <div className="policy-tree-category" key={type.name}>
                      <button
                        type="button"
                        className="policy-tree-toggle"
                        aria-expanded={expanded}
                        onClick={() => toggleType(type.name)}
                      >
                        <ChevronRight className={expanded ? "expanded" : ""} size={14} />
                        <span>{typeIndex + 1}) {type.name}</span>
                        <small>{type.policies.length}</small>
                      </button>
                      {expanded && (
                        <div className="policy-tree-parents policy-type-documents">
                          {type.policies.map((policy) => (
                            <button
                              type="button"
                              className={selected?.policy_id === policy.policy_id ? "active policy-tree-document" : "policy-tree-document"}
                              onClick={() => setSelectedPolicyId(policy.policy_id)}
                              key={policy.policy_id}
                            >
                              {policy.library_policy_id} {policyDisplayName(policy.title)}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
                {!loading && policies.length === 0 && (
                  <p>No policies yet. Generate them from Data Manufacturing.</p>
                )}
              </div>
            </Card>
            <Card
              className="policy-summary-card"
              title={selected?.parent_policy || "Policy summary"}
              action={selected && <Badge tone="effective">{selected.status}</Badge>}
            >
              <div className="policy-summary-scroll">
                {loading && <div className="policy-empty">Loading policy summaries...</div>}
                {error && <div className="data-message error">{error}</div>}
                {!loading && !error && !selected && (
                  <div className="policy-empty">
                    <BookOpen size={28} />
                    <h3>Policy Library is empty</h3>
                    <p>Use Generate Policy PDFs in Data Manufacturing to create and summarize 20 policies.</p>
                  </div>
                )}
                {selected && (
                  <div className="document policy-document-summary">
                    <small>MISTRAL-GENERATED POLICY SUMMARY</small>
                    <h2>{selected.library_policy_id} {policyDisplayName(selected.title)}</h2>
                    <div className="policy-summary-text">{selected.summary}</div>
                  </div>
                )}
                {selected && (
                  <dl className="policy-metadata-list policy-summary-metadata">
                    <div><dt>Policy ID</dt><dd>{selected.library_policy_id}</dd></div>
                    <div><dt>Policy code</dt><dd>{selected.policy_code}</dd></div>
                    <div><dt>Policy type</dt><dd>{selected.policy_type}</dd></div>
                    <div><dt>Version</dt><dd>{selected.version}</dd></div>
                    <div><dt>Effective</dt><dd>{selected.effective_date}</dd></div>
                    <div><dt>File</dt><dd>{selected.file_name}</dd></div>
                  </dl>
                )}
              </div>
            </Card>
            <Card className="related-policies-card" title="Related Policies" action={<span className="policy-control-count">{relatedPolicies.length}</span>}>
              {policyLinksLoading && <div className="data-message">Loading related policies...</div>}
              {policyLinksError && <div className="data-message error">{policyLinksError}</div>}
              {!policyLinksLoading && !policyLinksError && relatedPolicies.length === 0 && (
                <div className="data-message">No related policies are mapped.</div>
              )}
              <div className="related-policy-list">
                {relatedPolicies.map((related) => (
                  <button
                    type="button"
                    key={related.relationship_id}
                    onClick={() => setSelectedPolicyId(related.related_policy_id)}
                  >
                    <span className="related-policy-heading">
                      <strong>{related.related_library_policy_id}</strong>
                      <span>{policyDisplayName(related.related_policy_name) || "Policy details unavailable"}</span>
                    </span>
                    <small>{related.relationship_strength}% match</small>
                  </button>
                ))}
              </div>
            </Card>
            <Card className="mapped-controls-card" title="Mapped Controls" action={<span className="policy-control-count">{selectedPolicyControls.length}</span>}>
              {policyLinksLoading && <div className="data-message">Loading mapped controls...</div>}
              {!policyLinksLoading && !policyLinksError && !selectedMappedControl && (
                <div className="data-message">No controls are mapped to this policy.</div>
              )}
              {selectedMappedControl && (
                <div className="policy-control-content">
                  <div className="policy-control-item">
                    <div className="policy-control-summary">
                      <div>
                        <h3>{selectedMappedControl.control_name}</h3>
                        <p>{selectedMappedControl.control_id} - {selectedMappedControl.control_owner}</p>
                      </div>
                      <Badge>{selectedMappedControl.status}</Badge>
                    </div>
                    <p className="policy-control-description">{selectedMappedControl.control_description}</p>
                    <dl className="policy-control-review">
                      <div><dt>Type:</dt><dd>{selectedMappedControl.control_type}</dd></div>
                      <div><dt>Frequency:</dt><dd>{selectedMappedControl.frequency}</dd></div>
                      <div><dt>Automation:</dt><dd>{selectedMappedControl.automation}</dd></div>
                      <div><dt>Effectiveness:</dt><dd>{selectedMappedControl.effectiveness}%</dd></div>
                    </dl>
                  </div>
                  <div className="policy-control-navigation">
                    <button
                      type="button"
                      disabled={policyControlIndex === 0}
                      onClick={() => setPolicyControlIndex((index) => Math.max(0, index - 1))}
                    >
                      Previous
                    </button>
                    <span>{policyControlIndex + 1} of {selectedPolicyControls.length}</span>
                    <button
                      type="button"
                      disabled={policyControlIndex >= selectedPolicyControls.length - 1}
                      onClick={() => setPolicyControlIndex((index) => Math.min(selectedPolicyControls.length - 1, index + 1))}
                    >
                      Next
                    </button>
                  </div>
                </div>
              )}
            </Card>
            <PolicyCopilot
              session={session}
              onSelectPolicy={setSelectedPolicyId}
            />
          </>
        ) : (
          <ControlsWorkspace session={session} />
        )}
      </div>
    </>
  );
}

function PolicyCopilot({ session, onSelectPolicy }) {
  const storagePrefix = `policyCopilotLibrary:${session.user.user_id}`;
  const [messages, setMessages] = useState(() => {
    try {
      return JSON.parse(sessionStorage.getItem(`${storagePrefix}:messages`)) || [];
    } catch {
      return [];
    }
  });
  const [conversationId, setConversationId] = useState(
    () => sessionStorage.getItem(`${storagePrefix}:conversation`) || null,
  );
  const [question, setQuestion] = useState("");
  const [sending, setSending] = useState(false);
  const [chatError, setChatError] = useState("");

  useEffect(() => {
    sessionStorage.setItem(`${storagePrefix}:messages`, JSON.stringify(messages));
    if (conversationId) sessionStorage.setItem(`${storagePrefix}:conversation`, conversationId);
    else sessionStorage.removeItem(`${storagePrefix}:conversation`);
  }, [messages, conversationId, storagePrefix]);

  const resetChat = () => {
    setMessages([]);
    setConversationId(null);
    setQuestion("");
    setChatError("");
  };
  const sendQuestion = async (event, suggestedQuestion = null) => {
    event?.preventDefault();
    const prompt = (suggestedQuestion || question).trim();
    if (!prompt || sending) return;
    setQuestion("");
    setChatError("");
    setMessages((current) => [...current, { role: "user", content: prompt }]);
    setSending(true);
    try {
      const response = await apiRequest(
        "/api/policy-copilot/chat",
        {
          method: "POST",
          body: JSON.stringify({
            question: prompt,
            conversation_id: conversationId,
          }),
        },
        session.token,
      );
      setConversationId(response.conversation_id);
      setMessages((current) => [...current, {
        role: "assistant",
        content: response.answer,
        citations: response.citations || [],
      }]);
    } catch (requestError) {
      setChatError(requestError.message);
    } finally {
      setSending(false);
    }
  };

  return (
    <Card
      className="copilot"
      title="Policy Copilot"
      action={<button type="button" className="text-btn" onClick={resetChat}>New chat</button>}
    >
      <div className="chat" aria-live="polite">
        {messages.length === 0 && (
          <div className="chat-ai">
            <Sparkles size={18} />
            <p>Ask about any policy, limit, approval, exception, or requirement. Answers are retrieved from the Mistral Policy Library and include citations.</p>
          </div>
        )}
        {messages.map((message, index) => message.role === "user" ? (
          <div className="chat-user" key={`${index}-${message.content}`}>{message.content}</div>
        ) : (
          <div className="chat-ai" key={`${index}-${message.content.slice(0, 20)}`}>
            <Sparkles size={18} />
            <div className="chat-answer">{message.content}</div>
            {message.citations?.length > 0 && (
              <div className="citations">
                <small>CITATIONS</small>
                {message.citations.map((citation, citationIndex) => (
                  <button
                    type="button"
                    key={`${citation.policy_id}-${citation.section}-${citationIndex}`}
                    onClick={() => onSelectPolicy(citation.policy_database_id)}
                  >
                    <strong>{citation.policy_id} - {policyDisplayName(citation.policy_name)}</strong>
                    <span>{citation.section}</span>
                    <small>{citation.evidence}</small>
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
        {sending && <div className="chat-ai copilot-thinking"><Sparkles size={18} /><p>Searching the policy library...</p></div>}
      </div>
      {chatError && <div className="data-message error">{chatError}</div>}
      <form className="chat-input" onSubmit={sendQuestion}>
        <input
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Ask a policy question..."
          disabled={sending}
          aria-label="Ask Policy Copilot"
        />
        <button type="submit" disabled={sending || !question.trim()} aria-label="Send question"><Send size={16} /></button>
      </form>
    </Card>
  );
}
