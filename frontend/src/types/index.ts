export type WebsiteStatus =
  | 'ONLINE'
  | 'OFFLINE'
  | 'HTTP_ERROR'
  | 'TIMEOUT'
  | 'SSL_ERROR'
  | 'DNS_ERROR'
  | 'BROWSER_ERROR'
  | 'BLOCKED';

export interface DNSRecord {
  id?: number;
  scan_result_id?: number;
  domain: string;
  record_type: string;
  record_value: string;
  ttl: number | null;
  lookup_status: string;
  error_message: string | null;
  lookup_time_ms: number | null;
}

export interface SSLDetail {
  id?: number;
  scan_result_id?: number;
  domain: string;
  issuer: string | null;
  subject: string | null;
  valid_from: string | null;
  expiry_date: string | null;
  remaining_days: number | null;
  hostname_match: boolean;
  https_available: boolean;
  verification_status: string;
  error_message: string | null;
}

export interface ScanResult {
  id: number;
  scan_id: string;
  original_url: string;
  final_url: string | null;
  domain: string;
  status: WebsiteStatus;
  http_status_code: number | null;
  response_time_ms: number | null;
  server_info: string | null;
  website_title: string | null;
  screenshot_path: string | null;
  error_message: string | null;
  created_at: string;
  dns_records?: DNSRecord[];
  ssl_details?: SSLDetail | null;
}

export interface Scan {
  id: string;
  created_at: string;
  status: 'pending' | 'running' | 'completed' | 'cancelled' | 'failed';
  total_urls: number;
  completed_urls: number;
  progress_pct?: number;
  filename?: string | null;
  results?: ScanResult[];
}

export interface ScanHistoryItem {
  scan_id: string;
  created_at: string;
  status: string;
  total_urls: number;
  completed_urls: number;
  online_count: number;
  offline_count: number;
  dns_errors: number;
  ssl_issues: number;
  filename?: string | null;
}

export interface DashboardStats {
  total_scanned: number;
  online_count: number;
  offline_count: number;
  dns_errors: number;
  ssl_issues: number;
  avg_response_time: number;
  recent_scans: ScanHistoryItem[];
}

export type ThemeMode = 'light' | 'dark';
