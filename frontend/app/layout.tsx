import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Executive Assistant",
  description: "Voice + text AI assistant for Google Calendar, Tasks & Contacts",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
