import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  Globe,
  CheckCircle,
  XCircle,
  AlertTriangle,
  ShieldAlert,
  Timer,
  ArrowRight,
  Search,
  RefreshCw,
  Activity,
  Calendar,
  ExternalLink,
} from 'lucide-react';
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
  BarChart,
  Bar,
  XAxis,
  YAxis,
} from 'recharts';
import { scanApi } from '../services/api';
import type { DashboardStats } from '../types';
import {
  formatDate,
  formatResponseTime,
  getScanStatusBadgeClass,
} from '../utils/helpers';

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const fetchStats = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await scanApi.getDashboard();
      setStats(data);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to load dashboard data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStats();
  }, []);

  // Compute charts
  const statusPieData = stats
    ? [
        { name: 'Online', value: stats.online_count, color: '#10b981' },
        { name: 'Offline', value: stats.offline_count, color: '#ef4444' },
        { name: 'DNS Errors', value: stats.dns_errors, color: '#f59e0b' },
        { name: 'SSL Issues', value: stats.ssl_issues, color: '#ec4899' },
      ].filter(d => d.value > 0)
    : [];

  const total = stats?.total_scanned || 0;
  const online = stats?.online_count || 0;
  const availabilityPct = total > 0 ? ((online / total) * 100).toFixed(1) : '100.0';

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Welcome & Actions Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-gradient-to-r from-indigo-900 via-indigo-800 to-slate-900 rounded-2xl p-6 md:p-8 text-white shadow-xl shadow-indigo-950/10">
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-indigo-300 text-xs font-semibold uppercase tracking-wider">
            <Activity className="w-4 h-4 text-indigo-400" />
            <span>Real-time System Overview</span>
          </div>
          <h2 className="text-2xl md:text-3xl font-extrabold tracking-tight">
            WebPulse Health &amp; DNS Monitor
          </h2>
          <p className="text-slate-300 text-sm max-w-xl">
            Audit website reachability, DNS health, SSL certificates, and visual renderings across your fleet.
          </p>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          <button
            onClick={() => navigate('/scanner')}
            className="btn bg-white text-indigo-900 hover:bg-slate-100 font-semibold px-5 py-2.5 rounded-xl shadow-md transition-transform hover:scale-105"
          >
            <Search className="w-4 h-4" />
            <span>Launch Audit</span>
          </button>
          <button
            onClick={fetchStats}
            title="Refresh statistics"
            className="p-2.5 rounded-xl bg-white/10 hover:bg-white/20 text-white transition-colors"
          >
            <RefreshCw className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900/50 text-rose-700 dark:text-rose-400 text-sm flex items-center justify-between">
          <span>{error}</span>
          <button onClick={fetchStats} className="underline font-semibold hover:text-rose-900">
            Retry
          </button>
        </div>
      )}

      {/* KPI Cards Grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        {/* Total Scanned */}
        <div className="card p-5 flex flex-col justify-between hover:shadow-md transition-shadow">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-surface-500 dark:text-surface-400">Total Scanned</span>
            <div className="p-2 rounded-lg bg-indigo-50 dark:bg-indigo-950/50 text-indigo-600 dark:text-indigo-400">
              <Globe className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3">
            <span className="text-2xl md:text-3xl font-bold tracking-tight text-surface-900 dark:text-white">
              {loading ? '—' : stats?.total_scanned ?? 0}
            </span>
          </div>
        </div>

        {/* Online */}
        <div className="card p-5 flex flex-col justify-between hover:shadow-md transition-shadow">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-surface-500 dark:text-surface-400">Online</span>
            <div className="p-2 rounded-lg bg-emerald-50 dark:bg-emerald-950/50 text-emerald-600 dark:text-emerald-400">
              <CheckCircle className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3">
            <span className="text-2xl md:text-3xl font-bold tracking-tight text-emerald-600 dark:text-emerald-400">
              {loading ? '—' : stats?.online_count ?? 0}
            </span>
          </div>
        </div>

        {/* Offline */}
        <div className="card p-5 flex flex-col justify-between hover:shadow-md transition-shadow">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-surface-500 dark:text-surface-400">Offline</span>
            <div className="p-2 rounded-lg bg-rose-50 dark:bg-rose-950/50 text-rose-600 dark:text-rose-400">
              <XCircle className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3">
            <span className="text-2xl md:text-3xl font-bold tracking-tight text-rose-600 dark:text-rose-400">
              {loading ? '—' : stats?.offline_count ?? 0}
            </span>
          </div>
        </div>

        {/* DNS Errors */}
        <div className="card p-5 flex flex-col justify-between hover:shadow-md transition-shadow">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-surface-500 dark:text-surface-400">DNS Errors</span>
            <div className="p-2 rounded-lg bg-amber-50 dark:bg-amber-950/50 text-amber-600 dark:text-amber-400">
              <AlertTriangle className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3">
            <span className="text-2xl md:text-3xl font-bold tracking-tight text-amber-600 dark:text-amber-400">
              {loading ? '—' : stats?.dns_errors ?? 0}
            </span>
          </div>
        </div>

        {/* SSL Problems */}
        <div className="card p-5 flex flex-col justify-between hover:shadow-md transition-shadow">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-surface-500 dark:text-surface-400">SSL Problems</span>
            <div className="p-2 rounded-lg bg-pink-50 dark:bg-pink-950/50 text-pink-600 dark:text-pink-400">
              <ShieldAlert className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3">
            <span className="text-2xl md:text-3xl font-bold tracking-tight text-pink-600 dark:text-pink-400">
              {loading ? '—' : stats?.ssl_issues ?? 0}
            </span>
          </div>
        </div>

        {/* Avg Response Time */}
        <div className="card p-5 flex flex-col justify-between hover:shadow-md transition-shadow">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-surface-500 dark:text-surface-400">Avg Latency</span>
            <div className="p-2 rounded-lg bg-purple-50 dark:bg-purple-950/50 text-purple-600 dark:text-purple-400">
              <Timer className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3">
            <span className="text-2xl md:text-3xl font-bold tracking-tight text-surface-900 dark:text-white">
              {loading ? '—' : formatResponseTime(stats?.avg_response_time)}
            </span>
          </div>
        </div>
      </div>

      {/* Charts Section */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Availability Dial Card */}
        <div className="card p-6 flex flex-col justify-between">
          <div>
            <h3 className="text-base font-bold text-surface-900 dark:text-white">
              Availability Percentage
            </h3>
            <p className="text-xs text-surface-500 dark:text-surface-400 mt-1">
              Ratio of successfully reachable endpoints
            </p>
          </div>

          <div className="flex flex-col items-center justify-center py-6">
            <div className="relative flex items-center justify-center w-40 h-40">
              <svg className="w-full h-full transform -rotate-90">
                <circle
                  cx="80"
                  cy="80"
                  r="64"
                  stroke="currentColor"
                  strokeWidth="12"
                  className="text-surface-200 dark:text-surface-800"
                  fill="transparent"
                />
                <circle
                  cx="80"
                  cy="80"
                  r="64"
                  stroke="currentColor"
                  strokeWidth="12"
                  className="text-emerald-500 transition-all duration-1000 ease-out"
                  fill="transparent"
                  strokeDasharray={2 * Math.PI * 64}
                  strokeDashoffset={2 * Math.PI * 64 * (1 - (stats?.total_scanned ? online / stats.total_scanned : 1))}
                  strokeLinecap="round"
                />
              </svg>
              <div className="absolute flex flex-col items-center">
                <span className="text-3xl font-extrabold text-surface-900 dark:text-white">
                  {loading ? '—' : `${availabilityPct}%`}
                </span>
                <span className="text-[10px] uppercase font-bold text-emerald-600 dark:text-emerald-400 tracking-wider">
                  Health
                </span>
              </div>
            </div>

            <div className="flex items-center gap-6 mt-4 text-xs">
              <div className="flex items-center gap-2">
                <div className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
                <span className="text-surface-600 dark:text-surface-400">Online ({online})</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-2.5 h-2.5 rounded-full bg-rose-500" />
                <span className="text-surface-600 dark:text-surface-400">Offline ({stats?.offline_count || 0})</span>
              </div>
            </div>
          </div>

          <div className="pt-4 border-t border-surface-100 dark:border-surface-800 text-xs text-surface-500 flex justify-between">
            <span>Audit Reliability</span>
            <span className="font-semibold text-surface-700 dark:text-surface-300">Continuous</span>
          </div>
        </div>

        {/* Status Breakdown Donut Chart */}
        <div className="card p-6 flex flex-col justify-between lg:col-span-2">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-base font-bold text-surface-900 dark:text-white">
                Website Status Distribution
              </h3>
              <p className="text-xs text-surface-500 dark:text-surface-400 mt-1">
                Breakdown of response states from the latest audit data
              </p>
            </div>
          </div>

          <div className="h-64 flex items-center justify-center">
            {statusPieData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={statusPieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={90}
                    paddingAngle={4}
                    dataKey="value"
                  >
                    {statusPieData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#1e293b',
                      borderColor: '#334155',
                      borderRadius: '8px',
                      color: '#fff',
                      fontSize: '12px',
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="text-center text-surface-400 text-xs py-10">
                <Globe className="w-10 h-10 mx-auto text-surface-300 dark:text-surface-700 mb-2" />
                <span>No audit status data available yet. Start your first scan!</span>
              </div>
            )}
          </div>

          {/* Legend */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-4 border-t border-surface-100 dark:border-surface-800">
            <div className="flex items-center gap-2 text-xs">
              <span className="w-3 h-3 rounded-md bg-emerald-500" />
              <span className="text-surface-600 dark:text-surface-300 font-medium">Online ({stats?.online_count || 0})</span>
            </div>
            <div className="flex items-center gap-2 text-xs">
              <span className="w-3 h-3 rounded-md bg-rose-500" />
              <span className="text-surface-600 dark:text-surface-300 font-medium">Offline ({stats?.offline_count || 0})</span>
            </div>
            <div className="flex items-center gap-2 text-xs">
              <span className="w-3 h-3 rounded-md bg-amber-500" />
              <span className="text-surface-600 dark:text-surface-300 font-medium">DNS Errors ({stats?.dns_errors || 0})</span>
            </div>
            <div className="flex items-center gap-2 text-xs">
              <span className="w-3 h-3 rounded-md bg-pink-500" />
              <span className="text-surface-600 dark:text-surface-300 font-medium">SSL Issues ({stats?.ssl_issues || 0})</span>
            </div>
          </div>
        </div>
      </div>

      {/* Recent Scans Table */}
      <div className="card overflow-hidden">
        <div className="p-6 border-b border-surface-200 dark:border-surface-800 flex items-center justify-between">
          <div>
            <h3 className="text-base font-bold text-surface-900 dark:text-white">Recent Scans</h3>
            <p className="text-xs text-surface-500 dark:text-surface-400 mt-0.5">
              History of the latest audits performed across targets
            </p>
          </div>
          <Link
            to="/history"
            className="text-xs font-semibold text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 flex items-center gap-1.5"
          >
            <span>View Full History</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>

        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>Scan ID</th>
                <th>Executed At</th>
                <th>Websites</th>
                <th>Online</th>
                <th>Issues</th>
                <th>Status</th>
                <th className="text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={7} className="text-center py-8 text-surface-400 text-xs">
                    Loading recent scans...
                  </td>
                </tr>
              ) : !stats?.recent_scans || stats.recent_scans.length === 0 ? (
                <tr>
                  <td colSpan={7} className="text-center py-12">
                    <Activity className="w-8 h-8 mx-auto text-surface-300 dark:text-surface-700 mb-2" />
                    <p className="text-sm font-semibold text-surface-600 dark:text-surface-400">
                      No scan history found
                    </p>
                    <p className="text-xs text-surface-400 dark:text-surface-500 mt-1">
                      Run your first scan to populate real-time diagnostics.
                    </p>
                    <button
                      onClick={() => navigate('/scanner')}
                      className="btn-primary text-xs py-2 px-4 mt-4"
                    >
                      <Search className="w-3.5 h-3.5" />
                      <span>Start First Scan</span>
                    </button>
                  </td>
                </tr>
              ) : (
                stats.recent_scans.map(item => {
                  const issueCount = (item.offline_count || 0) + (item.dns_errors || 0) + (item.ssl_issues || 0);
                  return (
                    <tr key={item.scan_id} className="cursor-pointer" onClick={() => navigate(`/scan/${item.scan_id}`)}>
                      <td className="font-mono text-xs font-semibold text-indigo-600 dark:text-indigo-400">
                        {item.scan_id.substring(0, 8)}...
                      </td>
                      <td className="text-surface-600 dark:text-surface-400 text-xs">
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
                        {issueCount > 0 ? (
                          <span className="text-xs font-semibold text-rose-600 dark:text-rose-400">
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
                        <Link
                          to={`/scan/${item.scan_id}`}
                          className="p-1.5 text-xs text-indigo-600 dark:text-indigo-400 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 rounded-lg inline-flex items-center gap-1 font-semibold"
                          onClick={e => e.stopPropagation()}
                        >
                          <span>Review</span>
                          <ExternalLink className="w-3 h-3" />
                        </Link>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
