import DashboardGrid from "../components/DashboardGrid/DashboardGrid";
import StatusBar from "../components/StatusBar/StatusBar";

const slot = (t) => <div style={{ padding: 12 }}>{t}</div>;

export default function App() {
 return (
  <DashboardGrid
   statusBar={<StatusBar />}
   widgets={[
    { id: "email", title: "Email", element: slot("EMAIL WIDGET") },
    { id: "weather", title: "Vreme", element: slot("WEATHER WIDGET") },
    { id: "news", title: "Știri", element: slot("NEWS WIDGET") },
    { id: "system", title: "Sistem", element: slot("SYSTEM WIDGET") },
   ]}
  />
 );
}
