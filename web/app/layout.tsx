import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  metadataBase: new URL(process.env.PUBLIC_SITE_URL ?? "http://localhost:3000"),
  title: "财务披露质询分析 | SEC Review Lab",
  description:
    "上传财务披露文件，基于 SEC 审查框架生成有依据、可追溯的监管质询问题。",
  openGraph: {
    type: "website",
    title: "财务披露质询分析 | SEC Review Lab",
    description: "从财务披露中生成有文件依据、规则依据和拟答复策略的 SEC 质询。",
    images: [{ url: "/og.png", width: 1200, height: 630 }],
  },
  twitter: {
    card: "summary_large_image",
    title: "财务披露质询分析 | SEC Review Lab",
    description: "从财务披露中生成有依据、可追溯的 SEC 质询。",
    images: ["/og.png"],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
