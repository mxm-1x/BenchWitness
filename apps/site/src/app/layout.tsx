import type { Metadata } from "next";
import "../globals.css";

export const metadata: Metadata = {
  title: "BenchWitness — Graph-Native ML Evaluation Integrity",
  description:
    "Discover exact training/evaluation source-record overlap through FalkorDB, trace blast radius across evaluation claims, and perform approved, versioned recovery.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col bg-white text-neutral-950 selection:bg-neutral-900 selection:text-white">
        {children}
      </body>
    </html>
  );
}
