import { useState, useEffect, useCallback } from 'react';
import {
  X,
  ChevronLeft,
  ChevronRight,
  Download,
  ExternalLink,
  Camera,
  Search,
  Globe,
  Loader2,
} from 'lucide-react';
import { scanApi } from '../services/api';
import type { ScanResult } from '../types';
import { formatDate, getStatusBadgeClass, formatDomain, getScreenshotUrl } from '../utils/helpers';

export default function Screenshots() {
  const [items, setItems] = useState<ScanResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);

  const fetchScreenshots = useCallback(async () => {
    setLoading(true);
    try {
      const data = await scanApi.getScreenshots(100);
      setItems(data);
    } catch (err) {
      console.error('Failed to load screenshots gallery', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchScreenshots();
  }, [fetchScreenshots]);

  const filteredItems = items.filter(item => {
    const term = searchTerm.toLowerCase();
    return (
      (item.domain && item.domain.toLowerCase().includes(term)) ||
      (item.original_url && item.original_url.toLowerCase().includes(term)) ||
      (item.website_title && item.website_title.toLowerCase().includes(term))
    );
  });

  const activeItem = lightboxIndex !== null ? filteredItems[lightboxIndex] : null;

  return (
    <div className="space-y-8 animate-fade-in pb-16">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-extrabold text-surface-900 dark:text-white tracking-tight">
            Visual Rendering Gallery
          </h2>
          <p className="text-sm text-surface-500 dark:text-surface-400 mt-1">
            Browse automated Chromium full-page screenshots (1440 × 900) captured during audits.
          </p>
        </div>

        <div className="relative w-full sm:w-72">
          <input
            type="text"
            placeholder="Search domain in gallery..."
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
            className="input pl-9 text-xs"
          />
          <Search className="absolute left-3 top-2.5 w-3.5 h-3.5 text-surface-400" />
        </div>
      </div>

      {/* Gallery Grid */}
      {loading ? (
        <div className="p-16 text-center text-xs text-surface-400">
          <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2 text-indigo-500" />
          Loading visual captures...
        </div>
      ) : filteredItems.length === 0 ? (
        <div className="card p-12 text-center">
          <Camera className="w-10 h-10 mx-auto text-surface-300 dark:text-surface-700 mb-3" />
          <h3 className="text-base font-semibold text-surface-700 dark:text-surface-300">
            No screenshots found
          </h3>
          <p className="text-xs text-surface-400 dark:text-surface-500 mt-1">
            Screenshots are captured automatically for responsive websites during scan runs.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
          {filteredItems.map((item, index) => (
            <div
              key={item.id}
              onClick={() => setLightboxIndex(index)}
              className="card overflow-hidden group cursor-pointer hover:shadow-lg transition-all duration-200 border-surface-200 dark:border-surface-800"
            >
              {/* Thumbnail Container */}
              <div className="relative aspect-video bg-slate-900 overflow-hidden">
                <img
                  src={getScreenshotUrl(item.screenshot_path)}
                  alt={item.domain || item.original_url}
                  className="w-full h-full object-cover object-top transition-transform duration-300 group-hover:scale-105"
                  loading="lazy"
                />
                <div className="absolute inset-0 bg-slate-950/0 group-hover:bg-slate-950/20 transition-colors" />
                <div className="absolute top-2 right-2">
                  <span className={`badge ${getStatusBadgeClass(item.status)} shadow-sm`}>
                    {item.status}
                  </span>
                </div>
              </div>

              {/* Info footer */}
              <div className="p-4 space-y-1">
                <h4 className="text-sm font-bold text-surface-900 dark:text-white truncate">
                  {item.domain || formatDomain(item.original_url)}
                </h4>
                {item.website_title && (
                  <p className="text-xs text-surface-500 dark:text-surface-400 truncate">
                    {item.website_title}
                  </p>
                )}
                <div className="flex items-center justify-between text-[11px] text-surface-400 pt-2 border-t border-surface-100 dark:border-surface-800">
                  <span>{formatDate(item.created_at)}</span>
                  <span className="font-semibold text-indigo-600 dark:text-indigo-400">Preview</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Lightbox Modal */}
      {activeItem && lightboxIndex !== null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md animate-fade-in">
          {/* Close button */}
          <button
            onClick={() => setLightboxIndex(null)}
            className="absolute top-4 right-4 p-2.5 rounded-full bg-white/10 hover:bg-white/20 text-white transition-colors z-10"
          >
            <X className="w-5 h-5" />
          </button>

          {/* Prev / Next buttons */}
          {filteredItems.length > 1 && (
            <>
              <button
                onClick={() =>
                  setLightboxIndex((lightboxIndex - 1 + filteredItems.length) % filteredItems.length)
                }
                className="absolute left-4 top-1/2 -translate-y-1/2 p-3 rounded-full bg-white/10 hover:bg-white/20 text-white transition-colors"
              >
                <ChevronLeft className="w-6 h-6" />
              </button>

              <button
                onClick={() => setLightboxIndex((lightboxIndex + 1) % filteredItems.length)}
                className="absolute right-4 top-1/2 -translate-y-1/2 p-3 rounded-full bg-white/10 hover:bg-white/20 text-white transition-colors"
              >
                <ChevronRight className="w-6 h-6" />
              </button>
            </>
          )}

          {/* Lightbox Content Container */}
          <div className="card max-w-5xl w-full max-h-[92vh] flex flex-col overflow-hidden shadow-2xl bg-slate-900 border-slate-800 text-white">
            <div className="p-4 border-b border-slate-800 flex items-center justify-between shrink-0">
              <div className="flex items-center gap-3">
                <span className={`badge ${getStatusBadgeClass(activeItem.status)}`}>
                  {activeItem.status}
                </span>
                <span className="font-bold text-sm">
                  {activeItem.domain || activeItem.original_url}
                </span>
              </div>

              <div className="flex items-center gap-2">
                <a
                  href={getScreenshotUrl(activeItem.screenshot_path)}
                  download={`screenshot_${activeItem.domain}.png`}
                  className="btn-secondary text-xs py-1.5 px-3 bg-slate-800 text-slate-200 border-slate-700"
                >
                  <Download className="w-3.5 h-3.5" />
                  <span>Download Image</span>
                </a>
                <a
                  href={activeItem.final_url || activeItem.original_url}
                  target="_blank"
                  rel="noreferrer"
                  className="btn-secondary text-xs py-1.5 px-3 bg-slate-800 text-slate-200 border-slate-700"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  <span>Visit URL</span>
                </a>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-4 flex items-center justify-center bg-slate-950">
              <img
                src={getScreenshotUrl(activeItem.screenshot_path)}
                alt="Full screenshot"
                className="max-w-full h-auto max-h-[75vh] rounded object-contain shadow-2xl"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
