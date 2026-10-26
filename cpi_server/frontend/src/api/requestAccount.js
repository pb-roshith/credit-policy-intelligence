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
  path = path.split('/').map(part => {
    const decoded = decodeURIComponent(part);
    const value = unqualify(decoded);
    return value === decoded ? part : encodeURIComponent(value);
  }).join('/');
  if (typeof options.body === 'string') {
    const payload = JSON.parse(options.body);
    if (payload.credit_request_number) payload.credit_request_number = unqualify(payload.credit_request_number);
    if (payload.credit_request_numbers) payload.credit_request_numbers = payload.credit_request_numbers.map(unqualify);
    options = { ...options, body: JSON.stringify(payload) };
  }
  return { path, options, account };
}
