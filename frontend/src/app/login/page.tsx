import DevLogin from "./DevLogin";

export const dynamic = "force-dynamic";

const ERRORS: Record<string, string> = {
  idp_unavailable: "The identity provider is unavailable. Please try again.",
  idp_denied: "Sign-in was cancelled or denied by the identity provider.",
  state_mismatch: "The sign-in request expired or was tampered with. Please try again.",
  login_failed: "Sign-in could not be completed. Please try again.",
  oidc_disabled: "Single sign-on is not enabled on this deployment.",
};

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const { error } = await searchParams;
  const sso = (process.env.AUTH_MODE ?? "dev") === "oidc";
  return (
    <div className="login-wrap">
      <section className="login-side">
        <div className="brand" style={{ padding: 0 }}>
          <span className="brand-mark">V</span>Vehicle_Loan
        </div>
        <h1>Intelligent Vehicle Loan Advisor</h1>
        <p>
          Deterministic, policy-grounded eligibility with traceable citations,
          vehicle affordability, and AI explanations that can never override a
          decision.
        </p>
        <p className="small" style={{ opacity: 0.75 }}>
          Capstone demonstration. All lenders, policies, applicants and vehicles
          are synthetic. Results are indicative, not a binding loan sanction.
        </p>
      </section>
      <section className="login-main">
        <div style={{ width: "100%", maxWidth: 440 }}>
          {error && ERRORS[error] && (
            <div className="notice error" role="alert" style={{ marginBottom: 12 }}>
              {ERRORS[error]}
            </div>
          )}
          {sso ? (
            <>
              <h2 style={{ marginBottom: 6 }}>Sign in</h2>
              <p className="muted small" style={{ marginTop: 0 }}>
                You will be redirected to your organisation&apos;s identity
                provider (OIDC Authorization Code + PKCE). Tokens stay on the
                server; your browser only holds an HttpOnly session cookie.
              </p>
              <a className="btn primary" href="/api/auth/login">
                Sign in with single sign-on
              </a>
            </>
          ) : (
            <DevLogin />
          )}
        </div>
      </section>
    </div>
  );
}
