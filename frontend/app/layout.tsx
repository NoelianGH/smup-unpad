import '../globals.css';

export const metadata = {
  title: 'smup-unpad',
  description: 'Next.js frontend for smup-unpad Express backend'
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
