import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import HomePage from "./pages/HomePage";
import SettingsPage from "./pages/SettingsPage";
import CoursesPage from "./pages/CoursesPage";
import PlayerPage from "./pages/PlayerPage";
import PathsPage, { PathDetailPage } from "./pages/PathsPage";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<HomePage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="courses" element={<CoursesPage />} />
        <Route path="paths" element={<PathsPage />} />
        <Route path="paths/:slug" element={<PathDetailPage />} />
        <Route path="player/:roomCode" element={<PlayerPage />} />
      </Route>
    </Routes>
  );
}
