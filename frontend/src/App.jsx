import { useEffect, useState } from "react";
import { getHealth } from "./services/api";

function App() {
  const [health, setHealth] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch((err) => setError(err.message));
  }, []);

  return (
    <div style={{ fontFamily: "sans-serif", maxWidth: 600, margin: "3rem auto" }}>
      <h1>IntelliDoc</h1>
      <h3>System status</h3>
      {error && <p style={{ color: "crimson" }}>Backend unreachable: {error}</p>}
      {!health && !error && <p>Checking backend...</p>}
      {health && (
        <ul>
          <li>API: {health.status}</li>
          <li>Database: {health.database}</li>
        </ul>
      )}
    </div>
  );
}

export default App;