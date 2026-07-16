import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "XWGen Studio — Crossword Constructor",
  description: "Design, inspect, fill, and export American-style crossword grids.",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
