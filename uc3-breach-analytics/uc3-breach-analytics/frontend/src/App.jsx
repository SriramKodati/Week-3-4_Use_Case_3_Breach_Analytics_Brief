import { useEffect, useState } from "react";
import Upload from "./pages/Upload.jsx";
import ComingSoon from "./pages/ComingSoon.jsx";

export default function App() {
  const [tab, setTab] = useState("upload");
  useEffect(() => { document.documentElement.setAttribute("data-theme", "dark"); }, []);

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="brand"><span className="brand-mark" /><span className="brand-name">Breach Analytics</span></div>
        <nav className="nav-tabs">
          <button className={`nav-tab ${tab === "upload" ? "active" : ""}`} onClick={() => setTab("upload")}>Upload & Queue</button>
          <button className={`nav-tab ${tab === "persons" ? "active" : ""}`} onClick={() => setTab("persons")}>Exposure Table</button>
          <button className={`nav-tab ${tab === "review" ? "active" : ""}`} onClick={() => setTab("review")}>Review Queue</button>
        </nav>
      </header>
      <main className="app-main">
        {tab === "upload" && <Upload />}
        {tab === "persons" && <ComingSoon feature="The exposure table" day="Tuesday-Wednesday" />}
        {tab === "review" && <ComingSoon feature="The review queue" day="Wednesday" />}
      </main>
    </div>
  );
}
