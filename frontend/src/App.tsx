import "./App.css";
import "./styles/shared.css";
import "./styles/dashboard.css";
import "./styles/passDetail.css";
import "./styles/visualizations.css";

import SpectralHero from "./components/SpectralHero";
import { useBackendHealth } from "./hooks/useBackendHealth";
import Dashboard from "./pages/Dashboard";

const STATUS_LABEL: Record<string, string> = {
  checking: "Checking...",
  online: "Online",
  offline: "Offline",
};

// This app is a single page ("mission control" - see pages/Dashboard.tsx):
// location, satellite picker, preferences, the ranked mission queue, and
// the selected pass's dossier are all visible together, with no separate
// "pages" or routes to navigate between.
//
// Earlier versions of this header showed the current build phase (e.g.
// "Phase 8 - Frontend MVP") as a visible eyebrow line. That, and every
// other visitor-facing sign of build/phase progression, has been removed
// site-wide - development phases are a project-management detail for us,
// not something an actual visitor to the site needs to see.
//
// The animated spectral-band graphic (SpectralHero) originally ran as a
// tall banner right under the header, pushing the location/satellite/
// preferences controls further down the page. It's purely decorative, so
// it now lives as a slim closing flourish in the footer instead, keeping
// the top of the page focused on the controls and the mission queue - a
// thin gradient divider under the header keeps the same visual identity
// without costing vertical space there.
function App() {
  const { status } = useBackendHealth();

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <p className="masthead__eyebrow">Mission Control // Observation Deck</p>
          <h1 className="app-header__title">Satellite Observation &amp; Pass Prediction</h1>
        </div>
        <span className="app-header__status">
          <span className={`status-dot status-dot--${status}`} aria-hidden="true" />
          {STATUS_LABEL[status]}
        </span>
      </header>

      <div className="spectral-divider app-header__divider" aria-hidden="true" />

      <main className="app-main">
        <Dashboard />
      </main>

      <footer className="app-footer">
        <SpectralHero className="spectral-hero--footer" />
        <p className="app-footer__text">
          Observation Suitability Score is a heuristic ranking of observing conditions, not a
          probability of successfully seeing a satellite.
        </p>
      </footer>
    </div>
  );
}

export default App;
