export function filterExceptions(exceptions, status = "All", query = "") {
  const search = String(query).trim().replace(/\s+/g, " ").toLocaleLowerCase();
  return exceptions.filter(item => {
    if (status !== "All" && item.status !== status) return false;
    const fields = [item.id, item.credit_request_number, item.type, item.clause,
      item.severity, item.owner, item.account_user_id, item.due, item.status,
      item.exposure, item.exposure == null ? null : `$${Math.round(Number(item.exposure) / 1000000)}M`,
      item.credit_request_number && item.account_user_id
        ? `${item.credit_request_number}@${item.account_user_id}` : null];
    return !search || fields.some(value => value != null && String(value).replace(/\s+/g, " ").toLocaleLowerCase().includes(search));
  });
}
