import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AppLayout } from "./components/AppLayout";
import { GeneratePage } from "./features/generate/GeneratePage";
import { QualityPage } from "./features/quality/QualityPage";
import { ReversePage } from "./features/reverse/ReversePage";

const basename = import.meta.env.DEV ? undefined : "/app";

export function App() {
  return (
    <BrowserRouter basename={basename}>
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<Navigate to="/reverse" replace />} />
          <Route path="/reverse" element={<ReversePage />} />
          <Route path="/reverse/:projectId" element={<ReversePage />} />
          <Route path="/generate" element={<GeneratePage />} />
          <Route path="/quality" element={<QualityPage />} />
          <Route path="*" element={<Navigate to="/reverse" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
