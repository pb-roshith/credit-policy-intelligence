export function textInputError(label: string, value: string, maxLength: number): string | null {
  if (value.length > maxLength) return `${label} cannot exceed ${maxLength} characters.`;
  if (/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/.test(value)) {
    return `${label} contains a prohibited control character.`;
  }
  if (/<\s*(?:\/?\s*[A-Za-z]|[!?])/.test(value)) {
    return `${label}: use plain text or Markdown; HTML markup is not supported.`;
  }
  if (/\]\(\s*(?:javascript|vbscript|data)\s*:/i.test(value)) {
    return `${label} contains an unsupported executable or data link.`;
  }
  return null;
}

export function sourceUrlError(value: string): string | null {
  if (value.length > 2048) return "A URL cannot exceed 2048 characters.";
  if (/[\s\u0000-\u001f<>"'\\]/.test(value)) return "URLs must not contain whitespace, markup, or control characters.";
  try {
    const url = new URL(value);
    if (!["http:", "https:"].includes(url.protocol) || !url.hostname) return "Enter a valid HTTP/HTTPS URL.";
    if (url.username || url.password) return "URLs must not contain credentials.";
  } catch {
    return "Enter a valid HTTP/HTTPS URL.";
  }
  return null;
}
