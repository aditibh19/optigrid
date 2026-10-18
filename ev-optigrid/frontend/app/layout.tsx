import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";
import { AuthProvider } from "@/components/AuthProvider";
import Shell from "@/components/Shell";

export const metadata: Metadata = {
  title: "EV-OptiGrid",
  description: "Personalised EV charging decisions, explained: when, where and how much to charge.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>
          <Shell>{children}</Shell>
        </AuthProvider>
      </body>
    </html>
  );
}
