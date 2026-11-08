import "./globals.css";
import "./mobile.css";
export const viewport = { width: "device-width", initialScale: 1, viewportFit: "cover", themeColor: "#12202b" };
export const metadata = {
  title: "NightShift AI | Oilfield Digital Twin",
  description:
    "An interactive 3D digital twin for oilfield water operations, recorded telemetry, and verified response planning.",
};
export default function Layout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
