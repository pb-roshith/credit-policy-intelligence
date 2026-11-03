import { API, apiRequest } from '../../../api/client';
export const api=(path,options={})=>apiRequest('/api/risk-knowledge'+path,options);
export const post=(path,body)=>api(path,{method:'POST',...(body?{body:JSON.stringify(body)}:{})});
export const sourceUrl=id=>`${API}/api/risk-knowledge/documents/${encodeURIComponent(id)}/download`;
export const exportUrl=kind=>`${API}/api/risk-knowledge/export/${kind}`;
