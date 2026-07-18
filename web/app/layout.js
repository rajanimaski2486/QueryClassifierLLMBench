import "./globals.css";

export const metadata = {
  title: "Routing Bench — query classification leaderboard",
  description:
    "Benchmark of NVIDIA-hosted models on stock-image search query classification",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
