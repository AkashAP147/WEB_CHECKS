import { useState, useCallback, useRef, useEffect } from 'react';
import { scanApi } from '../services/api';
import type { Scan, ScanResult } from '../types';

export const ACTIVE_SCAN_STORAGE_KEY = 'webpulse_active_scan_id';

export function useScan() {
  const [scan, setScan] = useState<Scan | null>(null);
  const [results, setResults] = useState<ScanResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const lastCompletedRef = useRef<number>(-1);
  const lastStatusRef = useRef<string>('');

  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  const clearScan = useCallback(() => {
    stopPolling();
    try {
      localStorage.removeItem(ACTIVE_SCAN_STORAGE_KEY);
    } catch {
      // ignore storage errors
    }
    setScan(null);
    setResults([]);
    setError(null);
    lastCompletedRef.current = -1;
    lastStatusRef.current = '';
  }, [stopPolling]);

  const startPolling = useCallback(
    (scanId: string) => {
      stopPolling();
      lastCompletedRef.current = -1;
      lastStatusRef.current = '';
      pollingRef.current = setInterval(async () => {
        try {
          const scanData = await scanApi.getScan(scanId);
          setScan(scanData);

          const hasProgress = scanData.completed_urls !== lastCompletedRef.current;
          const statusChanged = scanData.status !== lastStatusRef.current;
          lastCompletedRef.current = scanData.completed_urls;
          lastStatusRef.current = scanData.status;

          // Only fetch full results array when there is new progress or terminal status
          if (hasProgress || statusChanged) {
            const resultsData = await scanApi.getScanResults(scanId);
            setResults(Array.isArray(resultsData) ? resultsData : ((resultsData as any)?.results || []));
          }

          if (
            scanData.status === 'completed' ||
            scanData.status === 'cancelled' ||
            scanData.status === 'failed'
          ) {
            stopPolling();
          }
        } catch {
          // Keep polling quietly
        }
      }, 600);
    },
    [stopPolling]
  );

  const startScan = useCallback(
    async (urls: string[]) => {
      setLoading(true);
      setError(null);
      setResults([]);
      try {
        const response = await scanApi.startScan(urls);
        try {
          localStorage.setItem(ACTIVE_SCAN_STORAGE_KEY, response.scan_id);
        } catch {
          // ignore storage errors
        }
        const scanData = await scanApi.getScan(response.scan_id);
        setScan(scanData);
        startPolling(response.scan_id);
        return response.scan_id;
      } catch (err: any) {
        const msg = err.response?.data?.detail || err.message || 'Failed to start scan';
        setError(msg);
        throw new Error(msg);
      } finally {
        setLoading(false);
      }
    },
    [startPolling]
  );

  const uploadExcelScan = useCallback(
    async (file: File) => {
      setLoading(true);
      setError(null);
      setResults([]);
      try {
        const response = await scanApi.uploadExcelScan(file);
        try {
          localStorage.setItem(ACTIVE_SCAN_STORAGE_KEY, response.scan_id);
        } catch {
          // ignore storage errors
        }
        const scanData = await scanApi.getScan(response.scan_id);
        setScan(scanData);
        startPolling(response.scan_id);
        return response.scan_id;
      } catch (err: any) {
        const msg = err.response?.data?.detail || err.message || 'Failed to upload Excel file';
        setError(msg);
        throw new Error(msg);
      } finally {
        setLoading(false);
      }
    },
    [startPolling]
  );

  const cancelScan = useCallback(async () => {
    if (!scan) return;
    try {
      await scanApi.cancelScan(scan.id);
      stopPolling();
      setScan(prev => (prev ? { ...prev, status: 'cancelled' } : null));
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to cancel scan');
    }
  }, [scan, stopPolling]);

  const loadScan = useCallback(
    async (scanId: string) => {
      setLoading(true);
      setError(null);
      try {
        localStorage.setItem(ACTIVE_SCAN_STORAGE_KEY, scanId);
      } catch {
        // ignore storage errors
      }
      try {
        const scanData = await scanApi.getScan(scanId);
        setScan(scanData);
        const resultsData = await scanApi.getScanResults(scanId);
        setResults(Array.isArray(resultsData) ? resultsData : ((resultsData as any)?.results || []));

        if (scanData.status === 'running' || scanData.status === 'pending') {
          startPolling(scanId);
        }
      } catch (err: any) {
        setError(err.response?.data?.detail || 'Failed to load scan');
      } finally {
        setLoading(false);
      }
    },
    [startPolling]
  );

  // Restore active scan from localStorage on mount so switching tabs never loses progress
  useEffect(() => {
    try {
      const activeScanId = localStorage.getItem(ACTIVE_SCAN_STORAGE_KEY);
      if (activeScanId && !scan) {
        loadScan(activeScanId);
      }
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    return () => stopPolling();
  }, [stopPolling]);

  return {
    scan,
    results,
    loading,
    error,
    startScan,
    uploadExcelScan,
    cancelScan,
    loadScan,
    clearScan,
    setError,
  };
}
