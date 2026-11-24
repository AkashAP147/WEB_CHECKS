import React, { useState, useMemo, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Search,
  Upload,
  FileSpreadsheet,
  Play,
  Square,
  Download,
  FileText,
  Table as TableIcon,
  ExternalLink,
  CheckCircle,
  XCircle,
  AlertTriangle,
  ShieldCheck,
  ShieldAlert,
  Loader2,
  Eye,
  RotateCcw,
  Filter,
  X,
  Camera,
  Server,
  Globe,
  Clock,
  Sparkles,
} from 'lucide-react';
import { useScan } from '../hooks/useScan';
import { scanApi } from '../services/api';
import type { ScanResult, WebsiteStatus } from '../types';
import {
  getStatusBadgeClass,
  formatResponseTime,
  formatDate,
  getScreenshotUrl,
  downloadBlob,
  cn,
} from '../utils/helpers';

export default function Scanner() {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<'single' | 'bulk' | 'excel'>('single');
  const [singleUrl, setSingleUrl] = useState('');
  const [bulkUrls, setBulkUrls] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);

  // Filters & Search
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [selectedResult, setSelectedResult] = useState<ScanResult | null>(null);
  const [downloadingType, setDownloadingType] = useState<'pdf' | 'excel' | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const {
    scan,
    results,
    loading,
    error,
    startScan,
    uploadExcelScan,
    cancelScan,
    setError,
  } = useScan();

  // Parsing & validation
  const handleStartSingleScan = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = singleUrl.trim();
    if (!trimmed) {
      setError('Please provide a website URL.');
      return;
    }
    await startScan([trimmed]);
  };

  const handleStartBulkScan = async (e: React.FormEvent) => {
    e.preventDefault();
    const urls = bulkUrls
      .split('\n')
      .map(u => u.trim())
      .filter(u => u.length > 0);

    if (urls.length === 0) {
      setError('Please enter at least one URL.');
      return;
    }
    await startScan(urls);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      if (!file.name.match(/\.(xlsx|xls|csv)$/i)) {
        setFileError('Please select a valid CSV or Excel file (.csv, .xlsx, or .xls)');
        setSelectedFile(null);
        return;
      }
      setSelectedFile(file);
      setFileError(null);
    }
  };

  const handleStartExcelScan = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) {
      setFileError('Please select a CSV or Excel file to upload.');
      return;
    }
    await uploadExcelScan(selectedFile);
  };

  const handleRetryFailed = async () => {
    const safeResults = Array.isArray(results) ? results : [];
    const failedUrls = safeResults
      .filter(r => r.status !== 'ONLINE')
      .map(r => r.original_url);
    if (failedUrls.length > 0) {
      await startScan(failedUrls);
    }
  };

  const handleDownloadReport = async (type: 'pdf' | 'excel') => {
    if (!scan) return;
    setDownloadingType(type);
    try {
      const cleanName = scan.filename ? scan.filename.replace(/\.[^/.]+$/, "").replace(/[^a-zA-Z0-9_-]/g, "_") : "";
      const baseName = cleanName ? `${cleanName}_${scan.id.substring(0, 8)}` : `WebPulse_Audit_${scan.id.substring(0, 8)}`;
      if (type === 'pdf') {
        const blob = await scanApi.downloadPDF(scan.id);
        downloadBlob(blob, `${baseName}.pdf`);
      } else {
        const blob = await scanApi.downloadExcel(scan.id);
        downloadBlob(blob, `${baseName}.xlsx`);
      }
    } catch (err: any) {
      alert(`Failed to download ${type.toUpperCase()} report: ` + (err.message || 'Error'));
    } finally {
      setDownloadingType(null);
    }
  };

  // Filtered results
  const filteredResults = useMemo(() => {
    const safeResults = Array.isArray(results) ? results : [];
    return safeResults.filter(r => {
      const matchesSearch =
        (r.domain && r.domain.toLowerCase().includes(searchTerm.toLowerCase())) ||
        (r.original_url && r.original_url.toLowerCase().includes(searchTerm.toLowerCase())) ||
        (r.website_title && r.website_title.toLowerCase().includes(searchTerm.toLowerCase()));

      const matchesStatus =
        statusFilter === 'ALL'
          ? true
          : statusFilter === 'ONLINE'
          ? r.status === 'ONLINE'
          : statusFilter === 'OFFLINE'
          ? r.status === 'OFFLINE'
          : statusFilter === 'ERRORS'
          ? r.status !== 'ONLINE'
          : r.status === statusFilter;

      return matchesSearch && matchesStatus;
    });
  }, [results, searchTerm, statusFilter]);

  const isScanning = scan?.status === 'running' || scan?.status === 'pending';
  const progressPct =
    scan && scan.total_urls > 0
      ? Math.round((scan.completed_urls / scan.total_urls) * 100)
      : 0;

  return (
    <div className="space-y-8 animate-fade-in pb-16">
      {/* Page Title Header */}
      <div>
        <h2 className="text-2xl font-extrabold text-surface-900 dark:text-white tracking-tight">
          Website Health &amp; DNS Scanner
        </h2>
        <p className="text-sm text-surface-500 dark:text-surface-400 mt-1">
          Perform live HTTP availability checks, DNS record verification, SSL certificate inspection, and full-page visual captures.
        </p>
      </div>

      {/* Input Card with Tabs */}
      <div className="card p-6 shadow-sm">
        {/* Tab Switcher */}
        <div className="flex border-b border-surface-200 dark:border-surface-800 mb-6">
          <button
            onClick={() => setActiveTab('single')}
            disabled={isScanning}
            className={`flex items-center gap-2 pb-3 px-4 text-sm font-semibold border-b-2 transition-colors ${
              activeTab === 'single'
                ? 'border-indigo-600 text-indigo-600 dark:text-indigo-400'
                : 'border-transparent text-surface-500 hover:text-surface-800 dark:hover:text-surface-200'
            }`}
          >
            <Search className="w-4 h-4" />
            <span>Single Website</span>
          </button>

          <button
            onClick={() => setActiveTab('bulk')}
            disabled={isScanning}
            className={`flex items-center gap-2 pb-3 px-4 text-sm font-semibold border-b-2 transition-colors ${
              activeTab === 'bulk'
                ? 'border-indigo-600 text-indigo-600 dark:text-indigo-400'
                : 'border-transparent text-surface-500 hover:text-surface-800 dark:hover:text-surface-200'
            }`}
          >
            <Globe className="w-4 h-4" />
            <span>Bulk URLs</span>
          </button>

          <button
            onClick={() => setActiveTab('excel')}
            disabled={isScanning}
            className={`flex items-center gap-2 pb-3 px-4 text-sm font-semibold border-b-2 transition-colors ${
              activeTab === 'excel'
                ? 'border-indigo-600 text-indigo-600 dark:text-indigo-400'
                : 'border-transparent text-surface-500 hover:text-surface-800 dark:hover:text-surface-200'
            }`}
          >
            <FileSpreadsheet className="w-4 h-4" />
            <span>CSV / Excel Upload</span>
          </button>
        </div>

        {error && (
          <div className="mb-4 p-3.5 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900/50 text-rose-700 dark:text-rose-400 text-sm flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Tab 1: Single URL */}
        {activeTab === 'single' && (
          <form onSubmit={handleStartSingleScan} className="space-y-4">
            <div className="flex flex-col sm:flex-row gap-3">
              <div className="relative flex-1">
                <input
                  type="text"
                  disabled={isScanning}
                  value={singleUrl}
                  onChange={e => setSingleUrl(e.target.value)}
                  placeholder="e.g. example.com or https://stripe.com"
                  className="input pl-10"
                />
                <Globe className="absolute left-3.5 top-3 w-4 h-4 text-surface-400" />
              </div>

              <button
                type="submit"
                disabled={isScanning || !singleUrl.trim()}
                className="btn-primary px-6"
              >
                {isScanning ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Auditing...</span>
                  </>
                ) : (
                  <>
                    <Play className="w-4 h-4" />
                    <span>Run Health Audit</span>
                  </>
                )}
              </button>
            </div>
            <p className="text-xs text-surface-400 dark:text-surface-500">
              Protocol (https://) is optional. Automated SSRF protection and hostname validation are active.
            </p>
          </form>
        )}

        {/* Tab 2: Bulk URLs */}
        {activeTab === 'bulk' && (
          <form onSubmit={handleStartBulkScan} className="space-y-4">
            <div className="space-y-2">
              <label className="text-xs font-semibold text-surface-600 dark:text-surface-300">
                Enter URLs (one per line)
              </label>
              <textarea
                disabled={isScanning}
                rows={6}
                value={bulkUrls}
                onChange={e => setBulkUrls(e.target.value)}
                placeholder="google.com&#10;github.com&#10;cloudflare.com&#10;microsoft.com"
                className="textarea font-mono text-xs"
              />
              <div className="flex items-center justify-between text-xs text-surface-500">
                <span>
                  Detected URLs:{' '}
                  <b>
                    {
                      bulkUrls
                        .split('\n')
                        .map(u => u.trim())
                        .filter(Boolean).length
                    }
                  </b>
                </span>
                <span>High-speed batch: up to 1,000 targets (auto-slices large 10k lists)</span>
              </div>
            </div>

            <button
              type="submit"
              disabled={isScanning || !bulkUrls.trim()}
              className="btn-primary px-6"
            >
              {isScanning ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Auditing URLs...</span>
                </>
              ) : (
                <>
                  <Play className="w-4 h-4" />
                  <span>Scan All Targets</span>
                </>
              )}
            </button>
          </form>
        )}

        {/* Tab 3: Excel Upload */}
        {activeTab === 'excel' && (
          <form onSubmit={handleStartExcelScan} className="space-y-4">
            <div
              onClick={() => !isScanning && fileInputRef.current?.click()}
              className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
                selectedFile
                  ? 'border-indigo-500 bg-indigo-50/30 dark:bg-indigo-950/20'
                  : 'border-surface-300 dark:border-surface-700 hover:border-indigo-400'
              } ${isScanning ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".xlsx,.xls,.csv,text/csv"
                disabled={isScanning}
                onChange={handleFileChange}
                className="hidden"
              />
              <div className="flex flex-col items-center">
                <FileSpreadsheet className="w-10 h-10 text-indigo-500 mb-2" />
                {selectedFile ? (
                  <div>
                    <span className="text-sm font-semibold text-surface-900 dark:text-white">
                      {selectedFile.name}
                    </span>
                    <p className="text-xs text-surface-500 mt-1">
                      {(selectedFile.size / 1024).toFixed(1)} KB — Click to change
                    </p>
                  </div>
                ) : (
                  <div>
                    <span className="text-sm font-semibold text-surface-800 dark:text-surface-200">
                      Upload a CSV or Excel file (.csv / .xlsx / .xls)
                    </span>
                    <p className="text-xs text-surface-400 dark:text-surface-500 mt-1">
                      WebPulse will automatically parse URLs from the first column of your file.
                    </p>
                  </div>
                )}
              </div>
            </div>

            {fileError && <p className="text-xs text-rose-500 font-medium">{fileError}</p>}

            <button
              type="submit"
              disabled={isScanning || !selectedFile}
              className="btn-primary px-6"
            >
              {isScanning ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Processing File...</span>
                </>
              ) : (
                <>
                  <Upload className="w-4 h-4" />
                  <span>Upload &amp; Start Scan</span>
                </>
              )}
            </button>
          </form>
        )}
      </div>

      {/* Live Scan Progress Section */}
      {scan && (
        <div className="card p-6 border-indigo-200 dark:border-indigo-900/50 shadow-md">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-4">
            <div>
              <div className="flex items-center gap-2">
                <span className={`badge ${isScanning ? 'badge-info' : 'badge-online'}`}>
                  {scan.status.toUpperCase()}
                </span>
                <span className="text-xs font-mono text-surface-400">
                  ID: {scan.id.substring(0, 8)}
                </span>
              </div>
              <h3 className="text-lg font-bold text-surface-900 dark:text-white mt-1">
                {isScanning
                  ? `Scanning ${scan.completed_urls} of ${scan.total_urls} websites...`
                  : `Scan completed: ${results.length} websites evaluated.`}
              </h3>
            </div>

            <div className="flex items-center gap-2 shrink-0">
              {isScanning && (
                <button onClick={cancelScan} className="btn-danger text-xs py-2 px-3.5">
                  <Square className="w-3.5 h-3.5" />
                  <span>Cancel Scan</span>
                </button>
              )}

              {!isScanning && (
                <>
                  <button
                    onClick={() => handleDownloadReport('pdf')}
                    disabled={downloadingType !== null}
                    className="btn-secondary text-xs py-2 px-3.5"
                  >
                    {downloadingType === 'pdf' ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <FileText className="w-3.5 h-3.5 text-rose-500" />
                    )}
                    <span>Download PDF</span>
                  </button>

                  <button
                    onClick={() => handleDownloadReport('excel')}
                    disabled={downloadingType !== null}
                    className="btn-secondary text-xs py-2 px-3.5"
                  >
                    {downloadingType === 'excel' ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <TableIcon className="w-3.5 h-3.5 text-emerald-500" />
                    )}
                    <span>Download Excel</span>
                  </button>

                  {results.some(r => r.status !== 'ONLINE') && (
                    <button
                      onClick={handleRetryFailed}
                      className="btn-secondary text-xs py-2 px-3.5 text-amber-600 dark:text-amber-400"
                    >
                      <RotateCcw className="w-3.5 h-3.5" />
                      <span>Retry Failed</span>
                    </button>
                  )}
                </>
              )}
            </div>
          </div>

          {/* Animated Progress Bar */}
          <div className="w-full bg-surface-100 dark:bg-surface-800 rounded-full h-3 overflow-hidden">
            <div
              className={`h-full transition-all duration-500 ease-out ${
                isScanning
                  ? 'bg-gradient-to-r from-indigo-500 to-indigo-600 animate-pulse'
                  : 'bg-emerald-500'
              }`}
              style={{ width: `${progressPct}%` }}
            />
          </div>

          <div className="flex items-center justify-between text-xs text-surface-500 dark:text-surface-400 mt-2">
            <span>
              {scan.completed_urls} / {scan.total_urls} Targets Checked
            </span>
            <span className="font-semibold">{progressPct}%</span>
          </div>
        </div>
      )}

      {/* Results Section */}
      {Array.isArray(results) && results.length > 0 && (
        <div className="card overflow-hidden">
          {/* Filter Bar */}
          <div className="p-4 sm:p-6 border-b border-surface-200 dark:border-surface-800 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="relative flex-1 max-w-sm">
              <input
                type="text"
                placeholder="Search domain or title..."
                value={searchTerm}
                onChange={e => setSearchTerm(e.target.value)}
                className="input pl-9 text-xs"
              />
              <Search className="absolute left-3 top-2.5 w-3.5 h-3.5 text-surface-400" />
            </div>

            <div className="flex items-center gap-2 overflow-x-auto pb-1 sm:pb-0">
              <span className="text-xs font-semibold text-surface-500 dark:text-surface-400 flex items-center gap-1 shrink-0">
                <Filter className="w-3.5 h-3.5" /> Filter:
              </span>

              {[
                { label: 'All', value: 'ALL' },
                { label: 'Online', value: 'ONLINE' },
                { label: 'Offline', value: 'OFFLINE' },
                { label: 'Errors', value: 'ERRORS' },
              ].map(f => (
                <button
                  key={f.value}
                  onClick={() => setStatusFilter(f.value)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors shrink-0 ${
                    statusFilter === f.value
                      ? 'bg-indigo-600 text-white'
                      : 'bg-surface-100 dark:bg-surface-800 text-surface-600 dark:text-surface-400 hover:bg-surface-200'
                  }`}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>

          {/* Results Table */}
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Status</th>
                  <th>Domain / URL</th>
                  <th>HTTP</th>
                  <th>Latency</th>
                  <th>DNS</th>
                  <th>SSL</th>
                  <th>Screenshot</th>
                  <th className="text-right">Diagnostics</th>
                </tr>
              </thead>
              <tbody>
                {filteredResults.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="text-center py-8 text-surface-400 text-xs">
                      No websites match your filter criteria.
                    </td>
                  </tr>
                ) : (
                  filteredResults.map(item => {
                    const isOnline = item.status === 'ONLINE';
                    return (
                      <tr
                        key={item.id}
                        className="hover:bg-surface-50 dark:hover:bg-surface-800/50 cursor-pointer transition-colors"
                        onClick={() => setSelectedResult(item)}
                      >
                        {/* Status */}
                        <td>
                          <span className={`badge ${getStatusBadgeClass(item.status)}`}>
                            {item.status}
                          </span>
                        </td>

                        {/* Domain / Title */}
                        <td>
                          <div className="flex flex-col">
                            <span className="font-semibold text-surface-900 dark:text-white text-xs">
                              {item.domain || item.original_url}
                            </span>
                            {item.website_title && (
                              <span className="text-[11px] text-surface-500 dark:text-surface-400 truncate max-w-xs">
                                {item.website_title}
                              </span>
                            )}
                          </div>
                        </td>

                        {/* HTTP Status */}
                        <td>
                          <span
                            className={`font-mono text-xs font-semibold ${
                              item.http_status_code && item.http_status_code >= 200 && item.http_status_code < 400
                                ? 'text-emerald-600 dark:text-emerald-400'
                                : 'text-surface-600 dark:text-surface-400'
                            }`}
                          >
                            {item.http_status_code || '—'}
                          </span>
                        </td>

                        {/* Latency */}
                        <td className="text-surface-600 dark:text-surface-400 text-xs">
                          {formatResponseTime(item.response_time_ms)}
                        </td>

                        {/* DNS indicator */}
                        <td>
                          {item.status === 'DNS_ERROR' ? (
                            <span className="text-rose-500 flex items-center gap-1 text-xs">
                              <XCircle className="w-3.5 h-3.5" /> Fail
                            </span>
                          ) : (
                            <span className="text-emerald-600 dark:text-emerald-400 flex items-center gap-1 text-xs">
                              <CheckCircle className="w-3.5 h-3.5" /> OK
                            </span>
                          )}
                        </td>

                        {/* SSL indicator */}
                        <td>
                          {item.status === 'SSL_ERROR' ? (
                            <span className="text-rose-500 flex items-center gap-1 text-xs">
                              <ShieldAlert className="w-3.5 h-3.5" /> Invalid
                            </span>
                          ) : isOnline ? (
                            <span className="text-emerald-600 dark:text-emerald-400 flex items-center gap-1 text-xs">
                              <ShieldCheck className="w-3.5 h-3.5" /> Valid
                            </span>
                          ) : (
                            <span className="text-surface-400 text-xs">—</span>
                          )}
                        </td>

                        {/* Screenshot thumbnail */}
                        <td>
                          {item.screenshot_path ? (
                            <div className="w-12 h-8 rounded border border-surface-200 dark:border-surface-700 overflow-hidden bg-surface-100 dark:bg-surface-800">
                              <img
                                src={getScreenshotUrl(item.screenshot_path)}
                                alt="thumb"
                                className="w-full h-full object-cover"
                              />
                            </div>
                          ) : (
                            <span className="text-[10px] text-surface-400">—</span>
                          )}
                        </td>

                        {/* Action */}
                        <td className="text-right">
                          <button
                            onClick={e => {
                              e.stopPropagation();
                              setSelectedResult(item);
                            }}
                            className="p-1.5 rounded-lg text-indigo-600 dark:text-indigo-400 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 font-semibold text-xs inline-flex items-center gap-1"
                          >
                            <Eye className="w-3.5 h-3.5" />
                            <span>Inspect</span>
                          </button>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Detail Modal / Drawer */}
      {selectedResult && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-fade-in">
          <div className="card w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden shadow-2xl">
            {/* Modal Header */}
            <div className="p-6 border-b border-surface-200 dark:border-surface-800 flex items-center justify-between shrink-0">
              <div className="flex items-center gap-3">
                <span className={`badge ${getStatusBadgeClass(selectedResult.status)}`}>
                  {selectedResult.status}
                </span>
                <h3 className="text-lg font-bold text-surface-900 dark:text-white truncate">
                  {selectedResult.domain || selectedResult.original_url}
                </h3>
              </div>
              <button
                onClick={() => setSelectedResult(null)}
                className="p-2 rounded-lg text-surface-400 hover:bg-surface-100 dark:hover:bg-surface-800"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-6 overflow-y-auto space-y-6 flex-1">
              {/* Basic Information */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-3">
                  <div>
                    <span className="text-xs text-surface-400">Original URL</span>
                    <p className="text-xs font-mono font-medium text-surface-800 dark:text-surface-200 break-all">
                      {selectedResult.original_url}
                    </p>
                  </div>
                  <div>
                    <span className="text-xs text-surface-400">Final Redirect URL</span>
                    <p className="text-xs font-mono font-medium text-surface-800 dark:text-surface-200 break-all">
                      {selectedResult.final_url || 'Same as original (no redirect)'}
                    </p>
                  </div>
                  <div>
                    <span className="text-xs text-surface-400">Page Title</span>
                    <p className="text-xs font-medium text-surface-800 dark:text-surface-200">
                      {selectedResult.website_title || '—'}
                    </p>
                  </div>
                </div>

                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-surface-400">HTTP Status</span>
                    <span className="font-mono text-xs font-bold text-surface-900 dark:text-white">
                      {selectedResult.http_status_code || '—'}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-surface-400">Latency / Response Time</span>
                    <span className="text-xs font-semibold text-surface-900 dark:text-white">
                      {formatResponseTime(selectedResult.response_time_ms)}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-surface-400">Web Server Header</span>
                    <span className="text-xs font-medium text-surface-700 dark:text-surface-300">
                      {selectedResult.server_info || 'Hidden / Not provided'}
                    </span>
                  </div>
                  {selectedResult.error_message && (
                    <div className="p-3 rounded-lg bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-400 text-xs">
                      <b>Error detail:</b> {selectedResult.error_message}
                    </div>
                  )}
                </div>
              </div>

              {/* Screenshot Preview */}
              <div>
                <h4 className="text-sm font-bold text-surface-900 dark:text-white mb-2 flex items-center gap-1.5">
                  <Camera className="w-4 h-4 text-indigo-500" />
                  <span>Desktop Render Preview (1440 × 900)</span>
                </h4>
                {selectedResult.screenshot_path ? (
                  <div className="rounded-xl border border-surface-200 dark:border-surface-800 overflow-hidden bg-slate-900 shadow-inner">
                    <img
                      src={getScreenshotUrl(selectedResult.screenshot_path)}
                      alt="Full Page Screenshot"
                      className="w-full h-auto max-h-96 object-contain"
                    />
                  </div>
                ) : (
                  <div className="p-8 text-center bg-surface-50 dark:bg-surface-800 rounded-xl text-xs text-surface-400">
                    No screenshot available for this target.
                  </div>
                )}
              </div>
            </div>

            {/* Modal Footer */}
            <div className="p-4 border-t border-surface-200 dark:border-surface-800 bg-surface-50 dark:bg-surface-900 flex justify-end">
              <button onClick={() => setSelectedResult(null)} className="btn-secondary text-xs px-4">
                Close Inspector
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
