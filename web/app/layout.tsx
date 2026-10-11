import type { Metadata } from "next";
import { Barlow, IBM_Plex_Mono } from "next/font/google";
import { Providers } from "@/components/pm/providers";
import "./globals.css";
import "./workspace.css";
import "./platform.css";
const barlow = Barlow({
  variable: "--font-barlow",
  weight: ["300", "400", "500", "600"],
  subsets: ["latin"],
  display: "swap",
});
const plexMono = IBM_Plex_Mono({
  variable: "--font-plex-mono",
  weight: ["400", "500"],
  subsets: ["latin"],
  display: "swap",
});
export const metadata: Metadata = {
  title: "BMW | Product Intelligence",
  description:
    "Customer evidence, product requirements and traceable PM decisions.",
  icons: { icon: "/brand/bmw-grey.svg" },
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${barlow.variable} ${plexMono.variable} antialiased`}
    >
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
