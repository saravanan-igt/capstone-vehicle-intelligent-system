import { Montserrat_Alternates } from "next/font/google";
import type { SVGProps } from "react";

// Downloaded at build time and self-hosted by Next.js; browsers never contact Google.
const wordmark = Montserrat_Alternates({
  subsets: ["latin"],
  weight: "800",
  display: "swap",
});

// Shield = published lending policy, car = vehicle finance, check = deterministic eligibility decision.
export function LogoMark(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 40 40"
      width={34}
      height={34}
      aria-hidden="true"
      {...props}
    >
      <rect width="40" height="40" rx="10" fill="#fff" />
      <path
        d="M20 3 34 8v11c0 8.5-6 15-14 18C12 34 6 27.5 6 19V8z"
        fill="#2b3ab0"
      />
      <path
        d="M13.6 19.5 15.6 14.6a1.6 1.6 0 0 1 1.5-1h5.8a1.6 1.6 0 0 1 1.5 1l2 4.9z"
        fill="#fff"
      />
      <path d="M16 18.6 17.3 15.4h5.4l1.3 3.2z" fill="#2b3ab0" />
      <rect x="10.5" y="19" width="19" height="6.5" rx="2" fill="#fff" />
      <circle
        cx="15"
        cy="25.8"
        r="2.3"
        fill="#f7b924"
        stroke="#2b3ab0"
        strokeWidth="1"
      />
      <circle
        cx="25"
        cy="25.8"
        r="2.3"
        fill="#f7b924"
        stroke="#2b3ab0"
        strokeWidth="1"
      />
      <circle
        cx="31"
        cy="31"
        r="6"
        fill="#36c98b"
        stroke="#fff"
        strokeWidth="2"
      />
      <path
        d="m28.3 31.1 1.8 1.8 3.4-3.6"
        fill="none"
        stroke="#fff"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function Logo({ className = "brand" }: { className?: string }) {
  return (
    <div className={className}>
      <LogoMark className="brand-mark" />
      <span className={`brand-name ${wordmark.className}`}>
        Cap<span className="brand-accent">stone</span>
      </span>
    </div>
  );
}
