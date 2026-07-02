import { useEffect } from "react";

function App() {
  useEffect(() => {
    // Redirect to the DroZon standalone HTML app
    window.location.replace("/drozon.html");
  }, []);

  return (
    <div
      data-testid="drozon-redirect-loader"
      style={{
        position: "fixed",
        inset: 0,
        background: "#080b10",
        color: "#2e7fc4",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: "'JetBrains Mono', monospace",
        letterSpacing: "3px",
        fontSize: "14px",
      }}
    >
      LOADING DROZON…
    </div>
  );
}

export default App;
