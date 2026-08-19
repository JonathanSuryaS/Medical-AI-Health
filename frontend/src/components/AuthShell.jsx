// AuthShell.jsx — the two-column frame both login and signup share (the layout
// from your reference screenshot: form on the left, brand panel on the right).
// Putting it in one component means login and signup stay visually identical and
// you edit the layout in one place. This is component reuse -- the React habit.


export default function AuthShell({ title, subtitle, children}){
    return (
        <div className="auth-page">
            <div className="auth-left">
                <div className="auth-box">
                    <div className="brand">
                        <span className="pulse" aria-hidden="true" />
                        <span>Medical Ai health</span>
                    </div>
                    <h1>{title}</h1>
                    <p className="auth-sub">{subtitle}</p>
                    {children}
                </div>
            </div>
            <div className="auth-right" aria-hidden="true">
                <div className="auth-art">
                    <div className="cross" />
                    <p>Answers grounded in trusted medical sources.</p>
                </div>
            </div>
        </div>
    )
}