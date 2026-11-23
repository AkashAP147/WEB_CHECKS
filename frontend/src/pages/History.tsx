import { useState, useEffect, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  Search,
  Filter,
  Download,
  FileText,
  FileSpreadsheet,
  Calendar,
  Table as TableIcon,
  Eye,
  Trash2,
  ChevronLeft,
  ChevronRight,
  Clock,
  RefreshCw,
  Globe,
  Loader2,
  Activity,
} from 'lucide-react';
import { scanApi } from '../services/api';
import type { ScanHistoryItem } from '../types';
import { formatDate, getScanStatusBadgeClass, downloadBlob } from '../utils/helpers';

export default function History() {
  const navigate = useNavigate();
  const [historyItems, setHistoryItems] = useState<ScanHistoryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [page, setPage] = useState(1);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  // Time-range batch export state (for all websites)
  const [timePreset, setTimePreset] = useState<'all' | '24h' | '7d' | '30d' | 'custom'>('all');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [exportStatus, setExportStatus] = useState('ALL');
  const [exportingType, setExportingType] = useState<'pdf' | 'excel' | null>(null);

  const handleExportTimeRange = async (type: 'pdf' | 'excel') => {
    setExportingType(type);
    try {
      const params = {
        preset: timePreset !== 'custom' ? timePreset : undefined,
        startDate: timePreset === 'custom' && startDate ? startDate : undefined,
        endDate: timePreset === 'custom' && endDate ? endDate : undefined,
        status: exportStatus !== 'ALL' ? exportStatus : undefined,
      };

      if (type === 'pdf') {
        const blob = await scanApi.exportTimeRangePDF(params);
        downloadBlob(blob, `WebPulse_AllWebsites_${timePreset}_${Date.now()}.pdf`);
      } else {
        const blob = await scanApi.exportTimeRangeExcel(params);
        downloadBlob(blob, `WebPulse_AllWebsites_${timePreset}_${Date.now()}.xlsx`);
      }
    } catch (err: any) {
      alert(`Export failed: ${err?.response?.data?.detail || err.message || 'No records found'}`);
    } finally {
      setExportingType(null);
    }
  };

  const limit = 15;

  const fetchHistory = useCallback(async () => {
    setLoading(true);
    try {
      const offset = (page - 1) * limit;
      const data = await scanApi.getHistory({
        limit,
        offset,
        search: searchTerm.trim() || undefined,
        status: statusFilter !== 'ALL' ? statusFilter : undefined,
      });
      setHistoryItems(data.items || []);
      setTotal(data.total || 0);
    } catch (err) {
      console.error('Failed to load scan history', err);
    } finally {
      setLoading(false);
    }
  }, [page, searchTerm, statusFilter]);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  const handleDownloadReport = async (scanId: string, type: 'pdf' | 'excel') => {
    setDownloadingId(`${scanId}_${type}`);
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
      setDownloadingId(null);
    }
  };

  const totalPages = Math.ceil(total / limit) || 1;

  return (
    <div className="space-y-8 animate-fade-in pb-16">
      {/* Title */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-extrabold text-surface-900 dark:text-white tracking-tight">
            Audit History &amp; Archives
          </h2>
          <p className="text-sm text-surface-500 dark:text-surface-400 mt-1">
            Browse, search, and download reports from previous website health checks.
          </p>
        </div>

        <button
          onClick={fetchHistory}
          className="btn-secondary text-xs py-2 px-3 self-start sm:self-auto"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Refresh</span>
        </button>
      </div>

      {/* Batch Export Card: All Websites within Analyzed Time Range */}
      <div className="card p-5 border-l-4 border-l-indigo-600 bg-gradient-to-r from-surface-50 to-white dark:from-surface-900/40 dark:to-surface-900 shadow-sm space-y-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <Download className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
              <h3 className="text-base font-bold text-surface-900 dark:text-white">
                Export All Websites by Analyzed Time Range
              </h3>
            </div>
            <p className="text-xs text-surface-500 dark:text-surface-400 mt-1">
              Download combined executive audit reports (PDF &amp; multi-sheet Excel) for all analyzed websites across the selected period.
            </p>
          </div>

          {/* Export Action Buttons */}
          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={() => handleExportTimeRange('pdf')}
              disabled={exportingType !== null}
              className="btn-secondary text-xs py-2 px-3.5 flex items-center gap-2 border-rose-200 dark:border-rose-900/40 hover:bg-rose-50 dark:hover:bg-rose-950/30 text-rose-600 dark:text-rose-400 font-semibold"
            >
              {exportingType === 'pdf' ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <FileText className="w-3.5 h-3.5 text-rose-500" />
              )}
              <span>Export All (PDF)</span>
            </button>

            <button
              onClick={() => handleExportTimeRange('excel')}
              disabled={exportingType !== null}
              className="btn-secondary text-xs py-2 px-3.5 flex items-center gap-2 border-emerald-200 dark:border-emerald-900/40 hover:bg-emerald-50 dark:hover:bg-emerald-950/30 text-emerald-600 dark:text-emerald-400 font-semibold"
            >
              {exportingType === 'excel' ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-500" />
              )}
              <span>Export All (Excel)</span>
            </button>
          </div>
        </div>

        {/* Time Range Filter Controls */}
        <div className="flex flex-wrap items-center gap-3 pt-3 border-t border-surface-200 dark:border-surface-800">
          <div className="flex items-center gap-1.5 overflow-x-auto">
            <span className="text-xs font-semibold text-surface-500 flex items-center gap-1 shrink-0 mr-1">
              <Calendar className="w-3.5 h-3.5" /> Time Window:
            </span>
            {[
              { id: 'all', label: 'All Time' },
              { id: '24h', label: 'Past 24 Hours' },
              { id: '7d', label: 'Past 7 Days' },
              { id: '30d', label: 'Past 30 Days' },
              { id: 'custom', label: 'Custom Range' },
            ].map(p => (
              <button
                key={p.id}
                onClick={() => setTimePreset(p.id as any)}
                className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors shrink-0 ${
                  timePreset === p.id
                    ? 'bg-indigo-600 text-white'
                    : 'bg-surface-100 dark:bg-surface-800 text-surface-600 dark:text-surface-400 hover:bg-surface-200 dark:hover:bg-surface-700'
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>

          {timePreset === 'custom' && (
            <div className="flex items-center gap-2 animate-fade-in text-xs">
              <input
                type="date"
                value={startDate}
                onChange={e => setStartDate(e.target.value)}
                className="input py-1 px-2.5 text-xs w-36"
                placeholder="From Date"
              />
              <span className="text-surface-400">to</span>
              <input
                type="date"
                value={endDate}
                onChange={e => setEndDate(e.target.value)}
                className="input py-1 px-2.5 text-xs w-36"
                placeholder="To Date"
              />
            </div>
          )}

          <div className="flex items-center gap-2 ml-auto text-xs">
            <span className="text-surface-400">Filter Status:</span>
            <select
              value={exportStatus}
              onChange={e => setExportStatus(e.target.value)}
              className="input py-1 px-2 text-xs w-32"
            >
              <option value="ALL">All Statuses</option>
              <option value="ONLINE">Online Only</option>
              <option value="OFFLINE">Offline Only</option>
              <option value="HTTP_ERROR">HTTP Errors</option>
              <option value="DNS_ERROR">DNS Errors</option>
              <option value="SSL_ERROR">SSL Issues</option>
            </select>
          </div>
        </div>
      </div>

      {/* Filter / Search Bar */}
      <div className="card p-4 flex flex-col sm:flex-row items-center justify-between gap-4">
        <div className="relative w-full sm:w-80">
          <input
            type="text"
            placeholder="Search domain..."
            value={searchTerm}
            onChange={e => {
              setSearchTerm(e.target.value);
              setPage(1);
            }}
            className="input pl-9 text-xs"
          />
          <Search className="absolute left-3 top-2.5 w-3.5 h-3.5 text-surface-400" />
        </div>

        <div className="flex items-center gap-2 w-full sm:w-auto overflow-x-auto">
          <span className="text-xs font-semibold text-surface-500 flex items-center gap-1 shrink-0">
            <Filter className="w-3.5 h-3.5" /> Status:
          </span>
          {['ALL', 'completed', 'running', 'failed', 'cancelled'].map(st => (
            <button
              key={st}
              onClick={() => {
                setStatusFilter(st);
                setPage(1);
              }}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold uppercase tracking-wider transition-colors shrink-0 ${
                statusFilter === st
                  ? 'bg-indigo-600 text-white'
                  : 'bg-surface-100 dark:bg-surface-800 text-surface-600 dark:text-surface-400 hover:bg-surface-200'
              }`}
            >
              {st}
            </button>
          ))}
        </div>
      </div>

      {/* History Table */}
      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>Scan ID</th>
                <th>Executed At</th>
                <th>Targets</th>
                <th>Online</th>
                <th>Offline</th>
                <th>Issues</th>
                <th>Status</th>
                <th className="text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={8} className="text-center py-12 text-surface-400 text-xs">
                    <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2 text-indigo-500" />
                    Loading audit history...
                  </td>
                </tr>
              ) : historyItems.length === 0 ? (
                <tr>
                  <td colSpan={8} className="text-center py-12">
                    <Clock className="w-8 h-8 mx-auto text-surface-300 dark:text-surface-700 mb-2" />
                    <p className="text-sm font-semibold text-surface-600 dark:text-surface-400">
                      No scan history matches your query
                    </p>
                    <p className="text-xs text-surface-400 dark:text-surface-500 mt-1">
                      Try clearing filters or initiate a new website audit.
                    </p>
                  </td>
                </tr>
              ) : (
                historyItems.map(item => {
                  const issueCount = (item.offline_count || 0) + (item.dns_errors || 0) + (item.ssl_issues || 0);
                  const isPdfDownloading = downloadingId === `${item.scan_id}_pdf`;
                  const isXlsxDownloading = downloadingId === `${item.scan_id}_excel`;

                  return (
                    <tr
                      key={item.scan_id}
                      className="hover:bg-surface-50 dark:hover:bg-surface-800/50 cursor-pointer"
                      onClick={() => navigate(`/scan/${item.scan_id}`)}
                    >
                      <td className="font-mono text-xs font-semibold text-indigo-600 dark:text-indigo-400">
                        {item.scan_id.substring(0, 8)}...
                      </td>
                      <td className="text-xs text-surface-600 dark:text-surface-400">
                        {formatDate(item.created_at)}
                      </td>
                      <td className="font-semibold text-surface-900 dark:text-white">
                        {item.total_urls}
                      </td>
                      <td>
                        <span className="text-xs font-semibold text-emerald-600 dark:text-emerald-400">
                          {item.online_count || 0}
                        </span>
                      </td>
                      <td>
                        <span className="text-xs font-semibold text-rose-600 dark:text-rose-400">
                          {item.offline_count || 0}
                        </span>
                      </td>
                      <td>
                        {issueCount > 0 ? (
                          <span className="text-xs font-semibold text-amber-600 dark:text-amber-400">
                            {issueCount}
                          </span>
                        ) : (
                          <span className="text-xs text-surface-400">0</span>
                        )}
                      </td>
                      <td>
                        <span className={`badge ${getScanStatusBadgeClass(item.status)}`}>
                          {item.status.toUpperCase()}
                        </span>
                      </td>
                      <td className="text-right">
                        <div
                          className="inline-flex items-center gap-1.5"
                          onClick={e => e.stopPropagation()}
                        >
                          <button
                            title="Download PDF"
                            onClick={() => handleDownloadReport(item.scan_id, 'pdf')}
                            disabled={isPdfDownloading}
                            className="p-1.5 rounded-lg hover:bg-surface-200 dark:hover:bg-surface-700 text-rose-600 dark:text-rose-400"
                          >
                            {isPdfDownloading ? (
                              <Loader2 className="w-3.5 h-3.5 animate-spin" />
                            ) : (
                              <FileText className="w-3.5 h-3.5" />
                            )}
                          </button>

                          <button
                            title="Download Excel"
                            onClick={() => handleDownloadReport(item.scan_id, 'excel')}
                            disabled={isXlsxDownloading}
                            className="p-1.5 rounded-lg hover:bg-surface-200 dark:hover:bg-surface-700 text-emerald-600 dark:text-emerald-400"
                          >
                            {isXlsxDownloading ? (
                              <Loader2 className="w-3.5 h-3.5 animate-spin" />
                            ) : (
                              <TableIcon className="w-3.5 h-3.5" />
                            )}
                          </button>

                          <Link
                            to={`/scan/${item.scan_id}`}
                            className="p-1.5 rounded-lg hover:bg-indigo-50 dark:hover:bg-indigo-950/40 text-indigo-600 dark:text-indigo-400 font-semibold text-xs inline-flex items-center gap-1"
                          >
                            <Eye className="w-3.5 h-3.5" />
                          </Link>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Bar */}
        {totalPages > 1 && (
          <div className="p-4 border-t border-surface-200 dark:border-surface-800 flex items-center justify-between">
            <span className="text-xs text-surface-500">
              Showing page {page} of {totalPages} ({total} audits)
            </span>
            <div className="flex items-center gap-2">
              <button
                disabled={page <= 1}
                onClick={() => setPage(p => Math.max(1, p - 1))}
                className="p-1.5 rounded-lg border border-surface-200 dark:border-surface-700 disabled:opacity-40"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <button
                disabled={page >= totalPages}
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                className="p-1.5 rounded-lg border border-surface-200 dark:border-surface-700 disabled:opacity-40"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
