import { useState, useEffect } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  Download,
  FileText,
  Table as TableIcon,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  Globe,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Server,
  Clock,
  Loader2,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Camera,
  Filter,
  Search,
  FileSpreadsheet,
  Square,
  Activity,
} from 'lucide-react';
import { useScan } from '../hooks/useScan';
import { scanApi } from '../services/api';
import type { ScanResult, DNSRecord, SSLDetail } from '../types';
import {
  getStatusBadgeClass,
  formatResponseTime,
  formatDate,
  getScreenshotUrl,
  downloadBlob,
  cn,
} from '../utils/helpers';

export default function ScanResults() {
  const { scanId } = useParams<{ scanId: string }>();
  const navigate = useNavigate();
  const { scan, results, loading, error, loadScan } = useScan();

  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<'dns' | 'ssl' | 'screenshot'>('dns');
  const [dnsFilter, setDnsFilter] = useState<string>('ALL');
  const [downloadingType, setDownloadingType] = useState<'pdf' | 'excel' | null>(null);

  // Status & Search filtering
  const [statusFilter, setStatusFilter] = useState<'ALL' | 'ONLINE' | 'OFFLINE' | 'ERRORS'>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');

  // Lazy loaded details per scan result
  const [dnsDataMap, setDnsDataMap] = useState<Record<number, DNSRecord[]>>({});
  const [sslDataMap, setSslDataMap] = useState<Record<number, SSLDetail | null>>({});
  const [loadingDetails, setLoadingDetails] = useState<Record<number, boolean>>({});

  useEffect(() => {
    if (scanId) {
      loadScan(scanId);
    }
  }, [scanId, loadScan]);

  const handleToggleExpand = async (result: ScanResult) => {
    if (expandedId === result.id) {
      setExpandedId(null);
      return;
    }

    setExpandedId(result.id);

    // Fetch DNS and SSL details if not already loaded
    if (!dnsDataMap[result.id] || !sslDataMap[result.id]) {
      setLoadingDetails(prev => ({ ...prev, [result.id]: true }));
      try {
        const domain = result.domain || result.original_url;
        const [dnsRes, sslRes] = await Promise.allSettled([
          scanApi.getDNSRecords(domain),
          scanApi.getSSLDetails(domain),
        ]);

        if (dnsRes.status === 'fulfilled') {
          setDnsDataMap(prev => ({ ...prev, [result.id]: dnsRes.value.records || [] }));
        }
        if (sslRes.status === 'fulfilled') {
          setSslDataMap(prev => ({ ...prev, [result.id]: sslRes.value }));
        }
      } catch (err) {
        console.error('Failed to load DNS/SSL details', err);
      } finally {
        setLoadingDetails(prev => ({ ...prev, [result.id]: false }));
      }
    }
  };

  const [pdfBatch, setPdfBatch] = useState<number>(1);
  const [pdfStatusFilter, setPdfStatusFilter] = useState<'ALL' | 'ONLINE' | 'OFFLINE' | 'ERRORS'>('ALL');
  const [pdfMode, setPdfMode] = useState<'summary' | 'issues' | 'visual'>('visual');
  const [isStopping, setIsStopping] = useState<boolean>(false);

  const handleStopScan = async () => {
    if (!scanId) return;
    setIsStopping(true);
    try {
      await scanApi.cancelScan(scanId);
      await loadScan(scanId);
    } catch (err) {
      console.error('Failed to stop scan', err);
    } finally {
      setIsStopping(false);
    }
  };

  const handleDownload = (type: 'pdf' | 'excel' | 'csv', batchNum?: number, statusOverride?: string) => {
    if (!scanId) return;
    let url = `/api/reports/${scanId}/${type}`;
    const params = new URLSearchParams();
    const selectedBatch = batchNum !== undefined ? batchNum : pdfBatch;
    if (type === 'pdf') {
      if (pdfMode === 'visual') {
        params.set('batch', String(selectedBatch > 0 ? selectedBatch : 1));
        params.set('batch_size', '1000');
      } else if (selectedBatch > 0) {
        params.set('batch', String(selectedBatch));
      }
      const s = statusOverride !== undefined ? statusOverride : pdfStatusFilter;
      if (s && s !== 'ALL') params.set('status', s);
      if (pdfMode) params.set('mode', pdfMode);
    }
    const qs = params.toString();
    if (qs) url += `?${qs}`;

    // Direct browser native download: NO Javascript in-memory buffering & NO 120s timeout
    const link = document.createElement('a');
    link.href = url;
    const cleanName = scan?.filename ? scan.filename.replace(/\.[^/.]+$/, "").replace(/[^a-zA-Z0-9_-]/g, "_") : "";
    const baseName = cleanName ? `${cleanName}_${scanId.substring(0, 8)}` : `WebPulse_Audit_${scanId.substring(0, 8)}`;
    link.setAttribute('download', `${baseName}.${type === 'excel' ? 'xlsx' : type}`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const safeResults = Array.isArray(results) ? results : [];
  const total = safeResults.length;
  const online = safeResults.filter(r => r.status === 'ONLINE').length;
  const offline = safeResults.filter(r => r.status === 'OFFLINE').length;
  const errors = total - (online + offline);
  const isScanning = scan?.status === 'running' || scan?.status === 'pending';

  // Filtered targets
  const filteredResults = safeResults.filter(item => {
    if (statusFilter === 'ONLINE' && item.status !== 'ONLINE') return false;
    if (statusFilter === 'OFFLINE' && item.status !== 'OFFLINE') return false;
    if (statusFilter === 'ERRORS' && (item.status === 'ONLINE' || item.status === 'OFFLINE')) return false;

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      const domain = (item.domain || '').toLowerCase();
      const origUrl = (item.original_url || '').toLowerCase();
      const title = (item.website_title || '').toLowerCase();
      const errMsg = (item.error_message || '').toLowerCase();
      const httpCode = String(item.http_status_code || '');
      if (!domain.includes(q) && !origUrl.includes(q) && !title.includes(q) && !errMsg.includes(q) && !httpCode.includes(q)) {
        return false;
      }
    }
    return true;
  });

  return (
    <div className="space-y-8 animate-fade-in pb-16">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/history')}
            className="p-2 rounded-xl border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 text-surface-600 dark:text-surface-300 hover:bg-surface-50 dark:hover:bg-surface-700 transition-colors shadow-xs"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-xl font-bold text-surface-900 dark:text-white">
                Audit Diagnostics
              </h2>
              {scan?.filename && (
                <span className="text-xs px-2.5 py-0.5 rounded-full bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 font-medium flex items-center gap-1 border border-emerald-200 dark:border-emerald-800">
                  <FileSpreadsheet className="w-3.5 h-3.5" />
                  {scan.filename}
                </span>
              )}
              <span className="font-mono text-xs px-2 py-0.5 rounded bg-surface-100 dark:bg-surface-800 text-surface-600 dark:text-surface-300">
                {scanId}
              </span>
            </div>
            <p className="text-xs text-surface-500 dark:text-surface-400 mt-0.5">
              Conducted on {scan ? formatDate(scan.created_at) : '—'}
            </p>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex flex-wrap items-center gap-2">
          {isScanning && (
            <button
              onClick={handleStopScan}
              disabled={isStopping}
              className="btn-danger text-xs py-2 px-3.5 shadow-xs flex items-center gap-1.5"
              title="Stop active scan process immediately"
            >
              {isStopping ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Square className="w-3.5 h-3.5 fill-current" />
              )}
              <span>Stop Scan</span>
            </button>
          )}

          {/* PDF Format Selector */}
          <select
            value={pdfMode}
            onChange={(e) => {
              const m = e.target.value as any;
              setPdfMode(m);
              if (m === 'issues') setPdfStatusFilter('ERRORS');
              if (m === 'visual' && (!pdfBatch || pdfBatch === 0)) setPdfBatch(1);
            }}
            className="text-xs py-2 px-2.5 rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 text-surface-700 dark:text-surface-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 shadow-xs cursor-pointer font-medium"
            title="Choose PDF format"
          >
            <option value="visual">PDF: Visual Report (1,000 Targets per PDF with Images)</option>
            <option value="summary">PDF: Executive Summary (All {total} Targets Table, Fast ~2 MB)</option>
            <option value="issues">PDF: Offline &amp; Issues Only (With Diagnostic Snapshots)</option>
          </select>

          {/* PDF Status Scope Selector (only if not in issues mode) */}
          {pdfMode !== 'issues' && (
            <select
              value={pdfStatusFilter}
              onChange={(e) => setPdfStatusFilter(e.target.value as any)}
              className="text-xs py-2 px-2.5 rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 text-surface-700 dark:text-surface-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 shadow-xs cursor-pointer"
              title="Filter by status"
            >
              <option value="ALL">Status: All Targets</option>
              <option value="ONLINE">Status: Online Only ({online})</option>
              <option value="OFFLINE">Status: Offline Only ({offline})</option>
              <option value="ERRORS">Status: Errors &amp; Warnings ({errors})</option>
            </select>
          )}

          {pdfMode === 'visual' && total > 1000 && (
            <select
              value={pdfBatch}
              onChange={(e) => setPdfBatch(Number(e.target.value))}
              className="text-xs py-2 px-2.5 rounded-lg border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 text-surface-700 dark:text-surface-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 shadow-xs cursor-pointer font-semibold text-indigo-600 dark:text-indigo-400"
              title="Select 1,000-target visual batch to download"
            >
              {Array.from({ length: Math.ceil(total / 1000) }, (_, i) => (
                <option key={i + 1} value={i + 1}>
                  Batch {i + 1} (Targets {i * 1000 + 1} – {Math.min((i + 1) * 1000, total)} with Screenshots)
                </option>
              ))}
            </select>
          )}

          <button
            onClick={() => handleDownload('pdf')}
            disabled={downloadingType !== null || loading}
            className="btn-secondary text-xs py-2 px-3.5 shadow-xs"
            title="Download formatted Audit PDF Report"
          >
            <FileText className="w-3.5 h-3.5 text-rose-500" />
            <span>PDF Report</span>
          </button>

          <button
            onClick={() => handleDownload('excel')}
            disabled={downloadingType !== null || loading}
            className="btn-secondary text-xs py-2 px-3.5 shadow-xs"
            title="Download formatted Excel Workbook"
          >
            <TableIcon className="w-3.5 h-3.5 text-blue-500" />
            <span>Excel (.xlsx)</span>
          </button>

          <button
            onClick={() => handleDownload('csv')}
            disabled={downloadingType !== null || loading}
            className="btn-secondary text-xs py-2 px-3.5 shadow-xs bg-emerald-50/50 dark:bg-emerald-950/20 border-emerald-200 dark:border-emerald-800 hover:bg-emerald-100/50 dark:hover:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300"
            title="Instant CSV export directly importable to Google Sheets & Excel"
          >
            <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
            <span className="font-semibold">Google Sheets (.csv)</span>
          </button>
        </div>
      </div>

      {/* Live Scan In Progress Banner with Stop Button */}
      {isScanning && (
        <div className="card p-4 border-indigo-200 dark:border-indigo-900 bg-gradient-to-r from-indigo-50/80 to-blue-50/80 dark:from-indigo-950/40 dark:to-blue-950/40 flex flex-col md:flex-row md:items-center justify-between gap-4 shadow-sm animate-fade-in">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-indigo-600 text-white animate-pulse shrink-0">
              <Activity className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="badge badge-info text-xs">AUDIT IN PROGRESS</span>
                <span className="text-xs text-surface-600 dark:text-surface-300 font-mono">
                  {scan?.completed_urls || 0} of {scan?.total_urls || 0} Targets Audited ({Math.round(scan?.progress_pct || 0)}%)
                </span>
              </div>
              <p className="text-xs text-surface-500 dark:text-surface-400 mt-0.5">
                Multi-worker engines are verifying HTTP response, DNS lookup, SSL validity, and visual snapshots.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3 w-full md:w-auto shrink-0">
            <div className="flex-1 md:w-48 bg-surface-200 dark:bg-surface-700 h-2.5 rounded-full overflow-hidden">
              <div
                className="bg-indigo-600 h-full rounded-full transition-all duration-300"
                style={{ width: `${Math.min(100, Math.round(scan?.progress_pct || 0))}%` }}
              />
            </div>
            <button
              onClick={handleStopScan}
              disabled={isStopping}
              className="btn-danger text-xs py-1.5 px-3 whitespace-nowrap shadow-xs"
            >
              {isStopping ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Square className="w-3.5 h-3.5 fill-current" />}
              <span>Stop Audit</span>
            </button>
          </div>
        </div>
      )}

      {/* Cancelled Alert Banner */}
      {scan?.status === 'cancelled' && (
        <div className="p-3.5 rounded-xl bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900/50 flex items-center justify-between gap-2 text-amber-800 dark:text-amber-300 text-xs shadow-xs animate-fade-in">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0 text-amber-500" />
            <span>
              <strong>Audit Stopped by User:</strong> Processing was halted. Showing {total} targets evaluated prior to stopping.
            </span>
          </div>
          <span className="font-mono text-[11px] font-semibold opacity-80 uppercase px-2 py-0.5 rounded bg-amber-100 dark:bg-amber-900/40">
            Cancelled
          </span>
        </div>
      )}

      {/* Interactive KPI Overview Strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <button
          onClick={() => setStatusFilter('ALL')}
          className={`card p-4 text-left transition-all cursor-pointer ${
            statusFilter === 'ALL'
              ? 'ring-2 ring-indigo-500 bg-indigo-50/40 dark:bg-indigo-950/20'
              : 'hover:border-surface-300 dark:hover:border-surface-600'
          }`}
        >
          <span className="text-xs text-surface-500 font-medium">Audited Targets</span>
          <div className="text-2xl font-bold text-surface-900 dark:text-white mt-1">
            {total}
          </div>
          <span className="text-[11px] text-surface-400 mt-0.5 block">Click to view all</span>
        </button>

        <button
          onClick={() => setStatusFilter(statusFilter === 'ONLINE' ? 'ALL' : 'ONLINE')}
          className={`card p-4 text-left transition-all cursor-pointer ${
            statusFilter === 'ONLINE'
              ? 'ring-2 ring-emerald-500 bg-emerald-50/40 dark:bg-emerald-950/20'
              : 'hover:border-surface-300 dark:hover:border-surface-600'
          }`}
        >
          <span className="text-xs text-emerald-600 dark:text-emerald-400 font-medium">Online Websites</span>
          <div className="text-2xl font-bold text-emerald-600 dark:text-emerald-400 mt-1">
            {online}
          </div>
          <span className="text-[11px] text-emerald-600/70 dark:text-emerald-400/70 mt-0.5 block">
            Filter online ({Math.round(total ? (online / total) * 100 : 0)}%)
          </span>
        </button>

        <button
          onClick={() => setStatusFilter(statusFilter === 'OFFLINE' ? 'ALL' : 'OFFLINE')}
          className={`card p-4 text-left transition-all cursor-pointer ${
            statusFilter === 'OFFLINE'
              ? 'ring-2 ring-rose-500 bg-rose-50/40 dark:bg-rose-950/20'
              : 'hover:border-surface-300 dark:hover:border-surface-600'
          }`}
        >
          <span className="text-xs text-rose-600 dark:text-rose-400 font-medium">Offline Websites</span>
          <div className="text-2xl font-bold text-rose-600 dark:text-rose-400 mt-1">
            {offline}
          </div>
          <span className="text-[11px] text-rose-600/70 dark:text-rose-400/70 mt-0.5 block">
            Filter offline ({Math.round(total ? (offline / total) * 100 : 0)}%)
          </span>
        </button>

        <button
          onClick={() => setStatusFilter(statusFilter === 'ERRORS' ? 'ALL' : 'ERRORS')}
          className={`card p-4 text-left transition-all cursor-pointer ${
            statusFilter === 'ERRORS'
              ? 'ring-2 ring-amber-500 bg-amber-50/40 dark:bg-amber-950/20'
              : 'hover:border-surface-300 dark:hover:border-surface-600'
          }`}
        >
          <span className="text-xs text-amber-600 dark:text-amber-400 font-medium">Errors &amp; Warnings</span>
          <div className="text-2xl font-bold text-amber-600 dark:text-amber-400 mt-1">
            {errors}
          </div>
          <span className="text-[11px] text-amber-600/70 dark:text-amber-400/70 mt-0.5 block">
            HTTP/DNS/SSL errors
          </span>
        </button>
      </div>

      {/* Filter and Search Bar */}
      <div className="card p-4 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4">
        {/* Status Filter Tabs */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 md:pb-0">
          <button
            onClick={() => setStatusFilter('ALL')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors flex items-center gap-1.5 whitespace-nowrap ${
              statusFilter === 'ALL'
                ? 'bg-indigo-600 text-white shadow-xs'
                : 'bg-surface-100 dark:bg-surface-800 text-surface-600 dark:text-surface-400 hover:bg-surface-200 dark:hover:bg-surface-700'
            }`}
          >
            <span>All Targets</span>
            <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-black/20 dark:bg-white/20">
              {total}
            </span>
          </button>

          <button
            onClick={() => setStatusFilter('ONLINE')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors flex items-center gap-1.5 whitespace-nowrap ${
              statusFilter === 'ONLINE'
                ? 'bg-emerald-600 text-white shadow-xs'
                : 'bg-surface-100 dark:bg-surface-800 text-surface-600 dark:text-surface-400 hover:bg-surface-200 dark:hover:bg-surface-700'
            }`}
          >
            <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
            <span>Online</span>
            <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-black/20 dark:bg-white/20">
              {online}
            </span>
          </button>

          <button
            onClick={() => setStatusFilter('OFFLINE')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors flex items-center gap-1.5 whitespace-nowrap ${
              statusFilter === 'OFFLINE'
                ? 'bg-rose-600 text-white shadow-xs'
                : 'bg-surface-100 dark:bg-surface-800 text-surface-600 dark:text-surface-400 hover:bg-surface-200 dark:hover:bg-surface-700'
            }`}
          >
            <XCircle className="w-3.5 h-3.5 text-rose-400" />
            <span>Offline</span>
            <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-black/20 dark:bg-white/20">
              {offline}
            </span>
          </button>

          <button
            onClick={() => setStatusFilter('ERRORS')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors flex items-center gap-1.5 whitespace-nowrap ${
              statusFilter === 'ERRORS'
                ? 'bg-amber-600 text-white shadow-xs'
                : 'bg-surface-100 dark:bg-surface-800 text-surface-600 dark:text-surface-400 hover:bg-surface-200 dark:hover:bg-surface-700'
            }`}
          >
            <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
            <span>Errors &amp; Warnings</span>
            <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-black/20 dark:bg-white/20">
              {errors}
            </span>
          </button>
        </div>

        {/* Search input */}
        <div className="relative min-w-[240px]">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-surface-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            placeholder="Search domain, title, error..."
            className="w-full pl-9 pr-8 py-1.5 rounded-lg border border-surface-200 dark:border-surface-700 bg-surface-50 dark:bg-surface-900 text-xs text-surface-900 dark:text-white placeholder-surface-400 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-xs text-surface-400 hover:text-surface-600"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* Websites List with Accordion */}
      <div className="card overflow-hidden">
        <div className="p-4 border-b border-surface-200 dark:border-surface-800 bg-surface-50/50 dark:bg-surface-900/50 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <h3 className="text-sm font-bold text-surface-900 dark:text-white">
              Audited Targets &amp; Deep Inspection
            </h3>
            <span className="text-xs text-surface-400">
              Showing {filteredResults.length} of {total} targets • Click any row to view DNS records, SSL cert, and full screenshot
            </span>
          </div>
          {(statusFilter !== 'ALL' || searchQuery) && (
            <button
              onClick={() => { setStatusFilter('ALL'); setSearchQuery(''); }}
              className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline text-left"
            >
              Reset filters
            </button>
          )}
        </div>

        <div className="divide-y divide-surface-200 dark:divide-surface-800">
          {loading ? (
            <div className="p-12 text-center text-surface-400 text-xs">
              <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2 text-indigo-500" />
              Loading audit results...
            </div>
          ) : filteredResults.length === 0 ? (
            <div className="p-12 text-center text-surface-400 text-xs">
              No results found matching current filter ({statusFilter}{searchQuery ? `, query: "${searchQuery}"` : ''}).
            </div>
          ) : (
            filteredResults.map(item => {
              const isExpanded = expandedId === item.id;
              const currentDns = dnsDataMap[item.id] || [];
              const currentSsl = sslDataMap[item.id];
              const isLoadingDetails = loadingDetails[item.id];

              const filteredDns = currentDns.filter(r =>
                dnsFilter === 'ALL' ? true : r.record_type === dnsFilter
              );

              return (
                <div key={item.id} className="transition-colors">
                  {/* Row Summary */}
                  <div
                    onClick={() => handleToggleExpand(item)}
                    className="p-4 flex flex-col md:flex-row md:items-center justify-between gap-4 cursor-pointer hover:bg-surface-50 dark:hover:bg-surface-800/50"
                  >
                    <div className="flex items-center gap-3">
                      <span className={`badge ${getStatusBadgeClass(item.status)}`}>
                        {item.status}
                      </span>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-sm text-surface-900 dark:text-white">
                            {item.domain || item.original_url}
                          </span>
                          <a
                            href={item.final_url || item.original_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            onClick={e => e.stopPropagation()}
                            className="text-surface-400 hover:text-indigo-600 transition-colors"
                          >
                            <ExternalLink className="w-3.5 h-3.5" />
                          </a>
                        </div>
                        {item.website_title && (
                          <span className="text-xs text-surface-500 truncate block max-w-md">
                            {item.website_title}
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-6 text-xs text-surface-500">
                      <div>
                        <span className="text-surface-400 mr-1.5">HTTP</span>
                        <span className="font-mono font-bold text-surface-900 dark:text-white">
                          {item.http_status_code || '—'}
                        </span>
                      </div>

                      <div>
                        <span className="text-surface-400 mr-1.5">Latency</span>
                        <span className="font-semibold text-surface-900 dark:text-white">
                          {formatResponseTime(item.response_time_ms)}
                        </span>
                      </div>

                      <div className="flex items-center gap-1">
                        {isExpanded ? (
                          <ChevronUp className="w-4 h-4 text-surface-400" />
                        ) : (
                          <ChevronDown className="w-4 h-4 text-surface-400" />
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Expanded Inspector Panel */}
                  {isExpanded && (
                    <div className="bg-surface-50/70 dark:bg-surface-950/40 p-6 border-t border-surface-200 dark:border-surface-800 space-y-6">
                      {/* Sub-tab navigation */}
                      <div className="flex items-center gap-3 border-b border-surface-200 dark:border-surface-800 pb-3">
                        <button
                          onClick={() => setActiveTab('dns')}
                          className={`text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors flex items-center gap-1.5 ${
                            activeTab === 'dns'
                              ? 'bg-indigo-600 text-white'
                              : 'bg-surface-200/60 dark:bg-surface-800 text-surface-600 dark:text-surface-300'
                          }`}
                        >
                          <Server className="w-3.5 h-3.5" />
                          <span>DNS Records</span>
                        </button>

                        <button
                          onClick={() => setActiveTab('ssl')}
                          className={`text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors flex items-center gap-1.5 ${
                            activeTab === 'ssl'
                              ? 'bg-indigo-600 text-white'
                              : 'bg-surface-200/60 dark:bg-surface-800 text-surface-600 dark:text-surface-300'
                          }`}
                        >
                          <ShieldCheck className="w-3.5 h-3.5" />
                          <span>SSL Certificate</span>
                        </button>

                        <button
                          onClick={() => setActiveTab('screenshot')}
                          className={`text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors flex items-center gap-1.5 ${
                            activeTab === 'screenshot'
                              ? 'bg-indigo-600 text-white'
                              : 'bg-surface-200/60 dark:bg-surface-800 text-surface-600 dark:text-surface-300'
                          }`}
                        >
                          <Camera className="w-3.5 h-3.5" />
                          <span>Visual Snapshot</span>
                        </button>
                      </div>

                      {isLoadingDetails ? (
                        <div className="py-8 text-center text-xs text-surface-400">
                          <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2 text-indigo-500" />
                          Fetching diagnostic details...
                        </div>
                      ) : (
                        <>
                          {/* TAB 1: DNS Records */}
                          {activeTab === 'dns' && (
                            <div className="space-y-4">
                              {/* Filter by Record Type */}
                              <div className="flex items-center gap-2 overflow-x-auto pb-1">
                                <span className="text-xs text-surface-400 mr-1">Filter type:</span>
                                {['ALL', 'A', 'AAAA', 'CNAME', 'MX', 'NS', 'TXT', 'SOA', 'CAA'].map(type => (
                                  <button
                                    key={type}
                                    onClick={() => setDnsFilter(type)}
                                    className={`px-2 py-0.5 rounded text-[11px] font-mono font-medium ${
                                      dnsFilter === type
                                        ? 'bg-indigo-600 text-white'
                                        : 'bg-surface-200 dark:bg-surface-800 text-surface-600 dark:text-surface-400'
                                    }`}
                                  >
                                    {type}
                                  </button>
                                ))}
                              </div>

                              {filteredDns.length === 0 ? (
                                <p className="text-xs text-surface-400 py-4">
                                  No DNS records matching filter {dnsFilter}.
                                </p>
                              ) : (
                                <div className="overflow-x-auto rounded-lg border border-surface-200 dark:border-surface-800">
                                  <table className="data-table text-xs">
                                    <thead>
                                      <tr>
                                        <th>Type</th>
                                        <th>Value / Target</th>
                                        <th>TTL</th>
                                        <th>Status</th>
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {filteredDns.map((r, i) => (
                                        <tr key={i}>
                                          <td className="font-mono font-bold text-indigo-600 dark:text-indigo-400">
                                            {r.record_type}
                                          </td>
                                          <td className="font-mono break-all text-surface-800 dark:text-surface-200">
                                            {r.record_value}
                                          </td>
                                          <td className="text-surface-500">{r.ttl ?? '—'}</td>
                                          <td>
                                            <span
                                              className={`badge ${
                                                r.lookup_status === 'success'
                                                  ? 'badge-online'
                                                  : 'badge-warning'
                                              }`}
                                            >
                                              {r.lookup_status}
                                            </span>
                                          </td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                </div>
                              )}
                            </div>
                          )}

                          {/* TAB 2: SSL Details */}
                          {activeTab === 'ssl' && (
                            <div className="space-y-4">
                              {currentSsl ? (
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                  <div className="card p-4 space-y-2 text-xs">
                                    <div className="flex justify-between border-b border-surface-100 dark:border-surface-800 pb-2">
                                      <span className="text-surface-400">Issuer</span>
                                      <span className="font-semibold text-surface-900 dark:text-white">
                                        {currentSsl.issuer || 'Unknown'}
                                      </span>
                                    </div>
                                    <div className="flex justify-between border-b border-surface-100 dark:border-surface-800 pb-2">
                                      <span className="text-surface-400">Subject / CN</span>
                                      <span className="font-semibold text-surface-900 dark:text-white">
                                        {currentSsl.subject || '—'}
                                      </span>
                                    </div>
                                    <div className="flex justify-between">
                                      <span className="text-surface-400">Hostname Match</span>
                                      <span
                                        className={`font-semibold ${
                                          currentSsl.hostname_match
                                            ? 'text-emerald-600'
                                            : 'text-rose-600'
                                        }`}
                                      >
                                        {currentSsl.hostname_match ? 'Matched' : 'Mismatch'}
                                      </span>
                                    </div>
                                  </div>

                                  <div className="card p-4 space-y-2 text-xs">
                                    <div className="flex justify-between border-b border-surface-100 dark:border-surface-800 pb-2">
                                      <span className="text-surface-400">Valid From</span>
                                      <span className="text-surface-700 dark:text-surface-300">
                                        {formatDate(currentSsl.valid_from)}
                                      </span>
                                    </div>
                                    <div className="flex justify-between border-b border-surface-100 dark:border-surface-800 pb-2">
                                      <span className="text-surface-400">Expiry Date</span>
                                      <span className="text-surface-700 dark:text-surface-300">
                                        {formatDate(currentSsl.expiry_date)}
                                      </span>
                                    </div>
                                    <div className="flex justify-between">
                                      <span className="text-surface-400">Remaining Days</span>
                                      <span
                                        className={`font-bold ${
                                          (currentSsl.remaining_days ?? 0) < 15
                                            ? 'text-rose-600'
                                            : 'text-emerald-600'
                                        }`}
                                      >
                                        {currentSsl.remaining_days ?? '—'} days
                                      </span>
                                    </div>
                                  </div>
                                </div>
                              ) : (
                                <p className="text-xs text-surface-400 py-4">
                                  No SSL/TLS certificate found or connection was not HTTPS.
                                </p>
                              )}
                            </div>
                          )}

                          {/* TAB 3: Visual Screenshot */}
                          {activeTab === 'screenshot' && (
                            <div className="space-y-3">
                              {item.screenshot_path ? (
                                <>
                                  <div className="flex justify-end">
                                    <a
                                      href={getScreenshotUrl(item.screenshot_path)}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline flex items-center gap-1"
                                    >
                                      <span>Open full-resolution screenshot</span>
                                      <ExternalLink className="w-3.5 h-3.5" />
                                    </a>
                                  </div>
                                  <div className="rounded-xl border border-surface-200 dark:border-surface-800 overflow-hidden bg-slate-900 shadow-inner">
                                    <img
                                      src={getScreenshotUrl(item.screenshot_path)}
                                      alt="Visual snapshot"
                                      className="w-full h-auto max-h-[500px] object-contain"
                                    />
                                  </div>
                                </>
                              ) : (
                                <p className="text-xs text-surface-400 py-6 text-center">
                                  No visual screenshot captured for this website.
                                </p>
                              )}
                            </div>
                          )}
                        </>
                      )}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
