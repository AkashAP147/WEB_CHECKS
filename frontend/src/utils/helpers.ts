export function getStatusColor(status: string): string {
  switch (status) {
    case 'ONLINE':
      return 'text-emerald-500';
    case 'OFFLINE':
      return 'text-rose-500';
    case 'HTTP_ERROR':
      return 'text-amber-500';
    case 'TIMEOUT':
      return 'text-orange-500';
    case 'SSL_ERROR':
      return 'text-rose-400';
    case 'DNS_ERROR':
      return 'text-amber-400';
    case 'BROWSER_ERROR':
      return 'text-purple-500';
    case 'BLOCKED':
      return 'text-surface-500';
    default:
      return 'text-surface-500';
  }
}

export function getStatusBadgeClass(status: string): string {
  switch (status) {
    case 'ONLINE':
      return 'badge-online';
    case 'OFFLINE':
      return 'badge-offline';
    case 'HTTP_ERROR':
    case 'TIMEOUT':
    case 'SSL_ERROR':
    case 'DNS_ERROR':
    case 'BROWSER_ERROR':
      return 'badge-warning';
    case 'BLOCKED':
      return 'badge-neutral';
    default:
      return 'badge-neutral';
  }
}

export function getScanStatusBadgeClass(status: string): string {
  switch (status?.toLowerCase()) {
    case 'completed':
      return 'badge-online';
    case 'running':
    case 'pending':
      return 'badge-info';
    case 'cancelled':
      return 'badge-warning';
    case 'failed':
      return 'badge-offline';
    default:
      return 'badge-neutral';
  }
}

export function formatResponseTime(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '—';
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '—';
  try {
    let s = String(dateStr).trim();
    // Normalize SQLite "YYYY-MM-DD HH:MM:SS" -> "YYYY-MM-DDTHH:MM:SS"
    if (s.includes(' ') && !s.includes('T')) {
      s = s.replace(' ', 'T');
    }
    // If no timezone offset exists, explicitly tag as UTC so the browser converts to local time
    if (!s.endsWith('Z') && !s.includes('+') && !s.slice(-6).match(/[+-]\d\d:\d\d/)) {
      s += 'Z';
    }
    const date = new Date(s);
    if (isNaN(date.getTime())) {
      const fallback = new Date(dateStr);
      if (isNaN(fallback.getTime())) return String(dateStr);
      return fallback.toLocaleString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: true,
      });
    }
    return date.toLocaleString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: true,
    });
  } catch {
    return String(dateStr);
  }
}

export function formatDomain(url: string): string {
  try {
    const u = new URL(url.startsWith('http') ? url : `https://${url}`);
    return u.hostname;
  } catch {
    return url;
  }
}

export function getScreenshotUrl(path: string | null | undefined): string {
  if (!path) return '';
  const clean = path.replace(/^\/+/, '');
  return `/${clean}`;
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function cn(...classes: (string | boolean | undefined | null)[]): string {
  return classes.filter(Boolean).join(' ');
}
