export function prepareAccountRequest(path, options = {}) {
  // Keep identical request numbers from different manager accounts distinct.
  let account;
  const unqualify = value => {
    if (typeof value !== 'string' || !/^CR-[0-9]+@/.test(value)) return value;
    const split = value.indexOf('@');
    const owner = value.slice(split + 1);
    if (account && account !== owner) throw new Error('Select requests from one account at a time.');
    account = owner;
    return value.slice(0, split);
  };
  const queryAt=path.indexOf('?');
  const pathname=queryAt<0?path:path.slice(0,queryAt);
  const originalQuery=queryAt<0?'':path.slice(queryAt+1);
  path = pathname.split('/').map(part => {
    const decoded = decodeURIComponent(part);
    const value = unqualify(decoded);
    return value === decoded ? part : encodeURIComponent(value);
  }).join('/');
  if(queryAt>=0){
    let changed=false;
    const entries=[...new URLSearchParams(originalQuery)].map(([key,value])=>{
      const result=['credit_request_number','request_id'].includes(key)?unqualify(value):value;
      if(result!==value)changed=true;
      return [key,result];
    });
    path+='?'+(changed?new URLSearchParams(entries).toString():originalQuery);
  }
  if (typeof options.body === 'string') {
    const payload = JSON.parse(options.body);
    if (payload.credit_request_number) payload.credit_request_number = unqualify(payload.credit_request_number);
    if (payload.credit_request_numbers) payload.credit_request_numbers = payload.credit_request_numbers.map(unqualify);
    options = { ...options, body: JSON.stringify(payload) };
  }
  return { path, options, account };
}
