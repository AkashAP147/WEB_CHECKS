import { useState, useCallback, useRef, useEffect } from 'react';
import { scanApi } from '../services/api';
import type { Scan, ScanResult } from '../types';

export function useScan() {
  const [scan, setScan] = useState<Scan | null>(null);
  const [results, setResults] = useState<ScanResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  const startPolling = useCallback(
    (scanId: string) => {
      stopPolling();
      pollingRef.current = setInterval(async () => {
        try {
          const scanData = await scanApi.getScan(scanId);
          setScan(scanData);
          const resultsData = await scanApi.getScanResults(scanId);
          setResults(Array.isArray(resultsData) ? resultsData : ((resultsData as any)?.results || []));

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
      }, 1500);
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
    setError,
  };
}
