export const POLICY_TYPE_ORDER = [
  "Leverage", "Collateral", "Pricing", "Tenor", "Covenant", "Sector",
  "Delegation", "Rating", "Country", "Industry", "LTV", "DSCR",
  "Concentration", "Currency", "Duration", "Liquidity",
];
export const policyDisplayName = (title = "") => title.replace(
  /^(?:(?:[A-Z]\.)?\d+(?:\.\d+)?|POL-\d+)\s+/,
  "",
);
export const META = {
  dashboard: [
    "Executive Dashboard",
    "Consolidated view of credit policy compliance & exceptions.",
  ],
  requests: [
    "Credit Request Workbench",
    "Review incoming credit requests with AI-assisted insights.",
  ],
  manufacturing: [
    "Data Manufacturing",
    "Generate realistic test data for the credit workflow.",
  ],
  policy: [
    "Policy Intelligence",
    "Enterprise policy knowledge center with AI copilot.",
  ],
  compliance: [
    "Compliance Review",
    "Run an AI-assisted policy review for any credit request.",
  ],
  exceptions: [
    "Exception Management",
    "Central registry of policy exceptions and remediation workflow.",
  ],
  simulator: [
    "Decision Simulator",
    "Interactive credit scenario analysis with real-time risk outputs.",
  ],
  portfolio: [
    "Portfolio Analytics",
    "Enterprise-wide policy breach, exception, and risk analytics.",
  ],
  observability: [
    "Observability",
    "Monitor OpenTelemetry traces, latency, and token usage for every AI feature.",
  ],
  profile: [
    "My Profile",
    "View your account details and securely update your password.",
  ],
};
