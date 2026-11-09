import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "Capstone — Intelligent Vehicle Loan Advisor",
  description:
    "Policy-grounded, explainable vehicle-loan eligibility (capstone, synthetic data).",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
