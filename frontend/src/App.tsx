import { Compass } from "lucide-react";
import { Link, Route, Routes } from "react-router-dom";
import AppShell from "./components/AppShell";
import { Button, EmptyState } from "./components/ui";
import { ModelStatusProvider } from "./lib/modelStatus";
import Dashboard from "./pages/Dashboard";
import Evaluation from "./pages/Evaluation";
import HistoryPage from "./pages/History";
import Landing from "./pages/Landing";
import Library from "./pages/Library";
import NewVerification from "./pages/NewVerification";
import Results from "./pages/Results";
import SettingsPage from "./pages/Settings";

function NotFound() {
  return (
    <div className="mx-auto max-w-lg py-24">
      <EmptyState icon={Compass} title="Page not found" body="That page does not exist." action={<Link to="/app"><Button>Go to dashboard</Button></Link>} />
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/app" element={<ModelStatusProvider><AppShell /></ModelStatusProvider>}>
        <Route index element={<Dashboard />} />
        <Route path="verify" element={<NewVerification />} />
        <Route path="results/:id" element={<Results />} />
        <Route path="library" element={<Library />} />
        <Route path="history" element={<HistoryPage />} />
        <Route path="evaluation" element={<Evaluation />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
