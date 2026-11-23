import { Routes, Route, Navigate } from 'react-router-dom';
import { useTheme } from './hooks/useTheme';
import MainLayout from './layouts/MainLayout';
import Dashboard from './pages/Dashboard';
import Scanner from './pages/Scanner';
import ScanResults from './pages/ScanResults';
import History from './pages/History';
import Screenshots from './pages/Screenshots';

export default function App() {
  const { theme, toggleTheme } = useTheme();

  return (
    <MainLayout theme={theme} toggleTheme={toggleTheme}>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/scanner" element={<Scanner />} />
        <Route path="/scan/:scanId" element={<ScanResults />} />
        <Route path="/history" element={<History />} />
        <Route path="/screenshots" element={<Screenshots />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </MainLayout>
  );
}
