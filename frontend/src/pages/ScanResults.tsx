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

  const handleDownload = async (type: 'pdf' | 'excel') => {
    if (!scanId) return;
    setDownloadingType(type);
    try {
      if (type === 'pdf') {
        const blob = await scanApi.downloadPDF(scanId);
        downloadBlob(blob, `WebPulse_Audit_${scanId}.pdf`);
      } else {
        const blob = await scanApi.downloadExcel(scanId);
        downloadBlob(blob, `WebPulse_Audit_${scanId}.xlsx`);
      }
    } catch (err: any) {
      alert(`Download failed: ` + (err.message || 'Error'));
    } finally {
      setDownloadingType(null);
    }
  };

  const safeResults = Array.isArray(results) ? results : [];
  const total = safeResults.length;
  const online = safeResults.filter(r => r.status === 'ONLINE').length;
  const offline = safeResults.filter(r => r.status === 'OFFLINE').length;
  const errors = total - (online + offline);

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
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-bold text-surface-900 dark:text-white">
                Audit Diagnostics
              </h2>
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
        <div className="flex items-center gap-2">
          <button
            onClick={() => handleDownload('pdf')}
            disabled={downloadingType !== null || loading}
            className="btn-secondary text-xs py-2 px-3.5"
          >
            {downloadingType === 'pdf' ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <FileText className="w-3.5 h-3.5 text-rose-500" />
            )}
            <span>PDF Report</span>
          </button>

          <button
            onClick={() => handleDownload('excel')}
            disabled={downloadingType !== null || loading}
            className="btn-secondary text-xs py-2 px-3.5"
          >
            {downloadingType === 'excel' ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <TableIcon className="w-3.5 h-3.5 text-emerald-500" />
            )}
            <span>Excel Export</span>
          </button>
        </div>
      </div>

      {/* KPI Overview Strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="card p-4">
          <span className="text-xs text-surface-500">Audited Targets</span>
          <div className="text-2xl font-bold text-surface-900 dark:text-white mt-1">
            {total}
          </div>
        </div>
        <div className="card p-4">
          <span className="text-xs text-emerald-600 dark:text-emerald-400">Online Websites</span>
          <div className="text-2xl font-bold text-emerald-600 dark:text-emerald-400 mt-1">
            {online}
          </div>
        </div>
        <div className="card p-4">
          <span className="text-xs text-rose-600 dark:text-rose-400">Offline Websites</span>
          <div className="text-2xl font-bold text-rose-600 dark:text-rose-400 mt-1">
            {offline}
          </div>
        </div>
        <div className="card p-4">
          <span className="text-xs text-amber-600 dark:text-amber-400">Errors &amp; Warnings</span>
          <div className="text-2xl font-bold text-amber-600 dark:text-amber-400 mt-1">
            {errors}
          </div>
        </div>
      </div>

      {/* Websites List with Accordion */}
      <div className="card overflow-hidden">
        <div className="p-4 border-b border-surface-200 dark:border-surface-800 bg-surface-50/50 dark:bg-surface-900/50 flex items-center justify-between">
          <h3 className="text-sm font-bold text-surface-900 dark:text-white">
            Audited Targets &amp; Deep Inspection
          </h3>
          <span className="text-xs text-surface-400">
            Click any row to view DNS records, SSL cert, and full screenshot
          </span>
        </div>

        <div className="divide-y divide-surface-200 dark:divide-surface-800">
          {loading ? (
            <div className="p-12 text-center text-surface-400 text-xs">
              <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2 text-indigo-500" />
              Loading audit results...
            </div>
          ) : safeResults.length === 0 ? (
            <div className="p-12 text-center text-surface-400 text-xs">
              No results found for this scan.
            </div>
          ) : (
            safeResults.map(item => {
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
                            <div>
                              {item.screenshot_path ? (
                                <div className="rounded-xl border border-surface-200 dark:border-surface-800 overflow-hidden bg-slate-900">
                                  <img
                                    src={getScreenshotUrl(item.screenshot_path)}
                                    alt="Visual snapshot"
                                    className="w-full h-auto max-h-[500px] object-contain"
                                  />
                                </div>
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
