import type { ReactNode } from 'react';
export type SharedDealInput = {
  customer: string; customer_type: string; industry: string; segment: string;
  geography: string; kyc: string; facility: string; currency: string; amount: number;
  tenure: number; pricing: string; repayment: string; collateral: boolean; due: string;
  rating: string; collateral_coverage: number; total_required_documents: number;
  uploaded_required_documents: number; creation_request_id: string;
};
export default function NewDealForm(props: {
  createDeal: (data: SharedDealInput) => Promise<any>;
  onCreated: (deal: any) => void; onCancel: () => void;
  loadCompanies?: () => Promise<Array<{ name: string; document_count?: number; library_access_error?: string | null }>>;
  getCompanyDetails?: (name: string) => Promise<{ industry?: string; geography?: string; segment?: string; kyc_status?: string }>;
}): ReactNode;
export function SharedDealCard(props: { deal: any }): ReactNode;
