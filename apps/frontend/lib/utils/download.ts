export function downloadBlobAsFile(blob: Blob, filename: string): void {
  if (typeof document === 'undefined') return;
  if (!document.body) return;
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.style.display = 'none';
  document.body.appendChild(link);
  link.click();
  setTimeout(() => {
    URL.revokeObjectURL(url);
    link.remove();
  }, 1000);
}

export function openUrlInNewTab(url: string): boolean {
  if (typeof window === 'undefined') return false;
  const newWindow = window.open(url, '_blank', 'noopener,noreferrer');
  if (newWindow) {
    newWindow.opener = null;
    return true;
  }
  return false;
}

/**
 * Prints a same-origin page (e.g. a /print/* route, with ?autoprint=true) via a
 * hidden iframe. Never opens a new tab/window, so browser popup blockers never
 * trigger. The page itself calls window.print() once loaded (see PrintAutoTrigger).
 */
export function printViaIframe(url: string): void {
  if (typeof document === 'undefined') return;

  const iframe = document.createElement('iframe');
  iframe.style.position = 'fixed';
  iframe.style.right = '0';
  iframe.style.bottom = '0';
  iframe.style.width = '0';
  iframe.style.height = '0';
  iframe.style.border = '0';
  iframe.setAttribute('aria-hidden', 'true');

  let cleaned = false;
  const cleanup = () => {
    if (cleaned) return;
    cleaned = true;
    iframe.remove();
  };

  iframe.onload = () => {
    iframe.contentWindow?.addEventListener('afterprint', cleanup);
  };
  // Fallback cleanup in case afterprint never fires (e.g. dialog dismissed via Esc in some browsers).
  setTimeout(cleanup, 60_000);

  document.body.appendChild(iframe);
  iframe.src = url;
}

/**
 * Sanitize a resume title for use as a filename
 * - Removes/replaces invalid filename characters
 * - Truncates to reasonable length
 * - Provides fallback if title is empty
 */
export function sanitizeFilename(
  title: string | null | undefined,
  fallbackId: string,
  type: 'resume' | 'cover-letter' = 'resume'
): string {
  // Use fallback if no title
  if (!title?.trim()) {
    return type === 'resume' ? `resume_${fallbackId}.pdf` : `cover_letter_${fallbackId}.pdf`;
  }

  // Normalize Unicode to NFC form to ensure consistent representation
  // This ensures "Currículum" (NFD: i + combining accent) and "Currículum" (NFC: í as single char) produce the same filename
  let sanitized = title.normalize('NFC').trim();

  // Remove or replace invalid characters: / \ : * ? " < > |
  sanitized = sanitized
    .replace(/[/\\:*?"<>|]/g, '-') // Replace invalid chars with dash
    .replace(/\s+/g, ' ') // Normalize whitespace
    .trim();

  // Truncate to 100 characters using Array.from() to handle multi-byte characters correctly
  // This prevents splitting multi-byte UTF-8 characters (Chinese, Japanese, emoji) mid-sequence
  const chars = Array.from(sanitized); // Handles grapheme clusters properly
  if (chars.length > 100) {
    sanitized = chars.slice(0, 100).join('').trim();
  }

  // Add .pdf extension
  return `${sanitized}.pdf`;
}
