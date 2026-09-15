const endpoint = process.env.CDP_ENDPOINT || "http://127.0.0.1:9223";
const pages = [
  "dashboard", "requests", "manufacturing", "policy", "compliance",
  "exceptions", "simulator", "portfolio", "profile",
];

const targets = await fetch(`${endpoint}/json`).then((response) => response.json());
const target = targets.find((item) => item.type === "page");
if (!target) throw new Error("No browser page target was found");

const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  socket.addEventListener("open", resolve, { once: true });
  socket.addEventListener("error", reject, { once: true });
});

let nextId = 1;
const pending = new Map();
const exceptions = [];
socket.addEventListener("message", ({ data }) => {
  const message = JSON.parse(data);
  if (message.id && pending.has(message.id)) {
    const { resolve, reject } = pending.get(message.id);
    pending.delete(message.id);
    return message.error ? reject(new Error(message.error.message)) : resolve(message.result);
  }
  if (message.method === "Runtime.exceptionThrown") {
    const details = message.params.exceptionDetails;
    exceptions.push(details.exception?.description || details.text);
  }
});

function command(method, params = {}) {
  const id = nextId++;
  socket.send(JSON.stringify({ id, method, params }));
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
}

const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
const evaluate = (expression) => command("Runtime.evaluate", {
  expression,
  awaitPromise: true,
  returnByValue: true,
});
const assertNoException = (label, startingAt) => {
  const found = exceptions.slice(startingAt);
  if (found.length) throw new Error(`${label}: ${found.join("; ")}`);
};

await command("Runtime.enable");
await command("Page.enable");
await command("Page.addScriptToEvaluateOnNewDocument", {
  source: `
    window.fetch = async (input) => {
      const url = String(input);
      let status = 200;
      let body = [];
      if (url.includes("/api/summary")) body = {};
      else if (url.includes("/api/auth/security-questions")) body = { questions: [] };
      else if (url.includes("/api/auth/recovery/")) body = { questions: [] };
      else if (url.includes("/api/compliance-review/") && url.includes("/latest")) {
        body = {
          overall_score: 82, compliance_status: "Compliant with Exceptions",
          executive_summary: "One warning requires review.",
          credit_request: {
            credit_request_number: "CR-10001", borrower_name: "Audit Manufacturing",
            industry: "Manufacturing", facility: "Term Loan", rating: "BBB",
            requested_amount: 10000000, exposure: 20000000, status: "In Review"
          },
          counts: { PASS: 1, WARNING: 1, BREACH: 0 },
          findings: [{
            policy_type: "Leverage", policy_clause: "CP-4.2", actual: "3.5x",
            threshold: "4.0x", variance: "Within limit", severity: "PASS",
            rationale: "The request is within the stated limit.",
            evidence: "Retrieved policy evidence.", policy_id: 1, library_policy_id: "1.1"
          }],
          heatmap: [{ policy_type: "Leverage", severity: "PASS" }],
          recommendations: ["Continue monitoring."]
        };
      }
      else if (url.includes("/api/auth/password-policy") || url.includes("/api/admin/password-policy")) {
        body = { minimum_length: 12, maximum_length: 128, minimum_uppercase: 1,
          minimum_lowercase: 1, minimum_digits: 1, minimum_special: 1 };
      } else if (url.includes("/api/admin/users")) body = { users: [] };
      else if (url.includes("/api/admin/logs")) body = { logs: [], page: 1, pages: 1, total: 0 };
      else if (url.includes("/api/data-manufacturing/policy-pdfs/status")) {
        body = { status: "idle", total_documents: 20, completed_documents: 0 };
      } else if (url.includes("/api/policies/") && url.includes("/relationships")) {
        body = [];
      } else if (url.includes("/api/policies/") && url.includes("/controls")) {
        body = [];
      } else if (url.endsWith("/api/policies")) {
        body = [{
          policy_id: 1, library_policy_id: "1.1", policy_code: "CP-4.2",
          title: "1.1 Wholesale Credit Policy", version: "1.0",
          policy_category: "Credit Policy", parent_policy: "Wholesale",
          clause_number: "4.2", effective_date: "2026-01-01", status: "Active",
          summary: "Audit policy summary.", page_count: 10, file_name: "policy.pdf",
          document_format: "PDF", source_type: "manufactured", policy_type: "Leverage"
        }];
      } else if (url.endsWith("/api/controls")) {
        body = [];
      } else if (url.includes("/api/requests")) {
        body = [{
          credit_request_number: "CR-10001", borrower_id: 1,
          borrower_name: "Audit Manufacturing", industry: "Manufacturing",
          exposure: 20000000, facility: "Term Loan", rating: "BBB",
          requested_amount: 10000000, status: "In Review", compliance_score: 82
        }];
      } else if (url.includes("/api/compliance-review/")) {
        status = 404;
        body = { detail: "No saved review" };
      }
      return new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
      });
    };
  `,
});
await command("Page.navigate", { url: "http://localhost:5173" });
await wait(1500);

let exceptionIndex = exceptions.length;
const registration = await evaluate(`(() => {
  const button = [...document.querySelectorAll("button")]
    .find((item) => item.textContent.includes("Create new user"));
  if (!button) return { clicked: false, text: document.body.innerText };
  button.click();
  return { clicked: true };
})()`);
await wait(300);
assertNoException("Create-new-user screen", exceptionIndex);
const registrationText = await evaluate("document.getElementById('root').innerText");
if (!String(registrationText.result.value || "").includes("Create an account")) {
  throw new Error(`Create-new-user screen did not render: click=${JSON.stringify(registration.result.value)}, text=${String(registrationText.result.value || "").slice(0, 200)}`);
}
console.log("Create-new-user screen: passed");

await evaluate(`sessionStorage.setItem("cpi-session", JSON.stringify({
  token: "runtime-audit",
  user: { user_id: "admin", role: "admin", status: "active", locked: false },
  expires_at: new Date(Date.now() + 300000).toISOString()
}))`);
exceptionIndex = exceptions.length;
await command("Page.reload", { ignoreCache: true });
await wait(700);
assertNoException("admin", exceptionIndex);
const adminContent = await evaluate("document.getElementById('root').innerText");
if (!String(adminContent.result.value || "").includes("Admin Dashboard")) {
  throw new Error("admin: administration screen did not render");
}
console.log("admin: passed");

exceptionIndex = exceptions.length;
await evaluate(`sessionStorage.setItem("cpi-session", JSON.stringify({
  token: "runtime-audit",
  user: { user_id: "runtime-audit", role: "credit_analyst", status: "active", locked: false },
  expires_at: new Date(Date.now() + 300000).toISOString()
}))`);
await command("Page.reload", { ignoreCache: true });
await wait(1200);
assertNoException("authenticated shell", exceptionIndex);

for (const page of pages) {
  exceptionIndex = exceptions.length;
  await command("Page.navigate", { url: `http://localhost:5173/#${page}` });
  await wait(1000);
  assertNoException(page, exceptionIndex);
  const content = await evaluate("document.getElementById('root').innerText");
  if (!String(content.result.value || "").trim()) throw new Error(`${page}: rendered an empty root`);
  console.log(`${page}: passed`);
}

socket.close();
