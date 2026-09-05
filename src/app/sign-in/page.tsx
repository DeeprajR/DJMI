type SignInPageProps = {
  searchParams: Promise<{
    error?: string;
    next?: string;
    retry_after?: string;
  }>;
};

function errorText(code?: string, retryAfter?: string): string | null {
  if (code === "rate_limited") {
    if (retryAfter) {
      return `Too many attempts. Try again in about ${retryAfter} seconds.`;
    }
    return "Too many attempts. Try again later.";
  }
  if (code === "invalid") {
    return "Invalid credentials.";
  }
  if (code === "invalid_origin") {
    return "This sign-in request could not be verified. Reload the page and try again.";
  }
  return null;
}

export default async function SignInPage({ searchParams }: SignInPageProps) {
  const params = await searchParams;
  const nextPath = params.next && params.next.startsWith("/") ? params.next : "/dashboard";
  const message = errorText(params.error, params.retry_after);

  return (
    <main id="main-content" tabIndex={-1} className="page auth-page">
      <section className="auth-intro" aria-labelledby="signin-heading">
        <span className="role-badge role-doctor w-fit">Doctor workspace</span>
        <h1 id="signin-heading">Welcome to your clinical workspace.</h1>
        <p>Prepare blood requests, review patient context, and keep track of associated samples.</p>
        <p className="text-sm">Use the account provided by your institution. Contact your administrator if you need access.</p>
      </section>
      <section className="panel auth-card" aria-labelledby="account-heading">
        <h2 id="account-heading">Sign in</h2>
        <p className="page-description">
          Enter your institution-provisioned account details.
        </p>

        {message ? (
          <div className="notice notice-error mt-5" role="alert">
            {message}
          </div>
        ) : null}

        <form method="post" action="/api/auth/sign-in" className="form-stack">
          <input type="hidden" name="next" value={nextPath} />
          <label className="field">
            Email
            <input
              name="email"
              type="email"
              required
              autoComplete="email"
              className="input"
            />
          </label>
          <label className="field">
            Password
            <input
              name="password"
              type="password"
              required
              autoComplete="current-password"
              className="input"
            />
          </label>
          <button
            type="submit"
            className="button button-primary w-full"
          >
            Sign in
          </button>
        </form>
        <p className="page-description mt-5">Registration is managed by your institution.</p>
      </section>
    </main>
  );
}
