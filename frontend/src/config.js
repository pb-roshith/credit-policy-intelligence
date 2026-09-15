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
  profile: [
    "My Profile",
    "View your account details and securely update your password.",
  ],
};
export const EXCEPTIONS = [
  [
    "EX-8821",
    "Leverage",
    "CP-4.2",
    "High",
    "$85M",
    "S. Chen",
    "2026-08-05",
    "Pending Approval",
  ],
  [
    "EX-8822",
    "Collateral",
    "COL-2.1",
    "High",
    "$62M",
    "M. Ruiz",
    "2026-07-28",
    "Active",
  ],
  [
    "EX-8823",
    "Concentration",
    "RAF-3.5",
    "Medium",
    "$140M",
    "A. Patel",
    "2026-08-12",
    "Remediation",
  ],
  [
    "EX-8824",
    "Covenant",
    "CP-6.4",
    "Low",
    "$18M",
    "J. Okafor",
    "2026-07-22",
    "Active",
  ],
  [
    "EX-8825",
    "Delegation",
    "DEL-3.1",
    "High",
    "$95M",
    "R. Kim",
    "2026-07-25",
    "Pending Approval",
  ],
  [
    "EX-8826",
    "Pricing",
    "PRC-1.1",
    "Low",
    "$12M",
    "L. Novak",
    "2026-08-30",
    "Closed",
  ],
  [
    "EX-8827",
    "Tenor",
    "CP-4.3",
    "Medium",
    "$40M",
    "T. Alvarez",
    "2026-08-18",
    "Remediation",
  ],
  [
    "EX-8828",
    "Leverage",
    "CP-4.2",
    "High",
    "$110M",
    "S. Chen",
    "2026-07-30",
    "Active",
  ],
];

