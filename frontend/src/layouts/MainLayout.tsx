import React, { useState } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard,
  Search,
  Clock,
  Camera,
  Activity,
  Sun,
  Moon,
  Menu,
  X,
  ChevronLeft,
  ChevronRight,
  PlusCircle,
  ShieldCheck,
  Trash2,
  AlertTriangle,
  Loader2,
} from 'lucide-react';
import { scanApi } from '../services/api';
import type { ThemeMode } from '../types';

interface MainLayoutProps {
  children: React.ReactNode;
  theme: ThemeMode;
  toggleTheme: () => void;
}

export default function MainLayout({ children, theme, toggleTheme }: MainLayoutProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [showResetModal, setShowResetModal] = useState(false);
  const [isResetting, setIsResetting] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  const handleResetDb = async () => {
    setIsResetting(true);
    try {
      const res = await scanApi.resetDatabase();
      setShowResetModal(false);
      alert(`Database successfully reset! Removed ${res.deleted_images} screenshots and cleared all scans.`);
      window.location.href = '/';
    } catch (err: any) {
      alert(`Failed to reset database: ${err?.response?.data?.detail || err.message}`);
    } finally {
      setIsResetting(false);
    }
  };

  const getPageTitle = () => {
    const path = location.pathname;
    if (path === '/') return 'Dashboard';
    if (path.startsWith('/scanner')) return 'Website Scanner';
    if (path.startsWith('/scan/')) return 'Scan Results & Diagnostics';
    if (path.startsWith('/history')) return 'Scan History';
    if (path.startsWith('/screenshots')) return 'Visual Gallery';
    return 'WebPulse';
  };

  const navItems = [
    { name: 'Dashboard', path: '/', icon: LayoutDashboard },
    { name: 'Scanner', path: '/scanner', icon: Search },
    { name: 'Scan History', path: '/history', icon: Clock },
    { name: 'Screenshots', path: '/screenshots', icon: Camera },
  ];

  return (
    <div className="flex h-screen bg-slate-50 dark:bg-surface-950 overflow-hidden font-sans">
      {/* Mobile Backdrop */}
      {mobileMenuOpen && (
        <div
          className="fixed inset-0 z-40 bg-slate-900/50 backdrop-blur-sm lg:hidden"
          onClick={() => setMobileMenuOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed lg:static inset-y-0 left-0 z-50 flex flex-col border-r border-surface-200 dark:border-surface-800 bg-white dark:bg-surface-900 transition-all duration-300 ease-in-out ${
          collapsed ? 'w-20' : 'w-64'
        } ${mobileMenuOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}`}
      >
        {/* Brand */}
        <div className="flex items-center justify-between h-16 px-4 border-b border-surface-100 dark:border-surface-800">
          <div className="flex items-center gap-3 overflow-hidden cursor-pointer" onClick={() => navigate('/')}>
            <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-indigo-600 text-white shadow-md shadow-indigo-500/25 shrink-0">
              <Activity className="w-6 h-6 animate-pulse" />
            </div>
            {!collapsed && (
              <div className="flex flex-col">
                <span className="font-extrabold text-lg tracking-tight text-surface-900 dark:text-white leading-none">
                  Web<span className="text-indigo-600">Pulse</span>
                </span>
                <span className="text-[10px] font-medium text-surface-500 dark:text-surface-400 tracking-wider uppercase mt-1">
                  Health & DNS Audit
                </span>
              </div>
            )}
          </div>
          <button
            onClick={() => setMobileMenuOpen(false)}
            className="p-1 rounded-lg text-surface-500 hover:bg-surface-100 dark:hover:bg-surface-800 lg:hidden"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Navigation Links */}
        <div className="flex-1 py-6 px-3 space-y-1.5 overflow-y-auto">
          {navItems.map(item => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.path}
                to={item.path}
                onClick={() => setMobileMenuOpen(false)}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3.5 py-2.5 rounded-xl font-medium text-sm transition-all duration-150 group ${
                    isActive
                      ? 'bg-indigo-50 dark:bg-indigo-950/40 text-indigo-600 dark:text-indigo-400 font-semibold shadow-xs'
                      : 'text-surface-600 dark:text-surface-400 hover:bg-surface-100 dark:hover:bg-surface-800 hover:text-surface-900 dark:hover:text-surface-100'
                  }`
                }
              >
                <Icon className="w-5 h-5 shrink-0 transition-transform group-hover:scale-110" />
                {!collapsed && <span>{item.name}</span>}
              </NavLink>
            );
          })}
        </div>

        {/* Pro Banner / Status */}
        {!collapsed && (
          <div className="p-4 mx-3 mb-4 rounded-xl bg-gradient-to-br from-indigo-500/10 to-purple-500/10 border border-indigo-200/50 dark:border-indigo-800/40">
            <div className="flex items-center gap-2 text-indigo-700 dark:text-indigo-300 font-semibold text-xs mb-1">
              <ShieldCheck className="w-4 h-4" />
              <span>Enterprise Guard</span>
            </div>
            <p className="text-[11px] text-surface-600 dark:text-surface-400 leading-relaxed">
              SSRF Protected, DNS &amp; SSL Real-time Diagnostics
            </p>
          </div>
        )}

        {/* Footer Collapse Toggle */}
        <div className="p-3 border-t border-surface-100 dark:border-surface-800 hidden lg:flex items-center justify-between">
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="flex items-center justify-center w-full py-2 text-xs font-medium text-surface-500 hover:text-surface-800 dark:hover:text-surface-200 hover:bg-surface-100 dark:hover:bg-surface-800 rounded-lg transition-colors gap-2"
          >
            {collapsed ? (
              <ChevronRight className="w-4 h-4" />
            ) : (
              <>
                <ChevronLeft className="w-4 h-4" />
                <span>Collapse Sidebar</span>
              </>
            )}
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex flex-col flex-1 h-screen overflow-hidden">
        {/* Top Header */}
        <header className="h-16 border-b border-surface-200 dark:border-surface-800 bg-white/80 dark:bg-surface-900/80 backdrop-blur-md px-6 flex items-center justify-between z-10 shrink-0">
          <div className="flex items-center gap-4">
            <button
              onClick={() => setMobileMenuOpen(true)}
              className="p-2 -ml-2 rounded-lg text-surface-600 hover:bg-surface-100 dark:text-surface-300 dark:hover:bg-surface-800 lg:hidden"
            >
              <Menu className="w-5 h-5" />
            </button>
            <h1 className="text-xl font-bold text-surface-900 dark:text-white tracking-tight">
              {getPageTitle()}
            </h1>
          </div>

          <div className="flex items-center gap-3">
            {/* Reset Database Button */}
            <button
              onClick={() => setShowResetModal(true)}
              className="px-3 py-2 text-xs font-semibold rounded-xl border border-rose-200 dark:border-rose-900/50 bg-rose-50/50 dark:bg-rose-950/20 text-rose-600 dark:text-rose-400 hover:bg-rose-100 dark:hover:bg-rose-950/40 flex items-center gap-1.5 transition-colors shadow-xs"
              title="Reset database & delete all images"
            >
              <Trash2 className="w-3.5 h-3.5 text-rose-500" />
              <span>Reset DB</span>
            </button>

            <button
              onClick={() => navigate('/scanner')}
              className="btn-primary text-xs py-2 px-3.5 hidden sm:inline-flex"
            >
              <PlusCircle className="w-4 h-4" />
              <span>Quick Scan</span>
            </button>

            {/* Theme Toggle */}
            <button
              onClick={toggleTheme}
              aria-label="Toggle theme"
              className="p-2.5 rounded-xl border border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 text-surface-600 dark:text-surface-300 hover:bg-surface-50 dark:hover:bg-surface-700 transition-colors shadow-xs"
            >
              {theme === 'dark' ? <Sun className="w-4 h-4 text-amber-400" /> : <Moon className="w-4 h-4 text-indigo-600" />}
            </button>
          </div>
        </header>

        {/* Page Content Viewport */}
        <main className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8">
          <div className="max-w-7xl mx-auto">{children}</div>
        </main>
      </div>

      {/* Confirmation Modal for Resetting Database */}
      {showResetModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-fade-in">
          <div className="bg-white dark:bg-surface-900 border border-surface-200 dark:border-surface-800 rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-rose-100 dark:bg-rose-950/60 flex items-center justify-center text-rose-600 dark:text-rose-400 shrink-0">
                <AlertTriangle className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-lg font-bold text-surface-900 dark:text-white">
                  Reset Database &amp; Storage
                </h3>
                <p className="text-xs text-surface-500 dark:text-surface-400">
                  Permanent data erasure confirmation
                </p>
              </div>
            </div>

            <p className="text-sm text-surface-600 dark:text-surface-300 leading-relaxed">
              Are you sure you want to completely reset the database? This action will permanently delete:
            </p>

            <ul className="text-xs text-surface-500 dark:text-surface-400 space-y-1.5 list-disc pl-5">
              <li>All historical scan runs and audit logs</li>
              <li>All URL scan results, DNS records, and SSL details</li>
              <li>All cached screenshots and PDF/Excel reports</li>
            </ul>

            <div className="flex items-center justify-end gap-3 pt-3 border-t border-surface-100 dark:border-surface-800">
              <button
                type="button"
                disabled={isResetting}
                onClick={() => setShowResetModal(false)}
                className="btn-secondary text-xs py-2 px-4"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={isResetting}
                onClick={handleResetDb}
                className="px-4 py-2 text-xs font-semibold rounded-xl bg-rose-600 hover:bg-rose-700 text-white flex items-center gap-2 shadow-sm transition-colors disabled:opacity-50"
              >
                {isResetting ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Resetting...</span>
                  </>
                ) : (
                  <>
                    <Trash2 className="w-3.5 h-3.5" />
                    <span>Yes, Reset Everything</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
