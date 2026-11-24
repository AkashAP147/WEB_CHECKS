import axios from 'axios';
import type { Scan, ScanResult, DashboardStats, ScanHistoryItem, DNSRecord, SSLDetail } from '../types';

const api = axios.create({
  baseURL: '/api',
  timeout: 120000,
});

export const scanApi = {
  startScan: async (urls: string[]): Promise<{ scan_id: string; status: string; total_urls: number; created_at: string }> => {
    const { data } = await api.post('/scan', { urls });
    return data;
  },

  uploadExcelScan: async (file: File): Promise<{ scan_id: string; status: string; total_urls: number; created_at: string }> => {
    const formData = new FormData();
    formData.append('file', file);
    const { data } = await api.post('/scan', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
  },

  getScan: async (scanId: string): Promise<Scan> => {
    const { data } = await api.get(`/scan/${scanId}`);
    return data;
  },

  getScanResults: async (scanId: string): Promise<ScanResult[]> => {
    const { data } = await api.get(`/scan/${scanId}/results`);
    return Array.isArray(data) ? data : data?.results || [];
  },

  cancelScan: async (scanId: string): Promise<void> => {
    await api.post(`/scan/${scanId}/cancel`);
  },

  getHistory: async (params?: { limit?: number; offset?: number; search?: string; status?: string }): Promise<{ items: ScanHistoryItem[]; total: number }> => {
    const { data } = await api.get('/history', { params });
    if (Array.isArray(data)) {
      return { items: data, total: data.length };
    }
    return { items: data?.items || [], total: data?.total ?? (data?.items?.length || 0) };
  },

  getScreenshots: async (limit: number = 60): Promise<ScanResult[]> => {
    const { data } = await api.get('/screenshots', { params: { limit } });
    return Array.isArray(data) ? data : [];
  },

  getDashboard: async (): Promise<DashboardStats> => {
    const { data } = await api.get('/dashboard');
    return data;
  },

  getDNSRecords: async (domain: string): Promise<{ records: DNSRecord[]; resolved_ipv4: string[]; resolved_ipv6: string[]; nameservers: string[]; mail_servers: string[]; spf_record: string | null; dmarc_record: string | null }> => {
    const { data } = await api.get(`/dns/${domain}`);
    return data;
  },

  getSSLDetails: async (domain: string): Promise<SSLDetail> => {
    const { data } = await api.get(`/ssl/${domain}`);
    return data;
  },

  downloadPDF: async (scanId: string, batch?: number): Promise<Blob> => {
    const url = batch ? `/reports/${scanId}/pdf?batch=${batch}` : `/reports/${scanId}/pdf`;
    const { data } = await api.get(url, { responseType: 'blob', timeout: 0 });
    return data;
  },

  downloadExcel: async (scanId: string): Promise<Blob> => {
    const { data } = await api.get(`/reports/${scanId}/excel`, { responseType: 'blob', timeout: 0 });
    return data;
  },

  downloadCSV: async (scanId: string): Promise<Blob> => {
    const { data } = await api.get(`/reports/${scanId}/csv`, { responseType: 'blob', timeout: 0 });
    return data;
  },

  exportTimeRangePDF: async (params?: { startDate?: string; endDate?: string; preset?: string; status?: string }): Promise<Blob> => {
    const { data } = await api.get('/reports/export/pdf', {
      params: {
        start_date: params?.startDate,
        end_date: params?.endDate,
        preset: params?.preset,
        status: params?.status,
      },
      responseType: 'blob',
      timeout: 0,
    });
    return data;
  },

  exportTimeRangeExcel: async (params?: { startDate?: string; endDate?: string; preset?: string; status?: string }): Promise<Blob> => {
    const { data } = await api.get('/reports/export/excel', {
      params: {
        start_date: params?.startDate,
        end_date: params?.endDate,
        preset: params?.preset,
        status: params?.status,
      },
      responseType: 'blob',
      timeout: 0,
    });
    return data;
  },

  resetDatabase: async (): Promise<{ success: boolean; message: string; deleted_images: number; deleted_reports: number }> => {
    const { data } = await api.post('/database/reset');
    return data;
  },
};

export default api;
