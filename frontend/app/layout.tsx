import type { Metadata } from "next";
import { Space_Grotesk, Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import TopNav from "@/components/TopNav";
import Providers from "./providers";

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-space-grotesk",
  weight: ["500", "700"],
});

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  weight: ["400", "500", "600"],
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "HardwareFabric — Fabric Builder",
  description: "Configure and instantly procure consumer, workstation, and rackmount hardware.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${spaceGrotesk.variable} ${inter.variable} ${jetbrainsMono.variable}`}>
      <body className="circuit-substrate min-h-screen font-body">
        <Providers>
          <TopNav />
          <main className="mx-auto max-w-[1600px] px-6 pb-16 pt-6">{children}</main>
        </Providers>
      </body>
    </html>
  );
}
